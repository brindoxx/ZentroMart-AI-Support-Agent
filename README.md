# ZentroMart AI Support Agent

A text and voice support assistant for ZentroMart, the fictional Indian retailer
in the IIT Guwahati Consulting & Analytics Club x Gnani.ai capstone. It combines
Gemini conversation planning, document-grounded answers, verified synthetic
order lookups and Gnani speech recognition and synthesis.

This is a local educational application, not a production service. Tickets are
local mock records, not messages to a real team. The agent cannot issue refunds
or cancel orders. See [submission readiness](report/README.md) for outstanding
requirements; the application is not yet a complete submission.

## What it does

- Discuss delivery, returns, refunds, cancellations, warranty and public products.
- Retrieve company sources and show supporting policy sections.
- Ask natural follow-up questions using bounded conversation context.
- Verify an order before revealing synthetic records or calculated estimates.
- Follow English, Hindi and Hinglish, including changes within a conversation.
- Accept typed messages, editable dictation or an automatic voice conversation.
- Create local handover tickets when enabled and confirmed by the actual tool.

## Install and run

Use Python 3.11 or newer; development has used Python 3.13. In PowerShell:

```powershell
git clone https://github.com/brindoxx/ZentroMart-AI-Support-Agent.git
cd ZentroMart-AI-Support-Agent
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Cloning requires access while the repository is private. Do not overwrite an
existing `.env`. Add Gemini and Gnani keys there, never in chat or Git.

Obtain the course dataset separately. Its extracted directory must contain
`kb/`, `data/`, `practice/` and `tools/`. Set `DATASET_DIR` to that location;
the local default is `dataset`. Its supplied documentation defines the schema.

```powershell
.\.venv\Scripts\python.exe -m zentromart validate
.\.venv\Scripts\python.exe -m streamlit run streamlit_app.py
```

Open `http://127.0.0.1:8501`. Restart the server after changing ASGI/WebSocket
routes. The current relay deliberately accepts local origins only; public
hosting needs a separate deployment/security review.

## Using the assistant

Confirm the one-time in-chat cloud-processing notice before starting. Confirmation
alone does not record audio or call a provider.

- **Text:** type and press Send or Enter.
- **Mic:** completed Gnani phrases appear in the input. Stop, edit if needed and
  Send. Dictation alone does not call Gemini.
- **Voice:** speak and pause. The same agent answers, Gnani TTS plays its reply,
  and listening resumes after playback. Click the voice button again to stop.
- **Order help:** enter the synthetic eight-digit order ID, then the requested
  phone suffix or pincode in the masked field. Voice pauses for verification.
  Never speak verification proofs.
- **Demo options:** guided synthetic orders provide tutorial credentials. Mock
  ticket creation is a separate opt-in and does not contact a human team.

Reply language follows the current message without a selector. Gemini chooses
language in its existing dialogue request; private steps use local language cues,
and numeric proofs preserve the current language. TTS uses the reply language.
Mixed Hindi/English STT may return Roman script, so language choice depends on
the actual transcript.

Gnani provides completed phrases after pauses, not per-word interim text. Voice
is sequential: listening stops during playback; interruption/barge-in is not
implemented. The user reported a successful live loop; this is not a repeatable
multi-language reliability benchmark.

## Architecture

```text
Text -----------------------------------------+
Mic -> local WebSocket relay -> Gnani STT -----+-> BrowserSession
                                                      |
                                               LLMConversation
                                                      |
                    +---------------------------------+-------------------+
                    |                                 |                   |
             Gemini dialogue                   Public-policy RAG   Private workflows
             and clarification                 retrieval + Gemini  verification, tools
                    |                                 |            and calculations
                    +---------------------------------+-------------------+
                                                      |
                                               Written response
                                                      |
                                           Gnani TTS in voice mode
```

Gemini proposes a structured next step; application code validates and dispatches
it. The model cannot authorize verification or invent executor results. Verified
order records and proofs do not enter its dialogue prompt. Verified synthetic
details can appear in replies sent to Gnani TTS, as disclosed before chat starts.

### Retrieval and policy

Ingestion preserves section IDs, source locations, status and effective dates.
Current policies take precedence over agent guides, help, FAQs and marketing,
with scoped historical, festive and marketplace exceptions. Historical support
logs are not policy authority.

**The main UI defaults to hybrid BM25 + multilingual E5-small retrieval.**
Document embeddings use a local NumPy cosine-search index; reciprocal-rank fusion
combines lexical and semantic results. The public index and encoder are cached
across reruns, while conversation state remains per tab. CPU encoder access is
serialized. Set `RETRIEVER=bm25` or `semantic` explicitly to compare methods;
missing vector dependencies/cache cause a setup error, not silent fallback.
Restart the app after changing retrieval configuration.

Optional local experiments support `EMBEDDING_MODEL=e5-small` or `bge-m3`, and
`RERANKER=none` or `mmarco-minilm`. Models use pinned revisions, CPU inference,
model-specific prefixes/pooling and separate vector caches. BGE-M3's publisher
checkpoint is loaded with PyTorch >=2.6 in explicit weights-only mode; remote
Python code is disabled. The reranker scores only the top 20 public candidates;
policy authority and date applicability are still enforced afterwards.

```powershell
.\.venv\Scripts\python.exe -m zentromart.evaluation.retrieval_experiment --models e5-small bge-m3 --offline --rerank
```

The experiment compares top-5/top-20 text and supplied ASR-like queries, records
per-language metrics and warm latency, and makes no Gemini/Gnani calls. Remove
`--offline` only when a model download is intended. Model downloads/warm-up are
excluded from warm query latency. Candidate reranking must earn its additional
latency; it is not assumed to improve quality. NumPy's exact cosine scores are
also checked against an independent SciPy calculation, not a FAISS benchmark.

