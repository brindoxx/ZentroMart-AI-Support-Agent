"""Primary UI tests; legacy record/review tests target legacy_streamlit_app.py."""
from collections import deque
from types import SimpleNamespace
import unittest
from unittest.mock import patch, MagicMock

from zentromart.config import PROJECT_ROOT
from zentromart.voice import VoiceSession, wav_from_pcm, VoiceError
from zentromart.live_voice import REGISTRY
from test_dialogue import result

try:
    from streamlit.testing.v1 import AppTest
except ImportError:
    AppTest = None


@unittest.skipIf(AppTest is None, "Install requirements-voice.txt")
class ComposerUITests(unittest.TestCase):
    def setUp(self):
        # Test wiring without loading/downloading the actual encoder.
        from zentromart.retrieval import BM25Index, load_search_documents
        index = BM25Index(load_search_documents(PROJECT_ROOT / 'dataset'))
        self.index_patch = patch('zentromart.runtime.build_public_index', return_value=index)
        self.index_patch.start()
        self.addCleanup(self.index_patch.stop)
        self.events = deque()
        self.mounts = []
        def render(**kwargs):
            self.mounts.append(kwargs)
            return SimpleNamespace(**(self.events.popleft() if self.events else {}))
        self.mock = patch("zentromart.composer.composer", side_effect=render)
        self.mock.start()
        self.addCleanup(self.mock.stop)
        self.app = AppTest.from_file(str(PROJECT_ROOT / "chat_app.py"), default_timeout=15).run()
        self.assertFalse(self.app.exception)
        self.addCleanup(lambda: REGISTRY.revoke(self.app.session_state.live_token))

    def allow(self):
        self.app.button(key="cloud_consent").click().run()
        model = self.app.session_state.support.model
        model._client = MagicMock()
        model._client.plan.return_value = result(action="respond", topic="general", reply="Hello! What can I help with?")
        return model

    def event(self, name, payload):
        self.events.append({name: payload})
        self.app.run()
        self.assertFalse(self.app.exception)

    def test_offline_start_has_no_provider_switches_and_waits_for_explicit_consent(self):
        self.assertFalse(self.app.get("segmented_control"))
        self.assertEqual({c.key for c in self.app.checkbox}, {"demo", "tickets"})
        self.assertTrue(self.mounts[-1]["disabled"])
        self.assertFalse(self.app.session_state.support.model.enabled)
        self.event("submitted", {"id": "no-consent", "text": "hi", "source": "typed"})
        self.assertEqual(self.app.session_state.support.model.calls, 0)
        self.assertFalse(self.app.session_state.speech.enabled)

    def test_voice_reply_language_switches_without_ending_conversation(self):
        model = self.allow()
        model._client.plan.side_effect = [
            result(action="respond", topic="general", language="hi-en", reply="Bilkul, batayein."),
            result(action="respond", topic="general", language="en", reply="Of course, tell me more.")]
        with patch.object(VoiceSession, "run", return_value=wav_from_pcm(bytes(100))) as speech:
            self.event("action", {"id": "switch-one", "action": "voice"})
            self.event("submitted", {"id": "switch-one", "source": "voice", "text": "aap madad kar sakte ho"})
            self.assertEqual(self.app.session_state.language, "hi-en")
            self.event("action", {"id": "switch-two", "action": "voice", "automatic": True})
            self.event("submitted", {"id": "switch-two", "source": "voice", "text": "Can you help me please"})
            self.assertEqual(self.app.session_state.language, "en")
            self.assertEqual([call.args[2] for call in speech.call_args_list], ["hi-en", "en"])
        self.assertTrue(self.app.session_state.live_mode)
        self.assertEqual(model.calls, 2)

    def test_text_uses_gemini_once_without_tts_or_sidebar_permission(self):
        model = self.allow()
        with patch.object(VoiceSession, "run", side_effect=AssertionError("No speech")):
            self.event("submitted", {"id": "typed", "text": "hi", "source": "typed"})
            self.event("submitted", {"id": "typed", "text": "hi", "source": "typed"})
        self.assertEqual(model.calls, 1)
        self.assertEqual(len(self.app.session_state.support.messages), 2)
        self.assertEqual(self.app.session_state.support.messages[-1]["path"], "dialogue")

    def test_vector_setup_failure_is_visible_without_model_calls_or_fallback(self):
        import streamlit as st
        st.cache_resource.clear()
        with patch('zentromart.runtime.build_public_index', side_effect=ValueError('missing cache')):
            self.app.run()
        self.assertFalse(self.app.exception)
        self.assertTrue(self.app.error)
        self.assertIn('No fallback', self.app.error[0].value)
        self.assertEqual(self.app.session_state.support.model.calls, 0)
        st.cache_resource.clear()

    def test_mic_action_issues_scoped_lease_without_key_loading_or_auto_submission(self):
        self.allow()
        with patch("zentromart.voice.load_voice_key", side_effect=AssertionError("No key before stream")):
            self.event("action", {"id": "mic", "action": "dictate"})
        self.assertIsNotNone(self.mounts[-1]["connection"])
        self.assertFalse(self.app.session_state.live_mode)
        self.assertEqual(self.app.session_state.support.messages, [])
        self.assertEqual(self.app.session_state.speech.attempts, 0)

    def test_live_voice_action_then_same_id_transcript_runs_model_and_tts_once(self):
        model = self.allow()
        self.event("action", {"id": "voice-one", "action": "voice"})
        with patch.object(VoiceSession, "run", return_value=wav_from_pcm(bytes(100))) as speech:
            self.event("submitted", {"id": "voice-one", "text": "hello", "source": "voice"})
            self.assertIn("audio", self.mounts[-1]["reply"])
            self.event("submitted", {"id": "voice-one", "text": "hello", "source": "voice"})
        self.assertEqual(model.calls, 1)
        speech.assert_called_once_with("synthesize", "Hello! What can I help with?", "en")
        self.assertEqual(len(self.app.session_state.support.messages), 2)

    def test_stop_revokes_lease_without_renewing_budgets(self):
        model = self.allow()
        self.event("action", {"id": "voice-one", "action": "voice"})
        token = self.app.session_state.live_token
        self.app.session_state.speech.attempts = 4
        model.calls = 5
        self.event("action", {"id": "stop", "action": "stop"})
        self.assertFalse(self.app.session_state.live_mode)
        self.assertFalse(self.app.session_state.speech.enabled)
        self.assertEqual((self.app.session_state.speech.attempts, model.calls), (4, 5))
        with self.assertRaises(VoiceError): REGISTRY.claim(token)

    def test_spoken_order_stops_voice_before_tts_and_shows_masked_proof(self):
        model = self.allow()
        self.event("action", {"id": "order", "action": "voice"})
        with patch.object(VoiceSession, "run", side_effect=AssertionError("No TTS during proof")):
            self.event("submitted", {"id": "order", "text": "Order 89782837", "source": "voice"})
        self.assertEqual(model.calls, 0)
        self.assertEqual(self.app.text_input(key="verification").proto.type, 1)
        self.assertTrue(self.mounts[-1]["disabled"])
        self.assertFalse(self.app.session_state.live_mode)

    def test_tts_failure_preserves_text_and_requires_explicit_restart(self):
        self.allow()
        self.event("action", {"id": "voice", "action": "voice"})
        with patch.object(VoiceSession, "run", side_effect=VoiceError("timeout")):
            self.event("submitted", {"id": "voice", "text": "hi", "source": "voice"})
        self.assertEqual(self.app.session_state.support.messages[-1]["text"], "Hello! What can I help with?")
        self.assertFalse(self.app.session_state.live_mode)
        self.assertIsNone(self.mounts[-1]["reply"])
        self.assertTrue(self.app.warning)

    def test_stale_automatic_restart_after_end_cannot_enable_microphone(self):
        self.allow()
        self.event("action", {"id": "old-next", "action": "voice", "automatic": True})
        self.assertIsNone(self.app.session_state.live_token)
        self.assertFalse(self.app.session_state.live_mode)
