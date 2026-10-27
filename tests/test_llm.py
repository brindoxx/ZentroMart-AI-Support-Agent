"""Model transport regression tests. Fake clients only; no network or user keys."""

from contextlib import redirect_stdout
from dataclasses import replace
from io import StringIO
import json
import os
from pathlib import Path
from types import SimpleNamespace as NS
import unittest
from unittest.mock import MagicMock, patch

from zentromart.config import LLMSettings, load_llm_settings, load_settings
from zentromart.llm import (
    GeminiModel, ModelDraft, ModelError, ModelRequest, _create_client, check_model, parse_draft,
)


SETTINGS = LLMSettings("gemini", "gemini-3.5-flash-lite", "synthetic-test-key")
REQUEST = ModelRequest("Trusted application instructions", "Synthetic customer text")
VALID = {"decision": "clarify", "reply": "ready", "language": "en", "evidence": []}


def response(value=None, *, reason="STOP", parts=None, feedback=None):
    if parts is None:
        parts = [NS(text=json.dumps(VALID if value is None else value), thought=False)]
    return NS(candidates=[NS(finish_reason=reason, content=NS(parts=parts))],
              prompt_feedback=feedback, model_version="gemini-3.5-flash-lite",
              usage_metadata=NS(prompt_token_count=12, candidates_token_count=8,
                                thoughts_token_count=None, total_token_count=20))


class ProviderFailure(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__("synthetic-private-payload-and-key")


class LLMConfigurationTests(unittest.TestCase):
    def test_environment_overrides_dotenv_without_mutating_it(self):
        values = {"LLM_PROVIDER": "gemini", "LLM_MODEL": SETTINGS.model, "LLM_API_KEY": "file-key"}
        with patch("zentromart.config.dotenv_values", return_value=values), patch.dict(
            os.environ, {"LLM_API_KEY": "environment-key"}, clear=True
        ):
            config = load_llm_settings(Path("."))
            self.assertEqual(config.api_key, "environment-key")
            self.assertEqual(values["LLM_API_KEY"], "file-key")
            self.assertNotIn("environment-key", repr(config))

    def test_missing_key_is_allowed_for_inspection_but_not_generation(self):
        settings = replace(SETTINGS, api_key="")
        self.assertFalse(check_model(settings)["key_present"])
        with self.assertRaisesRegex(ValueError, "LLM_API_KEY"), patch("zentromart.llm._create_client") as create:
            GeminiModel(settings)
        create.assert_not_called()

    def test_invalid_configuration_fails_without_echoing_values(self):
        for update in ({"provider": "other"}, {"model": "https://untrusted.example"},
                       {"timeout_seconds": 0}, {"timeout_seconds": True}, {"max_output_tokens": 9000},
                       {"retries": 3}, {"api_key": "synthetic key"}):
            with self.subTest(update=update), self.assertRaises(ValueError):
                replace(SETTINGS, **update)
        with patch("zentromart.config.dotenv_values", return_value={
            "LLM_PROVIDER": "gemini", "LLM_MODEL": SETTINGS.model, "LLM_TIMEOUT_SECONDS": "private-value"
        }), patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ValueError) as raised:
                load_llm_settings()
            self.assertNotIn("private-value", str(raised.exception))

    def test_existing_offline_configuration_ignores_bad_model_configuration(self):
        with patch("zentromart.config.dotenv_values", return_value={"LLM_PROVIDER": "not-implemented"}), patch.dict(
            os.environ, {}, clear=True
        ):
            self.assertEqual(load_settings().reference_date.isoformat(), "2026-10-20")