Calculations use **20 October 2026**, the dataset reference date. Business days
are Monday-Saturday excluding supplied holidays; return windows use calendar days.

## Configuration

Environment variables override `.env`. Relative paths resolve from the project
root. The UI can also read a server-side Streamlit `[llm]` secret containing
`provider`, `model` and `api_key`.

| Variable | Purpose |
| --- | --- |
| `DATASET_DIR` | Extracted course dataset; default `dataset` |
| `ARTIFACTS_DIR` | Generated indexes, evaluations and tickets; default `artifacts` |
| `RETRIEVER` | `hybrid` (default), `semantic`, or explicitly selected `bm25` |
| `RETRIEVAL_OFFLINE` | `true` uses only an already-downloaded encoder; default `false` |
| `EMBEDDING_MODEL` | `e5-small` or `bge-m3`; see the experiment results before switching |
| `RERANKER` | `none` or optional `mmarco-minilm` cross-encoder |
| `DATASET_REFERENCE_DATE` | Must remain `2026-10-20` |
| `LLM_PROVIDER` | `gemini` |
| `LLM_MODEL` | Explicit Gemini model ID; see the key-free example configuration |
| `LLM_API_KEY` | Gemini key; access and quota depend on the account |
| `LLM_TIMEOUT_SECONDS` | Timeout; default 20 seconds |
| `LLM_MAX_OUTPUT_TOKENS` | Output budget; default 1024 |
| `LLM_RETRIES` | Bounded transient-failure retries; default 1 |
| `GNANI_API_KEY` | Key for both Gnani STT and TTS |

No model or speech provider is silently substituted. Gnani is the only speech
provider; no browser Web Speech fallback is used.

## Diagnostics and tests

```powershell
# Offline inspection, validation and configuration check
.\.venv\Scripts\python.exe -m zentromart inspect --json
.\.venv\Scripts\python.exe -m zentromart validate
.\.venv\Scripts\python.exe -m zentromart llm-check

# Synthetic live check; consumes Gemini quota
.\.venv\Scripts\python.exe -m zentromart llm-check --live

# Retrieval without generation
.\.venv\Scripts\python.exe -m zentromart search "reverse pickup fee" --top-k 5

# Optional semantic/hybrid retrieval and comparison
.\.venv\Scripts\python.exe -m pip install -r requirements-semantic.txt
.\.venv\Scripts\python.exe -m zentromart compare-retrieval

# Offline regression tests
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
node tests/composer_frontend.mjs
```

Node.js is needed only for the frontend logic test, not the app. Semantic search
downloads its pinned encoder on first use. After download, `--offline` prevents
encoder downloads; it does not make Gemini offline. For dataset/BM25 work only,
install `requirements-core.txt`. Other requirements files select model, UI,
speech or semantic extras.

The UI, voice, CLI `chat` and `evaluate --agent support` use the same
`application.create_agent` factory and LLM-led controller. Public retrieval is
reused; every conversation gets fresh memory, verification and tool state.
`chat --support` remains a compatibility alias. CLI `answer`, `gemini` and
`gemini-stateful` evaluation adapters are explicit diagnostic/ablation modes.
See [evaluation](evals/README.md) for commands and quota controls.

The evaluation-only `prompt-only` adapter calls Gemini without documents or tools.
`compare-answers` compares it with stateless RAG on identical questions and model
settings. Full `support` evaluation measures the conversational agent separately.
A full 52-question live comparison is recorded in [measured results](evals/results.md):
decision agreement improved from 32.7% to 48.1%, and lexical required-fact
coverage from 12.2% to 38.8%. These are separate diagnostics, not overall answer
accuracy or scores for the full conversation agent. Eight RAG citation fallbacks
remain an improvement target. Additional live runs consume project quota.

## Privacy, limits and known limitations

- Use only synthetic data and consented recordings.
- Each browser tab owns its chat, verified state and budgets.
- Displayed chat is bounded to 24 messages; the UI saves no transcript/audio export.
- Planning and answering share 20 generation attempts per browser session.
  A policy question normally needs planning plus grounded generation.
- Speech has a separate 20-attempt session budget, 15-second captures and
  an 800-character limit per spoken reply.
- Clearing chat does not reset provider budgets or verification lockouts.
- Model failures currently pause further calls behind a generic warning.
  Category-specific errors and explicit model recovery controls remain unfinished.
  Failed voice turns are not automatically resubmitted.
- Verification and text minimization are educational safeguards, not production
  authentication or comprehensive PII protection.
- Citation-ID validation does not prove the cited passage entails the answer.

## Repository and submission

| Path | Contents |
| --- | --- |
| `streamlit_app.py`, `chat_app.py` | ASGI launcher and primary UI |
| `src/zentromart/` | Dialogue, retrieval, policy, tools, calculations and speech |
| `tests/` | Offline unit, integration, UI and browser-logic checks |
| `evals/` | Evaluation instructions and limitations |
| `report/` | Requirement audit and report/demo preparation |
| `.env.example` | Key-free configuration template |
| `legacy_streamlit_app.py` | Older interface retained for regression tests only |

Learning notes, credentials, environments, caches and runtime artifacts are
ignored by Git. Supplied dataset documents are unchanged. Submission still needs
an audio-folder batch command, sample outputs, a maximum four-page report,
a maximum two-minute demo and a public repository. Exclude secrets, environments
and a dataset copy from the submission ZIP; external dataset setup and packaging
still require a clean-environment check.
