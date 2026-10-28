"""Same-origin live PCM relay. The Gnani key never crosses into the browser.

The bounded routing registry holds speech-session leases, not order records,
audio or transcripts. Private support state remains in Streamlit session state.
"""

import asyncio
from contextlib import suppress
from dataclasses import dataclass, field
import json
import secrets
from threading import Lock
from time import monotonic
from urllib.parse import urlsplit

from .voice import VoiceError, service_error_code


@dataclass
class Lease:
    speech: object = field(repr=False)
    language: str
    mode: str
    event_id: str
    expires: float
    busy: bool = False
    revoked: bool = False


class LeaseRegistry:
    def __init__(self):
        self._leases = {}
        self._lock = Lock()

    def issue(self, speech, language, mode, event_id):
        if language not in {"en", "hi", "hi-en"} or mode not in {"dictate", "voice"}:
            raise VoiceError("invalid_language")
        if not isinstance(event_id, str) or not 1 <= len(event_id) <= 80:
            raise VoiceError("invalid_audio")
        with self._lock:
            self._leases = {token: lease for token, lease in self._leases.items()
                            if lease.expires > monotonic() and not lease.revoked}
            if len(self._leases) >= 64:
                raise VoiceError("paused")
            token = secrets.token_urlsafe(32)
            self._leases[token] = Lease(speech, language, mode, event_id, monotonic() + 120)
            return token

    def claim(self, token):
        if not isinstance(token, str) or len(token) > 100:
            raise VoiceError("consent_required")
        with self._lock:
            lease = self._leases.get(token)
            if not lease or lease.expires <= monotonic() or lease.revoked or lease.busy:
                raise VoiceError("consent_required")
            lease.busy = True
            return lease

    def revoke(self, token):
        if not isinstance(token, str):
            return
        with self._lock:
            lease = self._leases.pop(token, None)
            if lease:
                lease.revoked = True


REGISTRY = LeaseRegistry()


def same_local_origin(origin, host):
    """Local capstone only. No wildcard origins or cross-site WebSocket access."""
    try:
        parsed = urlsplit(origin)
        expected = urlsplit("http://" + host)
        return (parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1"}
                and parsed.hostname == expected.hostname and parsed.port == expected.port
                and not parsed.username and parsed.path in {"", "/"})
    except (ValueError, TypeError):
        return False


async def relay_turn(browser, lease):
    """Forward 1024-byte frames as recorded, return Gnani's completed phrases."""
    from websockets.asyncio.client import connect
    if lease.revoked or lease.expires <= monotonic():
        raise VoiceError("consent_required")
    key = lease.speech.reserve()
    headers = {"x-api-key-id": key, "lang_code": "hi-IN" if lease.language == "hi" else "en-IN",
               "x-sample-rate": "16000", "x-format": "transcribe", "itn_native_numerals": "false",
               "x-min-silence-ms": "700"}
    stopped = asyncio.Event()
    texts, seen = [], set()
    try:
        async with asyncio.timeout(40):
            async with connect("wss://api.vachana.ai/stt/v3/stream", additional_headers=headers,
                               open_timeout=12, close_timeout=2, max_size=65536) as provider:
                ready = json.loads(await asyncio.wait_for(provider.recv(), 5))
                if ready.get("type") != "connected":
                    raise VoiceError("service_failed")
                await browser.send_json({"type": "ready"})

                async def send():
                    frames = 0
                    while True:
                        if lease.revoked or not lease.speech.enabled:
                            raise VoiceError("consent_required")
                        event = await asyncio.wait_for(browser.receive(), 20)
                        if event["type"] == "websocket.disconnect":
                            raise VoiceError("consent_required")
                        pcm = event.get("bytes")
                        if pcm is not None:
                            frames += 1
                            if len(pcm) != 1024 or frames > 469:
                                raise VoiceError("invalid_audio")
                            await provider.send(pcm)
                        elif event.get("text") == '{"type":"stop"}':
                            for _ in range(32):
                                await provider.send(bytes(1024))
                                await asyncio.sleep(0.032)
                            stopped.set()
                            return
                        else:
                            raise VoiceError("invalid_audio")

                async def receive():
                    for _ in range(200):
                        if lease.revoked or not lease.speech.enabled:
                            raise VoiceError("consent_required")
                        try:
                            event = json.loads(await asyncio.wait_for(provider.recv(), 3))
                        except TimeoutError:
                            if stopped.is_set():
                                if texts:
                                    return
                                raise VoiceError("no_speech") from None
                            continue
                        if event.get("type") == "error":
                            raise VoiceError("service_failed")
                        if event.get("type") == "processing":
                            await browser.send_json({"type": "processing"})
                        if event.get("type") != "transcript":
                            continue
                        text, identity = event.get("text"), event.get("segment_id")
                        if not isinstance(text, str) or not text.strip() or len(text) > 4000:
                            raise VoiceError("no_speech")
                        if isinstance(identity, str) and identity in seen:
                            continue
                        if isinstance(identity, str):
                            seen.add(identity)
                        texts.append(text.strip())
                        if len(" ".join(texts)) > 4000:
                            raise VoiceError("invalid_audio")
                        await browser.send_json({"type": "transcript", "text": " ".join(texts)})
                        if lease.mode == "voice":
                            return  # End-of-speech finalization is Gnani VAD, not fake partial text.
                    raise VoiceError("service_failed")

                sender, receiver = asyncio.create_task(send()), asyncio.create_task(receive())
                try:
                    done, _ = await asyncio.wait((sender, receiver), return_when=asyncio.FIRST_COMPLETED)
                    for task in done:
                        task.result()
                    if receiver not in done:
                        await receiver
                    await browser.send_json({"type": "complete", "text": " ".join(texts), "id": lease.event_id})
                finally:
                    for task in (sender, receiver):
                        task.cancel()
                    for task in (sender, receiver):
                        with suppress(asyncio.CancelledError, Exception):
                            await task
    except VoiceError:
        raise
    except Exception as error:
        raise VoiceError(service_error_code(error)) from None


async def voice_socket(websocket):
    """Origin + expiring one-use capability are checked before provider access."""
    if not same_local_origin(websocket.headers.get("origin", ""), websocket.headers.get("host", "")):
        await websocket.close(code=1008)
        return
    await websocket.accept()
    token = None
    lease = None
    try:
        message = await asyncio.wait_for(websocket.receive_text(), 5)
        if len(message) > 256:
            raise VoiceError("consent_required")
        hello = json.loads(message)
        if not isinstance(hello, dict) or set(hello) != {"token"}:
            raise VoiceError("consent_required")
        token = hello["token"]
        lease = REGISTRY.claim(token)
        await relay_turn(websocket, lease)
    except Exception as error:
        code = str(error) if isinstance(error, VoiceError) else "service_failed"
        allowed = {"timeout", "authentication", "quota", "not_configured", "invalid_audio", "paused", "consent_required", "no_speech"}
        if lease and code in {"timeout", "authentication", "quota", "service_failed"}:
            lease.speech.blocked = True
        with suppress(Exception):
            await websocket.send_json({"type": "error", "code": code if code in allowed else "service_failed"})
    finally:
        if token:
            REGISTRY.revoke(token)  # A used capability can never start a second provider call.
        with suppress(Exception):
            await websocket.close()
