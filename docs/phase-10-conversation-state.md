# Phase 10: remember the conversation without treating memory as proof

## Why we need this phase

In Phase 9, every question stood alone. After "How long do UPI refunds take?",
the follow-up "And cards?" did not have an application-owned way to refer back
to refunds. Likewise, a customer answering "electronics" after a category
clarification needed the application to remember what it had asked.

`ConversationalAgent` now wraps the existing grounded answering flow. It keeps
small, structured state in Python memory, updates it conservatively from customer
text, retrieves fresh evidence, then uses the existing Gemini/citation guards.
The original one-shot `answer` and stateless `gemini` evaluator remain available.

This is not fine-tuning, a permanent user profile, a database, or a new model.
It is application code deciding what context to carry from one turn to the next.

## 1. What state contains

The dataclass holds the bound session ID, current policy topic/category/SKU,
explicit scenario dates, a claimed order ID if recognized, language preference,
missing context fields, a turn counter, and a bounded customer-memory window.
Sensitive/session/context fields are excluded from its representation.

Every category, date, SKU, and order ID extracted from customer text is an
unverified claim. Catalog lookup can resolve a SKU's public category, but it
proves neither ownership nor the delivery date of a customer's order.
`verification_status` is a read-only `not_connected` property. There is no
verification setter, proof checker, private-table read, or order tool in this phase.

An application-owned session ID associates turns. It does not authenticate a
person. One agent instance binds to one session and rejects a different session
until explicitly reset. A real multi-user service will still need authenticated
session ownership, expiry, access control, concurrency handling, and secure storage.

## 2. Own memory instead of trusting replayed history

`AgentRequest.history` is deliberately ignored by this adapter. A client cannot
inject an earlier "assistant verified this order" message and gain privileges.
The agent builds its own memory from customer messages it actually processed.

It keeps at most four recent customer turns, each at most 1,500 characters.
An overlong memory turn is dropped as a unit, not truncated mid-clause. Email
addresses, URLs, and long numeric sequences are minimized before storage and
forwarding. This is a basic regex-based measure, not comprehensive PII detection:
names, unusual formats, and other sensitive text can remain. Use synthetic data
for this capstone; it is not ready for real customer conversations.

Current questions still follow the existing Gemini input path. Minimizing past
memory does not mean the current customer message has been fully redacted.
The claimed order ID is not added as a structured model field; a current message
that contains one can still reach Gemini as customer text, as in Phase 9.

Assistant replies never enter this memory window. A previous answer is not
policy evidence, and its claims cannot verify a caller or authorize an action.
Earlier customer messages are passed separately as untrusted data, with explicit
memory instructions. They are not added as system instructions or citation sources.

## 3. Gather missing facts across turns

The parser recognizes a small set of support-topic keywords, product categories,
public SKU forms, labeled ISO dates, and explicit language preferences. These
are deterministic patterns, not a trained NER model or general intent parser.
Unrecognized wording can still require rephrasing or an explicit reset.

A typical supported flow is:

| Customer turn | Application behavior |
| --- | --- |
| "I want to return an item" | Set return-window topic; ask for category |
| "electronics" | Remember category; ask for delivery date |
| "2026-07-31" | Fill the requested date; apply the historical-window rule |
| "Actually delivered on 2026-08-01" | Replace the date and recheck current-policy applicability |

Category/date collection makes no model calls while required facts are missing.
A bare ISO date is accepted only when that date field is pending. Otherwise use
a label such as `delivered on 2026-07-31` or `placed on 2026-10-15`.

Slash dates, relative dates such as "yesterday", invalid/future dates, conflicting
date values, and reversed placement/delivery order are not guessed. Invalid
corrections clear the affected remembered date rather than silently reusing it.
Date checks use the frozen dataset reference date, 20 October 2026, not today's
computer date. A typed initial scenario can also receive its missing date later.

## 4. Clear stale facts when the subject changes

A different recognized category or SKU clears old scenario dates and customer
memory. A changed recognized order ID does the same, even if the new product
category is unchanged. Explicit phrases such as "a new order" or "another
product" also clear the previous scenario. Multiple recognized items/orders
trigger a one-item clarification instead of choosing one arbitrarily.

