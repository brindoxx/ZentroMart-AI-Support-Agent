# Phase 6: search by meaning and combine the rankings

## What this phase adds

BM25 finds shared words. Semantic retrieval compares numerical representations
of meaning, called embeddings. The project now has separate `bm25`, `semantic`,
and `hybrid` retrieval modes over the same 154 public evidence entries.

The model is an embedding encoder, not a chat model. It produces vectors rather
than customer replies. Policy precedence, order verification, and generated
answers remain later phases.

## Install and run

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-semantic.txt
.\.venv\Scripts\python.exe -m zentromart search "Nobody collected the item I want to send back" --retriever semantic
.\.venv\Scripts\python.exe -m zentromart search "reverse pickup fee" --retriever hybrid --json
.\.venv\Scripts\python.exe -m zentromart compare-retrieval
```

The first semantic run downloads model files into ignored `artifacts/models/`
and computes document embeddings under `artifacts/embeddings/`. Subsequent runs
reuse those files. After the download, add `--offline` to prevent model-network
access. The core install and default `--retriever bm25` continue to work without
the semantic extra or a model download.

Use `evaluate-retrieval --retriever semantic` or `--retriever hybrid` for one
method. `--asr` switches to the supplied ASR-style text. `compare-retrieval`
evaluates all three methods on original and ASR-style questions and writes six
individual reports plus a comparison report. These files stay out of Git.

## The embedding pipeline

```text
Document text + "passage: " -> local E5 encoder -> normalized document vector
Customer text + "query: "  -> local E5 encoder -> normalized query vector

query vector · document vector -> cosine similarity -> ranked evidence IDs
```

We use `intfloat/multilingual-e5-small` at revision
`614241f622f53c4eeff9890bdc4f31cfecc418b3`. Its vectors have 384 dimensions.
The model runs on the CPU, uses normalized vectors, and limits inputs to 512
tokens. The required query/passage prefixes apply to non-English inputs too.
These choices follow the [E5 model card](https://huggingface.co/intfloat/multilingual-e5-small).

The model can place related wording near one another without literal overlap,
such as a customer asking to "send it back" and a passage discussing returns.
Multilingual training can also help compare Hindi/Hinglish questions with English
documents. That is a capability to measure, not a guarantee for every query.

For vectors normalized to length one, their dot product equals cosine similarity.
We compute all 154 similarities directly with NumPy; a vector database or FAISS
is unnecessary at this scale. Semantic scores are not confidence percentages.
A high score can still correspond to outdated or inapplicable evidence.

The 512-token limit is a model constraint, not the character counts from Phase 4.
Inputs beyond it are truncated by the encoder. We keep whole original passages
in the results so later answer generation can inspect the source text.

## Why hybrid search uses ranks

BM25 scores and cosine similarities have different scales. Adding them directly
would give one method an arbitrary advantage. We instead use equal-weight
reciprocal rank fusion:

```text
fused score(document) = 1 / (60 + BM25 rank)
                     + 1 / (60 + semantic rank)
