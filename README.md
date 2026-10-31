# ZentroMart AI Support Agent

A text and voice support assistant for ZentroMart, the fictional Indian retailer
in the IIT Guwahati Consulting & Analytics Club x Gnani.ai capstone. It combines
Gemini conversation planning, document-grounded answers, verified synthetic
order lookups and Gnani speech recognition and synthesis.

This is a local educational application, not a production service. Tickets are
local mock records, not messages to a real team. The agent cannot issue refunds
or cancel orders. See [submission readiness](report/README.md) for outstanding
requirements; the application is not yet a complete submission.

## Evaluator overview

| Area | Current implementation / evidence |
| --- | --- |
| Interface and orchestration | Streamlit with a shared custom Python support controller; text, dictation and voice use the same agent factory |
| Conversation and generation | Gemini structured dialogue planning and document-grounded generation |
| Selected retrieval | BM25 + BGE-M3 dense embeddings, reciprocal-rank fusion, exact NumPy cosine search; no cross-encoder by default |
| Voice | Gnani STT and TTS through a local WebSocket relay; sequential listening and playback |
| Dataset validation | 9 CSVs, 21 KB documents, 1,000 synthetic orders, 1,783 order items and 244 historical logs |
| Practice evaluation | 52 questions and 23 conversations / 96 customer turns available; completed experiments below cover questions, not a full conversation benchmark |
| Regression checks | 309 Python tests passed; frontend composer checks and dataset validation passed on 31 October 2026 |
| Remaining deliverables | Audio-folder runner and saved sample outputs; report, demo and clean submission package |

