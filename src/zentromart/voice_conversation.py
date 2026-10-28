"""Session-local, turn-based STT -> assistant -> TTS orchestration.

No microphone capture, transcript persistence, provider credentials or retries
live here. The Streamlit recorder supplies one explicitly completed turn.
"""

from collections import deque

from .localization import DIGITS
from .voice import VoiceError, pcm_from_wav
from .web_session import PublicAccessError
from .workflows import submitted_proof


class VoiceTurnError(RuntimeError):
    """Reviewed stage/code only; never include transcript/provider details."""

    def __init__(self, stage, code):
        self.stage, self.code = stage, code
        super().__init__(code)


class VoiceConversation:
    def __init__(self):
        self.active = False
        self.phase = "idle"
        self._processed = deque(maxlen=40)

    def start(self):
        self.active, self.phase = True, "ready"

    def stop(self):
        self.active, self.phase = False, "idle"

    def run(self, turn_id, audio, support, speech, language, on_stage=None):
        """Consume an event at most once, even if its pipeline fails midway."""
        if not isinstance(turn_id, str) or not 1 <= len(turn_id) <= 100:
            raise VoiceTurnError("transcribe", "invalid_audio")
        if turn_id in self._processed:
            return None
        stage = "transcribe"

        def progress(value):
            nonlocal stage
            stage = self.phase = value
            if on_stage:
                on_stage(value)

        def check_consent():
            if self.active is not True or speech.enabled is not True:
                raise VoiceTurnError(stage, "consent_required")
            if support.dialogue_enabled is not True or support.model.enabled is not True:
                raise VoiceTurnError("assistant", "cloud_disabled")

        try:
            check_consent()
            if support.agent.state.phase in {"proof", "locked"}:
                raise VoiceTurnError("verification", "proof_required")
            if speech.blocked or speech.limit - speech.attempts < 2:
                raise VoiceTurnError(stage, "paused")
            if support.model.blocked or support.model.limit - support.model.calls < 2:
                raise VoiceTurnError("assistant", "cloud_paused")
            pcm_from_wav(audio)  # Reject malformed/oversized clips before any service call.
            self._processed.append(turn_id)
            progress("transcribe")
            transcript = speech.run("transcribe", audio, language)
            check_consent()
            if not isinstance(transcript, str) or not 1 <= len(transcript.strip()) <= 4000:
                raise VoiceTurnError(stage, "invalid_audio")
            # A spoken proof must never become a chat submission or verification.
            # This is best effort after STT; never speak real personal data.
            if submitted_proof(transcript.translate(DIGITS)):
                raise VoiceTurnError("verification", "proof_required")
            progress("assistant")
            support.submit(transcript)
            if support.agent.state.phase in {"proof", "locked"}:
                self.active, self.phase = False, "verification"
                return None  # Typed proof only; do not synthesize a proof exchange.
            latest = support.messages[-1] if support.messages else None
            if not latest or latest.get("role") != "assistant":
                raise VoiceTurnError(stage, "error")
            reply = latest.get("text")
            if not isinstance(reply, str) or not 1 <= len(reply.strip()) <= 800:
                raise VoiceTurnError("synthesize", "invalid_text")
            progress("synthesize")
            check_consent()
            output = speech.run("synthesize", reply, latest.get("language", language))
            if not isinstance(output, bytes) or not output.startswith(b"RIFF"):
                raise VoiceTurnError(stage, "error")
            self.phase = "ready"
            return output
        except VoiceTurnError:
            self.active, self.phase = False, "paused"
            raise
        except PublicAccessError as error:
            self.active, self.phase = False, "paused"
            code = str(error)
            raise VoiceTurnError("assistant", code if code in {"cloud_disabled", "cloud_failed", "cloud_paused"} else "error") from None
        except VoiceError as error:
            self.active, self.phase = False, "paused"
            code = str(error)
            allowed = {"timeout", "authentication", "quota", "not_configured", "invalid_audio", "invalid_text", "paused", "consent_required"}
            raise VoiceTurnError(stage, code if code in allowed else "error") from None
        except ImportError:
            self.active, self.phase = False, "paused"
            raise VoiceTurnError(stage, "dependency") from None
        except Exception:
            self.active, self.phase = False, "paused"
            raise VoiceTurnError(stage, "error") from None
