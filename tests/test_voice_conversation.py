"""Automatic voice turns, consent, deduplication and failure boundaries."""

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

from zentromart.voice import VoiceError, wav_from_pcm
from zentromart.voice_conversation import VoiceConversation, VoiceTurnError
from zentromart.web_session import PublicAccessError
from test_demo_voice import recording


class VoiceConversationTests(unittest.TestCase):
    def setup_turn(self):
        support = SimpleNamespace(dialogue_enabled=True,
            model=SimpleNamespace(enabled=True, blocked=False, calls=0, limit=20),
            agent=SimpleNamespace(state=SimpleNamespace(phase="public")), messages=[])
        def submit(text):
            support.messages.extend([{"role": "user", "text": text},
                                     {"role": "assistant", "text": "How can I help?", "language": "en"}])
        support.submit = MagicMock(side_effect=submit)
        speech = SimpleNamespace(enabled=True, blocked=False, attempts=0, limit=20,
                                 run=MagicMock(side_effect=["hello", wav_from_pcm(bytes(100))]))
        mode = VoiceConversation()
        mode.start()
        return mode, support, speech

    def test_automatic_pipeline_uses_same_chat_and_does_not_repeat_event(self):
        mode, support, speech = self.setup_turn()
        stages = []
        audio = mode.run("turn-one", recording(), support, speech, "en", stages.append)
        self.assertTrue(audio.startswith(b"RIFF"))
        self.assertEqual(stages, ["transcribe", "assistant", "synthesize"])
        support.submit.assert_called_once_with("hello")
        self.assertEqual(speech.run.call_args_list[1].args, ("synthesize", "How can I help?", "en"))
        self.assertEqual(mode.phase, "ready")
        self.assertIsNone(mode.run("turn-one", recording(), support, speech, "en"))
        self.assertEqual(speech.run.call_count, 2)

    def test_no_calls_without_both_consents_or_during_verification(self):
        for change in ("inactive", "voice_off", "cloud_off", "proof", "locked"):
            mode, support, speech = self.setup_turn()
            if change == "inactive": mode.stop()
            elif change == "voice_off": speech.enabled = False
            elif change == "cloud_off": support.model.enabled = False
            else: support.agent.state.phase = change
            with self.subTest(change=change), self.assertRaises(VoiceTurnError):
                mode.run("turn", recording(), support, speech, "en")
            speech.run.assert_not_called()
            support.submit.assert_not_called()

    def test_budgets_and_audio_are_checked_before_spending_credits(self):
        for change in ("voice_limit", "model_limit", "bad_clip"):
            mode, support, speech = self.setup_turn()
            if change == "voice_limit": speech.attempts = 19
            if change == "model_limit": support.model.calls = 19
            with self.subTest(change=change), self.assertRaises(VoiceTurnError):
                mode.run("turn", b"bad" if change == "bad_clip" else recording(), support, speech, "en")
            speech.run.assert_not_called()

    def test_stt_failure_never_calls_assistant_or_tts_and_cannot_auto_retry(self):
        mode, support, speech = self.setup_turn()
        speech.run.side_effect = VoiceError("timeout")
        with self.assertRaises(VoiceTurnError) as raised:
            mode.run("turn", recording(), support, speech, "en")
        self.assertEqual((raised.exception.stage, raised.exception.code), ("transcribe", "timeout"))
        self.assertFalse(mode.active)
        mode.start()
        self.assertIsNone(mode.run("turn", recording(), support, speech, "en"))
        self.assertEqual(speech.run.call_count, 1)
        support.submit.assert_not_called()

    def test_tts_failure_keeps_text_without_resubmitting_customer_message(self):
        mode, support, speech = self.setup_turn()
        speech.run.side_effect = ["hello", VoiceError("timeout")]
        with self.assertRaises(VoiceTurnError) as raised:
            mode.run("turn", recording(), support, speech, "en")
        self.assertEqual(raised.exception.stage, "synthesize")
        self.assertEqual(support.messages[-1]["text"], "How can I help?")
        mode.start()
        mode.run("turn", recording(), support, speech, "en")
        support.submit.assert_called_once()

    def test_model_failure_never_speaks_a_previous_answer(self):
        mode, support, speech = self.setup_turn()
        support.submit.side_effect = PublicAccessError("cloud_failed")
        with self.assertRaises(VoiceTurnError) as raised:
            mode.run("turn", recording(), support, speech, "en")
        self.assertEqual((raised.exception.stage, raised.exception.code), ("assistant", "cloud_failed"))
        self.assertEqual(speech.run.call_count, 1)

    def test_spoken_proof_is_not_submitted(self):
        mode, support, speech = self.setup_turn()
        speech.run.side_effect = ["phone last 4 digits 0042"]
        with self.assertRaises(VoiceTurnError) as raised:
            mode.run("turn", recording(), support, speech, "en")
        self.assertEqual(raised.exception.stage, "verification")
        support.submit.assert_not_called()
        self.assertNotIn("0042", str(raised.exception))

    def test_order_that_needs_proof_pauses_voice_before_tts(self):
        mode, support, speech = self.setup_turn()
        def order(text):
            support.agent.state.phase = "proof"
            support.messages.append({"role": "assistant", "text": "Type verification in the masked field."})
        support.submit.side_effect = order
        self.assertIsNone(mode.run("turn", recording(), support, speech, "en"))
        self.assertEqual(mode.phase, "verification")
        self.assertFalse(mode.active)
        self.assertEqual(speech.run.call_count, 1)

    def test_long_reply_stays_in_chat_without_truncated_speech(self):
        mode, support, speech = self.setup_turn()
        support.submit.side_effect = lambda text: support.messages.append({"role": "assistant", "text": "a" * 801})
        with self.assertRaises(VoiceTurnError) as raised:
            mode.run("turn", recording(), support, speech, "en")
        self.assertEqual(raised.exception.code, "invalid_text")
        self.assertEqual(speech.run.call_count, 1)

    def test_stop_does_not_recreate_or_reset_provider_budgets(self):
        mode, support, speech = self.setup_turn()
        speech.attempts = 4
        support.model.calls = 5
        mode.stop()
        self.assertFalse(mode.active)
        self.assertEqual((speech.attempts, support.model.calls), (4, 5))
