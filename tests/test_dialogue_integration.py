"""Browser consent, shared limits and the model-led Streamlit interaction."""

import unittest
from unittest.mock import MagicMock, patch

from zentromart.config import PROJECT_ROOT
from zentromart.web_session import BrowserSession, ConsentModel, PublicAccessError
from test_dialogue import result
import test_workflows as fixtures

try:
    from streamlit.testing.v1 import AppTest
except ImportError:
    AppTest = None


class DialogueIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.WorkflowTests.setUpClass()

    def session(self):
        backend, _, _ = fixtures.WorkflowTests().agent()
        model = ConsentModel()
        model._client = MagicMock()
        backend.public.model = model
        return BrowserSession(backend, model)

    def test_switch_enables_model_wording_and_shared_budget(self):
        session = self.session()
        session.submit("hello")
        session.model._client.plan.assert_not_called()
        session.preferences("en", cloud=True)
        session.model._client.plan.return_value = result(action="respond", topic="general", reply="Hello! Tell me what's on your mind.")
        session.submit("hi there")
        self.assertEqual(session.messages[-1]["text"], "I'm ZentroMart's AI support assistant. Hello! Tell me what's on your mind.")
        self.assertEqual(session.messages[-1]["path"], "dialogue")
        self.assertEqual(session.model.calls, 1)
        session.model.generate(MagicMock())
        self.assertEqual(session.model.calls, 2)
        session.model.limit = 2
        with self.assertRaisesRegex(PublicAccessError, "cloud_paused"):
            session.model.plan(MagicMock())

    def test_verification_bypasses_model_even_when_enabled(self):
        session = self.session()
        session.preferences("en", cloud=True)
        session.submit("Order 12345678")
        session.submit("0042", proof=True)
        self.assertTrue(session.agent.state.verified)
        self.assertEqual(session.model.calls, 0)
        session.model._client.plan.assert_not_called()
        self.assertEqual(session.agent._calls, [])

    def test_toggle_and_clear_do_not_reset_lockout_or_generation_budget(self):
        session = self.session()
        session.preferences("en", cloud=True)
        session.model.calls = 7
        for text in ("Order 12345678", "9999", "8888"):
            session.submit(text)
        session.preferences("en", cloud=False)
        session.clear()
        session.preferences("en", cloud=True)
        session.submit("Order 12345678")
        self.assertEqual(session.agent.state.phase, "locked")
        self.assertEqual(session.model.calls, 7)
        self.assertEqual(list(session.dialogue.history), [])

    def test_planner_error_pauses_same_provider_without_raw_error(self):
        session = self.session()
        session.preferences("en", cloud=True)
        session.model._client.plan.side_effect = ValueError("SECRET_PROVIDER_PAYLOAD")
        with self.assertRaisesRegex(PublicAccessError, "cloud_failed"):
            session.submit("hello")
        self.assertTrue(session.model.blocked)
        self.assertEqual(session.model.calls, 1)
        self.assertNotIn("SECRET", str(session.messages))

    def test_semantic_order_dispatch_is_not_labeled_as_no_model_call(self):
        session = self.session()
        session.preferences("en", cloud=True)
        session.model._client.plan.return_value = result(action="order", topic="delivery", reply="")
        session.submit("Where has my parcel got to?")
        self.assertEqual(session.messages[-1]["path"], "assisted")
        self.assertEqual(session.agent.state.phase, "order")

    @unittest.skipIf(AppTest is None, "Install requirements-ui.txt for Streamlit UI tests")
    def test_streamlit_generated_followups_for_unseen_item(self):
        app = AppTest.from_file(str(PROJECT_ROOT / "legacy_streamlit_app.py"), default_timeout=15)
        app.secrets["llm"] = {"provider": "gemini", "model": "gemini-test", "api_key": "test-key"}
        app.run()
        app.checkbox(key="cloud").check().run()
        with patch("zentromart.web_session.GeminiModel") as transport:
            transport.return_value.plan.side_effect = [
                result(action="respond", topic="general", reply="Hi! What can I help you with?"),
                result(reply="Sure. What would you like to send back?"),
                result(category="fashion", reply="When did you order the blouse?")]
            for text in ("hello", "check a return", "a blouse"):
                app.chat_input[0].set_value(text).run()
                self.assertFalse(app.exception)
            self.assertEqual(transport.return_value.plan.call_count, 3)
            transport.return_value.generate.assert_not_called()
        self.assertEqual(app.session_state.support.messages[-1]["text"], "When did you order the blouse?")
        self.assertTrue(any(c.value == "Gemini · conversation" for c in app.caption))
