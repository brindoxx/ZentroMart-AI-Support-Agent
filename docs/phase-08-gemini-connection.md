# Phase 8: connect Gemini without giving it control of the application

## What this phase is for

We have already built search and policy evidence preparation. We now need a
language model that can eventually explain that evidence to a customer.
You selected `gemini-3.5-flash-lite`; the adapter preserves that exact model ID.

This phase builds the connection and validates its output format. It deliberately
does not connect the model to policy retrieval, order lookup, ticket creation,
or the evaluation agent yet. Those boundaries let us test one responsibility
at a time. Phase 9 will build the grounded answering workflow.

The model is hosted by Google. Unlike the local E5 embedding encoder from
Phase 6, Gemini generation sends the supplied text over the network and consumes
your account's API allowance. A free-tier listing does not guarantee a particular
account's quota, access, or availability.

## 1. Local configuration and an optional dependency

`requirements-llm.txt` installs the optional `llm` extra, using the official
`google-genai` SDK. The core package still needs only its original dependency;
offline search, inspection, and unit-test imports do not require this SDK.

The private `.env` file belongs in the repository root, next to `pyproject.toml`.
Its public template is `.env.example`. Configure:

```dotenv
LLM_PROVIDER=gemini
LLM_MODEL=gemini-3.5-flash-lite
LLM_API_KEY=your_key_goes_here
LLM_TIMEOUT_SECONDS=20
LLM_MAX_OUTPUT_TOKENS=1024
LLM_RETRIES=1
```

The key shown above is a placeholder, not a usable credential. Never put a real
key in documentation, screenshots, commits, or chat. `.env` is ignored by Git.
Environment variables override file values, without the loader modifying the
process environment. Model settings are loaded separately so an invalid or
missing model configuration does not break an offline dataset command.

The key is excluded from the settings object's representation. Requests and
reply text are also excluded from their dataclass representations. This reduces
accidental disclosure; it is not encryption or a substitute for safe logging.

