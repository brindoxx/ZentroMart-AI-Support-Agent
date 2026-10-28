# Phase 12 — Streamlit and multilingual replies

The frontend is **Streamlit only**, as requested. This phase combines the old
language and interface phases. It connects the existing support backend to a
usable local chat rather than rebuilding policy decisions inside a page.

## What you can use now

- A native Streamlit chat with English, Hindi, and Hinglish preferences.
- A separate masked verification form that clears the submitted value.
- Session-bound order help, deterministic calculations, and policy-source panels.
- Explicit, separate controls for Gemini public questions and local mock tickets.
- A clear-conversation button that preserves lockouts and model-call limits.

The existing CLI continues to work. The app does not cancel orders, issue
refunds, approve claims, or contact a real support team. Voice comes in Phase 13;
hosting and final release preparation come in Phase 15.

## 1. Why Streamlit needs session state

Streamlit reruns the page script after interactions such as a checkbox change.
An ordinary local variable would disappear on the next rerun. Worse, a shared
global agent could mix different customers' verified records.

`streamlit_app.py` stores a `BrowserSession` in `st.session_state`. Each browser
tab therefore has its own agent, generated session identifier, model budget,
verification ledger, and displayed messages. It does not reconstruct that agent
when a language or consent checkbox changes.

Only expensive **public** inputs are cached: policy/catalog documents and the
holiday calendar, with a five-minute expiry and a bounded cache size. Private
order rows, proofs, agent objects, and chat histories are never put in a shared
Streamlit cache. The page builds a BM25 index per session from that public corpus.
Semantic/hybrid retrieval remain available through the existing CLI; this first
interface uses the established BM25 default without downloading embedding models.

## 2. Two different language paths

Public-policy questions continue through retrieval, policy selection, and Gemini.
The selected language becomes an explicit application preference; a conflicting
language request in a message does not override a selected UI language.

Private replies cannot use model translation: sending an order's refund reference,
amount, or verification proof to a translation prompt would break the intended
privacy boundary. Instead, `localization.py` contains authored sentence templates
for English, Hindi, and Hinglish. Dynamic dates, money, quantities, references,
and commands are preserved as placeholders. Policy evidence IDs are attached
after translation, so changing the language does not change the cited source.

Translation is deterministic: it does not choose a policy, approve a claim, or
recalculate an amount. A missing translation fails to a localized review notice
rather than labeling an untranslated paragraph as Hindi. The sentence adapter is
strict and coupled to the current workflow wording: when a sentence changes,
update its translations and tests together. A future keyed-message refactor
could make that maintenance easier.

In CLI auto mode, Hindi script or a small set of Hinglish signals selects the
language, which is retained through numeric proof turns. The UI always supplies
an explicit preference. Order labels, selected Hindi/Hinglish escalation phrases,
and Devanagari digits are supported. Devanagari digits are normalized to ASCII
before the strict tool boundary; leading zeros remain intact. This is a narrow
router, not a general Hindi/English understanding model. Commands, source IDs,
catalog IDs, and some recorded status labels intentionally remain unchanged.

## 3. Verification and privacy in the page

During verification, normal chat input is disabled and a password-style field
asks for a phone suffix or delivery pincode. A submit callback clears its widget
value before the next render. Display history records only a localized “hidden”
submission marker, not the proof. Executor arguments are cleared after processing
and are never retained in the displayed-history objects.

User display messages also minimize emails, links, and long numeric sequences.
This is a basic safeguard, not complete PII detection. Assistant text and source
text use plain-text display, so a generated Markdown image cannot fetch a remote
URL. There is no transcript export, URL-bound private state, raw tool payload
panel, or provider exception dump.

The backend also blocks obvious phone/pincode/proof submissions and emails on
the public-policy route, including attempts through `/policy`. Valid public
ISO dates remain usable for policy questions. These rules do not guarantee that
every possible sensitive phrase is detected: use only the supplied synthetic
examples, never real personal records.

Clearing the conversation removes its displayed history and private context, but
keeps this session's failed-proof ledger, ticket deduplication, and model budget.
Changing the language does not clear any of those safeguards. Closing the browser
or starting a new session can still bypass a session-local mock limit; production
authentication, cross-session throttling, and persistent idempotency are not built.

## 4. Separate consent and model quota controls

Both sidebar checkboxes start off:

1. Public-policy Gemini access permits public questions and bounded public memory
   to leave the device. The client and existing `.env` key load lazily only when
   a model call is actually requested. Verification and calculations work offline.
