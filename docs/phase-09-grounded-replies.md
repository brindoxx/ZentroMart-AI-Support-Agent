# Phase 9: use evidence to generate a guarded support reply

## What we have connected

Phase 8 proved Gemini could respond. Phase 9 gives it a useful job: explain
ZentroMart's public policies and public product facts from selected sources.
The new `GroundedAgent` implements our existing `AgentRequest`/`AgentResponse`
contract and is available through `answer` and the opt-in Gemini evaluator.

The flow is: customer question, retrieval, policy precedence/applicability,
bounded prompt, Gemini structured draft, local citation/action-pattern checks,
then an accepted reply or a fixed clarification/review response. API/provider
errors remain errors rather than being disguised as successful clarifications.

This is retrieval-augmented generation (RAG): sources are supplied at request
time. We have not trained or fine-tuned Gemini on the dataset.

## 1. Prepare evidence before asking the model

The agent reuses Phase 7's `PolicyEngine`, including its historical electronics,
festive fashion, and marketplace exception handling. It does not ask Gemini to
overrule those checks. The engine now also returns raw ranked retrieval IDs so
we can distinguish search hits from subsequently attached policy dependencies.

If a typed return-window scenario is missing its category, delivery date, or
fashion placement date, the agent asks for the relevant information without a
model call. Unsupported historical coverage or unavailable required evidence
gets a human-review response; this does not create a ticket. An empty usable
bundle asks for clarification instead of using Gemini's general knowledge.

Topic and scenario fields remain explicit developer inputs. This phase does not
automatically extract dates, SKUs, intent, or verified facts from arbitrary text.
General-topic mode can explain source conditions, but it does not establish
which exception applies to a customer's individual order.

## 2. Construct the prompt with clear trust boundaries

`ModelRequest.instructions` holds our application-owned instructions and trusted
policy context: frozen date, topic, applicability flags, notes, typed scenario,
and an optional requested language. The current customer message and public
passages are encoded separately as JSON data in `ModelRequest.message`.

Each passage keeps its ID, source, document type, authority order, role, and
complete text. The model is told that customer text and source prose are data,
not instructions to change its role, reveal prompts, or fabricate facts.
This separation helps but does not prove prompt-injection resistance.

The prompt forbids private-order assertions, completed actions, invented contact
details, and final deadline/financial calculations. The code has no private-table
reader or tool executor. An order-specific request must acknowledge that verified
lookup is not connected; it should not collect verification proof it cannot use.

The complete prompt must fit Phase 8's 48,000-character input bound. We reject
over-budget requests rather than chopping off exception clauses. Individual
customer messages are capped at 12,000 characters and top-K at 20. These are
character/application limits, not exact token or spend caps.

## 3. Check citations before showing the generated reply

Gemini returns the same four fields from Phase 8: decision, reply, language,
and evidence. We revalidate the draft contract before turning it into a response.

For an `answer`, evidence cannot be empty. Every declared ID must belong to the
actual supplied bundle, not merely exist somewhere in the repository. This also
rejects historical sources excluded for the current scenario. Bracketed inline
references must name exactly the same ID set as the structured evidence array.
An explicitly requested reply language must match the returned language code.

A mismatch discards the generated body and returns a fixed safe clarification.
We do not replace unknown IDs, invent citations, or retry until an answer passes.
Other decisions can have no citations if they make no company-policy claims.

A narrow English/Hindi/Hinglish confirmation-pattern check also rejects common
claims that an order was cancelled, a refund approved, or a ticket created.
There are no actual tool calls, and every returned executor trace remains empty.
This pattern check is not a complete multilingual semantic detector: paraphrased
action claims could still escape it. The absence of real private access is a
code boundary; the truthfulness of every sentence still requires evaluation.

Most importantly, citation validity is not semantic correctness. A model can
cite a supplied passage and still misread its amount, condition, or date. This
phase does not implement a claim-entailment verifier or guarantee zero
hallucinations. The evaluator's gold-ID and lexical diagnostics remain useful
precisely because valid citations alone are insufficient.

## 4. Keep it stateless until conversation handling is ready

The model receives only the current customer message. Session IDs and history
are not forwarded, persisted, or used as proof. This avoids pretending that a
previous turn authenticated a caller. It also means short follow-ups such as
"what about this one?" cannot yet reliably use earlier context.

Phase 10 will add application-owned conversation state and context handling.
Verified tools, real handovers, and deterministic business-day/amount calculations
remain later phases. An `escalate` decision here means review is needed, not that
an agent has been contacted or a ticket was created.