The measured experiments answer different questions: **does document grounding
help Gemini?** and **which retriever should the app use?** Their scores must not
be combined into an overall accuracy claim. See [measured results](#measured-results).

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

```mermaid
flowchart TD
    T[Typed message] --> UI[Streamlit chat]
    M[Mic: dictate] --> RELAY[Local WebSocket relay]
    V[Voice conversation] --> RELAY
    RELAY --> STT[Gnani speech to text]
    STT --> MODE{Input mode}
    MODE -->|Dictation: edit then send| UI
    MODE -->|Voice: submit completed turn| UI
    UI --> SESSION[Per-tab BrowserSession]
    SESSION --> CTRL[Shared support controller]
    CTRL -->|Public conversation| PLAN[Gemini dialogue planner]
    PLAN --> VALIDATE[Validate proposed next step]
    VALIDATE --> CHAT[Conversation or clarification]
    VALIDATE --> RAG[Public-policy retrieval and grounded Gemini answer]
    VALIDATE --> PRIVATE[Backend order workflow]
    CTRL -->|Verification and active private steps| PRIVATE
    PRIVATE --> CHECK[Local verification, mock tools and calculations]
    CHAT --> OUT[Text reply]
    RAG --> GUARD[Citation and evidence-ID checks]
    GUARD -->|Accepted answer or safe fallback| OUT
    CHECK --> OUT
    OUT --> DISPLAY[Display reply and available sources]
    OUT -->|Voice mode only| TTS[Gnani text to speech]
    TTS --> PLAY[Play reply]
    PLAY -->|Resume listening until stopped| RELAY
```

GitHub renders these Mermaid blocks as diagrams. Dictation only prepares text;
it does not call Gemini until the message is sent. Voice mode submits a completed
speech turn and speaks the resulting reply. Verification/private workflow steps
can be handled locally, so not every turn makes a Gemini request.

Gemini proposes a structured next step; application code validates and dispatches
it. The model cannot authorize verification or invent executor results. Verified
order records and proofs do not enter its dialogue prompt. Verified synthetic
details can appear in replies sent to Gnani TTS, as disclosed before chat starts.

### Retrieval and policy

Ingestion preserves section IDs, source locations, status and effective dates.
Current policies take precedence over agent guides, help, FAQs and marketing,
with scoped historical, festive and marketplace exceptions. Historical support
logs are not policy authority.

**The main UI defaults to hybrid BM25 + BGE-M3 dense retrieval, without reranking.**
Document embeddings use a local NumPy cosine-search index; reciprocal-rank fusion
combines lexical and semantic results. The public index and encoder are cached
across reruns, while conversation state remains per tab. CPU encoder access is
serialized. Set `RETRIEVER=bm25` or `semantic` explicitly to compare methods;
missing vector dependencies/cache cause a setup error, not silent fallback.
Restart the app after changing retrieval configuration.

```mermaid
flowchart LR
    DOCS[Public KB sections and catalog] --> META[Preserve IDs, dates and source metadata]
    META --> LEX[BM25 lexical index]
    META --> EMB[BGE-M3 dense encoder]
    EMB --> VEC[Cached normalized vectors]
    Q[Public search query] --> LEX
    Q --> QE[BGE-M3 query embedding]
    QE --> COS[Exact cosine search]
    VEC --> COS
    LEX --> RRF[Reciprocal-rank fusion]
    COS --> RRF
    RRF --> POLICY[Policy authority and applicability checks]
    POLICY --> EVID[Selected evidence bundle]
    EVID --> GEN[Gemini grounded generation]
    GEN --> SAFE[Citation checks and safe fallback]
    SAFE --> REPLY[Reply with source references]
    RRF -.-> EXP[Optional top-20 cross-encoder: tested, disabled]
```

This is the selected public-policy path, not a diagram of private order lookup.
Gold evaluation labels and historical support logs are not policy authority.

The measured choice and its limitations are in [retrieval experiments](evals/retrieval-experiments.md).
E5-small remains a lower-latency alternative. Local experiments support `EMBEDDING_MODEL=e5-small` or `bge-m3`, and
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
| `EMBEDDING_MODEL` | `bge-m3` (default) or lower-latency `e5-small` |
| `RERANKER` | `none` (default); optional `mmarco-minilm` regressed in the measured trial |
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
Additional live runs consume project quota; the results below are already measured.

## Measured results

Measured on **31 October 2026**, using the supplied practice set. These are
development-set results, not an unseen-test benchmark. There is no validated
single overall accuracy score, and unit-test counts are not answer-quality scores.

### 1. Prompt-only Gemini versus document-grounded RAG

Both arms used the same 52 original-text questions and requested
`gemini-3.5-flash-lite` model, with a 1024-token output budget. The RAG arm used
**E5-small**, not the subsequently selected BGE-M3 encoder. This stateless
experiment does not score the full UI conversation controller or voice pipeline.

| Metric | Prompt-only Gemini | E5 hybrid RAG | What is measured |
| --- | --- | --- | --- |
| Decision agreement | 32.7% (17/52) | 48.1% (25/52) | Whether answer / clarify / refuse / escalate matches an allowed action |
| Required-fact lexical coverage | 12.2% | 38.8% | Mean matching required facts across 49 applicable questions; not semantic correctness |
| Declared language agreement | 86.5% (45/52) | 94.2% (49/52) | Returned language label, not independent fluency review |
| Retrieval Hit@5 | 0% (no retrieval) | 83.0% (39/47) | At least one expected source among five results |
| Retrieval Recall@5 | 0% | 55.7% | Mean expected-source coverage across 47 gold-evidence cases |
| Citation precision | N/A | 76.7% | Mean expected-ID precision across 35 responses containing citations |
| Citation recall | 0% | 39.4% | Mean expected-source coverage across 47 cases |

- Both arms completed 52/52; **104 generation attempts**, zero provider/adapter errors.
- RAG returned 44 accepted generated answers and **8 citation-mismatch safe fallbacks**.
  These are grounding failures, not network failures; they remain an improvement target.
- No forbidden-claim lexical hits occurred in the eight labelled cases. This small
  lexical check is not a general safety guarantee.
- Calls were paced at five-second intervals, with a 250,000-input-TPM guard and
  no automatic provider retries. This does not control other clients' quota usage.

Decision agreement checks the action, not every claim. Lexical coverage can miss
valid paraphrases or accept misleading wording. Citation-ID matches do not prove
that the cited passage supports the answer. See the [full experiment and
reproduction command](evals/results.md) for configuration, hashes and limitations.

### 2. Embedding and cross-encoder experiments

The framework, chunking, BM25 and reciprocal-rank fusion stayed unchanged.
Each input variant had 52 queries, of which **47 had gold evidence IDs**.
ASR-like inputs are supplied text variants, not newly recorded speech or a Gnani
recognition benchmark. These runs made **zero Gemini/Gnani calls**.

| Configuration | Text Hit@5 | Text Recall@5 | ASR-like Hit@5 | ASR-like Recall@5 | Approx. warm search time |
| --- | --- | --- | --- | --- | --- |
| E5-small hybrid | 39/47 (83.0%) | 55.7% | 37/47 (78.7%) | 54.6% | 32 ms |
| **BGE-M3 hybrid: selected** | **41/47 (87.2%)** | **57.8%** | **39/47 (83.0%)** | **55.7%** | **246-271 ms** |
| E5-small hybrid + MiniLM cross-encoder | 36/47 (76.6%) | 53.9% | 33/47 (70.2%) | 50.7% | 1.68-1.70 s |
| BGE-M3 hybrid + MiniLM cross-encoder | 36/47 (76.6%) | 54.6% | Not run | Not run | 1.80 s |

Hit@5 asks whether any expected evidence was found; Recall@5 asks how much of the
expected evidence was found. Neither measures generated answer correctness.
The reranker scored 20 hybrid candidates before returning five. The final
BGE-plus-reranker check was deliberately text-only to bound development time.

Additional base-retrieval diagnostics:

| Encoder / input | Hit@20 | Recall@20 | MRR@5 | MRR@20 |
| --- | --- | --- | --- | --- |
| E5-small / text | 46/47 (97.9%) | 86.2% | 0.522 | 0.536 |
| E5-small / ASR-like | 47/47 (100%) | 86.5% | 0.511 | 0.531 |
| BGE-M3 / text | 45/47 (95.7%) | 88.7% | 0.543 | 0.552 |
| BGE-M3 / ASR-like | 46/47 (97.9%) | 83.7% | 0.584 | 0.600 |

MRR is the mean reciprocal rank of the first expected source: earlier is better,
with zero when no expected source is in the returned list. Reranked MRR@5 was
0.540 / 0.443 for E5 text / ASR-like and 0.529 for BGE text.

**Selection:** BGE-M3 improves top-five hits by two questions in each variant;
the tested cross-encoder reduces evidence coverage and is therefore disabled.
E5-small remains available for lower-latency machines. These results do not prove
all cross-encoders are ineffective or that BGE improves every retrieval depth.

The corpus contains 154 public sections/catalog records. E5 uses 384-dimensional
mean-pooled vectors with query/passage prefixes; BGE-M3 uses 1024-dimensional
CLS-pooled dense vectors without prefixes. Both were evaluated on CPU with a
512-token maximum. The reranker is
`cross-encoder/mmarco-mMiniLMv2-L12-H384-v1`; pinned revisions and commands
are recorded in [retrieval experiments](evals/retrieval-experiments.md).

Warm timings exclude downloads, model loading and document embedding; some runs
overlapped other CPU work, so they are approximate. BGE's checkpoint is about
2.27 GB and costs more memory than E5. The initial BGE report's pooling descriptor
was corrected without changing its actual publisher-defined CLS computation.

NumPy exact cosine scores matched an independent SciPy calculation. FAISS was
not benchmarked: switching storage with identical vectors and an exact metric
would not itself improve relevance. BGE sparse/multi-vector modes were not tested.

**Important:** the historical 48.1% decision-agreement result belongs to the E5
RAG experiment. BGE has only the retrieval evidence shown here; its end-to-end
answer quality and complete voice-agent reliability remain unmeasured.

### Evidence and validation status

Detailed reports retain aggregate/per-case metrics and configuration, not raw
prompts, replies, keys or proofs. Generated report JSON lives under ignored
`artifacts/evals/`; tracked [answer results](evals/results.md) and
[retrieval results](evals/retrieval-experiments.md) record the local run IDs and
reproduction steps. The 309-test regression suite, frontend composer check and
dataset validation passed after selecting BGE. A cached offline app-index smoke
check also returned five results. No fresh full live voice benchmark was run.

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

### What is the audio-folder runner?

It is a **batch evaluation entry point**, separate from the Streamlit interface.
An evaluator supplies a folder of audio recordings; the runner should process
each input through Gnani STT, the same support-agent factory and Gnani TTS, then
save its reply text, generated speech, retrieved source chunks and per-file
success/failure status in an output folder. It should report a failed input
honestly rather than claiming speech was generated or a tool succeeded.

This lets evaluators test reproducibly without manually clicking through the UI.
It does not mean training a new model, replacing the app or recording the
microphone automatically. **It is not implemented yet**, so no runnable batch
command is claimed here. Its exact file/session contract and sample outputs must
be documented when built; private order verification must not be bypassed.
