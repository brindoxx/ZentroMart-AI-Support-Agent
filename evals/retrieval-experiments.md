# Local embedding and reranking comparison

Measured on 31 October 2026. The framework, chunking, policy rules and BM25 +
reciprocal-rank-fusion algorithm stayed unchanged. Only the dense encoder and
optional candidate reranker changed. No Gemini or Gnani requests were made.

## Decision

Use **BM25 + BGE-M3 dense retrieval, without cross-encoder reranking**. BGE-M3
improved top-five evidence hits modestly at an acceptable local CPU cost. Keep
E5-small available for lower-latency deployments. The tested multilingual MiniLM
cross-encoder made evidence coverage worse and added substantial latency, so it
is implemented as an explicit experiment, not enabled by default.

## Results

Each input variant contains 52 practice questions; 47 have gold evidence labels
and contribute to retrieval metrics. Hit@5 means at least one expected evidence
ID was retrieved, not that the answer was correct. Recall@5 measures the fraction
of expected IDs found. The supplied ASR-like strings are not fresh audio/STT runs.

| Configuration | Text Hit@5 | Text Recall@5 | ASR-like Hit@5 | ASR-like Recall@5 | Approx. warm search time |
| --- | --- | --- | --- | --- | --- |
| E5-small hybrid | 39/47 (83.0%) | 55.7% | 37/47 (78.7%) | 54.6% | 32 ms |
| BGE-M3 hybrid | 41/47 (87.2%) | 57.8% | 39/47 (83.0%) | 55.7% | 246-271 ms |
| E5-small hybrid + MiniLM reranker | 36/47 (76.6%) | 53.9% | 33/47 (70.2%) | 50.7% | 1.68-1.70 s |
| BGE-M3 hybrid + MiniLM reranker | 36/47 (76.6%) | 54.6% | Not run | Not run | 1.80 s |

Reranking scored the top 20 hybrid candidates and returned five. Candidate
coverage alone was not the bottleneck: E5 top-20 hit 46/47 text cases and BGE
45/47. This particular cross-encoder failed to rank those candidates better for
the dataset's evidence labels. That does not establish that all rerankers fail.
The final BGE reranking check was deliberately text-only to bound time.

Warm latency excludes model download, model load and document embedding. Some
experiments overlapped other local CPU work; treat timings as approximate, not
an isolated performance benchmark. BGE-M3 requires more RAM and a roughly 2.27 GB
checkpoint, versus the smaller E5 option. The two-question Hit@5 gain is modest;
it is development-set evidence, not a statistically established general gain.

## Reproducibility

- E5: `intfloat/multilingual-e5-small`, revision
  `614241f622f53c4eeff9890bdc4f31cfecc418b3`, 384 dimensions, mean pooling,
  `query: ` / `passage: ` prefixes.
- BGE: `BAAI/bge-m3`, revision
  `5617a9f61b028005a4858fdac845db406aefb181`, 1024 dimensions, publisher CLS
  pooling, no prefixes. Only dense embeddings are used; this is not a test of
  BGE's sparse or multi-vector modes.
- Reranker: `cross-encoder/mmarco-mMiniLMv2-L12-H384-v1`, revision
  `1427fd652930e4ba29e8149678df786c240d8825`.
- CPU inference, normalized vectors, maximum 512 tokens for all models. BGE's
  larger supported context is intentionally unused in this controlled trial.
- Models are pinned; remote Python code is disabled. BGE uses explicit
  weights-only loading with PyTorch >=2.6. Separate encoder caches prevent mixing
  incompatible vectors.

```powershell
.\.venv\Scripts\python.exe -m zentromart.evaluation.retrieval_experiment --models e5-small bge-m3 --offline --rerank
```

Remove `--offline` only to authorize public model downloads on a new machine.
The bounded final check can be reproduced with:

```powershell
.\.venv\Scripts\python.exe -m zentromart.evaluation.retrieval_experiment --models bge-m3 --offline --rerank-only --variants question
```

Local aggregate reports (generated artifacts, not required in Git):

- E5: `artifacts/evals/20261031T120321Z-6c5599e7/report.json`
- BGE: `artifacts/evals/20261031T120734Z-4b1fb2d3/report.json`
- E5 + reranker: `artifacts/evals/20261031T120958Z-a7b5299e/report.json`
- BGE + reranker, text only: `artifacts/evals/20261031T121254Z-17338811/report.json`

The initial BGE report's descriptive pooling field inherited E5's label; the
actual model used the publisher's CLS pooling. The descriptor and cache identity
were corrected before the final reranked run. This did not change model weights
or the pooling computation used for the numbers above.

## Why not change the vector database?

The current NumPy index scores every normalized document vector using exact
cosine similarity. The experiment verified its scores against an independent
SciPy cosine calculation. This is not an actual FAISS benchmark. Changing to an
exact FAISS index with identical vectors and metric would not improve semantic
rankings; approximate indexes mainly trade speed, memory and recall at scale.
Persistent databases add filtering, updates and operational features, which are
not the immediate bottleneck for this small public corpus.

E5 and BGE are not the only embedding families: multilingual GTE and other
retrieval encoders are alternatives. They were not evaluated here. A broader
model sweep or database migration is deferred in favour of required deliverables.

## What these results do not show

The historical paired Gemini baseline/RAG numbers in [results](results.md) used
E5, not BGE. They remain explicitly reproducible with E5 flags. No new end-to-end
answer-quality claim follows from the BGE retrieval gain. Neither experiment is a
held-out benchmark or proof of complete voice-agent correctness. Policy authority,
date applicability, verification and tool authorization remain backend checks.

Restart the app to adopt a changed encoder. An explicit `EMBEDDING_MODEL` in `.env`
or the environment overrides the default; set it to `bge-m3` and `RERANKER=none`
for the selected configuration. Do not clear private verification state merely
to change retrieval settings.