2. Local mock ticket creation permits appending to ignored `artifacts/tickets/`.
   It does not notify a real support team. The normal tool success/failure gates
   still apply; enabling a checkbox is not proof that a ticket was created.

The browser session permits at most 20 model generation attempts. Existing
provider-level bounded retries are separate, so this is not an exact HTTP-call
or token limit. Failed generation attempts consume the budget; provider or
configuration failures pause further model calls in that session. Clearing chat
does not restart the budget. Order workflows remain usable while model access
is off or paused. The cap is a local demonstration guard, not account-wide quota
management or a production spending limit.

Your existing ignored `.env` continues to work; do not paste its key into chat.
The UI prefers Streamlit's server-side `st.secrets["llm"]` when configured, with
`provider`, `model`, and `api_key` fields; `.streamlit/secrets.toml` is already
ignored. No new secret file was created or key copied in this phase. The app
does not add a credential-entry box or change the model. A future hosted setup
must supply secrets server-side and add appropriate authentication.

## 5. Run and explore

From the repository root in PowerShell:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-ui.txt
.\.venv\Scripts\python.exe -m streamlit run streamlit_app.py
```

Open `http://127.0.0.1:8501`. The committed configuration binds only to loopback,
disables usage telemetry, and hides raw exception details. The native theme is
adapted from Streamlit's bundled Fluent example with a teal accent and local
system fonts: no separate frontend framework, injected CSS, or remote font load.

Try these separately:

1. With Gemini off, choose a language and check a supplied synthetic order. Enter
   the ID first, then the requested proof in the masked form. Do not guess other
   customers' details.
2. After verification, ask about delivery/refunds or use `/items`, `/item 1 1`,
   and `/reason change_of_mind` to explore conditional arithmetic.
3. Change languages and inspect whether dates, amounts, and source IDs stay the
   same. The selected preference affects new replies; old history is not rewritten.
4. Use the clear button and verify that no previous private record is displayed.
   Failed verification limits must still apply in the same session.
5. Enable Gemini only when ready to use API quota and ask a general policy
   question through `/policy`. Some missing-fact clarifications need no model call.
6. Enable mock tickets separately only when testing local ticket creation.

There is no microphone or audio upload yet. The interface makes no implied
promise that voice, hosting, or real customer authentication are already ready.

## 6. Verification and results

Verified environment: Python 3.13 and Streamlit **1.66.1**, with a bounded UI
dependency range in `pyproject.toml`. The full suite passes **198 tests**, including
20 new Phase 12 tests. Streamlit tests use its built-in `AppTest`: they run the
page and interact with widgets without starting a server or consuming API quota.

Tests cover template placeholders, language preferences, Hindi order labels and
digits, same-session lockout across language changes/clears, session isolation,
masked proof clearing, no proof in display history or saved executor arguments,
default-off consent, lazy key loading, model error pauses, generation limits,
and selected-language public replies with no verified records in their prompts.
The earlier workflow scenarios also run through both translation catalogs to
catch missing sentences. The supplied dataset validator and dependency checks
pass; supplied dataset files remain unchanged.

The same inspected six-turn development prefix from Phase 11 was evaluated with
model generation explicitly forbidden. All six turns completed with no errors:

| Diagnostic | Phase 11 | Phase 12 |
| --- | --- | --- |
| Decision match | 6/6 | 6/6 |
| Declared reply-language match | 0/6 | 6/6 |
| Expected tool-call match | 5/6 | 5/6 |
| Required-fact lexical coverage, five applicable rows | 60% | 60% |
| Gold citation precision / recall | 25% / 38.9% | 25% / 38.9% |

The missing expected tool call is the deliberately disabled ticket writer. No
private workflow in this sample called retrieval or Gemini. This is a development
regression check, not held-out evidence or a complete end-to-end benchmark.
Language declarations and placeholder preservation do not prove fluent or
semantically perfect translation; wider language and fluent-speaker review remain
needed. Live public-policy generation was not retested against the real Gemini
API in this phase. Its language path was checked using deterministic model stubs.

AppTest does not verify actual browser responsiveness, font rendering, scrolling,
or visual polish. Browser visual review should follow when the app is launched.
No server was started automatically. The next phase is **13: Gnani voice**; Phase
14 still needs broader evaluation and improvements, especially citation selection
and fact coverage, before Phase 15 deployment/report/demo preparation.
