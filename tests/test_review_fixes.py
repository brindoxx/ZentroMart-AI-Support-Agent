"""Regression evidence for the user's correctness, privacy and UX review."""

from dataclasses import replace
from datetime import date
import json
from pathlib import Path
import pickle
from tempfile import TemporaryDirectory
import tomllib
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from zentromart.calculations import BusinessCalendar, refund_timing
from zentromart.config import PROJECT_ROOT, FROZEN_REFERENCE_DATE
from zentromart.contracts import AgentRequest
from zentromart.conversation import ConversationalAgent, ConversationState, memory_text
from zentromart.demo import DemoGateway
from zentromart.grounding import GroundedAgent
from zentromart.ingestion import build_corpus, save_corpus
from zentromart.localization import EXACT_SENTENCES, TEMPLATE_BUCKETS, localize
from zentromart.retrieval import BM25Index, SearchDocument, corpus_fingerprint, load_search_documents
from zentromart.tools import MockToolGateway
from zentromart.voice import GnaniSpeech, VoiceError, VoiceSession
from zentromart.web_session import BrowserSession, ConsentModel, display_message
from zentromart.workflows import SupportAgent
import test_workflows as helpers


class ReviewFixTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.documents = load_search_documents(PROJECT_ROOT / "dataset")
        cls.index = BM25Index(cls.documents)
        cls.calendar = BusinessCalendar.load(PROJECT_ROOT / "dataset")

    def test_demo_ticket_consent_reaches_real_writer_and_can_be_revoked(self):
        with TemporaryDirectory() as directory:
            real = MockToolGateway(PROJECT_ROOT / "dataset", Path(directory))
            gateway = DemoGateway(real)
            agent = SupportAgent(self.index, MagicMock(), FROZEN_REFERENCE_DATE, calendar=self.calendar, gateway=gateway)
            browser = BrowserSession(agent, ConsentModel())
            browser.preferences("en", tickets=True)
            self.assertTrue(real.allow_ticket_writes)
            browser.submit("Human please")
            self.assertIn("confirmed", browser.messages[-1]["text"])
            self.assertTrue((Path(directory) / "tickets_created.csv").is_file())
            browser.preferences("en", tickets=False)
            self.assertFalse(real.allow_ticket_writes)
            browser.clear()
            browser.submit("Human please")
            self.assertIn("disabled", browser.messages[-1]["text"])
            self.assertEqual(len((Path(directory) / "tickets_created.csv").read_text().splitlines()), 2)

    def test_all_refund_routes_honor_recorded_completion_but_never_invent_it(self):
        for prefix in ("return", "cancellation", "rto"):
            order = {f"{prefix}_refund_initiated_on": "2026-10-10", f"{prefix}_refund_method": "upi"}
            self.assertEqual(refund_timing(order, self.calendar)["status"], "dated_timing")
            order[f"{prefix}_refund_completed_on"] = "2026-10-14"
            self.assertEqual(refund_timing(order, self.calendar)["status"], "completed")
            order[f"{prefix}_refund_completed_on"] = "2026-10-09"
            with self.assertRaises(ValueError):
                refund_timing(order, self.calendar)

    def test_completion_is_not_inferred_from_cancelled_or_rto_order_status(self):
        for prefix, status in (("cancellation", "cancelled"), ("rto", "returned_to_origin")):
            order = {"status": status, f"{prefix}_refund_initiated_on": "2026-10-01", f"{prefix}_refund_method": "upi"}
            self.assertEqual(refund_timing(order, self.calendar)["status"], "dated_timing")

    def test_verified_adapter_keeps_optional_completion_fields(self):
        gateway = MockToolGateway(PROJECT_ROOT / "dataset", PROJECT_ROOT / "artifacts/test-unused")
        gateway._module = MagicMock()
        gateway._module.lookup_order.return_value = {"found": True, "verified": True,
            **helpers.fixture(), "cancellation_refund_completed_on": "2026-10-14", "rto_refund_completed_on": "2026-10-15"}
        order = gateway.lookup_order("12345678", "0042")
        self.assertEqual(order["cancellation_refund_completed_on"], "2026-10-14")
        self.assertEqual(order["rto_refund_completed_on"], "2026-10-15")

    def test_missing_voice_key_is_recoverable_without_spending_or_reload(self):
        session = VoiceSession()
        session.enabled = True
        with patch("zentromart.voice.load_voice_key", side_effect=VoiceError("not_configured")):
            with self.assertRaises(VoiceError):
                session.run("synthesize", "Hello", "en")
        self.assertFalse(session.blocked)
        self.assertEqual(session.attempts, 0)
        with patch("zentromart.voice.load_voice_key", return_value="test-key"), patch.object(
                GnaniSpeech, "synthesize", new=AsyncMock(return_value=b"wav")):
            self.assertEqual(session.run("synthesize", "Hello", "en"), b"wav")

    def test_bad_clip_or_language_does_not_block_or_load_a_key(self):
        session = VoiceSession()
        session.enabled = True
        with patch("zentromart.voice.load_voice_key", side_effect=AssertionError("No key needed")):
            for action, value, language in (("transcribe", b"bad", "en"), ("synthesize", "Hello", "invalid")):
                with self.assertRaises(VoiceError):
                    session.run(action, value, language)
        self.assertFalse(session.blocked)
        self.assertEqual(session.attempts, 0)

    def test_manual_voice_recovery_keeps_spent_attempts_and_limit(self):
        session = VoiceSession()
        session.enabled = True
        with patch("zentromart.voice.load_voice_key", return_value="test-key"), patch.object(
                GnaniSpeech, "synthesize", new=AsyncMock(side_effect=VoiceError("service_failed"))):
            with self.assertRaises(VoiceError):
                session.run("synthesize", "Hello", "en")
        self.assertTrue(session.blocked)
        session.resume()
        self.assertFalse(session.blocked)
        self.assertEqual(session.attempts, 1)
        session.attempts = session.limit
        session.resume()
        with self.assertRaisesRegex(VoiceError, "paused"):
            session.run("synthesize", "Hello", "en")

    def test_redaction_preserves_public_facts_and_hides_identity_values(self):
        public = "INR 1,499, delivered 2026-10-15, refund amount 1499, paid ₹500"
        for redact in (memory_text, display_message):
            self.assertEqual(redact(public), public)
            for private in ("phone 9876543210", "order ID 81000001", "last 4 digits 0042", "pincode 001234", "फ़ोन ९८७६५४३२१०"):
                result = redact(private)
                self.assertNotEqual(result, private)
            mixed = redact("Order 81000001 cost INR 1,499 on 2026-10-15; phone 9876543210")
            self.assertNotIn("81000001", mixed)
            self.assertNotIn("9876543210", mixed)
            self.assertIn("INR 1,499", mixed)
            self.assertIn("2026-10-15", mixed)

    def test_metadata_copy_is_immutable_serializable_and_cache_safe(self):
        original = {"status": "current"}
        doc = SearchDocument("TEST-1", "Test", "Test text", "test.md", original)
        original["status"] = "superseded"
        self.assertEqual(doc.metadata["status"], "current")
        with self.assertRaises(TypeError):
            doc.metadata["status"] = "superseded"
        restored = pickle.loads(pickle.dumps(doc))
        self.assertEqual(doc, restored)
        with self.assertRaises(TypeError):
            restored.metadata["new"] = 1
        self.assertEqual(json.loads(json.dumps(doc.to_dict()))["metadata"], {"status": "current"})
        self.assertEqual(replace(doc, metadata={"status": "new"}).metadata["status"], "new")

    def test_conversation_reuses_engine_and_configuration_builds_no_answerer(self):
        model = MagicMock()
        with patch("zentromart.conversation.GroundedAgent", wraps=GroundedAgent) as constructed:
            agent = ConversationalAgent(self.index, model, FROZEN_REFERENCE_DATE)
            agent.configuration()
            self.assertEqual(constructed.call_count, 0)
            agent.respond(AgentRequest("s", "check a return"))
            self.assertEqual(constructed.call_count, 1)
            self.assertIs(constructed.call_args.kwargs["engine"], agent.engine)
        with self.assertRaises(ValueError):
            GroundedAgent(self.index, model, date(2026, 10, 19), engine=agent.engine)

    def test_removed_public_verification_property_cannot_accept_forged_status(self):
        state = ConversationState()
        self.assertFalse(hasattr(state, "verification_status"))
        with self.assertRaises(AttributeError):
            state.verification_status = "verified"

    def test_headphone_price_question_is_not_mistaken_for_a_phone_proof(self):
        agent = SupportAgent(self.index, MagicMock(), FROZEN_REFERENCE_DATE,
                             calendar=self.calendar, gateway=DemoGateway(MagicMock()))
        with patch.object(agent.public, "respond", return_value=MagicMock()) as public:
            agent.respond(AgentRequest("s", "/policy Do INR 1,499 headphones have a warranty?"))
        public.assert_called_once()

    def test_static_translations_use_dictionary_and_format_buckets_are_bounded(self):
        self.assertIn("No order is verified.", EXACT_SENTENCES)
        with patch.dict(TEMPLATE_BUCKETS, {}, clear=True):
            self.assertIn("सत्यापित", localize("No order is verified.", "hi"))
        self.assertIn("351", localize("Recorded refund amount: INR 351.", "hi"))
        self.assertLess(max(map(len, TEMPLATE_BUCKETS.values())), 15)

    def test_chunk_ids_and_hashes_are_reproducible_across_output_directories(self):
        chunks = build_corpus(PROJECT_ROOT / "dataset")
        self.assertEqual([chunk.chunk_id for chunk in chunks], [chunk.section_id for chunk in chunks])
        self.assertEqual(corpus_fingerprint(tuple(self.documents)), corpus_fingerprint(tuple(load_search_documents(PROJECT_ROOT / "dataset"))))
        with TemporaryDirectory() as directory:
            first = save_corpus(chunks, Path(directory), FROZEN_REFERENCE_DATE)
            second = save_corpus(chunks, Path(directory), FROZEN_REFERENCE_DATE)
            self.assertNotEqual(first, second)
            self.assertEqual((first / "chunks.jsonl").read_bytes(), (second / "chunks.jsonl").read_bytes())
            self.assertEqual(json.loads((first / "manifest.json").read_text())["corpus_sha256"],
                             json.loads((second / "manifest.json").read_text())["corpus_sha256"])

    def test_dependency_names_and_default_install_are_consistent(self):
        configuration = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text())
        self.assertEqual(configuration["project"]["name"], "zentromart-ai-support-agent")
        self.assertIn("-e .[ui,voice]", (PROJECT_ROOT / "requirements.txt").read_text())
        self.assertIn("-e .", (PROJECT_ROOT / "requirements-core.txt").read_text())
        self.assertIn("streamlit>=1.66.1,<2", configuration["project"]["optional-dependencies"]["ui"])


