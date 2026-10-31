# Evaluation

Evaluate retrieval, decisions, follow-ups, source usage and actual tool actions
against the supplied synthetic practice cases: 52 individual questions and
23 conversations containing 96 customer turns. Gold labels must never become
agent context.

## Current adapters

| Adapter | Behaviour | Limitation |
| --- | --- | --- |
| `baseline` | Always clarifies; no model or tools | Wiring check, NOT the required prompt-only LLM baseline |
| `prompt-only` | Gemini with a support prompt and the current question only | No documents, history, retrieval, tools or gold labels; evaluation only |
| `gemini` | Stateless public-policy RAG | No private tools or dialogue planner |
| `gemini-stateful` | Public-policy RAG with bounded context | Different controller from the primary UI |
| `support` | Shared factory and LLMConversation controller used by UI, voice and CLI chat | Fresh private state per conversation; explicit run-wide generation budget |

A completed run is not an accuracy claim. Existing small development runs do not
establish unseen-question performance. A paired prompt-only LLM versus RAG
measurement remains outstanding; the implementation is available below.

## Prompt-only versus RAG

```powershell
.\.venv\Scripts\python.exe -m zentromart evaluate --agent prompt-only --live --suite questions --max-cases 3
.\.venv\Scripts\python.exe -m zentromart compare-answers --live --max-cases 52 --retriever hybrid --interval-seconds 12 --max-generations 104
```

The paired command uses the same model, generation settings, question order,
input variant and scoring for both arms. RAG is the stateless grounded answerer
to isolate document grounding; full conversational-agent evaluation is separate.
The report retains both scores, case IDs, fingerprints, settings and failures.
A partial run is labelled as such and is never represented as the full set.

Both arms share a generation cap and serial pacing. Provider retries are disabled
for this comparison, and the first failure stops further spending. Configure the
interval and cap against your project's actual RPM, TPM and remaining daily quota
in AI Studio; pacing does not discover or guarantee those limits. Other clients
using the same project share that quota. No live benchmark is run automatically.

## Offline checks

```powershell
.\.venv\Scripts\python.exe -m zentromart evaluate
.\.venv\Scripts\python.exe -m zentromart evaluate --suite conversations
.\.venv\Scripts\python.exe -m zentromart evaluate-retrieval --top-k 5
.\.venv\Scripts\python.exe -m zentromart evaluate-retrieval --top-k 5 --asr
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
node tests/composer_frontend.mjs
```

Default evaluation uses the clarification-only wiring check. `--asr` uses supplied
ASR-like question text, not actual audio or Gnani recognition; conversation
inputs remain their original text.

Retrieval metrics use the 47 questions with gold evidence. Five questions without
gold evidence do not contribute to Hit@K, Recall@K or truncated MRR. Private
records and reference answers are not indexed. Policy anchors attached after
ranking must not count as raw retrieval hits.

## Retrieval comparison

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-semantic.txt
.\.venv\Scripts\python.exe -m zentromart compare-retrieval --top-k 5
```

This compares BM25, normalized multilingual E5 cosine search and reciprocal-rank
fusion on original and ASR-like text. Add `--offline` only after the encoder has
been downloaded. Model preparation is outside per-question retrieval latency.

Reports retain corpus/practice fingerprints, model revision, settings, language
breakdowns and cache information. The UI defaults to hybrid; record the actual
configuration and distinguish retrieval scores from answer accuracy. Preserve reports before
citing measurements in the final report.

## Live model evaluation

These commands consume Gemini quota. Choose case caps deliberately.

```powershell
.\.venv\Scripts\python.exe -m zentromart evaluate --agent gemini --live --suite questions --max-cases 6
.\.venv\Scripts\python.exe -m zentromart evaluate --agent gemini-stateful --live --suite conversations --max-cases 6
.\.venv\Scripts\python.exe -m zentromart evaluate --agent support --live --suite conversations --max-cases 6
```

Live adapters require `--live` and a positive case cap. Cases are a deterministic
prefix, not a curated success set; caps may end mid-conversation. Runs stop at
the first agent error. Failed and unattempted cases remain distinguishable.
Use `--retriever semantic` or `--retriever hybrid` for optional vector retrieval.
`--offline` prevents encoder downloads, not Gemini requests.

Ticket writes are disabled unless `--agent support --write-tickets` is explicitly
requested. These are local mock records, not real support contact. Escalation
decisions and successful ticket execution are separate measurements.

## Reports and interpretation

Runs save ignored `artifacts/evals/<run-id>/report.json` files with denominators,
errors, timings, dataset fingerprints, configuration and redacted traces. They
omit raw questions, replies, prompts, proofs, private payloads and tool arguments.
This is NOT the submission audio-output format, which must separately include
reply text, speech files and retrieved source chunks.

- Tool correctness uses executor-recorded actions, not model claims.
- Language-label agreement is not translation quality.
- Citation-ID agreement is not semantic entailment.
- Required-fact and forbidden-claim lexical checks need manual review.
- Retrieval, answer accuracy and conversation quality are different measurements.
- Mock speech tests do not establish recognition accuracy, pronunciation,
  provider availability or microphone quality.

## Outstanding evaluation work

1. Run the implemented prompt-only/RAG comparison after approving the quota budget.
2. Review its results using the same cases, model and scoring rules; report both
   scores, denominators, failures and limitations.
3. Run `evaluate --agent support` for the shared UI dialogue controller. It follows
   `RETRIEVER` (default hybrid) unless `--retriever` is explicit. Serial pacing and
   the generation cap cover both planning and grounded-answer calls. Each
   conversation has fresh verification and memory state.
4. Run recorded synthetic audio through Gnani STT, that controller and Gnani TTS,
   saving the required outputs and sources.
5. Review multi-turn language switches, unclear audio, verification failures,
   handovers, provider failures and recovery before final reporting.
