# ZentroMart AI Support Agent

A multilingual customer support capstone for **ZentroMart**, the fictional Indian
retailer in the supplied From Tokens to Transformers dataset.

Built as part of IIT Guwahati Consulting & Analytics Club's From Tokens to
Transformers course.

## Current progress

**Phases 1–12 complete: multilingual Streamlit chat and verified mock support.**
The project supports BM25, local multilingual semantic search, and hybrid rank
fusion over policy sections and public product facts, with separate retrieval
evaluation. A deterministic layer now prioritizes policy authority and applies
scoped historical, festive, and marketplace exceptions to explicit scenario facts.
Gemini now generates public-policy replies with source-ID checks, safe
clarification fallbacks, and an opt-in memory-backed conversation mode. Verified
mock order lookup, deterministic calculations, and opt-in local handover tickets
are now available in a Streamlit-only frontend with English, Hindi, and Hinglish
reply preferences. Gnani WebSocket voice is implemented with offline tests;
live recording/playback verification is still pending.

The planned agent will answer from company policies, verify callers before
showing order details, create handover tickets, and support English, Hindi,
Hinglish, and Gnani voice input/output.

## Local setup (PowerShell)

Use Python 3.11 or newer. The initial setup was verified with Python 3.13.

```powershell
git clone https://github.com/brindoxx/ZentroMart-AI-Support-Agent.git
cd ZentroMart-AI-Support-Agent
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -m zentromart
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

The repository is currently private; cloning requires authorized GitHub access.
Activation of the virtual environment is optional: the commands above use its
Python executable directly. Phases 1–5 need no API keys, GPU, or cloud services.

## Inspect and validate the dataset

```powershell
.\.venv\Scripts\python.exe -m zentromart inspect
.\.venv\Scripts\python.exe -m zentromart inspect --json
.\.venv\Scripts\python.exe -m zentromart validate
```

Inspection shows schemas and aggregate counts without exposing customer rows or
practice answers. Validation runs the supplied deeper checks, including order
math, evidence references, and verification gates. Both commands return a
nonzero exit code on failure. See the [Phase 2 learning guide](docs/phase-02-understanding-the-data.md)
for table relationships, empty-cell interpretation, and examples.

## Run the evaluation baseline

```powershell
.\.venv\Scripts\python.exe -m zentromart evaluate
.\.venv\Scripts\python.exe -m zentromart evaluate --suite questions --asr
```

The default offline baseline runs 52 questions and 96 conversation turns. It always asks
for clarification; it tests the framework and is not a working support agent.
Redacted reports are saved in ignored `artifacts/evals/` run folders. Lexical
checks require manual review, and an evaluation exit code of zero is not a
quality pass. See the [Phase 3 learning guide](docs/phase-03-evaluating-the-agent.md)
for metric definitions, session handling, and limitations.

## Prepare the knowledge base

```powershell
.\.venv\Scripts\python.exe -m zentromart ingest
.\.venv\Scripts\python.exe -m zentromart ingest --section RET-2
```

Ingestion turns the 21 KB documents into 84 sections, retaining metadata,
document-level context, tables, source line ranges, and historical policies.
It reads only `kb/*.md` and writes UTF-8 JSONL plus a manifest in ignored
`artifacts/knowledge/` run folders. It does not yet perform search or embeddings.
See the [Phase 4 learning guide](docs/phase-04-preparing-the-knowledge-base.md)
for chunk examples and why preserving policy context matters.

## Search policies and public products

```powershell
.\.venv\Scripts\python.exe -m zentromart search "reverse pickup fee" --top-k 3
.\.venv\Scripts\python.exe -m zentromart search "ELE-0012" --json
.\.venv\Scripts\python.exe -m zentromart evaluate-retrieval
.\.venv\Scripts\python.exe -m zentromart evaluate-retrieval --asr
```

BM25 searches 84 policy/support sections and 70 public catalog rows. JSON results
include the passage, metadata, and matching-term contributions. Private customer
and order records are excluded. The initial Hit@5 is 80.9% across 47 practice
questions with gold evidence, falling to 70.2% for their ASR-style text; these
are retrieval results, not answer accuracy. Five no-gold questions are excluded
from these relevance metrics. See the [Phase 5 learning guide](docs/phase-05-keyword-search.md)
for scoring, measured recall, examples, and limitations.

## Add semantic and hybrid search

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-semantic.txt
.\.venv\Scripts\python.exe -m zentromart search "Nobody collected my return" --retriever semantic
.\.venv\Scripts\python.exe -m zentromart search "reverse pickup fee" --retriever hybrid
.\.venv\Scripts\python.exe -m zentromart compare-retrieval
```

The optional semantic extra runs pinned multilingual E5-small locally on the CPU.
Its first use downloads the model; document embeddings are cached under ignored
`artifacts/`. Add `--offline` after the initial download. `--rebuild-embeddings`
recomputes document vectors if a cache is damaged. Query embeddings are not
persisted. BM25 remains the default and needs none of these model dependencies.
See the [Phase 6 learning guide](docs/phase-06-semantic-and-hybrid-search.md)
for prefixes, cosine similarity, reciprocal rank fusion, caching, and comparison
methodology.

At top-K 5, original-question Hit@5 is 80.9% for BM25, 78.7% for semantic,
and 83.0% for hybrid. For ASR-style text it is 70.2%, 83.0%, and 78.7%, respectively.
These are development retrieval results across 47 gold-evidence questions,
not chatbot accuracy. The full comparison and limitations are in the Phase 6 guide.

## Prepare applicable policy evidence

```powershell
.\.venv\Scripts\python.exe -m zentromart policy-search "electronics return window" --topic return_window --category electronics --delivered-on 2026-07-31
.\.venv\Scripts\python.exe -m zentromart policy-search "fashion returns" --topic return_window --category fashion --placed-on 2026-10-15 --json
.\.venv\Scripts\python.exe -m zentromart policy-search "Assured warranty" --topic warranty --sku ELE-0004
```

The evidence bundle places governing policies above FAQs and marketing, excludes
superseded passages outside explicit exceptions, and flags missing scenario
context. Topic and dates are supplied explicitly: there is no automatic intent
extraction, identity verification, deadline calculation, or generated answer yet.
`--retriever semantic --offline` and `--retriever hybrid --offline` also work after
model installation. Raw `search` and retrieval metrics remain unchanged.
See the [Phase 7 learning guide](docs/phase-07-policy-precedence.md) for the rules,
source provenance, boundary examples, and limitations. Core BM25 policy handling
needs no API keys or model download.

## Configuration

`src/zentromart/config.py` loads `.env` from the repository root. Environment
variables override `.env` values. Relative paths resolve from the repository
root, so running commands from another folder does not change the dataset path.

| Setting | Default | Purpose |
| --- | --- | --- |
| `DATASET_DIR` | `dataset` | Supplied documents, tables, practice cases, and tools |
| `ARTIFACTS_DIR` | `artifacts` | Future generated indexes and evaluation results |
| `DATASET_REFERENCE_DATE` | `2026-10-20` | Frozen date used by dataset policy calculations |

A different reference date is rejected to prevent incorrect policy calculations.
The Gemini adapter reads the model variables separately, only when requested.
Gnani remains reserved for the voice phases. Never commit `.env` or real credentials.

## Check the Gemini connection (Phase 8)

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-llm.txt
.\.venv\Scripts\python.exe -m zentromart llm-check
.\.venv\Scripts\python.exe -m zentromart llm-check --live
```

Set `LLM_PROVIDER=gemini`, `LLM_MODEL=gemini-3.5-flash-lite`, and `LLM_API_KEY`
in the ignored local `.env` file. The first check only inspects configuration;
`--live` sends a small synthetic connection test to Google and consumes API quota.
No dataset or customer records are sent by this check. Model access and free-tier
quota depend on the Google project; a configuration check is not proof of access.

The adapter validates structured JSON, bounds input/output and request attempts,
disables automatic tool calling, and sanitizes provider failures. It does not
change the requested model or switch to a paid fallback. The evaluator still
uses its offline baseline: a model connection is not yet a grounded support agent.
Read the [Phase 8 learning guide](docs/phase-08-gemini-connection.md).

## Generate a grounded policy reply (Phase 9)

```powershell
.\.venv\Scripts\python.exe -m zentromart answer "Is pickup free for change-of-mind fashion returns?" --topic return_fee --live
.\.venv\Scripts\python.exe -m zentromart answer "Electronics return window?" --topic return_window --category electronics --delivered-on 2026-07-31 --live --json
.\.venv\Scripts\python.exe -m zentromart evaluate --agent gemini --live --suite questions --max-cases 6
```

`--live` explicitly allows sending the current question and selected public
passages to Gemini. `--language en`, `hi`, or `hi-en` can set reply language.
Typed scenario fields are not caller verification and are not automatically
extracted from the question. Missing context, unavailable applicable policies,
over-budget input, and invalid citations produce safe fallbacks; model/provider
errors remain errors. No history, private order table, or tools enter generation.

Gemini evaluation requires an explicit case cap and stops on the first agent
error. Reports retain scores, outcome counters, model/prompt/index configuration,
and token counts, but omit question/reply text and credentials. The six-case
development sample is not a full benchmark or proof of semantic correctness.
Read the [Phase 9 learning guide](docs/phase-09-grounded-replies.md) for measured
results, citation limitations, and examples. `--offline` only keeps optional
semantic embeddings offline; Gemini answering still needs the network.

## Keep follow-up context in memory (Phase 10)

```powershell
.\.venv\Scripts\python.exe -m zentromart chat --live
.\.venv\Scripts\python.exe -m zentromart evaluate --agent gemini-stateful --live --suite conversations --max-cases 6
```

In chat, try `How long do UPI refunds take?`, then `And cards?`. Use `/reset`
to clear the conversation and `/quit` to exit. For returns, the agent can collect
a category and an explicit `YYYY-MM-DD` date over separate turns. Narrow routing
and slot patterns are not general intent/entity understanding. Product, order,
and topic changes conservatively clear earlier scenario facts.

One agent owns one session. External history and remembered claims never verify
identity; no private order tools are connected yet. Up to four minimized customer
turns are used as context, with fresh retrieval each time. No assistant answers
become policy evidence, and the application writes no transcript. Memory
minimization is not comprehensive PII detection. `answer` and `--agent gemini`
remain stateless for comparison. See the [Phase 10 learning guide](docs/phase-10-conversation-state.md).

## Repository layout

```text
dataset/                 Supplied synthetic dataset and documentation
src/zentromart/          Python package and central configuration
tests/                   Configuration, data, evaluation, retrieval, and policy tests
docs/                    Phase-by-phase learning notes
evals/                   Evaluation usage and adapter guidance
report/                  Final report workspace
.env.example             Public configuration template
pyproject.toml           Package metadata and dependencies
requirements.txt         Complete app installation (UI, Gemini, voice)
requirements-core.txt    Lightweight offline data/retrieval installation
```

The supplied dataset is kept together so its relative imports and offline mock
tools continue to work. Its own README describes policy precedence, identity
verification, and evaluation evidence IDs. All customer records are synthetic.

## Verified support workflows (combined Phase 11)

```powershell
.\.venv\Scripts\python.exe -m zentromart chat --support --live
```

Ask about an order, supply its eight-digit ID, then provide one requested
four-digit phone suffix or six-digit delivery pincode. Use only synthetic dataset
examples. Two failed submissions lock that order for the session, even after
`/reset`. This educational mock verification is **not production authentication**.

After verification, `/items` lists item lines, `/item 1 1` selects line 1 and one
unit, and `/reason change_of_mind` explicitly classifies a proposed return.
`/policy QUESTION` clears private context and returns to general policy help.
`/quit` exits. Private facts and proofs are never sent to Gemini; its connection
is available only for public-policy questions. Private-workflow replies now use
fixed English, Hindi, and Hinglish translations; `--language hi` or
`--language hi-en` explicitly selects the CLI reply language.

Ticket writing is disabled by default. Add `--write-tickets` to allow **local mock**
tickets under ignored `artifacts/tickets/`; this does not contact a real support
team. The assistant cannot cancel an order, approve a claim, or pay a refund.
Calculations are conditional estimates against the frozen 2026-10-20 snapshot.
See the [Phase 11 learning guide](docs/phase-11-verified-support-workflows.md).

## Streamlit frontend (Phase 12)

From the repository root:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-ui.txt
.\.venv\Scripts\python.exe -m streamlit run streamlit_app.py
```

Open `http://127.0.0.1:8501`. The app binds to the local computer, not your network.
Choose English, Hindi, or Hinglish in the sidebar. Synthetic order verification
works without Gemini; proofs use a masked form, are cleared after submission,
and never appear in the displayed history. Only public policies/catalog and
holidays are shared in a cache; each browser tab owns its agent and private state.

Gemini is **off by default**. Enable the public-policy checkbox when you want model
answers; it uses the existing local `.env` key unless a server-side Streamlit
`[llm]` secret is configured, never a key pasted into chat. Public
questions and bounded public context may then leave the device. The UI allows at
most 20 generation attempts per session (bounded provider retries are separate),
and pauses model access after a provider/configuration failure. Private workflows
remain available. Clearing the conversation does not reset call limits or
verification lockouts.

Local ticket creation is a separate, default-off checkbox. Tickets remain mock
CSV records, not real human contact. Chat history is session-only, limited to
the most recent 24 messages, with no transcript export or disk saving. Voice,
hosting, and production authentication are not part of this local UI.

The native theme uses Streamlit configuration, not a separate frontend framework
or injected CSS. See the [Phase 12 learning guide](docs/phase-12-streamlit-and-languages.md)
for the design, language rules, tests, and limitations.

## Guided demos and optional voice

Enable **Use guided demo orders** to see four invented tutorial scenarios and
their public test credentials. They use a separate gateway, not private rows
from the supplied dataset. Start an example, enter its displayed test suffix in
the masked form, and ask the suggested follow-up. Verification is not bypassed.
Demo tickets, when explicitly enabled, go to `artifacts/demo-tickets/`.

With **Use Gemini for natural conversation** enabled, Gemini understands the
request and writes greetings and follow-up questions. This is not a separate
hardcoded script for every item or intent. Grounded policy answers still use
retrieved company evidence; verified order facts and calculations stay in the
backend. With Gemini off, the existing local/offline workflows remain available.
Reply captions distinguish model-written conversation, model-assisted routing,
Gemini-generated policy answers, local workflows, and safe
fallbacks. Inline citation brackets are moved into the source panel for display;
the backend still retains and evaluates the original evidence IDs.

Planning and answering share the existing 20-generation session budget; a public
policy answer normally needs two generations. Clearing chat or switching demo
mode does not renew the budget. See [LLM-led conversation](docs/llm-led-conversation.md)
for the architecture, examples, safety boundaries and test coverage. Existing CLI
and evaluation modes retain their previous behavior for baseline comparisons.

For voice, install `requirements-voice.txt`, restart Streamlit, and enable
**Gnani voice**. Your existing `GNANI_API_KEY` in `.env` is read only when needed.
In dictation mode, record at most 15 seconds, click transcribe, review/edit the
transcript, then send it. Reading the latest reply aloud is a separate explicit
action in that mode. Both use Gnani credits; dictation does not automatically
submit or play replies. The optional voice-conversation mode below automates those
steps after explicit activation. Voice is disabled
during verification; type proofs in the masked form. Selected replies sent to TTS
may contain verified order details, as disclosed by the voice consent control.

There are 20 voice attempts per browser session, 800 characters per spoken reply,
no automatic retries, and no transcript/audio files saved by the voice adapter.
Clear/source/language changes discard pending audio and drafts, not usage limits.
The adapter is covered by simulated-service tests. A live TTS attempt on 28 October
timed out during connection, so successful live voice output is **not validated**.
Microphone capture and Gnani synthesis are separate: recorder errors can happen
before any Gnani request. The voice panel now includes microphone help/reset,
a strictly validated WAV-upload alternative, and an explicit speech playback test.
See the [Phase 13 guide and five-minute demo](docs/phase-13-voice-and-guided-demo.md).

### Voice conversation versus dictation

The mic/dictation path keeps **transcribe -> review -> Send**. For an automatic
conversation, enable Gemini and Gnani, then click **Start voice conversation**.
Record and stop a turn: the app runs **STT -> support assistant -> TTS** and
requests audio playback without extra transcribe/send/speak clicks. Record again
for the next turn; End restores typing. Browser autoplay may require Play.

This mode is turn-based, not continuous listening, full-duplex audio or barge-in.
It pauses for typed verification and shares the existing provider budgets.
Automatic sending and speaking require explicit mode activation. See the
[voice-conversation guide](docs/voice-conversation.md) for design, privacy,
failure recovery, costs, tests and the remaining live-service limitations.

### Review-driven fixes

The [review audit](docs/review-fixes.md) records each confirmed issue, correction,
and regression test, including findings that were not reproducible as reported.
Return help now asks about the item and relevant dates rather than requesting
policy-selection fields. Missing local voice keys and bad clips are recoverable;
service failures have an explicit retry button that preserves usage limits.

The distribution name is now `zentromart-ai-support-agent`. The existing local
checkout folder may still use the historical `ZetroMart` spelling; imports use
`zentromart`, and no repository/checkout move is required. The UI dependency range
allows Streamlit 1.x updates; behavior is currently verified on 1.66.1.

## Remaining roadmap

The former 11 remaining phases are consolidated into five larger phases, leaving
more time to test and improve each part:

| Phase | Scope | Status |
| --- | --- | --- |
| 11 (old 11–13) | Verified order workflows, handover tickets, deterministic calculations | Complete |
| 12 (old 14–15) | Multilingual replies and Streamlit web interface | Complete |
| 13 (old 16–17) | Gnani speech input/output and voice workflow | Implemented; live check pending |
| 14 (old 18–19) | Expanded evaluation, failure analysis, and improvements | Next |
| 15 (old 20–21) | Deployment, report, demonstration, and release preparation | Planned |

Phases 1–10 remain documented separately in `docs/`. The repository stays private
until the user chooses to publish it.

Keep service credentials, generated conversation records, and ticket files out
of this repository and the report. `.gitignore` excludes local credentials,
virtual environments, generated artifacts, and mock ticket output.
