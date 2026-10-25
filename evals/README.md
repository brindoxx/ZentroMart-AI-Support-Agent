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
