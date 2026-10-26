# Phase 5: find useful evidence with BM25

## What now works

We can submit a question and receive ranked policy sections and product facts.
The search corpus contains the 84 sections prepared in Phase 4 plus 70 public
product rows: 154 entries in total. Each result includes its evidence ID, score,
source, document metadata, and the contribution from each matching query term.

This is retrieval. We have not connected a language model to write answers.

## Try the commands

```powershell
.\.venv\Scripts\python.exe -m zentromart search "reverse pickup fee" --top-k 3
.\.venv\Scripts\python.exe -m zentromart search "ELE-0012" --top-k 3
.\.venv\Scripts\python.exe -m zentromart search "refund timeline" --json
.\.venv\Scripts\python.exe -m zentromart evaluate-retrieval
.\.venv\Scripts\python.exe -m zentromart evaluate-retrieval --asr
```

The concise search view shows rank, score, title, source, status, and matching
terms. `--json` includes the complete passage and individual term scores.
Each command rebuilds the small in-memory index from the current source files;
you do not need to run `ingest` first or select an old artifact folder.
Search prints results without writing query logs. An empty, punctuation-only,
stopword-only, or completely unmatched query returns no results. We do not pad
the list with arbitrary zero-score passages.

Retrieval evaluation writes redacted JSON reports under `artifacts/evals/`.
They contain ranked public evidence IDs and aggregate scores, without customer
query text, reference answers, or verification arguments. Generated reports
remain ignored by Git.

## BM25 versus NER

Named Entity Recognition identifies entities in text, such as a location or an
organization. BM25 ranks documents against a query by their words. It neither
extracts customer entities nor generates a response.

For "reverse pickup fee", a passage containing those words receives matching
term contributions. The section `[RET-6]` ranks first in this example. For a
product identifier such as `ELE-0012`, the matching catalog row ranks first and
keeps the evidence ID `products.csv:ELE-0012`, matching the evaluation format.

## How the score is calculated

For every distinct query term that appears in a passage, we compute:

```text
IDF = log(1 + (N - df + 0.5) / (df + 0.5))

term score = IDF × tf × (k1 + 1)
             -------------------------------------------
             tf + k1 × (1 - b + b × length / average_length)

passage score = sum of its matching term scores
```

- `N`: number of indexed passages.
- `df`: number of passages containing the term.
- `tf`: number of occurrences of the term in this passage.
- `length`: number of retained tokens in the passage.
- `k1`: controls how quickly repeated matches stop adding much benefit.
- `b`: controls document-length normalization.

Our defaults are `k1=1.2` and `b=0.75`. The positive smoothed IDF expression and
these defaults follow the convention documented by [Apache Lucene](https://lucene.apache.org/core/9_12_3/core/org/apache/lucene/search/similarities/BM25Similarity.html).
Our small implementation is not a Lucene integration and does not claim
byte-for-byte identical scores to Lucene's engine.

A rare word provides more discrimination than a word present almost everywhere.
Repeated matches help, but two occurrences do not simply double the score.
Length normalization reduces the advantage of a long passage that happens to
contain many words. A BM25 score is not a probability or confidence percentage.

We implement this in ordinary Python so the mechanics are visible and testable.
The corpus is small enough that scanning 154 entries per query is sufficient;
no search server or new dependency is necessary for this baseline.

## How text becomes tokens

The tokenizer applies Unicode normalization and case folding, separates words
at punctuation, and removes a fixed set of common English words such as "the"
and "my". It preserves negation words such as "no" and "not", although BM25
still does not understand their meaning.

Hindi vowel/nukta marks stay attached to their words. A naive word regex can
split these marks incorrectly, so the tokenizer explicitly handles Unicode
letters, numbers, and combining marks. It does not translate Hindi to English
or convert Romanized Hinglish to Devanagari.

Hyphenated identifiers are split consistently: `ELE-0012` becomes `ele` and
`0012`; leading zeros survive. Repeated query words are scored once. Equal
scores are ordered by evidence ID so runs are deterministic.

This baseline has no stemming: `refund` and `refunds` are different tokens.
There is also no synonym expansion, query rewriting, or semantic matching.
These choices are recorded with a tokenizer version in each evaluation report.

## Public product facts join the same search interface

Some questions need a product's category or warranty as well as a policy. We
adapt public product fields to `SearchDocument`, just like policy chunks. The
catalog adapter uses an explicit allowlist of its nine documented public fields.
A new CSV column cannot silently enter search without a code change.

Products have catalog provenance, not fabricated policy versions or effective
dates. Policy chunks retain their original version/status metadata. All original
policy text remains intact, including the warning attached to historical returns.

The index reads only `kb/*.md` and `data/products.csv`. It does not read customer
or order tables, support logs, practice questions, or expected answers. The
separate evaluation layer loads practice cases and passes only query text to
search.

## First measured baseline

With `top_k=5`, the initial development-set results are:

| Metric | Original questions | ASR-style text |
| --- | ---: | ---: |
| Questions evaluated | 52 | 52 |
| Questions with gold evidence | 47 | 47 |
| Hit@5 | 38/47 (80.9%) | 33/47 (70.2%) |
| Mean Recall@5 | 55.7% | 40.8% |
| Mean Reciprocal Rank@5 | 0.512 | 0.451 |

All gold evidence IDs occur in the index, so the misses are not caused by
omitting product evidence from the corpus. Five questions have no gold evidence
and are excluded from relevance metrics. Returning passages for one of those
questions does not demonstrate that the system should answer it.

Hit@5 only requires one expected source to appear. Recall@5 measures how many
of the expected sources appear; the gap matters because some questions need
several passages. These are practice/development results, not hidden-test
performance or customer-support answer accuracy.

The ASR run uses supplied speech-like text. It does not measure a real speech
recognizer. Results are also broken down by language in the saved report.
The index and practice-file fingerprints, tokenizer version, BM25 settings,
and top-K are recorded to make later comparisons interpretable.

## Inspect a failure before improving the baseline

Try "refund timeline". In the initial baseline, `[ESC-1]` ranks first because
it contains both "refund" and "timeline". That is a relevant escalation rule,
but not necessarily the general refund-method timeline the customer wanted.
Meanwhile, "refunds" and "timelines" do not count as exact matches to their
singular forms. This shows why a fluent-looking query can still retrieve the
wrong first passage.

We retain this baseline rather than adding rules for individual practice cases.
Phase 6 will add semantic retrieval and compare it under the same evaluation
conditions. Phase 7 will handle current-policy precedence and historical
applicability; a superseded section can still rank highly today, and its status
is shown to make that visible. A high search score never overrides policy rules.

## Read the code

1. `src/zentromart/retrieval.py`: tokenization, public-source adapters, and BM25.
2. `src/zentromart/evaluation/scoring.py`: shared retrieval metrics.
3. `src/zentromart/evaluation/retrieval.py`: single-question evaluation and reporting.
4. `tests/test_retrieval.py`: hand-calculated score, rarity, saturation, length,
   Unicode, deterministic results, and the public-data boundary.

The `evaluate` command still runs the Phase 3 clarification baseline for whole
agent behavior. Use `evaluate-retrieval` to measure this phase's search without
inventing answer or tool-use scores.
