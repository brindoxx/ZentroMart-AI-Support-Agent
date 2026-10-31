# Recorded support examples

`audio_demo/` is an unchanged copy of the real run
`artifacts/audio_runs/20261031T151324Z-sr7lzhud`, made on 31 October 2026.
It contains six completed audio turns across three cases, not mocked provider
responses. The input recordings were supplied and their processing approved by
the project owner. They are excluded from Git; this folder contains generated
Gnani reply speech, not copies of the speaker's recordings.

## Observed run

- All six turns completed STT, support processing and TTS; zero failed/skipped turns.
- Six Gemini generation attempts, twelve Gnani requests, no automatic retries.
- Cases 1 and 2 used fresh agents; all four case-3 turns shared one agent.
- Case 1 retrieved damage-policy evidence and generated a cited public answer.
- Case 2 requested an order ID for refund-specific help; it did not invent a refund status.
- Case 3 asked which item was damaged, retained the headphones context, asked for
  delivery timing, and switched to Hindi after the Hindi follow-up. It then asked
  for an order ID. No private lookup or refund action was performed.

These are **pipeline examples, not an accuracy benchmark**. Speech containers
were validated as nonempty 24-kHz mono 16-bit PCM WAV. Text and source-ID linkage
were inspected, but audio pronunciation/naturalness needs a human listening pass.
The Hindi refund input received a Hinglish reply; the final damage turns received
Hindi replies. Exact language/style consistency is not established by this sample.

## Known issue retained honestly

The first answer includes the obsolete sentence "verified order lookup is not
connected in this phase." That came from the public-answer prompt, not an actual
absence of the verified backend. This run used grounded prompt v3 from runner
commit `fb70162`. The obsolete instruction was identified during review and
corrected in grounded prompt v4. No further paid run was made after that
correction; it does not retroactively change these files or their results.
Do not present this wording as the final intended capability statement.

## Files

See `audio_demo/summary.json` for ordered outcomes and retrieval configuration,
`model_usage.json` for generation counts, and each numbered directory for
`reply.txt`, `reply.wav`, `sources.json` and `result.json`. The latter holds a
minimized transcript and executor-derived status/trace, not raw tool arguments.
Source chunks are public evidence selected by the agent, not gold labels.

The root README documents the exact command and `audio_cases.json` gives the
input filenames, STT hints and conversation order. Reproduction requires the
owner's recordings or equivalent consented synthetic inputs, provider access,
the separately obtained dataset and installed model dependencies. Model replies
may vary. The examples do not complete private verification or test failure
recovery; those paths have offline contract tests but need wider live evaluation.
