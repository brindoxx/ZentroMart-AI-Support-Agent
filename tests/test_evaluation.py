"""Check scoring correctness, session isolation, and label/report boundaries."""

from dataclasses import fields
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from zentromart.config import PROJECT_ROOT, load_settings
from zentromart.contracts import AgentRequest, AgentResponse, ToolCall
from zentromart.evaluation.cases import Case, Target, load_cases, parse_tool_calls
from zentromart.evaluation.runner import ClarificationBaseline, run_evaluation
from zentromart.evaluation.scoring import matches_fact, normalize, score_response, tool_calls_match


def target(**overrides):
    values = dict(decisions=("answer",), language="en", evidence=("RET-2", "REF-3"),
                  required_facts=("12", "My Orders / app"), forbidden_claims=("guaranteed refund",),
                  tool_calls=None)
    return Target(**{**values, **overrides})


class ScoringTests(unittest.TestCase):
    def test_alternative_decisions_and_multisource_retrieval(self):
        response = AgentResponse(
            "escalate", "Use My Orders within twelve days.", "en", evidence=("RET-2", "MADE-UP"),
            retrieved_evidence=("OTHER", "RET-2", "RET-2", "REF-3"),
        )
        scores = score_response(target(decisions=("answer", "escalate")), response,
                                {"RET-2", "REF-3", "OTHER"}, top_k=2)
        self.assertTrue(scores["decision_correct"])
        self.assertEqual(scores["citation_precision"], 0.5)
        self.assertEqual(scores["citation_recall"], 0.5)
        self.assertEqual(scores["invalid_citation_count"], 1)
        self.assertEqual(scores["retrieval_recall_at_k"], 0.5)
        self.assertEqual(scores["reciprocal_rank_at_k"], 0.5)
        self.assertEqual(scores["required_fact_lexical_coverage"], 1.0)

    def test_fact_boundaries_alternatives_and_forbidden_claims(self):
        self.assertFalse(matches_fact("120 days", "12"))
        self.assertFalse(matches_fact("happy", "app"))
        self.assertTrue(matches_fact("Use the APP", "My Orders / app"))
        self.assertTrue(matches_fact("Twelve days", "१२"))
        self.assertTrue(matches_fact("forty-nine rupees", "49"))
        self.assertTrue(matches_fact("₹1,249", "1249"))
        scores = score_response(target(), AgentResponse("answer", "A guaranteed refund", "en"), set(), 5)
        self.assertEqual(scores["forbidden_claim_lexical_hits"], 1)
        self.assertFalse(scores["forbidden_claim_lexical_clear"])

    def test_dates_normalize_between_supported_formats(self):
        for wording in ("27 October 2026", "27th October 2026", "२७ अक्टूबर २०२६"):
            with self.subTest(wording=wording):
                self.assertEqual(normalize(wording), "2026-10-27")
        self.assertTrue(matches_fact("Arrives 27 October 2026.", "2026-10-27"))

    def test_unanswerable_and_unlabeled_metrics_are_not_fake_perfect_scores(self):
        scores = score_response(target(evidence=(), required_facts=(), forbidden_claims=()),
                                ClarificationBaseline().respond(AgentRequest("s", "hello")), set(), 5)
        for name in ("retrieval_hit_at_k", "citation_recall", "citation_precision",
                     "required_fact_lexical_coverage", "forbidden_claim_lexical_clear", "tool_calls_correct"):
            self.assertIsNone(scores[name])

    def test_tool_matching_keeps_proofs_as_text_and_checks_unexpected_calls(self):
        wanted = parse_tool_calls("lookup_order(order_id=12345678, verification_value=0012)")
        self.assertEqual(wanted[0].arguments["verification_value"], "0012")
        self.assertTrue(tool_calls_match(wanted, wanted))
        self.assertFalse(tool_calls_match(wanted, (ToolCall("lookup_order", {"order_id": "12345678"}),)))
        self.assertFalse(tool_calls_match((), wanted))
        self.assertFalse(tool_calls_match(parse_tool_calls("lookup_order(order_id=12345678)"), wanted))
        self.assertTrue(tool_calls_match(parse_tool_calls("create_ticket()"),
                                        (ToolCall("create_ticket", {"summary": "test handover"}),)))
        with self.assertRaises(ValueError):
            parse_tool_calls("__import__('os').system('test')")

    def test_response_schema_rejects_invalid_decisions_and_trace_shapes(self):
        with self.assertRaises(ValueError):
            AgentResponse("refund_now", "hello", "en")
        with self.assertRaises(ValueError):
            AgentResponse("answer", "hello", "en", evidence=["RET-2"])
        with self.assertRaises(ValueError):
            ToolCall("lookup_order", {"verification_value": 12})


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.settings = load_settings()
        self.root = PROJECT_ROOT / "dataset"

    def test_loads_all_cases_and_asr_variants(self):
        questions = load_cases(self.root, "questions")
        conversations = load_cases(self.root, "conversations")
        asr = load_cases(self.root, "questions", asr=True)
        self.assertEqual(len(questions), 52)
        self.assertEqual(len(conversations), 23)
        self.assertEqual(sum(map(len, conversations)), 96)
        self.assertTrue(any(q[0].message != a[0].message for q, a in zip(questions, asr)))
        self.assertEqual({f.name for f in fields(AgentRequest)}, {"session_id", "message", "history"})

    def test_sessions_reset_but_conversation_history_contains_actual_replies(self):
        created = []
        class RecordingAgent:
            def __init__(self):
                self.requests = []
                created.append(self)

            def respond(self, request):
                self.requests.append(request)
                return AgentResponse("clarify", "ACTUAL_AGENT_REPLY", "en")

        report = run_evaluation(self.settings, factory=RecordingAgent, suite="conversations")
        self.assertEqual(len(created), 23)
        self.assertEqual(report["summary"]["total_rows"], 96)
        self.assertEqual(report["summary"]["error_rows"], 0)
        for agent in created:
            self.assertEqual(agent.requests[0].history, ())
            for index, request in enumerate(agent.requests):
                self.assertEqual(len(request.history), index * 2)
                if index:
                    self.assertEqual(request.history[-1].text, "ACTUAL_AGENT_REPLY")
        serialized = json.dumps(report)
        self.assertNotIn("ACTUAL_AGENT_REPLY", serialized)
        self.assertNotIn("verification_value", serialized)
        self.assertNotIn(created[0].requests[0].message, serialized)

    def test_baseline_completes_all_rows_without_tool_actions(self):
        with patch("zentromart.evaluation.runner.fingerprint", return_value="test-hash"):
            report = run_evaluation(self.settings)
        self.assertEqual(report["run_kind"], "wiring_baseline")
        self.assertEqual(report["sessions"], 75)
        self.assertEqual(report["summary"]["completed_rows"], 148)
        self.assertEqual(report["summary"]["metrics"]["tool_calls_correct"]["scored_rows"], 96)
        self.assertEqual(report["summary"]["metrics"]["retrieval_hit_at_k"]["mean"], 0)

    def test_agent_errors_are_counted_and_exception_secrets_are_omitted(self):
        class BrokenAgent:
            def respond(self, request):
                raise RuntimeError("SECRET_DO_NOT_PERSIST")

        report = run_evaluation(self.settings, factory=BrokenAgent, suite="questions")
        self.assertEqual(report["summary"]["error_rows"], 52)
        self.assertEqual(report["summary"]["completed_rows"], 0)
        self.assertIsNone(report["summary"]["metrics"]["decision_correct"]["mean"])
        self.assertNotIn("SECRET_DO_NOT_PERSIST", json.dumps(report))

    def test_loader_sorts_turns_and_rejects_missing_or_duplicate_turns(self):
        columns = ["conversation_id", "turn", "customer_message", "language", "expected_decision",
                   "gold_evidence", "must_include", "must_not_include", "expected_tool_calls"]
        base = dict.fromkeys(columns, "")
        base.update(conversation_id="PC001", customer_message="hello", language="en", expected_decision="clarify")
        with patch("zentromart.evaluation.cases.read_table", return_value=(columns, [
            {**base, "turn": "2"}, {**base, "turn": "1"},
        ])):
            sessions = load_cases(Path("unused"), "conversations")
            self.assertEqual([case.turn for case in sessions[0]], [1, 2])
        for turns in (("1", "3"), ("1", "1")):
            with self.subTest(turns=turns), patch("zentromart.evaluation.cases.read_table",
                return_value=(columns, [{**base, "turn": turn} for turn in turns])):
                with self.assertRaises(ValueError):
                    load_cases(Path("unused"), "conversations")

    def test_only_customer_text_crosses_boundary_and_secret_labels_do_not_persist(self):
        expected = target(required_facts=("LABEL_SECRET",), forbidden_claims=("FORBIDDEN_SECRET",),
                          tool_calls=(ToolCall("lookup_order", {"verification_value": "SECRET_PROOF"}),))
        case = Case("PQ0001", "questions:PQ0001", 1, "CUSTOMER_MESSAGE", expected)
        class InspectingAgent:
            def respond(self, request):
                self_request = vars(request)
                if set(self_request) != {"session_id", "message", "history"}:
                    raise AssertionError("Labels crossed request boundary")
                return AgentResponse("answer", "SECRET_REPLY", "en")

        with patch("zentromart.evaluation.runner.load_cases", return_value=[[case]]):
            report = run_evaluation(self.settings, factory=InspectingAgent, suite="questions")
        self.assertEqual(report["summary"]["error_rows"], 0)
        for secret in ("CUSTOMER_MESSAGE", "LABEL_SECRET", "FORBIDDEN_SECRET", "SECRET_PROOF", "SECRET_REPLY"):
            self.assertNotIn(secret, json.dumps(report))

    def test_invalid_run_options_fail_before_running(self):
        with self.assertRaises(ValueError):
            run_evaluation(self.settings, suite="conversations", asr=True)
        with self.assertRaises(ValueError):
            run_evaluation(self.settings, top_k=0)


if __name__ == "__main__":
    unittest.main()
