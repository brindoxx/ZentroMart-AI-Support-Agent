# Phase 13 — voice and a usable guided demo

## Why the screenshot looked robotic

Previously, “hello” reached a policy search. Without policy evidence, the agent
returned a generic clarification before calling Gemini. Order-status questions
also avoid Gemini deliberately: verification is application code, not a model's
decision. Enabling Gemini permits model calls; it does not force one on every turn.

Greetings and thanks now have natural local responses in all three languages.
The initial order-ID request is warmer. Public Gemini instructions also request
concise, natural support language without pretending to be human or promising an
unsupported outcome. Private calculations and tool gates remain deterministic.
Source brackets are hidden from displayed prose but available in the source
panel and unchanged in backend responses. Captions disclose which path replied.

## Five-minute walkthrough

Restart the running Streamlit process once to load the new agent classes and UI:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-voice.txt
.\.venv\Scripts\python.exe -m streamlit run streamlit_app.py
```

1. Say `hello`. Expect a greeting, not a missing-policy error. The caption says
   it was handled locally without Gemini.
2. Enable **Use guided demo orders**. Choose a scenario and click **Start this
   example**. Enter its test suffix when the masked verification form appears.
3. Ask the suggested follow-up. For the return example, the selected one-unit
   estimate is ₹351: ₹500 gross − ₹50 allocated coupon − ₹50 coupon clawback −
   ₹49 pickup fee. It is not approval or payment.
4. To see Gemini, enable public-policy access and ask
   `/policy How long do UPI refunds take?`. An accepted generated answer is
   labeled Gemini. A rejected/unavailable answer is not mislabeled as generated.
5. To explore handover, choose the damaged-item example. With ticket writing
   off, the reply explains that review is needed but no ticket was created.
   Enable local tickets only when you want an actual mock CSV record.

All credentials below are intentionally public **demo-only** values:

| Tutorial | Order ID | Test phone suffix | What it demonstrates |
| --- | --- | --- | --- |
| Shipped order | 81000001 | 4242 | Verification and delivery status |
| Fashion return | 81000002 | 1515 | Festive window, coupon clawback, pickup fee |
| UPI refund | 81000003 | 3030 | Initiation-based business-day range and reference |
| Damaged electronic item | 81000004 | 9090 | High-value human review, not auto-approval |

These orders are invented tutorial fixtures, not additions to the supplied data
or retrieval corpus. `DMO-*` SKUs are not public-catalog products. Their credentials
do not verify supplied-dataset orders. Switching sources clears private context;
each source retains its failed-proof ledger. Both sources share the same browser
model budget. Local demo tickets use a separate ignored output directory.

## Voice architecture

The implementation follows Gnani's official
[STT WebSocket protocol](https://docs.gnani.ai/api/STT/stt-websocket),
[TTS WebSocket protocol](https://docs.gnani.ai/api/TTS/tts-websocket), and
[voice catalog](https://docs.gnani.ai/api/TTS/available-voices).

Streamlit captures a short WAV recording. The adapter validates mono, 16-bit,
16-kHz PCM and a maximum 15-second clip, then sends paced PCM frames over the
STT socket. A silence tail closes the last speech segment. Returned segments
are collected and deduplicated. The user reviews and can edit the transcript
before sending it to the existing text workflow: transcription cannot authorize
tools by itself. A finite drain interval and overall timeout bound the connection;
review the transcript because there is no clip-level completion event.

TTS uses Timbre v2.5 with a locale-matched voice. It receives JSON audio chunks,
validates order/base64/size and completion, and wraps the returned raw PCM in a
playable WAV in memory. It synthesizes the chosen reply, not a new model answer.
Input uses the selected reply's language. Hinglish STT uses Hindi's supported
language code; its TTS uses the separate Hinglish voice/language. Actual accent,
code-switching, numeric pronunciation, and account availability need live review.

This is **record → transcribe → review → send → optionally play a reply**, not
continuous live listening, interruption handling, or full-duplex calling.
Provider streaming is implemented, but playback starts after collection, not at
the first audio chunk. These limitations are explicit rather than a real-time
conversation claim.

## Credits, privacy, and failure behavior

- A separate default-off consent control covers audio and selected replies sent
  to Gnani. TTS can send verified order details only when a user explicitly asks
  to speak that reply. Never use real personal data in this educational app.
- Recording/transcription/speech require explicit actions. Reruns do not trigger
  another service call. Gemini and Gnani have independent consent and budgets.
- Voice is disabled during proof collection. Verification stays in the masked
  typed field; do not speak proof values even outside that stage.
- `GNANI_API_KEY` stays in ignored `.env` and is never printed, copied to chat,
  or passed to browser JavaScript. Fixed provider endpoints use encrypted sockets.
- Each browser allows 20 voice attempts, including failed service requests.
  Invalid clips/text are rejected before key loading. Speech is capped at 800
  characters and returned audio at 5 MB. There are no automatic retries.
- Service failures pause voice; **Retry voice connection** explicitly resumes it
  without resetting attempts or automatically making another request. A missing
  local key or invalid clip can be corrected and retried without a page reload.
  Static notices replace raw provider errors. Text support remains available.
- The adapter does not write recordings, transcripts, or speech files. Session
  state and Streamlit's media delivery still use server/browser memory. Clearing
  context drops displayed audio/drafts; limits remain. Provider-side retention is
  outside this local application's control.

## Verification status and remaining work

The full offline suite passes **211 tests**, including 13 new demo/voice checks.
Tests cover demo isolation, proof gates, greetings, masked UI flows, shared model
budgets, lockouts across source changes, opt-in playback, disabled voice during
verification, WAV validation, quota pauses, STT framing/segment deduplication, and
TTS framing/completion/error sanitization. The supplied dataset validator and
dependency checks pass. No real Gemini/Gnani requests were made in this update;
your credits were not used for automated testing.

**Live Gnani validation is pending.** Having a configured key does not prove the
account can use these endpoints. First try a short greeting with TTS, then a short
recording, and check the dashboard's usage. Do not describe voice quality,
latency, or end-to-end accuracy as validated before recording those results.

Phase 14 will target observed failures and broader evaluation rather than
rebuilding the interface. Phase 15 covers deployment, documentation/report, and
demo preparation. Production authentication and unrestricted multi-user hosting
are not supplied by these mock tools.