class DraftTests(unittest.TestCase):
    def test_valid_languages_and_evidence_round_trip_without_repr_text(self):
        for language in ("en", "hi", "hi-en"):
            draft = parse_draft(json.dumps({**VALID, "language": language, "evidence": ["RET-2"]}))
            self.assertEqual(draft.evidence, ("RET-2",))
            self.assertNotIn("ready", repr(draft))
        self.assertNotIn(REQUEST.message, repr(REQUEST))

    def test_bad_fields_types_and_invented_tool_traces_are_rejected(self):
        invalid = [[], {"decision": "answer"}, {**VALID, "decision": []}, {**VALID, "reply": " "},
                   {**VALID, "reply": 42}, {**VALID, "language": "unknown"},
                   {**VALID, "evidence": "RET-2"}, {**VALID, "evidence": [1]},
                   {**VALID, "evidence": ["RET-2", "RET-2"]}, {**VALID, "tool_calls": []}]
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(ModelError) as raised:
                parse_draft(json.dumps(value))
            self.assertEqual(raised.exception.code, "invalid_response")

    def test_non_json_duplicates_and_nonfinite_constants_are_rejected(self):
        for text in ("not JSON", "```json\n{}\n```", '{"decision":"clarify","decision":"answer"}',
                     json.dumps(VALID).replace('"ready"', 'NaN'), "x" * 32001):
            with self.subTest(text=text[:40]), self.assertRaises(ModelError):
                parse_draft(text)

    def test_inputs_are_bounded_not_silently_truncated(self):
        for instructions, message in (("", "hello"), ("rules", " "), ("rules", "x" * 48000)):
            with self.assertRaises(ValueError):
                ModelRequest(instructions, message)


