"""Offline UI integration of dictation versus automatic conversation turns."""

from io import BytesIO
import unittest
from unittest.mock import patch

from zentromart.config import PROJECT_ROOT
from zentromart.voice import VoiceError, VoiceSession, wav_from_pcm
from test_demo_voice import recording
from test_dialogue import result

try:
    from streamlit.testing.v1 import AppTest
except ImportError:
    AppTest = None


@unittest.skipIf(AppTest is None, "Install requirements-voice.txt")
class VoiceModeUITests(unittest.TestCase):
    def app(self):
        app = AppTest.from_file(str(PROJECT_ROOT / "streamlit_app.py"), default_timeout=15)
        app.secrets["llm"] = {"provider": "gemini", "model": "gemini-test", "api_key": "test-key"}
        app.run()
        app.checkbox(key="voice_enabled").check().run()
        return app

    def start(self):
        app = self.app()
        app.checkbox(key="cloud").check().run()
        app.button(key="voice_start").click().run()
        self.assertTrue(app.session_state.voice_conversation.active)
        self.assertTrue(app.chat_input[0].disabled)
        return app

    def turn(self, app, transcript="hello", tts_error=None):
        # AppTest cannot capture a real microphone. Supply exactly one completed
        # recorder event, then return None after the app creates its next widget.
        clips = iter([BytesIO(recording()), None])
        def microphone(*args, **kwargs):
            return next(clips, None) if kwargs["key"].startswith("conversation_recording_") else None
        with patch("streamlit.audio_input", side_effect=microphone), patch.object(
                VoiceSession, "run", side_effect=[transcript, tts_error or wav_from_pcm(bytes(100))]) as speech, patch(
                "zentromart.web_session.GeminiModel") as model:
            model.return_value.plan.return_value = result(action="respond", topic="general", reply="Hello! Tell me what's on your mind.")
            app.run()
            self.assertFalse(app.exception)
            return speech, model

    def test_start_requires_consent_and_makes_no_provider_call(self):
        app = self.app()
        self.assertTrue(app.button(key="voice_start").disabled)
        with patch.object(VoiceSession, "run", side_effect=AssertionError("No voice request")):
            app.checkbox(key="cloud").check().run()
            app.button(key="voice_start").click().run()
        self.assertTrue(app.session_state.voice_conversation.active)
        self.assertFalse(app.exception)

    def test_completed_recording_automatically_runs_stt_model_tts_and_autoplay_once(self):
        app = self.start()
        speech, model = self.turn(app)
        self.assertEqual(speech.call_count, 2)
        self.assertEqual(speech.call_args_list[1].args, ("synthesize", "Hello! Tell me what's on your mind.", "en"))
        model.return_value.plan.assert_called_once()
        self.assertEqual(len(app.session_state.support.messages), 2)
        self.assertEqual(app.session_state.support.messages[-1]["path"], "dialogue")
        self.assertTrue(app.get("audio")[0].proto.autoplay)
        with patch.object(VoiceSession, "run", side_effect=AssertionError("No duplicate requests")):
            app.run()
        self.assertFalse(app.get("audio")[0].proto.autoplay)
        self.assertEqual(len(app.session_state.support.messages), 2)

    def test_end_removes_audio_and_restores_typing_without_resetting_budgets(self):
        app = self.start()
        self.turn(app)
        app.session_state.voice_session.attempts = 4
        calls = app.session_state.support.model.calls
        app.button(key="voice_end").click().run()
        self.assertFalse(app.session_state.voice_conversation.active)
        self.assertFalse(app.get("audio"))
        self.assertFalse(app.chat_input[0].disabled)
        self.assertEqual(app.session_state.voice_session.attempts, 4)
        self.assertEqual(app.session_state.support.model.calls, calls)

    def test_tts_failure_keeps_model_reply_and_pauses_without_automatic_retry(self):
        app = self.start()
        speech, _ = self.turn(app, tts_error=VoiceError("timeout"))
        self.assertEqual(speech.call_count, 2)
        self.assertFalse(app.session_state.voice_conversation.active)
        self.assertEqual(app.session_state.support.messages[-1]["text"], "Hello! Tell me what's on your mind.")
        self.assertFalse(app.get("audio"))
        self.assertIn("Speech playback generation failed", app.warning[0].value)
        with patch.object(VoiceSession, "run", side_effect=AssertionError("No retry")):
            app.run()
        self.assertEqual(len(app.session_state.support.messages), 2)

    def test_spoken_order_pauses_for_masked_verification_before_tts(self):
        app = self.start()
        speech, model = self.turn(app, transcript="Order 89782837")
        self.assertEqual(speech.call_count, 1)
        model.assert_not_called()
        self.assertEqual(app.session_state.support.agent.state.phase, "proof")
        self.assertFalse(app.session_state.voice_conversation.active)
        self.assertEqual(app.text_input(key="verification").proto.type, 1)
        self.assertTrue(app.button(key="voice_start").disabled)
        self.assertFalse(app.get("audio"))

    def test_settings_changes_end_voice_mode_and_discard_pending_audio(self):
        for setting in ("cloud", "voice_enabled", "demo", "clear", "language"):
            with self.subTest(setting=setting):
                app = self.start()
                app.session_state.voice_audio = wav_from_pcm(bytes(100))
                if setting == "language":
                    app.segmented_control(key="language").set_value("hi").run()
                elif setting == "clear":
                    app.button(key="clear").click().run()
                elif setting == "demo":
                    app.checkbox(key="demo").check().run()
                else:
                    app.checkbox(key=setting).uncheck().run()
                self.assertFalse(app.exception)
                self.assertFalse(app.session_state.voice_conversation.active)
                self.assertIsNone(app.session_state.voice_audio)

    def test_dictation_transcribes_but_does_not_submit_or_speak_automatically(self):
        app = self.app()
        with patch("streamlit.file_uploader", return_value=BytesIO(recording())):
            app.run()
            with patch.object(VoiceSession, "run", return_value="hello") as speech:
                app.button(key="transcribe").click().run()
        self.assertEqual(speech.call_count, 1)
        self.assertEqual(speech.call_args.args[0], "transcribe")
        self.assertEqual(app.text_area(key="voice_draft").value, "hello")
        self.assertEqual(app.session_state.support.messages, [])
        self.assertFalse(app.get("audio"))
        with patch.object(VoiceSession, "run", side_effect=AssertionError("No automatic TTS")):
            app.button(key="send_voice").click().run()
        self.assertEqual(len(app.session_state.support.messages), 2)
        self.assertFalse(app.exception)
