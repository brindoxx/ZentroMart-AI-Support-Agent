"""Offline localization, privacy, consent and Streamlit interaction checks."""

import json
from string import Formatter
import unittest
from unittest.mock import MagicMock, patch

from zentromart.config import PROJECT_ROOT
from zentromart.contracts import AgentRequest
from zentromart.localization import LANGUAGES, SENTENCES, choose_language, localize
from zentromart.ui_text import TEXT
from zentromart.web_session import BrowserSession, ConsentModel, PublicAccessError, display_message

from test_workflows import WorkflowTests, fixture


class LocalizationTests(unittest.TestCase):
    def test_every_reviewed_template_preserves_placeholders_in_both_translations(self):
        for english, hindi, hinglish in SENTENCES:
            fields = {name for _, name, _, _ in Formatter().parse(english) if name}
            values = {name: f"VALUE_{name}" for name in fields}
            for language, target in (("hi", hindi), ("hi-en", hinglish)):
                with self.subTest(sentence=english, language=language):
                    self.assertEqual(localize(english.format(**values), language), target.format(**values))

    def test_unknown_sentence_fails_closed_and_ui_catalogs_have_same_keys(self):
        with self.assertRaises(ValueError):
            localize("A new unreviewed approval.", "hi")
        self.assertEqual(set(TEXT), set(LANGUAGES))
        for language in LANGUAGES:
            self.assertEqual(set(TEXT[language]), set(TEXT["en"]))

    def test_language_detection_and_explicit_preference(self):
        self.assertEqual(choose_language("Mera refund nahi mila"), "hi-en")
        self.assertEqual(choose_language("मेरे ऑर्डर की स्थिति"), "hi")
        self.assertEqual(choose_language("0042", "hi-en"), "hi-en")
        self.assertEqual(choose_language("मेरे ऑर्डर", preferred="en"), "en")

    def test_existing_workflow_scenarios_have_reviewed_translations(self):
        # Exercise the Phase 11 regression suite without changing its English assertions.
        missing = []
        def checked(text, language):
            for target in ("hi", "hi-en"):
                try:
                    localize(text, target)
                except ValueError:
                    missing.append(text)
            return localize(text, language)
        result = unittest.TestResult()
        with patch("zentromart.workflows.localize", side_effect=checked):
            unittest.defaultTestLoader.loadTestsFromTestCase(WorkflowTests).run(result)
        self.assertFalse(result.errors)
        self.assertFalse(result.failures)
        self.assertEqual(missing, [])

    def test_hindi_order_and_devanagari_proof_never_reach_model(self):
        helper = WorkflowTests()
        WorkflowTests.setUpClass()
        agent, _, model = helper.agent()
        first = helper.turn(agent, "मेरे ऑर्डर १२३४५६७८ की स्थिति")
        self.assertEqual(first.language, "hi")
        reply = helper.turn(agent, "फोन के आखिरी अंक ००४२ हैं")
        self.assertTrue(agent.state.verified)
        self.assertEqual(reply.language, "hi")
        self.assertNotIn("0042", reply.reply)
        self.assertNotEqual(agent.last_trace.reason, "translation_unavailable")
        model.generate.assert_not_called()

    def test_translation_preserves_refund_amount_date_reference_and_evidence(self):
        WorkflowTests.setUpClass()
        helper = WorkflowTests()
        for language in ("hi", "hi-en"):
            agent, _, model = helper.agent(fixture(return_refund_initiated_on="2026-10-15",
                return_refund_method="upi", return_refund_amount_inr=351, return_rrn="000TESTREF"))
            agent.set_language(language)
            helper.verify(agent, "Refund order 12345678")
            reply = helper.turn(agent, "refund timing")
            for value in ("351", "000TESTREF", "2026-10-20", "[REF-2]"):
                self.assertIn(value, reply.reply)
            self.assertEqual(reply.language, language)
            self.assertNotEqual(agent.last_trace.reason, "translation_unavailable")
            model.generate.assert_not_called()

    def test_language_change_and_reset_do_not_remove_lockout(self):
        WorkflowTests.setUpClass()
        helper = WorkflowTests()
        agent, gateway, _ = helper.agent()
        helper.turn(agent, "Order 12345678")
        helper.turn(agent, "9999")
        agent.set_language("hi")
        result = helper.turn(agent, "8888")
        self.assertEqual(result.language, "hi")
        self.assertEqual(result.decision, "refuse")
        helper.turn(agent, "/reset")
        agent.set_language("hi-en")
        self.assertEqual(helper.turn(agent, "Order 12345678").decision, "refuse")
        self.assertEqual(len(gateway.calls), 3)

    def test_localized_human_and_safety_requests_do_not_assert_refund(self):
        WorkflowTests.setUpClass()
        helper = WorkflowTests()
        for message in ("सपोर्ट टीम से बात करनी है", "battery phool rahi hai", "बैटरी फूल गई है"):
            agent, _, model = helper.agent()
            reply = helper.turn(agent, message)
            self.assertEqual(reply.decision, "escalate")
            self.assertFalse(reply.tool_calls)  # Writes disabled.
            self.assertNotEqual(agent.last_trace.reason, "translation_unavailable")
            model.generate.assert_not_called()

    def test_public_policy_route_blocks_labeled_proofs_and_full_phone_numbers(self):
        WorkflowTests.setUpClass()
        for text in ("/policy 0042", "/policy My phone is +91 9876543210", "/policy मेरा पिनकोड ००१२३४ है", "test@example.com"):
            agent, _, model = WorkflowTests().agent()
            reply = agent.respond(AgentRequest("test", text))
            self.assertEqual(reply.decision, "clarify")
            self.assertEqual(agent.last_trace.reason, "public_privacy_guard")
            model.generate.assert_not_called()

    def test_public_reply_requests_selected_language_and_contains_no_verified_record(self):
        from zentromart.llm import ModelDraft, ModelResult
        WorkflowTests.setUpClass()
        for language in LANGUAGES:
            agent, _, model = WorkflowTests().agent()
            model.generate.side_effect = None
            model.generate.return_value = ModelResult(ModelDraft("clarify", TEXT[language]["intro"], language, ()), "test", 1, 0.1, {})
            WorkflowTests().verify(agent)
            agent.set_language(language)
            reply = agent.respond(AgentRequest("session", "/policy How does Plus membership work?"))
            self.assertEqual(reply.language, language)
            self.assertFalse(agent.state.verified)
            sent = model.generate.call_args.args[0]
            self.assertIn(f'"reply_language": "{language}"', sent.instructions)
            for secret in ("0042", "12345678", "subtotal_inr"):
                self.assertNotIn(secret, sent.message + sent.instructions)


class WebSessionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        WorkflowTests.setUpClass()

    def session(self):
        agent, gateway, _ = WorkflowTests().agent()
        return BrowserSession(agent, ConsentModel()), gateway

    def test_proof_history_and_executor_arguments_are_not_retained(self):
        session, _ = self.session()
        session.submit("Order 12345678")
        session.submit("0042", proof=True)
        saved = json.dumps(session.messages)
        self.assertNotIn("0042", saved)
        self.assertNotIn("12345678", saved)
        self.assertNotIn("verification_value", saved)
        self.assertEqual(session.agent._calls, [])
        session.clear()
        self.assertFalse(session.agent.state.verified)
        self.assertEqual(session.messages, [])

    def test_state_and_write_preferences_are_session_local(self):
        first, gateway = self.session()
        second, _ = self.session()
        first.preferences("hi", cloud=True, tickets=True)
        self.assertTrue(gateway.allow_ticket_writes)
        self.assertFalse(second.agent.allow_ticket_writes)
        self.assertFalse(second.model.enabled)
        first.submit("Order 12345678")
        self.assertEqual(second.agent.state.phase, "public")
        with self.assertRaises(ValueError):
            first.preferences("invalid")
        with self.assertRaises(ValueError):
            first.preferences("hi", cloud="yes")

    def test_display_minimization_and_bounded_history(self):
        self.assertNotIn("0042", display_message("phone last 4 digits 0042"))
        self.assertNotIn("test@example.com", display_message("test@example.com"))
        session, _ = self.session()
        for _ in range(20):
            session.submit("/reset")
        self.assertEqual(len(session.messages), 24)
        self.assertNotIn("messages", repr(session))

    def test_consent_is_checked_before_loading_a_key_and_error_pauses_calls(self):
        model = ConsentModel()
        with patch("zentromart.web_session.load_llm_settings", side_effect=AssertionError("No key read")):
            with self.assertRaisesRegex(PublicAccessError, "cloud_disabled"):
                model.generate(MagicMock())
        model.enabled = True
        model._client = MagicMock()
        model._client.generate.side_effect = ValueError("SECRET")
        with self.assertRaisesRegex(PublicAccessError, "cloud_failed") as raised:
            model.generate(MagicMock())
        self.assertNotIn("SECRET", str(raised.exception))
        with self.assertRaisesRegex(PublicAccessError, "cloud_paused"):
            model.generate(MagicMock())
        self.assertEqual(model._client.generate.call_count, 1)

    def test_call_limit_and_reset_does_not_reset_budget(self):
        session, _ = self.session()
        session.model.enabled = True
        session.model._client = MagicMock()
        for _ in range(20):
            session.model.generate(MagicMock())
        session.clear()
        with self.assertRaisesRegex(PublicAccessError, "cloud_paused"):
            session.model.generate(MagicMock())

    def test_custom_secret_loader_is_lazy_and_only_called_once(self):
        loader = MagicMock(return_value=MagicMock())
        model = ConsentModel(settings_loader=loader)
        loader.assert_not_called()
        model.enabled = True
        with patch("zentromart.web_session.GeminiModel") as transport:
            model.generate(MagicMock())
            model.generate(MagicMock())
        loader.assert_called_once()
        transport.assert_called_once_with(loader.return_value)


