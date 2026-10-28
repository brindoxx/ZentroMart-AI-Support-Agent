# Evaluation workspace

Run the framework from the repository root:

```powershell
.\.venv\Scripts\python.exe -m zentromart evaluate
.\.venv\Scripts\python.exe -m zentromart evaluate --suite questions --asr
.\.venv\Scripts\python.exe -m zentromart evaluate --suite conversations
```

The default CLI uses a deliberately unskilled clarification baseline to test the
framework. It makes no model or tool calls. A poor baseline score is expected and does not
represent our future agent. `--asr` replaces single-question inputs with the
provided ASR-style text; it does not run speech recognition. With the default
`--suite all`, conversation inputs remain their original text.

Implementation lives in `src/zentromart/evaluation/`; shared agent inputs and
outputs live in `src/zentromart/contracts.py`. Future Python adapters can pass a
factory to `run_evaluation(settings, factory=YourAgent, agent_name="your-agent")`.
The CLI defaults to `--agent baseline`; the opt-in `--agent gemini` adapter is
described below.

Each run creates `artifacts/evals/<UTC-timestamp>-<unique-id>/report.json`. Reports
include per-case scores, aggregate metrics with denominators, suite summaries,
timings, the fixed dataset date, and a SHA-256 dataset fingerprint. They exclude
customer messages, replies, history, reference answers, verification values,
tool arguments, and exception messages. Generated artifacts remain ignored by Git.

Practice labels stay inside the evaluator. Never import this module into the
retrieval index or use the practice reference answers as agent context.

Read `docs/phase-03-evaluating-the-agent.md` for metric definitions, limitations,
session behavior, and the next implementation steps.

## Retrieval-only baseline (Phase 5)

```powershell
.\.venv\Scripts\python.exe -m zentromart evaluate-retrieval --top-k 5
.\.venv\Scripts\python.exe -m zentromart evaluate-retrieval --top-k 5 --asr
```

This evaluates BM25 over policy sections and public product rows, without
generating replies or claiming decision/tool accuracy. All 52 single questions
run; 47 with gold evidence contribute to Hit@K, Recall@K, and truncated MRR.
Reports include per-language summaries, ranked public IDs, settings, and corpus/
practice fingerprints. They exclude raw questions and reference answers.

The initial original-text Hit@5 is 38/47 (80.9%); ASR-text Hit@5 is 33/47 (70.2%).
Read `docs/phase-05-keyword-search.md` for full metrics and the fixed baseline's
limitations. Generated reports use the same ignored `artifacts/evals/` area,
with `run_kind: retrieval_evaluation` to distinguish them from agent runs.

## Semantic and hybrid comparison (Phase 6)

Install `requirements-semantic.txt`, then run:

```powershell
.\.venv\Scripts\python.exe -m zentromart evaluate-retrieval --retriever semantic
.\.venv\Scripts\python.exe -m zentromart evaluate-retrieval --retriever hybrid --asr
.\.venv\Scripts\python.exe -m zentromart compare-retrieval
```

The comparison uses BM25, cosine retrieval with pinned multilingual E5-small,
and equal-weight reciprocal rank fusion. Each method runs on original and
ASR-style text at the same top-K. Six individual reports and one aggregate report
are saved. The same document vectors and model instance are shared during a
comparison; gold labels never enter the retrievers. Model download and passage
encoding happen before measured per-question search latency.

Reports retain encoder/package revisions, prefixes, length limit, corpus and
practice hashes, fusion settings, and cache status. Read
`docs/phase-06-semantic-and-hybrid-search.md` for interpretation and limitations.

Measured Hit@5 on original questions: BM25 80.9%, semantic 78.7%, hybrid 83.0%.
On ASR-style text: BM25 70.2%, semantic 83.0%, hybrid 78.7%. All methods share
47 scored questions per variant. The guide includes Recall@5 and MRR; no method
wins every metric or input variant.

