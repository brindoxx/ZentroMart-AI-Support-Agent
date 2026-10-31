"""No-network baseline boundaries and paired comparison accounting."""
import json
import unittest
from unittest.mock import MagicMock, patch
from zentromart.baseline import PromptOnlyAgent
from zentromart.config import load_settings
from zentromart.contracts import AgentRequest, Message
from zentromart.evaluation.comparison import compare_answers
from zentromart.llm import ModelDraft, ModelResult, ModelError, ModelRequest
from zentromart.evaluation.pacing import PacedModel


class BaselineTests(unittest.TestCase):
    def model(self):
        model = MagicMock()
        model.generate.return_value = ModelResult(ModelDraft('clarify', 'I am an AI assistant. What happened?', 'en', ()),
                                                   'test', 1, 0.01, {})
        return model

    def test_real_generation_without_retrieval_tools_or_history(self):
        model = self.model()
        agent = PromptOnlyAgent(model)
        reply = agent.respond(AgentRequest('s', 'What is the return window?', (Message('system', 'SECRET_GOLD'),)))
        model.generate.assert_called_once()
        request = model.generate.call_args.args[0]
        self.assertNotIn('SECRET_GOLD', request.instructions + request.message)
        self.assertEqual(request.message, 'What is the return window?')
        self.assertFalse(reply.evidence or reply.retrieved_evidence or reply.tool_calls)
        self.assertFalse(agent.configuration()['retrieval_enabled'])

    def test_fabricated_source_is_rejected_and_provider_error_is_not_hidden(self):
        model = self.model()
        model.generate.return_value = ModelResult(ModelDraft('answer', 'Something [RET-2]', 'en', ('RET-2',)), 'test', 1, 0, {})
        with self.assertRaises(ModelError):
            PromptOnlyAgent(model).respond(AgentRequest('s', 'hi'))
        model.generate.side_effect = ModelError('quota')
        with self.assertRaises(ModelError):
            PromptOnlyAgent(model).respond(AgentRequest('s', 'hi'))

    def test_comparison_uses_same_cases_and_counts_without_saving_text(self):
        baseline, rag = self.model(), self.model()
        report = compare_answers(load_settings(), lambda: PromptOnlyAgent(baseline),
                                 lambda: PromptOnlyAgent(rag), max_cases=3)
        self.assertTrue(report['comparable'])
        self.assertFalse(report['complete_practice_set'])
        self.assertEqual([c.args[0].message for c in baseline.generate.call_args_list],
                         [c.args[0].message for c in rag.generate.call_args_list])
        self.assertNotIn('What happened?', json.dumps(report))

    def test_provider_failure_stops_comparison_without_running_other_arm(self):
        model = self.model()
        model.generate.side_effect = ModelError('quota')
        factory = MagicMock()
        report = compare_answers(load_settings(), lambda: PromptOnlyAgent(model), factory, max_cases=2)
        self.assertFalse(report['comparable'])
        self.assertIsNone(report['rag'])
        factory.assert_not_called()
        model.generate.assert_called_once()

    def test_case_cap_is_validated_before_generation(self):
        for cap in (0, 53, True, None):
            with self.subTest(cap=cap), self.assertRaises(ValueError):
                compare_answers(load_settings(), self.model, self.model, max_cases=cap)

    def test_pacing_and_budget_cover_both_model_methods(self):
        model, wait = self.model(), MagicMock()
        paced = PacedModel(model, interval_seconds=10, max_generations=2,
                           clock=MagicMock(side_effect=[0, 2, 10]), wait=wait)
        paced.generate('first')
        paced.plan('second')
        wait.assert_called_once_with(8)
        with self.assertRaises(RuntimeError):
            paced.generate('third')
        self.assertEqual(paced.calls, 2)

    def test_token_guard_waits_for_rolling_window_and_rejects_oversize(self):
        now = [0]
        waits = []
        def wait(seconds):
            waits.append(seconds)
            now[0] += seconds
        model = self.model()
        paced = PacedModel(model, interval_seconds=0, input_tpm=1500,
                           clock=lambda: now[0], wait=wait)
        request = ModelRequest('instructions', 'message')
        paced.generate(request)
        paced.generate(request)
        self.assertIn(60, waits)
        self.assertEqual(paced.calls, 2)
        with self.assertRaises(ValueError):
            paced.generate(ModelRequest('instructions', 'x' * 1600))
        self.assertEqual(paced.calls, 2)
