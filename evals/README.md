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
not a customer-answer benchmark. The CLI evaluator remains the offline baseline;
there is no `--agent gemini` yet. Do not interpret transport success as policy
accuracy or an end-to-end agent score.
