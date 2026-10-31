# Prompt-only versus RAG: measured results

Measured on 31 October 2026 using all 52 original-text practice questions.
Both arms completed 52/52 with zero provider/adapter errors. The case IDs match,
and the comparison report marks the full practice set complete.

This is a **stateless document-grounding experiment**, not a score for the full
UI conversation agent, voice recognition, private verification or tool handling.
Practice data is not a held-out test.

## Results

| Metric | Prompt-only Gemini | Hybrid RAG | Denominator / meaning |
| --- | --- | --- | --- |
| Decision agreement | 32.7% (17/52) | 48.1% (25/52) | Expected action: answer, clarify, refuse or escalate |
| Required-fact lexical coverage | 12.2% | 38.8% | Mean per-question coverage on 49 questions with required facts |
| Declared language agreement | 86.5% (45/52) | 94.2% (49/52) | Returned language label; not independent language-quality review |
| Retrieval Hit@5 | 0% (no retrieval) | 83.0% (39/47) | At least one expected source among the top five; 47 gold-evidence cases |
| Retrieval Recall@5 | 0% | 55.7% | Mean fraction of expected sources retrieved across 47 cases |
| Citation precision | N/A (no citations) | 76.7% | Mean source-ID precision across 35 responses containing citations |
| Citation recall | 0% | 39.4% | Mean expected-source coverage across 47 cases |

RAG produced 44 accepted generated answers and **8 citation-mismatch fallbacks**.
These are completed safe responses, not provider errors. The guard replaced
unaccepted generated drafts, so zero invalid IDs in final replies does not mean
the model never attempted an invalid citation. No forbidden-claim lexical hits
were found in the eight labelled cases, but that is not a general safety proof.

## How these scores are calculated

- **Decision agreement:** count whether each returned decision belongs to that
  question's allowed decisions; divide by 52. It does not check every fact in
  the reply. A wrong clarification instead of an expected answer loses this check.
- **Fact coverage:** for each question, check its supplied required facts against
  normalized reply wording, then average that question's fraction across 49
  applicable questions. For example, two matching facts out of three gives
  66.7% for that question. These are lexical checks, not a semantic judge:
  paraphrases, translation and negation can mislead them.
- **Retrieval Hit@5:** a question counts as a hit if at least one expected section
  appears among the five ranked sources. It does not guarantee all needed
  sections were found or that the eventual answer used them correctly.
- **Citation precision/recall:** compare cited IDs with the expected source IDs.
  Correct IDs do not prove the sentence they accompany is supported.

There is no trustworthy single overall accuracy percentage in this experiment.
The gain in fact coverage is encouraging, but the current decision and citation
results need improvement before submission-quality claims.

## Reproduce the experiment

```powershell
.\.venv\Scripts\python.exe -m zentromart compare-answers --live --max-cases 52 --retriever hybrid --embedding-model e5-small --reranker none --offline --interval-seconds 5 --input-tpm 250000 --max-generations 104
```

This command consumes Gemini quota. It was configured against the user's stated
15 RPM / 250,000 input TPM / 500 RPD limits, with no more than 12 requests/minute
from this process, a conservative UTF-8-based input-token guard and no automatic
provider retries. It used **104 generation attempts**. Other clients' project
usage is not discovered or controlled. Check remaining daily quota before reruns.
The encoder must already be cached for `--offline`.

- Requested model: `gemini-3.5-flash-lite`; SDK `1.75.0`.
- Output budget: 1024 tokens; timeout setting: 20 seconds; retries: 0.
- RAG: top-K 5, 154 public sections/catalog records, BM25 + normalized E5 cosine
  search, equal-weight reciprocal-rank fusion with constant 60 and candidate-K 20.
- Encoder: `intfloat/multilingual-e5-small`, revision
  `614241f622f53c4eeff9890bdc4f31cfecc418b3`, 384 dimensions, CPU.
- Dataset fingerprint: `9708964f058e739d1cba23cb54e49cea622ecd31fc2d63d7daf85375ef91a7d3`.
- Public corpus fingerprint: `c14435479f1e7ba19981eb47dd58707b3b6c06cf5ec0f748d29df916082ff3bd`.
- Prompt-only prompt hash: `304deb00076bc5199941553024baecf4f98f41cdfbb9406ff095c57722cfc9f1`.
- RAG prompt hash: `58c99c829c9332f98a8fa6b6779e0329d9abf035637b08b98915746da2702f02`.
- Local redacted report: `artifacts/evals/20261031T051257Z-3e50d17b/report.json`.

The report retains aggregate/per-case metrics and configuration, not raw prompts,
replies, keys or proofs. Reported wall times include pacing and cold-start/provider
delays and should not be interpreted as isolated model-speed measurements.

## Next improvement targets

1. Inspect the citation-validation failures without weakening grounding checks.
2. Evaluate the shared dialogue agent on complete conversations; do not substitute
   this stateless score for that experiment.
3. Review wrong decisions and missing facts with public policy context and
   language-aware manual checks before changing retrieval or prompts.
4. Keep the first paired run as a baseline; label subsequent tuned runs as
   development results rather than unseen-test performance.