## 2. Two checks with different meanings

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-llm.txt
.\.venv\Scripts\python.exe -m zentromart llm-check
.\.venv\Scripts\python.exe -m zentromart llm-check --live
```

Without `--live`, the command prints configuration, key presence, SDK version,
and limits. It creates no SDK client and makes no network request. Seeing
`key_present: true` proves only that a value was supplied, not that it is valid.

With `--live`, the command sends a fixed, synthetic connection test. The model
must return a specific small JSON object. The command validates that object and
prints only status, model metadata, timing, attempts, and token counts—not the
key, prompt, raw response, or hidden reasoning. It reads no dataset tables and
uploads no corpus. It does not create a persistent chat or upload a file.

This test consumes quota. The application cannot determine whether your Google
project has billing enabled; use a free-tier project if zero spend is required.
There is no automatic paid-plan upgrade, fallback model, or provider switch.

## 3. A structured draft instead of arbitrary text

`ModelRequest` separates application-owned instructions from the user message.
They are sent as separate system and user fields; customer text cannot directly
become the system instruction through the adapter interface. This separation
helps establish trust boundaries but does not alone solve prompt injection.

The model is asked for a JSON object with exactly four fields:

```json
{
  "decision": "clarify",
  "reply": "ready",
  "language": "en",
  "evidence": []
}
```

The decision must be `answer`, `clarify`, `escalate`, or `refuse`. Language must
be `en`, `hi`, or `hi-en`. Evidence is a list of text IDs, not full documents.
The SDK request supplies a JSON Schema, and our parser validates the returned
JSON again. Extra fields, missing fields, wrong types, blank replies, duplicate
keys, duplicate evidence IDs, and malformed JSON are rejected.

Why validate twice? A provider's structured-output feature helps with shape,
but the application must still own its contract and handle abnormal responses.
Incomplete generation and safety-blocked responses never become accepted drafts.

This format does not prove that the content is true. An evidence ID can have
the right type while pointing to a nonexistent or inapplicable source. Phase 9
must check IDs against the supplied evidence and assess answer grounding.

`ModelDraft` is not an executor-confirmed `AgentResponse`. There is no
`tool_calls` field in the schema, and automatic function calling is disabled.
A model-written claim that it created a ticket would not establish that an
action happened. Only later application-owned tools can provide that proof.

## 4. Keep requests bounded and failures understandable

The adapter uses Google's fixed Gemini Developer API endpoint, not an arbitrary
URL from a customer message or an inferred Vertex project. It uses the SDK's
`models.generate_content` method with JSON output and minimal thinking for the
chosen model. No search, code execution, tools, uploads, or persistent chat are
enabled.

Input is capped at 48,000 characters across instructions and message; over-budget
requests fail instead of silently losing important policy text. Characters are
not tokens, so this is an application safety bound, not an exact quota estimate.
Output defaults to 1,024 tokens, configurable from 128 to 4,096. Thinking can
consume part of a model's output budget, so hitting the limit is an error to
handle—not a reason to accept partial JSON.

Each HTTP attempt has a default 20-second timeout, configurable from 1 to 60.
`LLM_RETRIES=1` permits one additional generation attempt after a timeout or a
temporary server/transport failure. SDK retries are disabled to avoid multiplying
attempts across two retry loops. Backoff is bounded; retries keep the same model.
Timeout is per attempt, not a hard total duration for the whole operation.

Authentication errors, quota errors, missing models, rejected requests, malformed
outputs, and blocked responses are not retried. In particular, `429` may mean a
daily allowance is exhausted, so blindly retrying could waste requests. A timeout
can occur after Google processed a request; a retry may consume more allowance.

Provider failures become short, static error codes/messages. Raw provider error
bodies, request text, headers, and keys are not logged by this application.
SDK clients are closed after use. Token counts are retained when supplied;
missing usage remains null rather than pretending the request used zero tokens.

There is no local persistence of generation requests, raw responses, or thought
text. This is not a claim of zero retention by Google. Review the provider's
free-tier data-use terms before sending anything beyond synthetic project data.

## Verification status

On 27 October 2026, the real `llm-check --live` succeeded with the requested and
reported model both `gemini-3.5-flash-lite`, using Google Gen AI SDK 1.75.0.
It completed on the first attempt in 7.837 seconds, reporting 42 prompt tokens,
34 candidate tokens, and 76 total tokens. Thought-token count was not supplied
and remains null. This is one connection sample, not a latency benchmark.

All 90 automated tests passed, including 20 model configuration/transport tests.
The installed SDK also accepted the generation/timeout/retry configuration in
an offline validation check. Dependency and supplied dataset validation passed.
The model check sent only the fixed synthetic probe and wrote no response file.

Live success proves this key could call this model at that time. It does not
establish the account's billing tier, remaining quota, multilingual answer
quality, policy accuracy, or future availability.

## Read the implementation and what follows

1. `config.py`: separate, secret-safe `LLMSettings` and loader.
2. `llm.py`: request/draft contracts, parser, Gemini adapter, safe probe.
3. `__main__.py`: explicit `llm-check` and `--live` entry point.
4. `tests/test_llm.py`: fake-provider regressions without user keys or API calls.

Phase 9 will combine query, policy context, and selected evidence into a grounded
prompt, validate citations, and connect the result to our agent/evaluation
contracts. The current clarification baseline and retrieval scores are unchanged.

## Official references

- [Google Gen AI Python SDK](https://googleapis.github.io/python-genai/):
  `generate_content`, JSON schemas, client configuration, and cleanup.
- [Gemini structured outputs](https://ai.google.dev/gemini-api/docs/structured-output):
  structured response support and its limits.
- [Gemini thinking](https://ai.google.dev/gemini-api/docs/thinking): thinking levels
  and output-token budgeting.
- [Gemini API rate limits](https://ai.google.dev/gemini-api/docs/rate-limits) and
  [pricing/data use](https://ai.google.dev/gemini-api/docs/pricing): account-dependent
  quota and the distinction between a free tier and unlimited usage.
