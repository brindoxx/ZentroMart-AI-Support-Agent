# ZetroMart AI Support Agent

A multilingual customer support capstone for **ZentroMart**, the fictional Indian
retailer in the supplied From Tokens to Transformers dataset. The repository
name uses **ZetroMart**; the assistant and dataset retain **ZentroMart**.

Built as part of IIT Guwahati Consulting & Analytics Club's From Tokens to
Transformers course.

## Current progress

**Phase 1: project foundation.** The Python package, configuration, environment
template, dataset layout, and setup checks are ready. Retrieval, model calls,
order workflows, the web interface, and voice support are not implemented yet.

The planned agent will answer from company policies, verify callers before
showing order details, create handover tickets, and support English, Hindi,
Hinglish, and Gnani voice input/output.

## Local setup (PowerShell)

Use Python 3.11 or newer. The initial setup was verified with Python 3.13.

```powershell
git clone https://github.com/brindoxx/ZetroMart-AI-Support-Agent.git
cd ZetroMart-AI-Support-Agent
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -m zentromart
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

The repository is currently private; cloning requires authorized GitHub access.
Activation of the virtual environment is optional: the commands above use its
Python executable directly. Phase 1 needs no API keys, GPU, or cloud services.

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
tests/                   Configuration boundary checks
evals/                   Evaluation workspace for Phase 3
report/                  Final report workspace
.env.example             Public configuration template
pyproject.toml           Package metadata and dependencies
requirements.txt         Editable local installation
```

The supplied dataset is kept together so its relative imports and offline mock
tools continue to work. Its own README describes policy precedence, identity
verification, and evaluation evidence IDs. All customer records are synthetic.

## Next phases

1. Phase 2: inspect and validate the data and table relationships.
2. Phase 3: establish an evaluation runner before building retrieval.
3. Phases 4–9: parse documents, retrieve evidence, and generate grounded replies.
4. Phases 10–15: conversation state, verified tools, calculations, and interface.
5. Phases 16–21: voice, evaluation, deployment, documentation, and release.

Keep service credentials, generated conversation records, and ticket files out
of this repository and the report. `.gitignore` excludes local credentials,
virtual environments, generated artifacts, and mock ticket output.
