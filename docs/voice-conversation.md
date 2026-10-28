# Dictation versus voice conversation

The app now has two experiences, built from native Streamlit controls:

| Mode | What happens after recording |
| --- | --- |
| Mic / dictation | Transcribe, review/edit, then explicitly Send. Speech playback remains optional. |
| Voice conversation | Automatically transcribe, submit to the support assistant, synthesize its reply and request playback. |

## Try voice conversation

1. Fully restart Streamlit after updating, because Python modules from an older
   run can stay loaded. Use the project's virtual environment.
2. Enable **Use Gemini for natural conversation** and **Enable Gnani voice**.
3. Read the automatic-submission/credit notice and click **Start voice conversation**.
4. Click the recorder, speak a short synthetic question, then stop recording.
5. The app shows transcription, assistant and speech-generation progress. The
   transcript and answer enter the same chat; audio playback is requested once.
6. Record another turn to continue, or click **End voice conversation** to type.
   If the browser blocks autoplay, use the audio player's Play button.

The microphone is **not continuously open**. Each turn requires recording and
stopping; there is no silence-triggered hands-free capture, full-duplex streaming
or barge-in/interruption. End removes the recorder/audio UI and prevents future
turns; it does not promise cancellation of an already-running provider request.
This is a turn-based conversational pipeline, not a clone of ChatGPT live voice.

## What runs where

`Completed recording -> Gnani STT -> existing BrowserSession/LLMConversation -> Gnani TTS -> browser audio player`

- Gnani handles speech recognition and speech generation, not support reasoning.
- The same Gemini conversation controller understands the transcript, asks for
  missing information and routes factual questions through retrieval/grounding.
- The same backend still owns verification, private order facts, calculations
  and mock ticket execution. Voice does not create a second or less-safe agent.
- `VoiceConversation` coordinates the turn and consumes its recorder-event ID
  before starting service calls. Reruns cannot replay the same submitted turn.
- Streamlit supplies capture, state, progress and playback. No new frontend,
  browser-side API key or extra speech provider is introduced.

## Consent, privacy and limits

Voice mode is off by default and needs both provider opt-ins plus the explicit
Start action. Unlike dictation, its transcript is **not reviewed before sending**.
Its replies go automatically to Gnani, potentially including verified synthetic
order details. Use synthetic data only. Capture/transcript minimization is not
a comprehensive personal-data detector, and STT may mishear speech.

Never speak verification proofs. The mode pauses when the backend requests
proof, skips TTS for that exchange, and shows the masked typed verification form.
Detected spoken proof values are rejected before chat submission; they have
already passed through STT, so this is not permission to speak sensitive data.
After typed verification, explicitly start voice mode again.

Each ordinary completed turn consumes two voice attempts (STT and TTS), plus
one or two Gemini generations. Existing session-wide caps remain 20 voice
attempts and 20 model generations, shared with dictation, playback tests and text
chat. Two available attempts/generations are required before starting a turn.
Clearing, stopping, changing language/source or toggling providers does not renew
budgets or verification lockouts. Mode and pending audio reset on those changes.

Input is still capped at 15 seconds, mono 16-bit/16-kHz WAV. TTS is capped at 800
characters. Longer answers remain written in full instead of being silently
truncated or spending an unbounded number of speech requests. Audio stays in
memory; no new recording/transcript export or persistence is added.

## Failure behavior

- STT failure: no assistant or TTS request; pause and show the speech error.
- Assistant failure: no TTS request and no playback of an old answer.
- TTS failure: keep the new written answer, discard old audio and pause. Do not
  resend the customer message. You can explicitly read the latest reply aloud
  after fixing the connection, without repeating STT or the assistant request.
- Reruns do not retry failed provider calls. Retry connection does not itself
  send a request or renew budgets; starting mode needs a fresh recording event.
- Browser capture and autoplay failures remain browser/device concerns. The
  existing microphone help, dictation WAV fallback and manual audio player remain.

## Verification

Offline controller tests cover ordering, consent, budget checks, duplicate events,
STT/model/TTS failures, typed-proof pauses, long replies and budget preservation.
AppTest exercises a complete mocked STT -> real support-session -> mocked Gemini
-> mocked TTS turn, automatic-playback flags, no replay on reruns, End, settings
changes, verification UI and unchanged review-before-send dictation behavior.

These checks do **not** prove browser microphone permissions, audible autoplay,
speech quality or successful live Gnani service access. Earlier connection
timeouts remain an external dependency; voice mode cannot bypass them. No live
provider calls were made for this implementation's automated tests.