Fallback language uses an explicit override if supplied; otherwise Devanagari
text selects Hindi and other text defaults to English. Successful model replies
can declare English, Hindi, or Hinglish. This simple fallback script heuristic
is not a full language detector or a completed multilingual-support evaluation.

## Try one question

Run from the repository root with the optional model requirements installed:

```powershell
.\.venv\Scripts\python.exe -m zentromart answer "Does a change-of-mind fashion return have a pickup fee?" --topic return_fee --live
.\.venv\Scripts\python.exe -m zentromart answer "Electronics return window?" --topic return_window --category electronics --delivered-on 2026-07-31 --live --json
.\.venv\Scripts\python.exe -m zentromart answer "Fashion return window?" --topic return_window --category fashion --live --json
```

The last example requests placement context without calling Gemini. The CLI
still requires explicit `--live` permission and model configuration for the
answering workflow; use `policy-search` for a credential-free policy-only check.

`--language hi` or `--language hi-en` sets reply language. `--retriever semantic`
or `hybrid` uses the Phase 6 indexes. Here `--offline` applies only to the local
embedding model; Gemini generation still sends data over the network.
`--json` shows the reply, accepted evidence IDs, raw retrieval IDs, empty tool
trace, and a redacted grounding outcome. Do not save real customer replies in Git.

## 5. Measure a small, explicit live sample

```powershell
.\.venv\Scripts\python.exe -m zentromart evaluate --agent gemini --live --suite questions --max-cases 6
```

Gemini evaluation requires both `--live` and a positive row cap. Cases are taken
in existing session/turn order, not selected for success. A conversation can be
cut short by the cap. Reports state available/planned/attempted rows and stop
on the first agent error to avoid repeatedly burning quota after a failure.
The default `evaluate` command still uses the offline clarification baseline.

Each session gets a fresh agent. Expected decisions, facts, and gold evidence
stay in the evaluator; only customer text crosses the agent request boundary.
The agent does not import the evaluator or read practice/reference answers.

Generated reports remain in ignored `artifacts/evals/` folders. They omit prompt,
question, reply, history, key, raw provider errors, and verification values.
They retain metrics, fixed guard outcomes/reasons, token counts, and a whitelist
of model/prompt/index configuration. A deterministic guard fallback is a completed
response, with its own counter; an API error is an error row excluded from
quality means. Neither is hidden as an accepted generated answer.
When a provider error has no reliable attempt count, that trace field is null,
not a misleading zero. Pre-generation fallbacks have zero model attempts.

## Initial verification and results

The six-question original-text development run on 27 October 2026 used Gemini
3.5 Flash-Lite, BM25 top-K 5, the fixed 20 October dataset date, and prompt
`zentromart-grounded-v1`. All six rows completed with zero provider errors.
Five generated drafts passed the gates; one became a citation-mismatch fallback.

| Diagnostic | Result | Denominator |
| --- | ---: | ---: |
| Decision match | 66.7% | 6 rows |
| Declared language match | 100% | 6 rows |
| Mean gold-ID citation precision | 80.0% | 5 scored rows |
| Mean gold-ID citation recall | 50.0% | 5 gold-evidence rows |
| Raw retrieval Hit@5 | 100% | 5 gold-evidence rows |
| Mean required-fact lexical coverage | 33.3% | 6 rows |

These are prefix-sample diagnostics, not full-suite accuracy. The sample is too
small to establish general quality, and its high retrieval hit rate does not
erase missing facts or wrong decisions. Citation recall also shows that finding
at least one source is different from covering all expected evidence.

Separate synthetic pickup-fee checks in English and Hindi each encountered a
citation rejection on an initial call and passed on a subsequent diagnostic call.
Those calls inspected source-ID consistency, not independent semantic quality.
They demonstrate model variability and safe withholding, not guaranteed
multilingual correctness. No automatic retry-on-citation-failure was added.

All 110 automated tests passed, including 20 new grounding/evaluation tests.
They use fake model results and real public documents to cover source scope,
historical exclusions, citation mismatches, no-model fallbacks, language override,
budget rejection, action-confirmation patterns, input separation, bounded runs,
and report redaction. Provider errors remain visible. The prompt/data separation
test is a wiring regression, not a comprehensive adversarial model evaluation.

## Read the code

Start with `src/zentromart/grounding.py`, then `tests/test_grounding.py`.
`policy.py` now exposes original hit IDs; `evaluation/runner.py` adds bounded
selection, early stopping, and redacted outcome counters. `__main__.py` wires
the opt-in commands without changing the default offline workflows.

The prompting approach follows Google's advice to give clear constraints and
structured output, but project-specific precedence and guards belong to our
application. See [Google's prompt design guidance](https://ai.google.dev/gemini-api/docs/prompting-strategies).