try:
    from streamlit.testing.v1 import AppTest
except ImportError:
    AppTest = None


@unittest.skipIf(AppTest is None, "Install requirements.txt")
class ReviewedUITests(unittest.TestCase):
    def test_return_help_collects_requirements_without_policy_jargon_or_api_calls(self):
        with patch("zentromart.web_session.GeminiModel", side_effect=AssertionError("No model needed")):
            app = AppTest.from_file(str(PROJECT_ROOT / "legacy_streamlit_app.py"), default_timeout=15).run()
            app.chat_input[0].set_value("hello").run()
            app.chat_input[0].set_value("check a return").run()
            self.assertIn("what item", app.session_state.support.messages[-1]["text"])
            self.assertNotIn("policy", app.session_state.support.messages[-1]["text"].lower())
            self.assertEqual(app.session_state.support.messages[-1]["path"], "clarification")
            app.chat_input[0].set_value("a shirt").run()
            self.assertIn("order date", app.session_state.support.messages[-1]["text"])
            self.assertFalse(app.exception)

    def test_explicit_voice_recovery_button_does_not_clear_budget(self):
        app = AppTest.from_file(str(PROJECT_ROOT / "legacy_streamlit_app.py"), default_timeout=15).run()
        app.checkbox(key="voice_enabled").check().run()
        app.session_state.voice_session.blocked = True
        app.session_state.voice_session.attempts = 3
        app.run()
        app.button(key="voice_retry").click().run()
        self.assertFalse(app.session_state.voice_session.blocked)
        self.assertEqual(app.session_state.voice_session.attempts, 3)
        self.assertFalse(app.exception)
