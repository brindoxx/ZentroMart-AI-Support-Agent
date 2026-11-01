"""Final conversation regressions with controlled model adapters, never paid calls."""
import json
import unittest
from unittest.mock import MagicMock, patch
from zentromart.calculations import BusinessCalendar
from zentromart.config import PROJECT_ROOT, FROZEN_REFERENCE_DATE
from zentromart.contracts import AgentRequest
from zentromart.dialogue import LLMConversation
from zentromart.grounding import GroundedAgent
from zentromart.llm import ModelDraft, ModelResult, ModelError
from zentromart.policy import PolicyContext
from zentromart.presentation import disclose_ai, prepare_speech
from zentromart.retrieval import BM25Index, load_search_documents
from zentromart.web_session import BrowserSession, ConsentModel, VALIDATION_NOTES
from zentromart.workflows import SupportAgent
from test_dialogue import result
from test_workflows import FakeGateway


def draft(reply, evidence=(), language='en'):
    return ModelResult(ModelDraft('answer', reply, language, evidence), 'test', 1, 0.1,
                       {'prompt_token_count': 10, 'total_token_count': 15})


class CompletionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.index = BM25Index(load_search_documents(PROJECT_ROOT / 'dataset'))
        cls.calendar = BusinessCalendar.load(PROJECT_ROOT / 'dataset')

    def agent(self, *plans):
        model = MagicMock()
        model.plan.side_effect = list(plans)
        backend = SupportAgent(self.index, model, FROZEN_REFERENCE_DATE,
                               calendar=self.calendar, gateway=FakeGateway())
        return LLMConversation(backend, model), model

    def turn(self, agent, text):
        return agent.respond(AgentRequest('demo', text))

    def test_exact_reported_exchange_context_repair_and_real_executor_ticket(self):
        agent, model = self.agent(
            result(action='respond', topic='general', reply='Hello! How can I help?'),
            result(action='clarify', topic='damage', reply='Could you tell me what item arrived damaged?'),
            result(action='search', topic='pickup', reply=''))
        model.generate.side_effect = [draft('Pickup is free. [FAKE-1]', ('FAKE-1',)),
            draft('For verified damage claims, no reverse pickup fee applies. [DWM-2]', ('DWM-2',))]
        agent.backend.allow_ticket_writes = True
        with patch.object(agent.backend.public.engine, 'assemble', wraps=agent.backend.public.engine.assemble) as assemble:
            greeting = self.turn(agent, 'hello')
            self.turn(agent, 'what is the return for this for a damaged product')
            pickup = self.turn(agent, 'do i need to pay for the pickup or')
        self.assertIn('AI support assistant', greeting.reply)
        self.assertEqual(pickup.evidence, ('DWM-2',))
        self.assertNotIn('FAKE-1', pickup.reply)
        self.assertEqual(agent.last_trace.reason, 'citation_repaired')
        self.assertEqual(agent.last_trace.model_attempts, 2)
        self.assertEqual(agent.last_trace.prompt_token_count, 20)
        self.assertTrue(any('damaged product' in call.args[0] and 'pickup or' in call.args[0]
                            for call in assemble.call_args_list))
        self.assertIn('damaged product', model.generate.call_args.args[0].message)
        self.assertNotIn('FAKE-1', model.generate.call_args.args[0].message)
        handover = self.turn(agent, 'i request for a human support')
        self.assertIn('TKT12345678', handover.reply)
        self.assertEqual(len(agent.backend.gateway.tickets), 1)
        self.assertEqual(model.plan.call_count, 3)

    def test_disclosure_once_and_after_explicit_clear(self):
        agent, model = self.agent(result(action='respond', topic='general', reply='Hello!'),
                                  result(action='respond', topic='general', reply='You are welcome.'),
                                  result(action='respond', topic='general', reply='Hello again!'))
        self.assertIn('AI support assistant', self.turn(agent, 'hi').reply)
        self.assertNotIn('AI support assistant', self.turn(agent, 'thanks').reply)
        agent.reset()
        self.assertIn('AI support assistant', self.turn(agent, 'hi again').reply)
        self.assertEqual(model.plan.call_count, 3)

    def test_context_omission_retains_claims_but_new_subject_drops_them(self):
        agent, _ = self.agent(result(topic='damage', category='electronics', delivered_on='2026-10-19', reply='What happened?'),
                              result(topic='pickup', reply='What else should I check?'),
                              result(topic='return_window', category='fashion', new_subject=True, reply='When did you place that order?'))
        self.turn(agent, 'My headphones arrived damaged yesterday')
        self.turn(agent, 'what about pickup')
        self.assertEqual(agent.context.category, 'electronics')
        self.assertEqual(agent.context.delivered_on.isoformat(), '2026-10-19')
        self.turn(agent, 'A different item, a blouse')
        self.assertEqual(agent.context.category, 'fashion')
        self.assertIsNone(agent.context.delivered_on)
        self.assertNotIn('headphones', '\n'.join(agent.history))

    def grounded(self, model, enabled=True):
        return GroundedAgent(self.index, model, FROZEN_REFERENCE_DATE,
                             context=PolicyContext('damage'), repair_citations=enabled)

    def test_still_invalid_second_draft_stays_blocked_with_no_third_call(self):
        model = MagicMock()
        model.generate.return_value = draft('False. [FAKE]', ('FAKE',))
        agent = self.grounded(model)
        answer = self.turn(agent, 'Damage pickup fee?')
        self.assertEqual(model.generate.call_count, 2)
        self.assertEqual(agent.last_trace.reason, 'citation_mismatch')
        self.assertEqual(answer.evidence, ())
        self.assertNotIn('False', answer.reply)
        self.assertIn('human review', answer.reply)

    def test_valid_first_answer_uses_one_call(self):
        model = MagicMock()
        model.generate.return_value = draft('No reverse pickup fee for verified damage. [DWM-2]', ('DWM-2',))
        agent = self.grounded(model)
        self.turn(agent, 'Damage pickup fee?')
        self.assertEqual(model.generate.call_count, 1)
        self.assertIsNone(agent.last_trace.reason)

    def test_unsafe_claim_or_wrong_language_does_not_trigger_repair(self):
        for value in (draft('I have approved your refund. [FAKE]', ('FAKE',)),
                      draft('निःशुल्क। [FAKE]', ('FAKE',), 'hi')):
            model = MagicMock()
            model.generate.return_value = value
            agent = GroundedAgent(self.index, model, FROZEN_REFERENCE_DATE,
                context=PolicyContext('damage'), reply_language='en', repair_citations=True)
            answer = self.turn(agent, 'Damage policy?')
            self.assertEqual(model.generate.call_count, 1)
            self.assertEqual(answer.evidence, ())

    def test_transport_error_never_triggers_citation_repair(self):
        model = MagicMock()
        model.generate.side_effect = ModelError('quota')
        with self.assertRaises(ModelError):
            self.turn(self.grounded(model), 'Damage policy?')
        self.assertEqual(model.generate.call_count, 1)

    def test_public_context_does_not_cross_into_new_private_history(self):
        agent, model = self.agent(result(topic='damage', reply='Which item?'))
        self.turn(agent, 'My private item description')
        self.turn(agent, 'Order 12345678')
        self.turn(agent, '0042')
        self.assertEqual(list(agent.history), [])
        self.assertTrue(agent.backend.state.verified)
        self.assertEqual(model.plan.call_count, 1)

    def test_web_diagnostic_is_safe_and_disclosure_applies_to_local_first_reply(self):
        agent, model = self.agent(result(action='search', topic='damage', reply=''))
        model.generate.return_value = draft('Unaccepted. [FAKE]', ('FAKE',))
        consent = ConsentModel()
        session = BrowserSession(agent.backend, consent, dialogue=LLMConversation(agent.backend, consent))
        session.preferences(None, cloud=True)
        consent._client = model
        session.submit('What is the damage policy?')
        saved = session.messages[-1]
        self.assertIn('Source references did not match', saved['diagnostic'])
        self.assertIn('AI support assistant', saved['text'])
        self.assertNotIn('FAKE', json.dumps(session.messages))
        self.assertIsNone(VALIDATION_NOTES.get('SECRET_PROVIDER_PAYLOAD'))

    def test_speech_dates_ids_preserve_amounts_and_do_not_guess_years(self):
        text = 'Order ID 81000001 arrives on 2026-10-22. INR 1,499. [DEL-1]'
        spoken = prepare_speech(text, 'en')
        self.assertIn('8100 0001', spoken)
        self.assertIn('22 October 2026', spoken)
        self.assertIn('INR 1,499', spoken)
        self.assertNotIn('[DEL-1]', spoken)
        self.assertEqual(text, 'Order ID 81000001 arrives on 2026-10-22. INR 1,499. [DEL-1]')
        self.assertEqual(prepare_speech('15 October; PIN 001234; INR 12345678', 'en'),
                         '15 October; PIN 001234; INR 12345678')
        self.assertIn('अक्टूबर 2026', prepare_speech('2026-10-22', 'hi'))
        self.assertEqual(prepare_speech(spoken, 'en'), spoken)
