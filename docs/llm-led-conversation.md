# LLM-led conversation

## What changed

The Streamlit app's Gemini switch now enables `LLMConversation`, rather than
using Gemini only after rule-based questions have collected every field.
Restart the app after updating, clear the old conversation and enable **Use
Gemini for natural conversation**. Consent remains off by default.

Try greeting the assistant, asking to send something back, then describing an
item in your own words. Gemini writes the question, interprets the item and
chooses whether to ask another question, retrieve evidence, request an order
workflow or hand over. This also applies to delivery, refund, membership and
other supported topics—not only returns. English, Hindi and Hinglish use the
selected reply language.

## How a turn works

1. The application intercepts order IDs, verification proofs, pending verification,
   explicit commands and known urgent safety requests before calling Gemini.
2. Gemini receives minimized customer wording, up to four earlier public customer
   messages, the previous public question, public scenario fields and the frozen
   dataset date. It never receives verified order rows, proofs or executor arguments.
3. Gemini returns a typed proposal: respond, clarify, search, order or handover.
   The application checks its schema, language, category/SKU and scenario dates.
4. A greeting or clarification uses Gemini's wording, subject to structural and
   action-claim guards. A factual policy answer goes through fresh retrieval and
   the existing grounded answerer, with evidence checks and citations.
5. Personalized requests route to application-owned workflows. The model cannot
   verify identity, execute arbitrary tools or approve refunds. Backend results
   determine private facts, calculations and actual mock ticket success.

Example: “a blouse” can become the public category `fashion` without adding
`blouse` to an item keyword list. The model can then ask when it was ordered.
Policy applicability still uses validated dates and the supplied company rules.
The reference date remains **20 October 2026**, not today's date.

## What remains deterministic

Authentication gates, lockouts, explicit commands, private record access,
refund calculations and truthful action confirmations remain backend-owned.
Their local replies are not falsely presented as model-written. Gemini-assisted
routing has its own caption. Cloud-off mode retains the older local behavior.
Existing CLI/evaluation modes are unchanged for baseline comparison.

This separation is intentional: an LLM chooses conversational steps, but its
proposal is not permission to access a record or evidence that an action occurred.

## Cost and recovery

Planning and grounded answers share one 20-generation browser-session budget.
A simple greeting or clarification uses one generation. A policy answer normally
uses a plan plus an answer; a plan missing required context may instead use a
second planning generation to ask for it. Provider retries remain separately
bounded by existing configuration. There is no automatic model substitution.
Clear, language changes and demo switches do not reset usage or lockouts.
Provider/configuration failures pause further model calls in that session;
disable Gemini to use the offline workflows while checking configuration.

## Verification and limitations

Contract tests reject model-proposed verification, arbitrary tools, malformed
fields and invalid dates. Controller tests cover model-authored questions,
non-return grounding, missing context, fake action confirmations, private-data
exclusion and lockouts. Browser/AppTest checks cover consent, shared budgeting,
privacy, source switching infrastructure and the greeting/return/blouse flow.

A bounded live check on 28 October 2026 made two planner requests to the locally
configured Gemini model, without retries or private data. It returned a generated
greeting and asked when the blouse was ordered. No ticket was written and no
Gnani credits were used. This confirms connectivity and the new schema, not
comprehensive dialogue accuracy or provider availability guarantees.

Minimization is not comprehensive PII detection: use synthetic data only.
Conversational wording guards are not semantic proof that every model sentence
is correct. Factual answers require the evidence path, but wider adversarial and
multilingual evaluation remains part of Phase 14. Backend private responses are
still controlled templates; this change does not claim every reply is generated.

## Incremental commits

- `7752199`: typed model proposals and schema-aware transport, tested then pushed.
- `4d01339`: model-led controller and guarded dispatch, tested then pushed.
- App integration: session routing, consent, honest labels, shared budget and UI
  regressions; committed only after the integration checks.