try:
    from streamlit.testing.v1 import AppTest
except ImportError:
    AppTest = None


@unittest.skipIf(AppTest is None, "Install requirements-ui.txt for Streamlit UI tests")
class StreamlitTests(unittest.TestCase):
    def app(self):
        return AppTest.from_file(str(PROJECT_ROOT / "legacy_streamlit_app.py"), default_timeout=15).run()

    def test_startup_offline_and_cloud_consent_notice(self):
        with patch("zentromart.web_session.load_llm_settings", side_effect=AssertionError("No key read")):
            app = self.app()
            self.assertFalse(app.exception)
            self.assertFalse(app.checkbox(key="cloud").value)
            self.assertFalse(app.checkbox(key="tickets").value)
            app.button(key="start_policy").click().run()
            self.assertFalse(app.exception)
            app.chat_input[0].set_value("/policy How does Plus membership work?").run()
            self.assertTrue(app.warning)
            self.assertIn("Gemini", app.warning[0].value)

    def test_opted_in_public_chat_uses_server_side_secrets_and_selected_language(self):
        from zentromart.llm import ModelDraft, ModelResult
        for language in LANGUAGES:
            app = AppTest.from_file(str(PROJECT_ROOT / "legacy_streamlit_app.py"), default_timeout=15)
            app.secrets["llm"] = {"provider": "gemini", "model": "gemini-test", "api_key": "test-key"}
            app.session_state.language = language
            app.run()
            app.checkbox(key="cloud").check().run()
            with patch("zentromart.web_session.GeminiModel") as transport:
                from test_dialogue import result
                transport.return_value.plan.return_value = result(action="search", topic="membership", reply="", language=language)
                transport.return_value.generate.return_value = ModelResult(
                    ModelDraft("clarify", TEXT[language]["intro"], language, ()), "test", 1, 0.1, {})
                app.chat_input[0].set_value("/policy How does Plus membership work?").run()
            self.assertFalse(app.exception)
            self.assertFalse(app.warning)
            self.assertEqual(app.session_state.support.messages[-1]["text"], TEXT[language]["intro"])
            self.assertEqual(transport.call_args.args[0].model, "gemini-test")
            self.assertNotIn("test-key", json.dumps(app.session_state.support.messages))

    def test_masked_form_clears_proof_and_keeps_it_out_of_history(self):
        app = self.app()
        app.chat_input[0].set_value("Order 89782837").run()
        self.assertFalse(app.exception)
        self.assertEqual(app.text_input(key="verification").proto.type, 1)
        self.assertTrue(app.chat_input[0].disabled)
        app.text_input(key="verification").set_value("4533")  # Published synthetic example.
        app.button(key="verify_submit").click().run()
        self.assertFalse(app.exception)
        self.assertTrue(app.session_state.support.agent.state.verified)
        self.assertNotIn("4533", json.dumps(app.session_state.support.messages))
        self.assertEqual(app.session_state.support.agent._calls, [])
        app.button(key="clear").click().run()
        self.assertFalse(app.exception)
        self.assertFalse(app.session_state.support.agent.state.verified)
        self.assertEqual(app.session_state.support.messages, [])

    def test_bad_proof_language_change_clear_and_second_session_isolation(self):
        app = self.app()
        app.chat_input[0].set_value("Order 89782837").run()
        app.text_input(key="verification").set_value("not a proof")
        app.button(key="verify_submit").click().run()
        self.assertEqual(app.text_input(key="verification").value, "")
        app.session_state.language = "hi"
        app.run()
        app.text_input(key="verification").set_value("bad again")
        app.button(key="verify_submit").click().run()
        self.assertEqual(app.session_state.support.agent.state.phase, "locked")
        app.button(key="clear").click().run()
        app.chat_input[0].set_value("Order 89782837").run()
        self.assertEqual(app.session_state.support.agent.state.phase, "locked")
        self.assertFalse(app.exception)
        second = self.app()
        self.assertFalse(second.exception)
        self.assertEqual(second.session_state.support.agent.state.phase, "public")
        self.assertEqual(second.session_state.support.messages, [])


def load_tests(loader, tests, pattern):
    # Imported Phase 11 helpers are not additional top-level test cases.
    suite = unittest.TestSuite()
    for case in (LocalizationTests, WebSessionTests, StreamlitTests):
        suite.addTests(loader.loadTestsFromTestCase(case))
    return suite


if __name__ == "__main__":
    unittest.main()