```

A method contributes nothing if the document is absent from its candidate list.
Each method supplies its top 20 candidates, or more when the requested output
top-K exceeds 20. These settings are fixed before comparing results; no
per-question rules or gold-evidence boosts are used.

For a passage ranked second by BM25 and first by semantic search, the fused
score is `1/62 + 1/61`. A passage supported by both rankings often rises above a
passage returned by only one. Equal final scores are ordered by evidence ID.

JSON search results label their score type as `bm25`, `cosine`, or `rrf`. Hybrid
results also include each component's rank and raw score. Keyword contributions
explain only the BM25 component; they do not explain the neural model's reasoning.

## Cache behavior and reproducibility

Only document vectors are persisted. Customer query text and query vectors are
not saved in the embedding cache. The document corpus still comes only from
`kb/*.md` and the allowlisted public fields of `data/products.csv`.

The cache key includes the corpus fingerprint, exact evidence-ID order, model
revision, query/passage prefix settings, dimension, length limit, and installed
embedding-library versions. A changed corpus or encoder configuration selects a
different cache. Each saved matrix has a checksum and is loaded with pickle
disabled; shape, finite values, and unit-vector norms are checked.

The manifest is published only after the complete matrix is written. A corrupt
cache fails clearly. Use `--rebuild-embeddings` to recompute it; the replacement
manifest points to a new matrix instead of deleting old run files.

Model loading uses a pinned public snapshot, local CPU execution, safetensors
weights, and `trust_remote_code=False`. The local encoder does not send customer
text to an embedding API. `--offline` requires the model snapshot to have already
been downloaded; it does not substitute a different model if files are missing.

The document cache avoids repeated passage encoding. It does not eliminate model
startup or query-encoding time. Reported search latency excludes index/model
construction, so it should not be interpreted as cold application startup time.

## How to interpret the comparison

All methods use the same corpus, 52 practice questions, and top-K setting.
The 47 questions with gold evidence contribute to Hit@K, Recall@K, and truncated
MRR; five no-gold questions remain outside those relevance averages. A semantic
retriever normally returns candidates even for an unsupported query, so a
retrieval hit or high similarity is not an abstention decision.

The comparison keeps per-language summaries and separate original/ASR results.
These are development-set measurements. A hybrid method can improve some cases
and worsen others; the implementation does not promise that fusion always wins.

## Measured Phase 6 results

The real-model comparison completed offline using the cached E5 snapshot and
document embeddings. Settings were fixed at top-K 5, 20 candidates per hybrid
component, and fusion constant 60. Each row below scores the same 47 questions
with gold evidence; all 52 questions were run for each input variant.

| Input | Method | Hit@5 | Mean Recall@5 | MRR@5 |
| --- | --- | ---: | ---: | ---: |
| Original questions | BM25 | 38/47 (80.9%) | 55.7% | 0.512 |
| Original questions | Semantic | 37/47 (78.7%) | 53.2% | 0.552 |
| Original questions | Hybrid | 39/47 (83.0%) | 55.7% | 0.522 |
| ASR-style text | BM25 | 33/47 (70.2%) | 40.8% | 0.451 |
| ASR-style text | Semantic | 39/47 (83.0%) | 56.7% | 0.569 |
| ASR-style text | Hybrid | 37/47 (78.7%) | 54.6% | 0.511 |

Hybrid finds at least one expected source for one more original question than
BM25. Semantic retrieval finds one fewer original question overall, but tends
to put the first correct passage nearer the top, as its higher MRR shows.
Semantic search is strongest on the supplied ASR-style text, improving Hit@5
by six questions over BM25. Hybrid fusion does not preserve every semantic win.
We retain all three selectable modes and keep the default BM25 baseline intact.

These small development samples do not establish a universal winner. The
language breakdown is in the generated reports, and neither these metrics nor
a high similarity demonstrate a correct customer-facing answer.

There is also an applicability failure to inspect: the real semantic query
"Nobody collected my return" ranked the superseded `[RETv3-2]` section first.
Its historical warning and status were preserved, but similarity alone did not
apply the policy rules. This is precisely the distinction Phase 7 must address.

This run used Sentence Transformers 5.7.0, Transformers 5.21.0, PyTorch 2.14.1,
and NumPy 2.5.4 on Python 3.13. All 53 automated tests passed without skips, and
the dependency check passed. Unit tests use fake vectors; the six-way comparison
is a separate real-model integration run rather than a unit-test download.

## Read the implementation

1. `retrieval.py`: shared evidence types, unchanged BM25 defaults, and index factory.
2. `semantic.py`: lazy E5 loading, validated document cache, and cosine search.
3. `hybrid.py`: reciprocal rank fusion over component candidates.
4. `evaluation/retrieval.py`: the same evidence metrics for all three methods.
5. `tests/test_semantic.py`: fake-vector tests for prefixes, cosine normalization,
   cache reuse/invalidation/corruption, and rank fusion without downloads.

The next phase will decide which retrieved documents should take precedence
and which historical policies apply to a customer's situation.
