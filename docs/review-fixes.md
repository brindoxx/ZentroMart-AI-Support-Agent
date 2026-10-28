# Review-driven correctness and usability audit

This pass addresses the user's issue list and return-help screenshot. It does not
claim that live Gnani validation or the broader held-out evaluation is complete.

| Finding | Audit and action |
| --- | --- |
| Demo tickets silently disabled | Not reproduced in the original create call: it already enabled its wrapped writer. Made consent an explicit delegating property so both enable **and revoke** immediately reach the real writer. Added an isolated real CSV write through BrowserSession, not just a mocked success. |
| Cancellation/RTO completion hardcoded away | Calculator and gateway now accept optional route-specific completion dates and validate them. The supplied CSV has only `return_refund_completed_on`; missing completion is **unknown**, not proof of nonpayment. Do not manufacture dates from cancelled/RTO statuses. |
| Voice stuck after bad input/key | Invalid audio was already checked before the blocking try/except. Added recovery tests; moved missing-key loading before attempt accounting/blocking, and validate language locally. Service errors still pause requests, but an explicit retry button resumes without resetting the attempt limit or making a request itself. |
| Prices and dates redacted | Shared context-aware minimization preserves ISO dates and labeled monetary facts; labeled identities and other long numeric sequences are still minimized. Proof-stage submissions remain hidden as a whole. This is best-effort minimization, not complete PII detection. |
| Browser accesses `_calls` | Replaced external private-field assignment with `SupportAgent.clear_tool_trace()`. |
| Frozen document has mutable metadata | Copy metadata into an immutable scalar-only mapping. Public serialization exports detached dictionaries; pickle reconstruction preserves immutability for Streamlit caches. |
| Stale `verification_status` | Removed from the public conversation state. Its capability configuration correctly reports no private verification; the outer support workflow owns actual verification. Slotted state cannot accept a forged dynamic verification attribute. |
| Untyped failure/ticket maps | Added `dict[str, int]` and `dict[str, str | None]` annotations. |
| Repeated discarded GroundedAgent objects | Previously one real answerer per turn plus discarded startup/configuration instances, not three per turn. Extracted validation/configuration helpers and reused the session's validated PolicyEngine. Only one answerer is constructed for an actual public turn. |
| Linear translation scan | Static sentences use a dictionary lookup. Formatted sentences retain placeholder validation and use small first-word buckets instead of scanning the full catalog. No cache retains private rendered strings. |
| UUID chunk IDs break hashing | Not reproduced: `chunk_id=section_id` was already deterministic. UUIDs name separate output runs. Tests prove repeated corpus payloads and hashes are identical while output directories differ. Keep collision-safe run folders. |
| Zetro/Zentro names | Corrected the Python distribution name. Branding/imports were already ZentroMart/zentromart. Kept the existing checkout folder and Git remote intact rather than breaking running tools and historical paths. |
| Minimal default requirements | `requirements.txt` now installs UI, model SDK, and voice dependencies. `requirements-core.txt` preserves the lightweight offline option. Semantic models remain optional to avoid an unnecessary large download. |
| Streamlit pin blocks patch releases | The old `<1.67` already allowed 1.66.x patches; it blocked the next **minor** release. Relaxed to `<2`; current tests use installed 1.66.1. This is not a guarantee about every future 1.x release. |

## Customer-facing conversation

The previously mechanical “provide the product category to choose a policy” is
replaced by a concrete question: “What item would you like to return?” followed by
clothing/electronics/book examples. “A shirt” is recognized as clothing; the next
question asks when the order was placed, retaining the correct festive-policy
distinction between placement and delivery dates. One missing fact is requested
at a time, in English, Hindi, or Hinglish. Ordinary clarification is labeled a
quick question instead of an error-like fallback.

These prompts do not require a model call. Gemini still explains supported public
policy facts when enabled; verified order access, arithmetic, and approvals remain
separate. Warmer wording never grants authorization or changes a refund amount.

## Verification

All **228 tests pass**, including 17 new regression tests in
`tests/test_review_fixes.py`. Dependency checks and the supplied dataset validator
pass; BM25 remains 38/47 Hit@5. No live Gemini/Gnani calls or user credits were
used. The dataset is unchanged. The renamed editable package was installed and
the old misspelled registration removed; source files were retained.

The new tests exercise real isolated mock
ticket writes and revocation, completion and missing-data cases for all refund
routes, bad-input and missing-key voice recovery, explicit retry and preserved
budgets, public-fact/identity minimization, metadata mutation/pickle/JSON behavior,
constructor counts/engine reuse, deterministic corpus artifacts, dependency
configuration, and the screenshot's Streamlit return flow without API calls.

Restart Streamlit once after upgrading so previous agent instances and cached
document objects are replaced. This does not constitute production authentication;
continue using synthetic data only.
