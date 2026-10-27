# Phase 7: choose the right policy evidence

## What we are building and why

Our eventual agent should give useful support answers grounded in ZentroMart's
policies, not merely repeat a passage that sounds similar to the question.
Phases 5 and 6 found relevant text. This phase prepares the evidence a future
answering model can use, with authority and applicability made explicit.

A search score measures relevance, not permission to apply a policy. A generic
FAQ can match a refund question perfectly while omitting payment-specific timing.
A historical returns document can match a pickup question while no longer being
the governing policy. Improving embeddings alone does not fix those problems.

We now have a deterministic `PolicyEngine` and a `policy-search` command. Neither
generates customer replies nor executes order actions.

## The evidence pipeline

```text
Query + explicit topic/scenario facts
    -> existing BM25, semantic, or hybrid top-K
    -> attach relevant topic sections and curated policy dependencies
    -> check effective dates and narrowly scoped historical exceptions
    -> order by authority; label exceptions, uncertainty, and provenance
    -> evidence bundle for a future answering layer
```

The engine uses only the existing public corpus: policy/support sections and
allowlisted product fields. It does not open customer tables, order records,
practice questions, or reference answers. Scenario facts supplied through this
developer-facing command are not verified customer information.

## 1. Separate relevance from authority

`KB-00.1` gives the authority order: current policy, agent guide, help document,
FAQ, then marketing. We apply it to retrieved evidence and attached dependencies,
not to every document in the corpus. An unrelated policy should not rise just
because its document type has high authority.

For example, retrieving `FAQ-1` attaches `REF-2` and `REF-3`. The detailed refund
policies come before the FAQ. Retrieving the Plus marketing section attaches
`PLS-1` and `PLS-2`; promotional wording cannot expand policy benefits.

The dependency map is curated from the supplied sources. It is not an automatic
contradiction detector and contains no question-specific practice-answer rules.
Explicit topics also provide anchor sections when a query misses important
words. Later application code must identify the topic; this phase does not
classify arbitrary customer language into topics.

## 2. Preserve historical rules only within their stated scope

`RET-3` explicitly preserves the previous electronics return window for items
delivered before 1 August 2026. That exception is based on delivery date, not
order placement. The engine reads the cutoff from the policy text and checks
the historical/current document version links.

| Electronics delivery date | Evidence treatment |
| --- | --- |
| Before 1 March 2026 | Outside supplied historical coverage; review required |
| 1 March through 31 July 2026 | `RETv3-2` governs the historical window, supported by `RET-3` |
| 1 August 2026 onward | Current window; exclude the superseded section |
| Not supplied | Request delivery context; do not unlock historical evidence |

The historical policy became effective on 1 March 2026. We do not assume its
coverage extends further into the past. Nor do we revive its old free-pickup
statement (`RETv3-6`): preserving a return window does not preserve every clause
in the old document. Current pickup policy remains relevant.

The old window is a governing historical source; the conflicting current
general window is labeled background for that scenario. Both texts remain
traceable instead of silently editing or rewriting a source.

## 3. Use the correct date for festive fashion returns

`RET-8` gives fashion orders placed from 1 October through 15 October 2026 a
30-day-from-delivery window. Both placement boundaries are inclusive.

Here, placement date decides eligibility for the extension; delivery date is the
future deadline calculation's starting point. An order placed on 15 October can
qualify even if delivered after that day. A placement on 16 October does not.

If placement date is missing, the result is `needs_context` and the relevant
window sections are labeled conditional. This phase selects the rule; it does
not calculate the final calendar deadline or decide if an order is returnable.

## 4. Keep catalog facts below policy decisions

Some public product rows have an Assured badge despite marketplace fulfillment.
`MKS-3` explicitly excludes marketplace products from Assured benefits.

For `ELE-0004`, the engine derives category and seller from the public catalog,
puts `MKS-3` first, and labels `WAR-2` as limited by the marketplace exception.
The badge stays visible as a catalog fact, not an eligibility decision.

Without a SKU, marketplace applicability remains `conditional_on_seller`.
A general warranty explanation can remain conditional; the engine does not
pretend to know the customer's seller. Public SKU lookup is not order lookup
and proves no ownership or caller identity.

## Try the command

Run these from the repository root in PowerShell:

```powershell
.\.venv\Scripts\python.exe -m zentromart policy-search "electronics returns" --topic return_window --category electronics --delivered-on 2026-07-31
.\.venv\Scripts\python.exe -m zentromart policy-search "electronics returns" --topic return_window --category electronics --delivered-on 2026-08-01
.\.venv\Scripts\python.exe -m zentromart policy-search "fashion returns" --topic return_window --category fashion
.\.venv\Scripts\python.exe -m zentromart policy-search "Assured warranty" --topic warranty --sku ELE-0004 --json
.\.venv\Scripts\python.exe -m zentromart policy-search "Nobody collected my return" --topic pickup --retriever semantic --offline
```

The first two examples switch between historical and current evidence. The
third asks for placement context instead of guessing the festive extension.
The fourth exposes the full structured warranty evidence. The final command
requires the optional semantic installation and previously downloaded model.

All scenario dates must be on or before the frozen dataset date, 20 October
2026. Future dates, reversed placement/delivery dates, unknown SKUs, and category
conflicts are rejected. The machine's current date does not change these rules.

## Read the evidence bundle

The JSON includes rule version, reference date, index configuration and corpus
fingerprint, applicability states, required context, full source text/metadata,
excluded sections with reasons, and dependency links.

Each entry records its origin: `retrieved`, `topic_anchor`, or
`policy_dependency`. Only actual search hits have a retrieval rank, score, and
score type. Attached sources have null retrieval fields; attaching them must
not be reported as a retrieval improvement.

`--top-k` limits raw search hits, not the expanded evidence bundle. The engine
preserves sources and gives the future generator structured guidance rather
than merging conflicting documents into an invented policy.

`evidence_prepared` means this preparation step completed, not that an answer is
correct or a request is approved. `needs_context` identifies missing scenario
facts. `review_required` blocks unsupported historical coverage or unavailable
required policy evidence, including an empty usable bundle; a lower-authority
FAQ is not a substitute.

## Tests, limitations, and the next phase

The policy regression tests control ranking while using real public passages.
They test English/Hindi FAQ conflicts, marketing, historical boundaries, festive
boundaries, marketplace badges, provenance, invalid context, unavailable sources,
and deterministic operation without private file access. They do not establish
end-to-end answer accuracy. Existing retrieval benchmarks remain unchanged.

Verification completed with all 70 automated tests passing, including 17 policy
tests. The dependency check and supplied dataset validator passed too. A fresh
BM25 evaluation retained Hit@5 of 38/47 (80.9%). An offline real-model check of
"Nobody collected my return" retrieved the historical `RETv3-2` passage, then
excluded it from the pickup bundle and attached current pickup evidence. This
is a concrete integration check, not a new benchmark score.

This is a dataset-specific policy adapter, not a general legal/rule engine.
Its curated links and explicit applicability branches need review when source
rules change. Recognized date-format or version-link changes fail explicitly;
arbitrary wording changes still require human review. Not every possible
conflict is automatically detected.

No LLM, automatic intent extraction, conversation state, identity verification,
order tools, financial/deadline calculation, or interface is added here.
Phase 8 introduces model integration; Phase 9 will connect evidence to grounded
customer-facing replies. This separation lets us test policy handling before
asking a model to explain it.

Start reading `src/zentromart/policy.py`, then `tests/test_policy.py`, and finally
the `policy-search` branch of `src/zentromart/__main__.py`.
