# ZentroMart AI Support Agent

A multilingual customer support capstone for **ZentroMart**, the fictional Indian
retailer in the supplied From Tokens to Transformers dataset.

Built as part of IIT Guwahati Consulting & Analytics Club's From Tokens to
Transformers course.

## Current progress

**Phases 1–4 complete: foundation, inspection, evaluation, and knowledge ingestion.**
The Python package, configuration, dataset inspection, validation commands,
offline baseline evaluation runner, and section-based knowledge corpus are ready.
Retrieval, model calls,
order workflows, the web interface, and voice support are not implemented yet.

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
Python executable directly. Phases 1–4 need no API keys, GPU, or cloud services.

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
The model and Gnani variables in `.env.example` are placeholders for future
integrations. Never commit `.env` or real credentials.

## Repository layout

```text
dataset/                 Supplied synthetic dataset and documentation
src/zentromart/          Python package and central configuration
tests/                   Configuration, data, evaluation, and ingestion tests
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
4. Next, Phase 5: add keyword retrieval; Phases 6–9 add semantic search and grounded replies.
5. Phases 10–15: conversation state, verified tools, calculations, and interface.
6. Phases 16–21: voice, evaluation, deployment, documentation, and release.

Keep service credentials, generated conversation records, and ticket files out
of this repository and the report. `.gitignore` excludes local credentials,
virtual environments, generated artifacts, and mock ticket output.
