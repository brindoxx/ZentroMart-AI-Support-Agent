"""Public tutorial fixtures and mocked speech services: no credits consumed."""

import asyncio
import base64
from io import BytesIO
import json
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
import wave

from zentromart.config import PROJECT_ROOT, FROZEN_REFERENCE_DATE
from zentromart.calculations import BusinessCalendar
from zentromart.contracts import AgentRequest
from zentromart.demo import DemoGateway, SCENARIOS
from zentromart.retrieval import BM25Index, load_search_documents
from zentromart.voice import GnaniSpeech, VoiceError, VoiceSession, pcm_from_wav, wav_from_pcm
from zentromart.workflows import SupportAgent


def recording(frames=160, rate=16000):
    output = BytesIO()
    with wave.open(output, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(bytes(frames * 2))
    return output.getvalue()


class DemoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.index = BM25Index(load_search_documents(PROJECT_ROOT / "dataset"))
        cls.calendar = BusinessCalendar.load(PROJECT_ROOT / "dataset")

    def agent(self):
        model = MagicMock()
        model.generate.side_effect = AssertionError("No model needed for demo order workflows")
        gateway = DemoGateway(MagicMock())
        return SupportAgent(self.index, model, FROZEN_REFERENCE_DATE, calendar=self.calendar, gateway=gateway)

    def turn(self, agent, text):
        return agent.respond(AgentRequest("demo", text))

    def test_greetings_do_not_search_or_consume_verification_attempts(self):
        agent = self.agent()
        self.assertIn("AI support", self.turn(agent, "hello").reply)
        self.turn(agent, "Order 81000001")
        self.turn(agent, "hello")
        self.turn(agent, "thanks")
        self.assertEqual(agent.state.phase, "proof")
        self.assertEqual(agent.state.failures["81000001"], 0)
        self.assertEqual(self.turn(agent, "4242").decision, "answer")

    def test_greetings_are_localized_and_do_not_hide_real_issues(self):
        for language in ("hi", "hi-en"):
            agent = self.agent()
            agent.set_language(language)
            self.assertEqual(self.turn(agent, "hello").language, language)
            self.assertEqual(agent.last_trace.reason, "greeting")
            self.assertEqual(self.turn(agent, "hello my battery is swelling").decision, "escalate")

    def test_each_demo_exercises_real_verification_and_policy_logic(self):
        for case in SCENARIOS:
            agent = self.agent()
            self.assertEqual(self.turn(agent, case["question"] + " Order " + case["id"]).decision, "clarify")
            self.assertFalse(agent.state.verified)
            reply = self.turn(agent, case["proof"])
            self.assertTrue(agent.state.verified)
            self.assertNotEqual(agent.last_trace.reason, "translation_unavailable")
            if case["id"] == "81000002":
                self.assertIn("INR 351", reply.reply)
            elif case["id"] == "81000003":
                self.assertIn("DEMOREF0003", reply.reply)
            elif case["id"] == "81000004":
                self.assertEqual(reply.decision, "escalate")
                self.assertIn("disabled", reply.reply)

    def test_demo_does_not_look_up_supplied_orders_or_skip_proof(self):
        backend = MagicMock()
        gateway = DemoGateway(backend)
        self.assertEqual(gateway.lookup_order("81000001"), {"verification_required": True})
        self.assertFalse(gateway.lookup_order("89782837", "4242")["verified"])
        self.assertFalse(gateway.lookup_order("81000001", "9999")["verified"])
        with self.assertRaises(ValueError):
            gateway.lookup_order("81000001", "+91 4242")
        backend.lookup_order.assert_not_called()
        result = gateway.lookup_order("81000001", "4242")
        result["items"].clear()
        self.assertTrue(gateway.lookup_order("81000001", "4242")["items"])


class VoiceTests(unittest.TestCase):
    def test_audio_validation_before_spending_credits(self):
        self.assertEqual(len(pcm_from_wav(recording())), 320)
        for audio in (b"not a wav", recording(rate=8000), recording(frames=16 * 16000)):
            with self.assertRaises(VoiceError):
                pcm_from_wav(audio)
        with wave.open(BytesIO(wav_from_pcm(bytes(100))), "rb") as wav:
            self.assertEqual(wav.getframerate(), 24000)

    def test_consent_key_privacy_and_pause_after_error(self):
        session = VoiceSession()
        with patch("zentromart.voice.load_voice_key", side_effect=AssertionError("No key read")):
            with self.assertRaisesRegex(VoiceError, "consent_required"):
                session.run("transcribe", recording(), "en")
        session.enabled = True
        with patch("zentromart.voice.load_voice_key", side_effect=VoiceError("not_configured")):
            with self.assertRaises(VoiceError):
                session.run("transcribe", recording(), "en")
        self.assertFalse(session.blocked)
        self.assertEqual(session.attempts, 0)
        self.assertNotIn("SECRET", repr(GnaniSpeech("SECRET")))

    def test_budget_no_automatic_retry_and_invalid_text(self):
        session = VoiceSession()
        session.enabled = True
        with self.assertRaisesRegex(VoiceError, "invalid_text"):
            session.run("synthesize", "x" * 801, "en")
        with patch("zentromart.voice.load_voice_key", return_value="test-key"), patch.object(
                GnaniSpeech, "synthesize", new=AsyncMock(return_value=b"wav")) as call:
            for _ in range(20):
                self.assertEqual(session.run("synthesize", "Hello", "en"), b"wav")
            with self.assertRaisesRegex(VoiceError, "paused"):
                session.run("synthesize", "Hello", "en")
        self.assertEqual(call.call_count, 20)

    def test_tts_protocol_and_chunk_validation_without_a_real_service(self):
        socket = MagicMock()
        socket.send = AsyncMock()
        socket.recv = AsyncMock(side_effect=[json.dumps({"type": "start"}), json.dumps({"type": "audio", "data": {
            "chunk_index": 1, "audio": base64.b64encode(bytes(100)).decode(), "is_final": False}}),
            json.dumps({"type": "complete", "data": {"chunk_index": 2, "audio": "", "is_final": True}})])
        context = MagicMock()
        context.__aenter__ = AsyncMock(return_value=socket)
        context.__aexit__ = AsyncMock(return_value=False)
        with patch("websockets.asyncio.client.connect", return_value=context) as connect:
            audio = asyncio.run(GnaniSpeech("test-key").synthesize("Hello", "en"))
        self.assertTrue(audio.startswith(b"RIFF"))
        self.assertEqual(connect.call_args.args[0], "wss://api.vachana.ai/api/v1/tts")
        self.assertEqual(json.loads(socket.send.call_args.args[0])["voice"], "Pranav")

    def test_tts_provider_error_does_not_expose_payload_or_key(self):
        context = MagicMock()
        context.__aenter__ = AsyncMock(side_effect=RuntimeError("SECRET"))
        with patch("websockets.asyncio.client.connect", return_value=context):
            with self.assertRaisesRegex(VoiceError, "service_failed") as raised:
                asyncio.run(GnaniSpeech("SECRET").synthesize("Hello", "en"))
        self.assertNotIn("SECRET", str(raised.exception))

    def test_stt_streams_pcm_and_collects_deduplicated_segments(self):
        class Socket:
            def __init__(self):
                self.messages = [json.dumps({"type": "connected"}), json.dumps({"type": "transcript", "text": "Hello", "segment_id": "one"}),
                                 json.dumps({"type": "transcript", "text": "Hello", "segment_id": "one"})]
                self.frames = []
            async def recv(self):
                if self.messages:
                    await asyncio.sleep(0)
                    return self.messages.pop(0)
                await asyncio.sleep(1.2)
                raise TimeoutError
            async def send(self, frame):
                self.frames.append(frame)
        socket = Socket()
        context = MagicMock()
        context.__aenter__ = AsyncMock(return_value=socket)
        context.__aexit__ = AsyncMock(return_value=False)
        with patch("websockets.asyncio.client.connect", return_value=context) as connect:
            self.assertEqual(asyncio.run(GnaniSpeech("test-key").transcribe(recording(), "hi-en")), "Hello")
        self.assertTrue(socket.frames)
        self.assertTrue(all(len(frame) == 1024 for frame in socket.frames))
        self.assertEqual(connect.call_args.kwargs["additional_headers"]["lang_code"], "hi-IN")


try:
    from streamlit.testing.v1 import AppTest
except ImportError:
    AppTest = None


@unittest.skipIf(AppTest is None, "Install requirements-voice.txt")
class TutorialUITests(unittest.TestCase):
    def app(self):
        return AppTest.from_file(str(PROJECT_ROOT / "streamlit_app.py"), default_timeout=15).run()

    def test_demo_selector_and_verification_are_usable_without_keys(self):
        app = self.app()
        app.checkbox(key="demo").check().run()
        app.button(key="demo_start").click().run()
        self.assertFalse(app.exception)
        app.text_input(key="verification").set_value("4242")
        app.button(key="verify_submit").click().run()
        self.assertTrue(app.session_state.support.agent.state.verified)
        self.assertNotIn("4242", json.dumps(app.session_state.support.messages))
        app.checkbox(key="demo").uncheck().run()
        self.assertFalse(app.session_state.support.agent.state.verified)
        app.checkbox(key="demo").check().run()
        self.assertFalse(app.session_state.support.agent.state.verified)
        self.assertFalse(app.exception)

    def test_greeting_shows_local_path_and_voice_synthesis_is_explicit(self):
        app = self.app()
        with patch("zentromart.voice.load_voice_key", side_effect=AssertionError("No key read")):
            app.chat_input[0].set_value("hello").run()
            app.checkbox(key="voice_enabled").check().run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state.support.messages[-1]["path"], "local")
        with patch.object(VoiceSession, "run", return_value=wav_from_pcm(bytes(100))) as call:
            app.button(key="speak").click().run()
            call.assert_called_once()
        self.assertTrue(app.get("audio"))
        app.button(key="clear").click().run()
        self.assertFalse(app.get("audio"))
        self.assertFalse(app.exception)

    def test_voice_is_disabled_during_verification_and_demo_switch_keeps_lockout(self):
        app = self.app()
        app.checkbox(key="demo").check().run()
        app.checkbox(key="voice_enabled").check().run()
        app.button(key="demo_start").click().run()
        self.assertTrue(app.button(key="transcribe").disabled)
        self.assertTrue(app.button(key="send_voice").disabled)
        self.assertTrue(app.button(key="speak").disabled)
        for value in ("9999", "8888"):
            app.text_input(key="verification").set_value(value)
            app.button(key="verify_submit").click().run()
        shared_model = app.session_state.support.model
        app.checkbox(key="demo").uncheck().run()
        self.assertIs(app.session_state.support.model, shared_model)
        app.checkbox(key="demo").check().run()
        app.button(key="demo_start").click().run()
        self.assertEqual(app.session_state.support.agent.state.phase, "locked")
        self.assertFalse(app.exception)


if __name__ == "__main__":
    unittest.main()
