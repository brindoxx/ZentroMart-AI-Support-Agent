# ZentroMart AI Support Agent

A multilingual customer support capstone for **ZentroMart**, the fictional Indian
retailer in the supplied From Tokens to Transformers dataset.

Built as part of IIT Guwahati Consulting & Analytics Club's From Tokens to
Transformers course.

## Current progress

**Phases 1–3 complete: foundation, dataset inspection, and evaluation framework.**
The Python package, configuration, dataset inspection, validation commands, and
offline baseline evaluation runner are ready. Retrieval, model calls,
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
Python executable directly. Phases 1–3 need no API keys, GPU, or cloud services.

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
tests/                   Configuration, data, and evaluation regression tests
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
3. Next, Phase 4: parse documents into sections; Phases 5–9 add retrieval and grounded replies.
4. Phases 10–15: conversation state, verified tools, calculations, and interface.
5. Phases 16–21: voice, evaluation, deployment, documentation, and release.

Keep service credentials, generated conversation records, and ticket files out
of this repository and the report. `.gitignore` excludes local credentials,
virtual environments, generated artifacts, and mock ticket output.
