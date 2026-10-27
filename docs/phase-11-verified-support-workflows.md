# Phase 11 — verified support workflows

This combined phase covers the former phases 11–13: order verification, human
handover tickets, and deterministic calculations. The goal is to move from
explaining general policies to helping with a particular synthetic order without
letting a language model authorize access or invent an action.

## 1. The trust boundary

Public questions still use the conversation/retrieval/Gemini pipeline. Private
questions take an application-owned path:

1. Ask for one eight-digit order ID and make the initial unverified mock lookup.
2. Ask for one four-digit registered-phone suffix OR six-digit delivery pincode.
3. Validate the submitted shape and check it with the supplied lookup tool.
4. Bind the verified result to this order and session.
5. Render only approved fields or calculate from verified facts and policy rules.

The model never receives private order rows or verification proofs and cannot
select or execute these tools. A previous assistant statement such as “verified”
is not evidence. Caller-supplied history cannot restore verification. Switching
orders clears the old record, selected item, quantity, and reason.

`tools.py` wraps the supplied `dataset/tools/tools.py` without editing it. It
allowlists needed fields and removes contact details, address, customer identity,
and the verification pincode. Even a backend that accidentally returns an order
before proof is reduced to a generic verification-required result.

## 2. Verification is deliberately limited

Unknown orders and wrong proofs receive the same failure wording. Full phone
numbers and multiple candidate proofs are not silently converted into valid
proof. Leading zeros are preserved. Conversational labeling is accepted only
when one clear candidate can be extracted, including “last four digits … hain”.

Two failed submissions lock that order for this session. Malformed submissions
also consume an attempt. `/reset` clears private context but preserves failed
attempts and ticket deduplication. A new backend session needs a new agent object.
The implementation also caps the number of tracked orders/tickets per session.

This is synthetic educational verification, **not secure real-world login**.
There is no OTP, persistent rate limit, cross-session lockout, or production
identity service. Knowing a suffix or pincode must not be treated as sufficient
authentication for a real retailer.

## 3. Human review without invented success

The router detects human requests, safety issues, unauthorized activity, legal
requests, high-value damage, repeat contacts, and qualifying overdue refunds.
An unverified handover omits the claimed order ID. A verified handover can include
the bound order ID, detected intent, checks performed, and escalation reason.
Summaries are fixed structured descriptions: no proof or raw customer message.

Ticket writing is off by default. With explicit `--write-tickets`, the supplied
mock tool appends to `artifacts/tickets/tickets_created.csv`, not the dataset.
Only a successful tool response containing a valid ticket ID allows the reply to
confirm creation. A failed or uncertain write is not automatically retried: it
might already have appended a row before failing. Repeated requests reuse the
session result instead of generating duplicate tickets.

These are local mock records, not real human contact. The assistant has no tool
to cancel an order, approve a replacement, or issue a refund. It guides customers
to My Orders where appropriate and labels calculations as estimates.

## 4. Why calculations belong in code

The model should explain policy, not decide arithmetic. `calculations.py` provides
small testable functions for return windows, pickup fees, coupon allocation,
refund estimates, and refund deadlines.

- Return windows use the item category plus the existing policy engine's narrow
  historical and festive exceptions. Existing return requests are assessed on
  their recorded request date, not automatically rejected because today is later.
- The chosen date convention treats delivery as day zero and includes the
  resulting calendar deadline. Policy wording does not completely settle ordinal
  counting; this convention is explicit and tested, not an unstated certainty.
- Business days are Monday–Saturday excluding the supplied holidays. Initiation
  day is excluded when adding business days. The maximum expected date is
  inclusive; escalation requires **more than three** business days beyond it.
- Refund timing starts from a recorded initiation date, not a guessed pickup or
  delivery date. Missing completion alone does not prove nonpayment: overdue
  routing also requires the customer's report that the refund has not arrived.
- An estimate requires one selected item line, a valid quantity, and a classified
  reason. Duplicate SKUs require a line selection. Unknown reasons do not cause a
  guessed pickup fee. Membership controls the applicable fee waiver.
- Coupon discount is allocated proportionally. When the remaining gross basket
  falls below the coupon minimum, the remaining coupon discount is clawed back.
  Whole-order fee refunds follow their specific policy conditions.