class GeminiTransportTests(unittest.TestCase):
    def client(self, value=None):
        client = MagicMock()
        client.models.generate_content.return_value = response() if value is None else value
        return client

    def test_configuration_check_never_creates_a_client_or_imports_sdk(self):
        with patch("zentromart.llm._create_client") as create, patch("zentromart.llm.import_module") as imports:
            report = check_model(SETTINGS)
        create.assert_not_called()
        imports.assert_not_called()
        self.assertFalse(report["network_attempted"])
        self.assertNotIn(SETTINGS.api_key, json.dumps(report))

    def test_client_pins_google_endpoint_timeout_and_disables_sdk_retries(self):
        module = MagicMock()
        with patch("zentromart.llm.import_module", return_value=module):
            _create_client(SETTINGS)
        kwargs = module.Client.call_args.kwargs
        self.assertFalse(kwargs["vertexai"])
        self.assertEqual(kwargs["http_options"]["base_url"], "https://generativelanguage.googleapis.com")
        self.assertEqual(kwargs["http_options"]["timeout"], 20000)
        self.assertEqual(kwargs["http_options"]["retry_options"]["attempts"], 1)

    def test_optional_dependency_missing_is_a_safe_error(self):
        with patch("zentromart.llm.import_module", side_effect=ImportError("private-details")):
            with self.assertRaises(ModelError) as raised:
                _create_client(SETTINGS)
        self.assertEqual(raised.exception.code, "dependency_missing")
        self.assertNotIn("private-details", str(raised.exception))

    def test_valid_request_uses_separate_system_and_user_text_and_no_tools(self):
        client = self.client()
        with patch("zentromart.llm._create_client", return_value=client):
            result = GeminiModel(SETTINGS).generate(REQUEST)
        kwargs = client.models.generate_content.call_args.kwargs
        self.assertEqual(kwargs["model"], SETTINGS.model)
        self.assertEqual(kwargs["contents"][0]["role"], "user")
        self.assertEqual(kwargs["config"]["system_instruction"], REQUEST.instructions)
        self.assertEqual(kwargs["config"]["response_mime_type"], "application/json")
        self.assertTrue(kwargs["config"]["automatic_function_calling"]["disable"])
        self.assertNotIn("tools", kwargs["config"])
        self.assertEqual(result.draft, ModelDraft("clarify", "ready", "en", ()))
        self.assertEqual(result.usage["prompt_token_count"], 12)
        client.close.assert_called_once()

    def test_transient_failure_retries_with_the_same_model_and_then_succeeds(self):
        client = self.client()
        client.models.generate_content.side_effect = [ProviderFailure(503), response()]
        with patch("zentromart.llm._create_client", return_value=client), patch("zentromart.llm.sleep") as wait:
            result = GeminiModel(SETTINGS).generate(REQUEST)
        self.assertEqual(result.attempts, 2)
        wait.assert_called_once_with(1)
        self.assertEqual({call.kwargs["model"] for call in client.models.generate_content.call_args_list}, {SETTINGS.model})

    def test_auth_quota_not_found_and_bad_requests_are_not_retried(self):
        for status, code in ((401, "authentication"), (403, "authentication"), (429, "quota"),
                             (404, "model_unavailable"), (400, "request_rejected")):
            with self.subTest(status=status):
                client = self.client()
                client.models.generate_content.side_effect = ProviderFailure(status)
                with patch("zentromart.llm._create_client", return_value=client), patch("zentromart.llm.sleep") as wait:
                    with self.assertRaises(ModelError) as raised:
                        GeminiModel(SETTINGS).generate(REQUEST)
                self.assertEqual(raised.exception.code, code)
                self.assertNotIn("synthetic-private", str(raised.exception))
                self.assertEqual(client.models.generate_content.call_count, 1)
                wait.assert_not_called()
                client.close.assert_called_once()

    def test_timeout_attempts_are_bounded_and_safe(self):
        client = self.client()
        client.models.generate_content.side_effect = TimeoutError("private-message")
        with patch("zentromart.llm._create_client", return_value=client), patch("zentromart.llm.sleep"):
            with self.assertRaises(ModelError) as raised:
                GeminiModel(SETTINGS).generate(REQUEST)
        self.assertEqual(raised.exception.code, "timeout")
        self.assertEqual(client.models.generate_content.call_count, 2)
        self.assertNotIn("private-message", str(raised.exception))

    def test_incomplete_blocked_and_unexpected_tool_outputs_never_become_drafts(self):
        invalid = [
            (response(reason="MAX_TOKENS"), "incomplete"),
            (response(reason="SAFETY"), "blocked"),
            (response(feedback=NS(block_reason="SAFETY")), "blocked"),
            (NS(candidates=[]), "invalid_response"),
            (response(parts=[NS(text=json.dumps(VALID), function_call=NS(name="create_ticket"))]), "invalid_response"),
            (response(parts=[NS(text="hidden reasoning", thought=True)]), "invalid_response"),
        ]
        for value, code in invalid:
            with self.subTest(code=code):
                client = self.client(value)
                with patch("zentromart.llm._create_client", return_value=client):
                    with self.assertRaises(ModelError) as raised:
                        GeminiModel(SETTINGS).generate(REQUEST)
                self.assertEqual(raised.exception.code, code)
                self.assertEqual(client.models.generate_content.call_count, 1)

    def test_thought_parts_are_not_returned_and_missing_usage_is_unknown(self):
        value = response(parts=[NS(text="private reasoning", thought=True), NS(text=json.dumps(VALID))])
        value.usage_metadata = None
        client = self.client(value)
        with patch("zentromart.llm._create_client", return_value=client):
            result = GeminiModel(SETTINGS).generate(REQUEST)
        self.assertEqual(result.draft.reply, "ready")
        self.assertTrue(all(count is None for count in result.usage.values()))

    def test_client_creation_and_cleanup_errors_do_not_leak_details(self):
        with patch("zentromart.llm._create_client", side_effect=RuntimeError("private-key")):
            with self.assertRaises(ModelError) as raised:
                GeminiModel(SETTINGS).generate(REQUEST)
        self.assertNotIn("private-key", str(raised.exception))
        client = self.client()
        client.close.side_effect = RuntimeError("private-cleanup")
        with patch("zentromart.llm._create_client", return_value=client):
            self.assertEqual(GeminiModel(SETTINGS).generate(REQUEST).draft.reply, "ready")

    def test_live_probe_checks_content_but_only_returns_metadata(self):
        client = self.client()
        with patch("zentromart.llm._create_client", return_value=client):
            report = check_model(SETTINGS, live=True)
        self.assertEqual(report["status"], "live_check_passed")
        self.assertTrue(report["network_attempted"])
        self.assertNotIn("reply", report)
        self.assertNotIn(SETTINGS.api_key, json.dumps(report))

    def test_cli_dry_check_does_not_validate_or_load_the_dataset(self):
        from zentromart.__main__ import main
        stream = StringIO()
        with patch("sys.argv", ["zentromart", "llm-check"]), patch(
            "zentromart.config.load_llm_settings", return_value=SETTINGS
        ), patch("zentromart.__main__.load_settings", side_effect=AssertionError("Unexpected dataset load")), patch(
            "zentromart.llm._create_client", side_effect=AssertionError("Unexpected API call")
        ), redirect_stdout(stream):
            main()
        self.assertFalse(json.loads(stream.getvalue())["network_attempted"])


if __name__ == "__main__":
    unittest.main()
