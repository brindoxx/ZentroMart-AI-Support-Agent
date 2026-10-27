"""Stateless, text-only Gemini transport. No retrieval, private tables, or tools.

Structured output is a draft, not proof of grounding or an executor trace.
Only an explicit caller invokes the API; importing this module is offline.
"""

from copy import deepcopy
from dataclasses import dataclass, field
from importlib import import_module, metadata
import json
from time import perf_counter, sleep
from typing import Protocol

from .config import LLMSettings
from .contracts import DECISIONS


DRAFT_SCHEMA = {
    "type": "object",
    "properties": {
        "decision": {"type": "string", "enum": sorted(DECISIONS)},
        "reply": {"type": "string"},
        "language": {"type": "string", "enum": ["en", "hi", "hi-en"]},
        "evidence": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["decision", "reply", "language", "evidence"],
    "additionalProperties": False,
}
ERROR_MESSAGES = {
    "dependency_missing": "Install requirements-llm.txt to use the Gemini adapter.",
    "authentication": "Gemini rejected access. Check the local key and project permissions.",
    "quota": "Gemini quota was reached. Check AI Studio limits; no automatic quota retry was made.",
    "model_unavailable": "The configured Gemini model is unavailable to this endpoint or account. No substitute was used.",
    "request_rejected": "Gemini rejected the request. Check model capabilities and configuration.",
    "timeout": "The Gemini request timed out after the configured attempts.",
    "unavailable": "Gemini could not be reached or was temporarily unavailable.",
    "request_failed": "The Gemini adapter failed. No raw provider details were logged.",
    "blocked": "Gemini blocked the response. No draft was accepted.",
    "incomplete": "Gemini did not complete the response. No partial draft was accepted.",
    "invalid_response": "Gemini returned an invalid structured response. No draft was accepted.",
}


class ModelError(RuntimeError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(ERROR_MESSAGES[code])


@dataclass(frozen=True)
class ModelRequest:
    instructions: str = field(repr=False)
    message: str = field(repr=False)

    def __post_init__(self) -> None:
        if any(not isinstance(value, str) or not value.strip()
               for value in (self.instructions, self.message)):
            raise ValueError("Model instructions and message must be nonempty text")
        if len(self.instructions) + len(self.message) > 48000:
            raise ValueError("Model input exceeds the application's 48000-character budget")


@dataclass(frozen=True)
class ModelDraft:
    decision: str
    reply: str = field(repr=False)
    language: str
    evidence: tuple[str, ...]


@dataclass(frozen=True)
class ModelResult:
    draft: ModelDraft
    model_version: str | None
    attempts: int
    elapsed_seconds: float
    usage: dict[str, int | None]


class StructuredModel(Protocol):
    def generate(self, request: ModelRequest) -> ModelResult: ...


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON field")
        result[key] = value
    return result


def _invalid_constant(value):
    raise ValueError("Non-JSON numeric constant")


def parse_draft(text: str) -> ModelDraft:
    """Validate again locally; JSON syntax alone does not make a valid contract."""
    try:
        if not isinstance(text, str) or len(text) > 32000:
            raise ValueError
        value = json.loads(text, object_pairs_hook=_unique_object, parse_constant=_invalid_constant)
        if not isinstance(value, dict) or set(value) != set(DRAFT_SCHEMA["required"]):
            raise ValueError
        if not isinstance(value["decision"], str) or value["decision"] not in DECISIONS:
            raise ValueError
        if not isinstance(value["reply"], str) or not value["reply"].strip() or len(value["reply"]) > 8000:
            raise ValueError
        if value["language"] not in ("en", "hi", "hi-en"):
            raise ValueError
        evidence = value["evidence"]
        if not isinstance(evidence, list) or len(evidence) > 32 or any(
            not isinstance(item, str) or not item.strip() or len(item) > 200 for item in evidence
        ) or len(set(evidence)) != len(evidence):
            raise ValueError
        return ModelDraft(value["decision"], value["reply"], value["language"], tuple(evidence))
    except (ValueError, TypeError, RecursionError):
        raise ModelError("invalid_response") from None


def sdk_version() -> str | None:
    try:
        return metadata.version("google-genai")
    except metadata.PackageNotFoundError:
        return None


def _create_client(settings: LLMSettings):
    try:
        genai = import_module("google.genai")
    except ImportError:
        raise ModelError("dependency_missing") from None
    # Pin the destination; never infer Vertex, a custom gateway, or a key from SDK env vars.
    return genai.Client(
        api_key=settings.api_key, vertexai=False,
        http_options={"base_url": "https://generativelanguage.googleapis.com",
                      "api_version": "v1beta", "timeout": settings.timeout_seconds * 1000,
                      "retry_options": {"attempts": 1}},
    )


def _error_code(exc: Exception) -> str:
    code = getattr(exc, "code", None)
    if code in (401, 403):
        return "authentication"
    if code == 429:
        return "quota"
    if code == 404:
        return "model_unavailable"
    if code == 408 or isinstance(exc, TimeoutError):
        return "timeout"
    if code in (500, 502, 503, 504):
        return "unavailable"
    if type(code) is int and 400 <= code < 500:
        return "request_rejected"
    # httpx is an optional SDK dependency; core/offline callers never import it.
    try:
        httpx = import_module("httpx")
        if isinstance(exc, httpx.TimeoutException):
            return "timeout"
        if isinstance(exc, httpx.TransportError):
            return "unavailable"
    except ImportError:
        pass
    return "request_failed"


def _decode(response) -> tuple[ModelDraft, dict[str, int | None]]:
    feedback = getattr(response, "prompt_feedback", None)
    reason = getattr(feedback, "block_reason", None)
    if reason and getattr(reason, "value", reason) != "BLOCK_REASON_UNSPECIFIED":
        raise ModelError("blocked")
    candidates = getattr(response, "candidates", None)
    if not candidates or len(candidates) != 1:
        raise ModelError("invalid_response")
    candidate = candidates[0]
    reason = getattr(candidate, "finish_reason", None)
    reason = getattr(reason, "value", reason)
    if reason in {"SAFETY", "BLOCKLIST", "PROHIBITED_CONTENT", "SPII", "IMAGE_SAFETY", "RECITATION"}:
        raise ModelError("blocked")
    if reason != "STOP":
        raise ModelError("incomplete")
    parts = getattr(getattr(candidate, "content", None), "parts", None) or []
    text = []
    for part in parts:
        if getattr(part, "function_call", None) or getattr(part, "inline_data", None) or getattr(part, "executable_code", None):
            raise ModelError("invalid_response")
        if getattr(part, "thought", False):
            continue
        if not isinstance(getattr(part, "text", None), str):
            raise ModelError("invalid_response")
        text.append(part.text)
    draft = parse_draft("".join(text))
    metadata_value = getattr(response, "usage_metadata", None)
    usage = {}
    for name in ("prompt_token_count", "candidates_token_count", "thoughts_token_count", "total_token_count"):
        count = getattr(metadata_value, name, None)
        usage[name] = count if type(count) is int and count >= 0 else None
    return draft, usage


class GeminiModel:
    def __init__(self, settings: LLMSettings):
        settings.require_key()
        self.settings = settings

    def generate(self, request: ModelRequest) -> ModelResult:
        if not isinstance(request, ModelRequest):
            raise ValueError("Expected a validated ModelRequest")
        started = perf_counter()
        client = None
        try:
            client = _create_client(self.settings)
            for attempt in range(1, self.settings.retries + 2):
                try:
                    response = client.models.generate_content(
                        model=self.settings.model,
                        contents=[{"role": "user", "parts": [{"text": request.message}]}],
                        config={"system_instruction": request.instructions,
                                "response_mime_type": "application/json",
                                "response_json_schema": deepcopy(DRAFT_SCHEMA),
                                "max_output_tokens": self.settings.max_output_tokens,
                                "candidate_count": 1,
                                "thinking_config": {"thinking_level": "minimal"},
                                "automatic_function_calling": {"disable": True}},
                    )
                except Exception as exc:
                    code = _error_code(exc)
                    if code in {"timeout", "unavailable"} and attempt <= self.settings.retries:
                        sleep(2 ** (attempt - 1))
                        continue
                    raise ModelError(code) from None
                draft, usage = _decode(response)
                version = getattr(response, "model_version", None)
                return ModelResult(draft, version if isinstance(version, str) else None,
                                   attempt, round(perf_counter() - started, 3), usage)
        except ModelError:
            raise
        except Exception:
            raise ModelError("request_failed") from None
        finally:
            if client is not None:
                try:
                    client.close()
                except Exception:
                    pass  # Cleanup must not expose provider payloads or hide the result.


def check_model(settings: LLMSettings, *, live: bool = False) -> dict:
    report = {"provider": settings.provider, "model": settings.model,
              "key_present": bool(settings.api_key), "sdk_version": sdk_version(),
              "network_attempted": False, "timeout_seconds": settings.timeout_seconds,
              "max_output_tokens": settings.max_output_tokens, "retries": settings.retries}
    if not live:
        report["status"] = "configuration_only_not_a_live_test"
        return report
    request = ModelRequest(
        "This is a connection test, not customer support. Return decision clarify, reply ready, "
        "language en, and an empty evidence array. Do not use tools or add other fields.",
        "Run the connection test.",
    )
    result = GeminiModel(settings).generate(request)
    if result.draft != ModelDraft("clarify", "ready", "en", ()):
        raise ModelError("invalid_response")
    report.update(status="live_check_passed", network_attempted=True,
                  model_version=result.model_version, attempts=result.attempts,
                  elapsed_seconds=result.elapsed_seconds, usage=result.usage)
    return report