- Decimal arithmetic rounds once at the end to whole rupees using half-up
  rounding. A negative result requires review; it is not presented as a debt.

For example, a synthetic ₹500 selected quantity from a ₹1,000 basket with a ₹100
coupon receives ₹50 allocated discount. If the remaining basket loses coupon
eligibility, another ₹50 is clawed back. With a ₹49 fashion pickup deduction, the
estimate is ₹351. This is arithmetic, not refund approval.

Missing grocery slot times, unrecorded bank verification, and date-only wallet
initiation cannot establish exact deadlines. The workflow asks or qualifies its
reply rather than manufacturing those facts. All calculations use the dataset's
frozen reference date, **2026-10-20**, not the computer's current date.

## 5. Keeping rules aligned with evidence

The adapter fingerprints the selected policy text and authority metadata. A
changed policy snapshot fails closed until its deterministic rules are reviewed.
The loaded holiday table must also agree with the public calendar source. Reports
include rule versions and policy/calendar hashes for reproducibility.

Do not update a hash merely to suppress a failure. Read the changed policy,
update the relevant logic and boundary tests, then intentionally accept the new
snapshot. This prevents an updated document from silently contradicting old code.

## 6. Try it locally

From the repository root in PowerShell:

```powershell
.\.venv\Scripts\python.exe -m zentromart chat --support --live
```

Use a synthetic order from the supplied examples. Enter its ID first, then its
requested proof when asked. Never use a real customer's details. Useful commands:

- `/items`: show verified line numbers, SKUs, and quantities.
- `/item 1 1`: select line 1 and one unit, without assuming the whole line returns.
- `/reason change_of_mind`: explicitly classify a proposed return; it is not approval.
- `/policy What is the return window?`: clear private context and ask a public question.
- `/reset`: clear the conversation, retaining this session's lockout safeguards.
- `/quit`: exit.

Add `--write-tickets` only to try local ticket creation. Gemini is configured for
public fallback, so `--live` is required even though verification and calculations
themselves use no API calls. No conversation transcript is saved. Verification
arguments exist transiently in executor traces for scoring; do not print or save
them. Standard reports omit arguments, messages, replies, and private payloads.

## 7. What was tested and what still needs work

The full offline suite passes **178 tests**, including 39 new workflow/calculation
tests. Coverage includes lockout after reset, unknown orders, malformed proofs,
order switching, forged history, session isolation, ticket failure and uncertain
writes, fee waivers, coupon clawback, half-up rounding, historical/festive dates,
holiday arithmetic, strict overdue boundaries, and report redaction. Integration
tests use the supplied synthetic lookup and write an actual mock ticket only in
an isolated temporary directory. No supplied data or tools were edited.

A bounded six-turn conversation-development run initially stalled because labeled
order IDs and proofs were parsed too narrowly. Reviewing minimized inputs exposed
the routing gap. The parser was extended and regression-tested without allowing
arbitrary number extraction or sending private messages to the model.

The final run (`20261027T181229Z-be1789cb`) completed all six turns without errors
and without Gemini calls:

| Diagnostic | Result | Meaning |
| --- | --- | --- |
| Decision match | 6/6 | Clarification, answer, or escalation matched the target |
| Expected tool calls | 5/6 | One expected ticket was intentionally disabled |
| Declared language match | 0/6 | Private replies are English; this prefix expects Hinglish |
| Required-fact lexical coverage | 60% of five applicable rows | Reply detail still needs improvement |
| Gold citation precision / recall | 25% / 38.9% | Policy-ID selection needs review and improvement |

Private flows do not call the retriever; zero raw retrieval hits on this run do
not measure BM25 quality. This repeatedly examined prefix is development feedback,
not a held-out benchmark or proof of production readiness. Ticket success is
separately tested with isolated writes; a disabled-write evaluation is not a
successful end-to-end handover demonstration.

Private rendering is currently fixed English and intent recognition is narrow.
Phase 12 adds multilingual replies and the web interface. Phase 13 adds Gnani
voice, Phase 14 broadens evaluation and improvements, and Phase 15 prepares
deployment, the report, demonstration, and release. These correspond to the five
combined phases agreed after Phase 10.
