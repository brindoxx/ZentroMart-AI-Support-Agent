# Composer-first live voice

## User experience

The default app has one bottom text composer with a mic, a separate waveform
voice-conversation button and Send. Provider checkboxes, recorder/upload panels
and Transcribe/Send-reviewed/Read-aloud buttons are removed from the primary UI.
Language, New/Clear conversation and optional demo settings stay in the sidebar.

Before the first cloud action, a single in-chat confirmation discloses Gemini,
Gnani, credits and the fact that spoken replies can contain verified synthetic
order details. It does not start recording or call either provider. After that,
clicking mic or voice is the explicit action for speech. This replaces separate
provider switches, not browser security: Chrome/Edge still asks for microphone
permission. Use synthetic data only, never real personal data or proofs.

### Dictation mic

Click mic, speak, and see completed Gnani phrases appear directly in the input.
Click mic again to finish. Existing typed text is preserved as a prefix. Edit
the resulting text and press Send/Enter. Dictation does not automatically submit
the message or generate speech.

### Voice conversation

Click waveform, speak, and pause. Gnani's VAD produces a completed segment;
the app automatically submits it to the existing support agent, generates speech
with Gnani TTS and plays it through the unlocked browser AudioContext. Listening
resumes only after playback completes. Click waveform again to end. This avoids
echoing the assistant into STT, but it is not full-duplex/barge-in speech.

Capture is bounded to 15 seconds per listening turn, not a single uploaded WAV
after recording. Gnani's streaming endpoint currently publishes **completed
phrases after a pause**, not per-word interim hypotheses. We show those real
events immediately. A live connection is not a guarantee of word-by-word text,
zero latency or uninterrupted provider availability.

## Architecture

`browser AudioWorklet -> same-origin authenticated WebSocket relay -> Gnani STT`

`Gnani completed phrase -> composer -> BrowserSession/LLMConversation -> Gnani TTS -> browser AudioContext`

- `streamlit_app.py` is a small `st.App` ASGI launcher. It serves `chat_app.py`
  and the `/api/voice` WebSocket route. The run command is unchanged, but a full
  server restart is necessary when switching from the previous entry point.
- `composer.py` registers an inline CCv2 component. This is still a Streamlit
  app, not a second React/Next app or a legacy iframe injection. Scoped styles
  use Streamlit theme variables. Input text and transcripts use text/value
  properties, not HTML injection.
- The AudioWorklet resamples actual browser audio to mono 16-kHz signed 16-bit
  little-endian PCM and emits 1,024-byte frames while capture is running.
  Synthetic tests verify 44.1/48-kHz input resampling and frame format.
- `live_voice.py` relays each frame immediately to Gnani, not after the entire
  recording. Completed transcript segments flow back to the composer over the
  same socket. Voice mode ends its turn on the first finalized VAD segment;
  dictation accumulates segments until Stop or the 15-second cap.
- The provider key is read server-side only. The browser receives an expiring,
  single-use relay capability, sent in the first WebSocket message rather than
  a URL query. It is not a provider key. Origin/host must match a local app
  origin. Invalid, reused, expired, revoked and cross-session capabilities are
  rejected before provider access.
- The bounded, locked routing registry contains only short-lived speech leases
  and session counters, not private order records, audio or transcript history.
  It exists solely to bridge Streamlit's UI thread and the ASGI socket handler.
- All speech paths share the same atomic 20-attempt VoiceSession budget. Model
  generations retain the separate existing cap. Ordinary voice turns require
  capacity for both STT and TTS, and sufficient model capacity before listening.
- Each UI event has a channel-scoped ID. An action and its finalized transcript
  share a turn ID but are different events. Replayed submissions do not call
  the model or TTS again. A late finalized transcript after Stop cannot submit.

## Privacy and failure behavior

The same agent owns conversation, retrieval and tools; voice is not a separate
hardcoded assistant. Order IDs and typed verification follow the existing local
gates. Voice pauses and the composer is disabled when a proof is requested.
Proof must be typed into the masked form, never spoken. Detected unsolicited
spoken proof text is not submitted to the support agent; STT already heard it,
so this is not comprehensive personal-data protection.

TTS receives the verified synthetic details present in an answer only when voice
mode was explicitly started. It never receives the proof exchange. TTS failure
keeps the written reply, ends the voice loop and does not resend the customer
message. STT failure calls no assistant or TTS. No alternate speech service is
used as fallback. Errors are safe categories, not raw provider messages/keys.

Changing language/source, clearing chat or ending voice closes capture/playback,
revokes the capability and discards pending audio. Source changes also discard
verified records, while preserving verification-failure ledgers. No operation
renews model/voice limits. There are no automatic retries after provider failure.
A new explicit mic/voice click can retry within the remaining budget.

Browser permission, slow networks and provider inference still affect latency.
TTS is currently assembled as a bounded WAV before playback, not streamed to
the speaker chunk-by-chunk. Replies above 800 characters remain text-only with
an error rather than being silently truncated. Local browser capture supports
localhost/127.0.0.1; production/remote hosting needs a separate authenticated
HTTPS/origin-policy design. Do not expose this local mock demo publicly as-is.

## Capstone brief review

The supplied VoiceOps 2026 brief was read in full; the Step 4 page was also
rendered and visually checked. It requires Gnani-only STT/TTS wrapped around
the same Step 3 agent, synthetic data and protected keys. Its example uses SDK
REST calls on completed clips. The current implementation uses the same vendor's
documented WebSocket APIs to satisfy the user's additional live-transcription
requirement, without substituting browser speech recognition/synthesis.

The brief's setup snippet is reference material, not permission to expose keys,
publish this private repository or weaken verification. No such action was taken.
The source PDF is not copied into Git.

Other submission requirements identified in the brief are **not made complete
by this interface work**: one-command audio-folder evaluation/export with text,
speech and evidence; a measured prompt-only-versus-RAG comparison; a maximum
four-page report; a maximum two-minute spoken demo; and the final public repo/
submission package excluding credentials, environments and a dataset copy.
Those remain release/evaluation work. Existing retrieval supports semantic and
hybrid modes, but the default UI is still BM25; default vector/hybrid integration
and the brief's embedding requirement need an explicit final audit.
Also audit AI identification in the first returned answer (not only the UI
banner), clear spoken formatting of dates/order numbers, and the requested
unclear-audio recovery behavior in live recordings.

## Verification

- Relay tests: frames precede transcript completion, strict origins, session
  isolation, single use/expiry, invalid frames, disabled access and safe timeouts.
- Primary UI AppTest: explicit initial consent, no provider switches, typed
  Gemini calls, dictation lease creation without key loading, automatic TTS,
  duplicate events, stale restarts, Stop, typed-proof pause and TTS failures.
- Earlier UI tests explicitly target `legacy_streamlit_app.py` and are retained
  as regression comparisons, not described as testing the new composer.
- `node tests/composer_frontend.mjs`: fake browser/audio/socket state tests,
  live phrase rendering, dictation not auto-sending, VAD turn submission, once-only
  playback, resume after playback, Stop/late-event safety and PCM resampling.
- Actual local browser review: new dark composer visibly rendered, the one-time
  consent disappeared after confirmation, and typing worked without submission.
  No real microphone was opened and no provider call was made in that review.

Successful live provider speech and audible end-to-end conversation remain
unverified here. The earlier Gnani connection timeouts remain an external
dependency, not something a composer redesign can guarantee away.

Provider reference: https://docs.gnani.ai/api/STT/stt-websocket