## Policy regression scenarios (Phase 7)

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_policy.py -v
```

These source-grounded unit tests cover precedence, historical/festive date
boundaries, marketplace exclusions, missing context, and evidence provenance.
They use controlled rankings over the public corpus, without evaluation labels
or model downloads. They are not a new chatbot-accuracy or retrieval benchmark.
`policy-search` can attach explicit topic anchors and policy dependencies, so its
bundle may exceed top-K; these attached passages must not count as raw retrieval
hits. Existing Phase 5/6 metrics continue to measure the unmodified retrievers.

## Model transport checks (Phase 8)

`tests/test_llm.py` uses fake Gemini clients to exercise configuration, schema
validation, bounded retries, blocked/incomplete outputs, safe failures, and the
no-network default check. Tests do not consume API quota or load local keys.
`python -m zentromart llm-check --live` is a separate synthetic integration check,
not a customer-answer benchmark. Phase 8 left the evaluator on its offline
baseline; Phase 9 adds the opt-in adapter below. Do not interpret transport success as policy
accuracy or an end-to-end agent score.

## Grounded Gemini adapter (Phase 9)

```powershell
.\.venv\Scripts\python.exe -m zentromart evaluate --agent gemini --live --suite questions --max-cases 6
```

Both `--live` and a positive `--max-cases` are required. Selection is a deterministic
prefix in session/turn order, not a curated list of successes. A cap may stop
mid-conversation. `planned_rows`, `available_rows`, the cap, attempted rows, and
early-stop status are recorded. The `gemini` adapter remains stateless and cannot
use private tools, so conversation/tool metrics are not readiness claims.

The first agent error stops this CLI run; failed rows stay in the report, and
unattempted cases do not masquerade as completed ones. Deterministic citation or
missing-context fallbacks are completed responses, with separate `grounding_outcomes`
counters. Per-row traces contain only fixed outcomes/reasons and token counts.
Provider errors have no raw payloads; their messages are not saved.

Reports include a whitelisted `agent_configuration` with requested model, SDK,
prompt version/hash, policy rule version, corpus/index settings, timeout, output
budget, and retries. No key is included. Actual raw retrieval IDs remain separate
from attached policy evidence, so anchors do not inflate retrieval metrics.

An accepted citation means an ID belonged to the supplied bundle and matched
the reply's bracketed references. It is not an entailment check. Likewise,
gold-ID precision and lexical fact coverage are diagnostics requiring review,
not a universal accuracy score. Initial six-case results and limitations are in
`docs/phase-09-grounded-replies.md`.

## Conversation state (Phase 10)

```powershell
.\.venv\Scripts\python.exe -m zentromart evaluate --agent gemini-stateful --live --suite conversations --max-cases 6
```

The new opt-in adapter owns its memory rather than accepting `AgentRequest.history`
as authoritative replay. The existing factory creates a fresh agent for each
conversation. One instance rejects a different session ID until reset. A bounded
customer-only memory window supports follow-ups; no assistant reply or claimed
verification becomes evidence or permission for private tools.

Reports record the conversation version, memory-prompt hash, memory limits,
no-verification status, index/model settings, and redacted grounding counters.
They do not save memory, slots, claimed order IDs, prompts, or replies. Unknown
or ambiguous slot values trigger clarification without a model call. The same
case cap and stop-on-first-error rules apply. Typed/runtime scenario context
changes the retrieval query for short follow-ups, so keep stateful and stateless
results separate; these are different agent configurations.

Phase 10's live verification used a synthetic six-turn sequence with only three
generation calls; it was not a scored run of the supplied conversation suite.
Its results and remaining parser/answer-quality limitations are documented in
`docs/phase-10-conversation-state.md`.

## Verified mock workflows (combined Phase 11)

```powershell
.\.venv\Scripts\python.exe -m zentromart evaluate --agent support --live --suite conversations --max-cases 6
```

The support adapter creates fresh workflow state for each session. It executes
verification, private rendering, arithmetic, and handover routing in application
code; the model receives public-policy questions only. `--live` acknowledges that
public fallback may use Gemini, even when a particular run makes no model calls.
Use a positive case cap; stop-on-error protections still apply.

Ticket writes are disabled by default. Only add `--write-tickets` deliberately:
it appends local mock tickets to ignored `artifacts/tickets/tickets_created.csv`.
It does not contact a real human team. A correct escalation decision may still
miss the expected ticket tool call when writes are disabled; report both metrics.

Tool correctness uses executor-recorded calls, not model assertions. Arguments
are inspected transiently but omitted from saved reports, along with verification
proofs, raw messages, private order payloads, and replies. Configuration records
policy/calendar hashes and the write flag. Do not print or serialize raw traces.

At the end of Phase 11, the six-turn development-prefix run completed without errors: decisions
6/6, expected tool calls 5/6 (ticket writes disabled), declared language 0/6,
and required-fact lexical coverage 60% over five applicable rows. Private replies
were English in that phase; Phase 12 adds multilingual rendering. Gold citation
precision was 25%, recall 38.9%; these require improvement/review, not a claim of
fully correct answers. Private flows perform no retrieval, so their zero raw
retrieval hits are not a regression in BM25. This repeatedly inspected prefix is
development evidence, not a held-out benchmark. See the Phase 11 learning guide
for the routing fix, tests, and limitations.

## Multilingual frontend checks (Phase 12)

Install `requirements-ui.txt`, then run the existing full unittest command.
The suite includes native `streamlit.testing.v1.AppTest` interactions: offline
startup, disabled cloud consent, masked proof submission/clearing, language
switching, lockout after clearing, and separate browser-session state. AppTest
does not verify browser layout, scrolling, or rendered font quality. No server
or paid API call is needed for these checks.

The same six-turn development prefix was rerun with a model stub that raises on
any generation call. All six rows completed without errors: decisions 6/6,
declared language 6/6, tools 5/6 with writes disabled, lexical fact coverage 60%
over five applicable rows, citation precision 25%, recall 38.9%. This shows the
new local language path works on that inspected sample; it does not establish
general translation or answer accuracy. Report ID: `20261028T051015Z-1e5d1503`.
It preceded the version-label bump to support/conversation v2; localization v1
and the tested behavior are unchanged by that label-only bump.

The 198-test suite includes 20 new Phase 12 tests. Fixed template tests check
placeholders in Hindi and Hinglish; public Gemini paths are tested with model
stubs, not fresh live API calls. Fluent-speaker review, wider Hinglish/Hindi
wording, citation improvement, voice/ASR, and held-out evaluation remain future
work. Do not compare declared-language match to semantic translation accuracy.