A topic switch conservatively clears scenario facts and memory too. This can
require the customer to repeat information, but avoids carrying an old item's
delivery date into an unrelated warranty/refund question. Language preference
can survive a topic/item switch. `/reset` clears session claims and memory,
restoring only the CLI's configured default language if one was supplied.

Detection is deliberately narrow: natural-language corrections, multilingual
order references, negations, and multi-intent messages are not comprehensively
understood. If an unrecognized switch leaves ambiguous context, use `/reset`.
Do not interpret this parser as production-grade entity or reference resolution.

## 5. Retrieve again rather than recycling old evidence

Each valid turn runs retrieval and policy preparation again. For a short
same-scenario follow-up, the most recent minimized customer turn augments the
retrieval query. A known public SKU is also added to the query. Up to four
earlier customer turns can help Gemini interpret the current question.

The current policy context goes through the same applicability checks as Phase 7.
Changing an electronics delivery date from July to August excludes the old
window passage on the next turn. A model that still cites it is rejected by
the existing Phase 9 supplied-source guard. No previous evidence IDs are blindly
reused, and memory itself is never a valid citation source.

The combined prompt keeps the existing 48,000-character limit. Over-budget input
gets a clarification; we do not cut policy exception clauses to make room.
There is no extra LLM call for topic or slot extraction, helping preserve quota.

## Try the chat

```powershell
.\.venv\Scripts\python.exe -m zentromart chat --live
```

Try `How long do UPI refunds take?`, followed by `And cards?`. Then type `/reset`
and try the category/date sequence above. `/quit`, end-of-input, or interruption
ends the chat; the application clears its in-memory agent on exit. It writes no
transcript file. Terminal/OS logging policies are outside that guarantee.

`--language hi` or `hi-en` can set the starting language. Recognized explicit
preferences and Hindi script can update it; short follow-ups retain it. This is
not a full multilingual language detector. The existing model language/citation
checks still apply. `--retriever hybrid --offline` uses cached local embeddings,
but Gemini remains online. `--live` is always required to start the chat.

A provider error ends the CLI chat instead of repeatedly submitting more turns
after exhausted quota. Customer claims already in state do not become verified
because of an API error. The API's own bounded transport retries remain unchanged.

## Evaluation and verification

```powershell
.\.venv\Scripts\python.exe -m zentromart evaluate --agent gemini-stateful --live --suite conversations --max-cases 6
```

This opt-in adapter uses the existing evaluator's fresh-agent-per-conversation
factory. `--max-cases` remains mandatory, and the run stops at the first agent
error. A cap can truncate a conversation. Reports record configuration/version
and safe outcome counters, not memory, slots, raw order IDs, prompts, or replies.

Keep results separate from stateless `--agent gemini`: query augmentation and
memory make this a different agent configuration. Tools are still absent, so
conversation/tool scores cannot establish order-workflow readiness.

The synthetic live verification on 27 October 2026 had six turns and only three
generation calls. The first refund question and its card follow-up both produced
accepted replies citing `REF-2`. Reset, category collection, and date collection
made no generation calls. The final historical-return draft was withheld for a
citation mismatch. This demonstrates context flow and guarded withholding, not
perfect answer quality. No automatic retry-until-citations-pass was added.

Google reported 1,742, 1,837, and 2,038 total tokens for those three calls: 5,617
in total. No raw reply or transcript file was saved. Verification remained
`not_connected` on every turn, and the final reset cleared session and memory.
This was a synthetic integration check, not a scored conversation-suite benchmark.

All 139 automated tests passed, including 29 conversation tests. They cover
missing-fact collection, follow-up retrieval, corrections, topic/product/order
switches, session binding/reset, forged history, memory budgets/minimization,
language preference, provider failures, evaluator isolation, and CLI shutdown.
They use fake model results and public sources without loading user API keys.

## Where to read next

Start with `src/zentromart/conversation.py` and `tests/test_conversation.py`.
`grounding.py` accepts bounded earlier-customer context and a retrieval query;
its stateless defaults are unchanged. `policy.py` exposes public scenario
validation without opening private tables. `__main__.py` wires chat and the
separate stateful evaluation choice.

Phase 11 will add the supplied identity-checked mock order tools. Remembered
order IDs, customer statements, and prior model replies must never bypass those
tool gates. The dataset's mock verification is itself not production-grade auth.
