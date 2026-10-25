# Phase 3: build the measuring system before the agent

## Purpose

Phase 2 established that the dataset is usable. Phase 3 gives us a repeatable
way to test the behavior of the agent we will build. Without this, changing an
embedding model or prompt could improve one example while breaking ten others
without us noticing.

This phase contains no language-model connection or retriever. The command runs
a deliberately weak baseline that always requests more information in English.
It tests loading, session handling, scoring, and report generation. Its results
are not a claim of chatbot quality.

## Run it

```powershell
.\.venv\Scripts\python.exe -m zentromart evaluate
.\.venv\Scripts\python.exe -m zentromart evaluate --suite questions
.\.venv\Scripts\python.exe -m zentromart evaluate --suite questions --asr
.\.venv\Scripts\python.exe -m zentromart evaluate --suite conversations
```

The default evaluates 52 questions plus 96 conversation turns: 148 responses
across 75 independent sessions. Each question is its own session. The other
23 sessions are complete multi-turn conversations. `--asr` uses the provided
speech-like text for single questions; this does not test actual audio, Gnani,
or transcription quality.

Each run prints a summary and saves a JSON report beneath the configured
`ARTIFACTS_DIR`. A timestamp and unique suffix prevent overwriting previous runs.
The CLI exits nonzero for agent errors or invalid inputs. A zero exit code means
the evaluation ran successfully, not that the agent answered correctly.

## Keep questions separate from the answer key

```text
Practice CSV row
    ├─ Customer message ──> AgentRequest ──> AgentResponse
    └─ Expected labels ──────────────────> Scorer
                                             │
                                             ▼
                                      Redacted JSON report
```

`AgentRequest` contains a session ID, customer message, and previous messages.
It does not receive expected decisions, reference answers, gold evidence,
expected tool calls, the customer's record ID, or the dataset's hidden order ID
column. An order ID mentioned by the customer remains part of their message.

The loader does not retain reference-answer text. It loads only the scoring
labels needed by this phase. These evaluation labels must never become retrieved
knowledge or few-shot examples for the live agent.

## What the agent will return

`AgentResponse` defines a common interface for the future text agent, UI, and
evaluation runner:

| Field | Meaning |
| --- | --- |
| `decision` | `answer`, `clarify`, `escalate`, or `refuse` |
| `reply` | Customer-facing response text |
| `language` | Agent-declared language code |
| `evidence` | Section or catalog IDs cited in the answer |
| `retrieved_evidence` | Ranked IDs returned by the retriever |
| `tool_calls` | Calls recorded by the trusted tool executor |

Separating retrieved evidence from cited evidence matters. The retriever might
find the right section while the answer generator cites something else. We need
to distinguish those failures.

Tool traces must be recorded by the application when it executes tools. A model
claiming that it used `create_ticket` is not proof that a ticket was created.
Action-success and privacy checks will be added alongside the actual tool flow.

## What the metrics mean

| Metric | Interpretation |
| --- | --- |
| Decision correctness | Does the predicted decision belong to the allowed decisions? |
| Declared-language match | Does the returned language code match the expected code? |
| Citation precision | Fraction of cited IDs appearing in the gold evidence set |
| Citation recall | Fraction of the gold evidence IDs included in the citations |
| Invalid citation count | Cited IDs absent from the KB/catalog inventory |
| Retrieval Hit@K | Did any expected evidence appear in the first K distinct results? |
| Retrieval Recall@K | What fraction of all expected evidence appeared in those results? |
| Reciprocal Rank@K | 1 divided by the position of the first correct retrieved ID; zero for a miss |
| Required-fact lexical coverage | Fraction of required facts whose listed wording/alternatives matched |
| Forbidden-claim lexical hits | Number of forbidden claims whose wording matched |
| Tool-call correctness | Correct call sequence and count, with the expected arguments |

For example, if gold evidence is `[RET-2, REF-3]` and retrieval returns
`[OTHER, RET-2]`, Hit@2 is 1, Recall@2 is 0.5, and reciprocal rank is 0.5.
Finding one source does not mean we found every source needed to answer.

For lookup calls, arguments must match exactly, including leading zeros. An
unverified lookup must not unexpectedly include a verification value. A label
of `create_ticket()` specifies the action but no summary wording, so additional
summary/reason arguments are allowed. Order and verification arguments are
compared in memory and never serialized into reports.

Each metric has its own denominator. No gold evidence means retrieval recall
is not applicable, rather than automatically perfect. Single questions have no
tool-call labels, so tool accuracy is not scored for them. Conversation turns
with an empty tool-call label expect no calls. Failed agent calls are counted
separately and excluded from metric means; always read the error count first.

## Limits of automatic scoring

The fact matcher handles case, whitespace, Unicode digits, some grouped amounts,
English number words up to 99, and day/month/year dates with full English or
Hindi month names. ` ; ` separates required facts, while ` / ` separates
acceptable alternatives within a fact. Token boundaries stop `12` matching
`120` or `app` matching `happy`.

This is still a lexical diagnostic, not the dataset's complete semantic grading
standard. It can miss valid paraphrases, Hindi number words, spoken dates, or
wording that changes punctuation. It can also match words in a wrong or negated
claim. Forbidden-claim matching has the same limitations. Human review is always
required; no combined pass score or semantic-correctness percentage is produced.

Likewise, an agent's declared `hi` code does not prove that its reply is Hindi.
A valid citation ID does not prove that the passage supports the answer. Tool
trace matching does not prove that an action succeeded or that no private data
was disclosed. We document these gaps instead of treating them as solved.

## Conversation state and reproducibility

The runner creates a new agent instance for every independent session. Within
one conversation, it passes prior customer messages and the actual earlier
agent replies. It never substitutes a reference answer for a previous reply.
This lets later tests reveal whether the agent handles its own mistakes and
maintains verification correctly.

If a response raises an exception, that row records only the exception type.
The conversation continues with a neutral unavailable-response placeholder.
An exception constructing the agent or malformed evaluation data aborts the run.

Reports contain case IDs, numerical/boolean scores, timing, suite summaries,
the fixed reference date, and a dataset SHA-256 fingerprint. The fingerprint
helps detect dataset changes; it does not contain the dataset itself. Future
model adapters should also record their model/prompt/retrieval configuration.
Current timings measure the baseline, not model or voice latency.

Raw prompts, replies, histories, reference answers, tool arguments, and exception
messages stay out of reports. Artifacts remain excluded from Git. This reporting
boundary does not itself certify privacy-safe agent behavior.

## What to read in the code

1. `contracts.py`: the request and response interface.
2. `evaluation/cases.py`: loading, label separation, and conversation grouping.
3. `evaluation/scoring.py`: individual comparisons and lexical normalization.
4. `evaluation/runner.py`: agent sessions, summaries, and report creation.
5. `tests/test_evaluation.py`: examples of correct matches, failures, and boundaries.

Phase 4 will parse policy sections into retrieval chunks. Once a retriever is
available, these same evidence metrics will measure it; once the generator is
available, the response checks will measure its decisions and answers.
