# ZentroMart AI Support Agent

A multilingual customer support capstone for **ZentroMart**, the fictional Indian
retailer in the supplied From Tokens to Transformers dataset.

Built as part of IIT Guwahati Consulting & Analytics Club's From Tokens to
Transformers course.

## Current progress

**Phases 1–8 complete: retrieval, policy handling, and a verified Gemini connection.**
The project supports BM25, local multilingual semantic search, and hybrid rank
fusion over policy sections and public product facts, with separate retrieval
evaluation. A deterministic layer now prioritizes policy authority and applies
scoped historical, festive, and marketplace exceptions to explicit scenario facts.
Grounded customer replies, order workflows, the web interface, and
voice support are planned for later phases.

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

The default runs 52 questions and 96 conversation turns. The baseline always asks
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
requirements.txt         Editable local installation
```

The supplied dataset is kept together so its relative imports and offline mock
tools continue to work. Its own README describes policy precedence, identity
verification, and evaluation evidence IDs. All customer records are synthetic.

## Next phases

1. Completed: inspect and validate the data and table relationships.
2. Completed: establish the baseline evaluation runner before building retrieval.
3. Completed: parse knowledge documents into sections with metadata and source context.
4. Completed: add keyword retrieval with BM25 and measure its development baseline.
5. Completed: semantic/hybrid retrieval and a real-model comparison on both input variants.
6. Completed: policy precedence, scoped applicability, and evidence provenance.
7. Completed: Gemini model connection with a successful synthetic live access check.
8. Next, Phase 9: connect policy evidence to grounded replies.
9. Phases 10–15: conversation state, verified tools, calculations, and interface.
10. Phases 16–21: voice, evaluation, deployment, documentation, and release.

Keep service credentials, generated conversation records, and ticket files out
of this repository and the report. `.gitignore` excludes local credentials,
virtual environments, generated artifacts, and mock ticket output.
