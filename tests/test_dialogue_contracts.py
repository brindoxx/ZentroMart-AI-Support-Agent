"""Strict model proposals and transport, without making API calls."""

import json
import unittest
from unittest.mock import MagicMock, patch

from zentromart.dialogue_contracts import PLAN_SCHEMA, parse_plan
from zentromart.llm import GeminiModel, ModelError
import test_llm as transport_tests


def proposal(**changes):
    return {"action": "clarify", "topic": "return_window", "category": None, "sku": None,
            "placed_on": None, "delivered_on": None, "reply": "What would you like to send back?",
            "language": "en", "new_subject": False, **changes}


class DialogueContractTests(unittest.TestCase):
    def test_model_cannot_propose_verification_or_executable_tools(self):
        for change in ({"verified": True}, {"action": "lookup_order"}, {"action": "approve_refund"},
                       {"topic": "invented"}, {"category": "unknown"}, {"new_subject": "false"}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                parse_plan(json.dumps(proposal(**change)))

    def test_dates_sku_schema_and_wording_are_validated(self):
        valid = parse_plan(json.dumps(proposal(category="fashion", placed_on="2026-10-10")))
        self.assertEqual(valid.category, "fashion")
        self.assertNotIn("send back", repr(valid))
        for change in ({"placed_on": "2026-11-01"}, {"placed_on": "2026-02-30"},
                       {"placed_on": "2026-10-15", "delivered_on": "2026-10-10"},
                       {"sku": "PRIVATE-ORDER"}, {"reply": ""}, {"reply": "x" * 1201}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                parse_plan(json.dumps(proposal(**change)))
        with self.assertRaises(ValueError):
            parse_plan(json.dumps(proposal())[:-1] + ',"action":"search"}')

    def test_plan_transport_uses_its_schema_and_still_disables_function_execution(self):
        response = transport_tests.response()
        response.candidates[0].content.parts[0].text = json.dumps(proposal())
        client = MagicMock()
        client.models.generate_content.return_value = response
        with patch("zentromart.llm._create_client", return_value=client):
            result = GeminiModel(transport_tests.SETTINGS).plan(transport_tests.REQUEST)
        self.assertEqual(result.draft.action, "clarify")
        configuration = client.models.generate_content.call_args.kwargs["config"]
        self.assertEqual(configuration["response_json_schema"], PLAN_SCHEMA)
        self.assertTrue(configuration["automatic_function_calling"]["disable"])
        client.close.assert_called_once()

    def test_malformed_plan_is_rejected_by_the_transport(self):
        from unittest.mock import MagicMock
        client = MagicMock()
        response = transport_tests.response()
        response.candidates[0].content.parts[0].text = '{"verified":true}'
        client.models.generate_content.return_value = response
        with patch("zentromart.llm._create_client", return_value=client), self.assertRaises(ModelError):
            GeminiModel(transport_tests.SETTINGS).plan(transport_tests.REQUEST)
