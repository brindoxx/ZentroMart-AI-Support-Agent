"""Shared controller parity, private isolation and CLI wiring; no provider calls."""
from io import StringIO
import json
import unittest
from unittest.mock import MagicMock, patch
from zentromart.application import create_agent
from zentromart.config import load_settings
from zentromart.contracts import AgentRequest
from zentromart.dialogue import LLMConversation
from zentromart.web_session import BrowserSession
from test_dialogue import result
import test_workflows as fixtures
from test_llm import SETTINGS


class ApplicationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.WorkflowTests.setUpClass()

    def agent(self, model=None):
        model = model or MagicMock()
        return create_agent(load_settings(), model, index=fixtures.WorkflowTests.index,
                            calendar=fixtures.WorkflowTests.calendar, gateway=fixtures.FakeGateway())

    def test_browser_and_direct_controller_share_behaviour_and_configuration(self):
        model = MagicMock()
        model.plan.return_value = result(action='respond', topic='general', reply='Hello! Tell me more.')
        direct, ui = self.agent(model), self.agent(model)
        session = BrowserSession(ui.backend, model, dialogue=ui)
        session.preferences(None, cloud=True)
        response = direct.respond(AgentRequest('direct', 'hello'))
        session.submit('hello')
        self.assertEqual(session.messages[-1]['text'], response.reply)
        self.assertEqual(session.dialogue.configuration(), direct.configuration())
        self.assertIs(session.dialogue, ui)

    def test_each_factory_call_has_fresh_private_state_and_no_proofs_enter_planner(self):
        model = MagicMock()
        first, second = self.agent(model), self.agent(model)
        for text in ('Order 12345678', '0042'):
            first.respond(AgentRequest('first', text))
        self.assertTrue(first.backend.state.verified)
        self.assertFalse(second.backend.state.verified)
        self.assertIsNot(first.backend.state, second.backend.state)
        model.plan.assert_not_called()
        model.plan.return_value = result(action='respond', topic='general', reply='You are welcome.')
        first.respond(AgentRequest('first', 'thanks'))
        self.assertNotIn('0042', model.plan.call_args.args[0].message)

    def test_factory_default_uses_runtime_retriever_without_loading_a_model_key(self):
        with patch('zentromart.application.build_public_index', return_value=fixtures.WorkflowTests.index) as build:
            agent = create_agent(load_settings(), MagicMock(), gateway=fixtures.FakeGateway())
        self.assertIsInstance(agent, LLMConversation)
        self.assertEqual(build.call_args.args[2], 'hybrid')

    def test_cli_chat_uses_shared_factory(self):
        from zentromart.__main__ import main
        model = MagicMock()
        model.plan.return_value = result(action='respond', topic='general', reply='Hello! Tell me more.')
        with patch('sys.argv', ['zentromart', 'chat', '--live', '--retriever', 'bm25']), \
             patch('zentromart.config.load_llm_settings', return_value=SETTINGS), \
             patch('zentromart.llm.GeminiModel', return_value=model), \
             patch('zentromart.retrieval.build_indexes', return_value={'bm25': fixtures.WorkflowTests.index}), \
             patch('zentromart.application.create_agent', side_effect=lambda *a, **kw: self.agent(model)) as factory, \
             patch('builtins.input', side_effect=['hello', '/quit']), patch('sys.stdout', new_callable=StringIO):
            main()
        factory.assert_called_once()
        model.plan.assert_called_once()

    def test_evaluation_support_uses_same_factory_with_fresh_agents(self):
        from zentromart.__main__ import main
        report = {'summary': {'error_rows': 0}}
        def evaluate(settings, **options):
            one, two = options['factory'](), options['factory']()
            self.assertIsInstance(one, LLMConversation)
            self.assertIsNot(one.backend.state, two.backend.state)
            self.assertEqual(options['agent_name'], 'shared_support_dialogue')
            return report
        with patch('sys.argv', ['zentromart', 'evaluate', '--agent', 'support', '--live',
                               '--retriever', 'bm25', '--max-cases', '1']), \
             patch('zentromart.config.load_llm_settings', return_value=SETTINGS), \
             patch('zentromart.llm.GeminiModel'), \
             patch('zentromart.retrieval.build_indexes', return_value={'bm25': fixtures.WorkflowTests.index}), \
             patch('zentromart.evaluation.runner.run_evaluation', side_effect=evaluate), \
             patch('zentromart.evaluation.runner.save_report', return_value='mock-report'), \
             patch('zentromart.evaluation.runner.format_summary', return_value='mock-summary'), \
             patch('sys.stdout', new_callable=StringIO), self.assertRaises(SystemExit) as stopped:
            main()
        self.assertEqual(stopped.exception.code, 0)
        self.assertIn('dialogue_version', report['agent_configuration'])
        self.assertEqual(report['pacing']['attempted_generations'], 0)
