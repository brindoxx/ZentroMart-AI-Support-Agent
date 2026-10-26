# Evaluation workspace

Run the framework from the repository root:

```powershell
.\.venv\Scripts\python.exe -m zentromart evaluate
.\.venv\Scripts\python.exe -m zentromart evaluate --suite questions --asr
.\.venv\Scripts\python.exe -m zentromart evaluate --suite conversations
```

The current CLI uses a deliberately unskilled clarification baseline to test the
framework. It makes no model or tool calls. A poor score is expected and does not
represent our future agent. `--asr` replaces single-question inputs with the
provided ASR-style text; it does not run speech recognition. With the default
`--suite all`, conversation inputs remain their original text.

Implementation lives in `src/zentromart/evaluation/`; shared agent inputs and
outputs live in `src/zentromart/contracts.py`. Future Python adapters can pass a
factory to `run_evaluation(settings, factory=YourAgent, agent_name="your-agent")`.
The CLI currently accepts only `--agent baseline`.

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
