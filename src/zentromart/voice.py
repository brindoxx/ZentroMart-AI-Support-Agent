"""Bounded Gnani WebSocket adapter; audio stays in memory, no automatic retries.

Record-and-send UX, not a continuously listening or full-duplex browser call.
Protocol: https://docs.gnani.ai/api/STT/stt-websocket and /api/TTS/tts-websocket
"""

import asyncio
import base64
from contextlib import suppress
from dataclasses import dataclass, field
from io import BytesIO
import json
import os
import re
import wave

from dotenv import dotenv_values
from .config import PROJECT_ROOT


class VoiceError(RuntimeError):
    """Safe static error code only. Never wrap raw network/provider errors."""


def pcm_from_wav(audio):
    if not isinstance(audio, bytes) or not 44 <= len(audio) <= 500000:
        raise VoiceError("invalid_audio")
    try:
        with wave.open(BytesIO(audio), "rb") as wav:
            if (wav.getnchannels(), wav.getsampwidth(), wav.getframerate(), wav.getcomptype()) != (1, 2, 16000, "NONE"):
                raise ValueError
            frames = wav.getnframes()
            if not 1 <= frames <= 15 * 16000:
                raise ValueError
            pcm = wav.readframes(frames)
            if len(pcm) != frames * 2:
                raise ValueError
            return pcm
    except (wave.Error, EOFError, ValueError):
        raise VoiceError("invalid_audio") from None


def wav_from_pcm(pcm):
    if not pcm or len(pcm) % 2 or len(pcm) > 5_000_000:
        raise VoiceError("invalid_response")
    result = BytesIO()
    with wave.open(result, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(24000)
        wav.writeframes(pcm)
    return result.getvalue()


def load_voice_key():
    values = {**dotenv_values(PROJECT_ROOT / ".env"), **os.environ}
    key = values.get("GNANI_API_KEY")
    if not isinstance(key, str) or not key or any(char.isspace() for char in key) or key.lower().startswith(("your", "paste", "replace")):
        raise VoiceError("not_configured")
    return key


@dataclass
class GnaniSpeech:
    api_key: str = field(repr=False)

    async def transcribe(self, audio, language):
        pcm = pcm_from_wav(audio)
        if language not in {"en", "hi", "hi-en"}:
            raise VoiceError("invalid_language")
        # STT lists en-IN/hi-IN, not a distinct Hinglish language code.
        headers = {"x-api-key-id": self.api_key, "lang_code": "en-IN" if language == "en" else "hi-IN",
                   "x-sample-rate": "16000", "x-format": "transcribe", "itn_native_numerals": "false"}
        from websockets.asyncio.client import connect
        try:
            async with asyncio.timeout(35):
                async with connect("wss://api.vachana.ai/stt/v3/stream", additional_headers=headers,
                                   open_timeout=8, close_timeout=2, max_size=65536) as socket:
                    ready = json.loads(await asyncio.wait_for(socket.recv(), 5))
                    if ready.get("type") != "connected":
                        raise ValueError
                    async def send():
                        # Pad the tail and include silence so VAD can close the last segment.
                        stream = pcm + bytes(32000)
                        for start in range(0, len(stream), 1024):
                            await socket.send(stream[start:start + 1024].ljust(1024, b"\0"))
                            await asyncio.sleep(0.032)
                    sender = asyncio.create_task(send())
                    segments, seen = [], set()
                    try:
                        for _ in range(200):
                            try:
                                event = json.loads(await asyncio.wait_for(socket.recv(), 5))
                            except TimeoutError:
                                if not sender.done():
                                    continue  # A long uninterrupted utterance need not emit a segment yet.
                                if not sender.cancelled() and sender.exception() is None and segments:
                                    break
                                raise
                            if event.get("type") == "error":
                                raise ValueError
                            if event.get("type") == "transcript":
                                text, identity = event.get("text"), event.get("segment_id")
                                if not isinstance(text, str) or not text.strip() or len(text) > 4000:
                                    raise ValueError
                                if not isinstance(identity, str) or identity not in seen:
                                    segments.append(text.strip())
                                    if isinstance(identity, str):
                                        seen.add(identity)
                        else:
                            raise ValueError
                        await sender
                        transcript = " ".join(segments)
                        if not transcript or len(transcript) > 4000:
                            raise ValueError
                        return transcript
                    finally:
                        sender.cancel()
                        with suppress(asyncio.CancelledError):
                            await sender
        except Exception:
            raise VoiceError("service_failed") from None

    async def synthesize(self, text, language):
        if not isinstance(text, str) or not text.strip() or len(text) > 800 or language not in {"en", "hi", "hi-en"}:
            raise VoiceError("invalid_text")
        from websockets.asyncio.client import connect
        payload = {"text": re.sub(r"\[[^\]\n]+\]", "", text), "model": "timbre-v2.5",
                   "voice": {"en": "Pranav", "hi": "Nalini", "hi-en": "Poorvi"}[language],
                   "language": {"en": "en-IN", "hi": "hi-IN", "hi-en": "hi-en"}[language],
                   "audio_config": {"sample_rate": 24000, "num_channels": 1, "sample_width": 2,
                                    "encoding": "linear_pcm", "container": "raw"}}
        try:
            async with asyncio.timeout(30):
                async with connect("wss://api.vachana.ai/api/v1/tts", additional_headers={"X-API-Key-ID": self.api_key},
                                   open_timeout=8, close_timeout=2, max_size=1_000_000) as socket:
                    await socket.send(json.dumps(payload, ensure_ascii=False))
                    output, previous_index = bytearray(), -1
                    for _ in range(500):
                        event = json.loads(await socket.recv())
                        if event.get("type") == "error":
                            raise ValueError
                        if event.get("type") not in {"audio", "complete"}:
                            continue
                        data = event["data"]
                        index = data["chunk_index"]
                        if type(index) is not int or index <= previous_index:
                            raise ValueError
                        previous_index = index
                        output.extend(base64.b64decode(data.get("audio", ""), validate=True))
                        if len(output) > 5_000_000:
                            raise ValueError
                        if data.get("is_final") is True:
                            return wav_from_pcm(bytes(output))
                    raise ValueError
        except Exception:
            raise VoiceError("service_failed") from None


class VoiceSession:
    def __init__(self):
        self.enabled = False
        self.attempts = 0
        self.limit = 20
        self.blocked = False

    def resume(self):
        """Explicit user retry after fixing access; never renew the budget."""
        self.blocked = False

    def run(self, action, value, language):
        if self.enabled is not True:
            raise VoiceError("consent_required")
        if self.blocked or self.attempts >= self.limit:
            raise VoiceError("paused")
        if action not in {"transcribe", "synthesize"}:
            raise VoiceError("invalid_action")
        if language not in {"en", "hi", "hi-en"}:
            raise VoiceError("invalid_language")
        # Validate locally before loading a key or spending any credits.
        if action == "transcribe":
            pcm_from_wav(value)
        elif not isinstance(value, str) or not 1 <= len(value) <= 800:
            raise VoiceError("invalid_text")
        key = load_voice_key()  # A corrected local key can be retried without reloading.
        self.attempts += 1
        try:
            client = GnaniSpeech(key)
            return asyncio.run(getattr(client, action)(value, language))
        except VoiceError as error:
            self.blocked = str(error) == "service_failed"
            raise
