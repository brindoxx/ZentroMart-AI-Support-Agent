# Two-minute demo: recording guide

Aim for 1:45-1:55, not exactly two minutes. This is a demonstration plan, not a
set of assistant answers to paste into the app. Let the actual agent answer.
Use the current code, not the older saved reply with the obsolete lookup sentence.

## Before recording

1. Start the app, let BGE finish loading and test the mic/speaker beforehand.
2. Open the app directly in Chrome/Edge at localhost. Allow microphone access.
3. Clear the conversation; confirm the in-chat cloud-processing notice.
4. In **Demo options**, leave guided orders off for the public-policy portion.
   Enable **demo handover tickets** if you want the confirmed mock-ticket ending.
   This permission is not a refund approval. It only allows a local CSV write.
5. Hide terminals, `.env`, provider dashboards, browser notifications and real
   personal data. Do not speak verification proofs or show real customer records.
6. Record system audio and your microphone, with headphones to avoid feedback.
   Only record your own voice. Keep the final MP4 at or below 120 seconds.

## Timed script and actions

| Time | What to show | What to say / do |
| --- | --- | --- |
| 0:00-0:12 | App title and composer | **Narration:** "I'm Mrinal Subudhi. This is ZentroMart's AI support assistant. It uses Gemini with company documents, and Gnani for both speech recognition and speech generation." |
| 0:12-0:40 | Start voice mode; let its real reply play | **Customer:** "What is the return policy for a damaged product?" Do not narrate over the response. |
| 0:40-1:02 | Continue the same voice session | **Customer follow-up:** "Do I need to pay for the pickup?" Let the reply play. This should refer to the damaged-item context, not a new unrelated question. If the agent asks for clarification, answer it honestly. |
| 1:02-1:15 | Stop voice; expand policy sources | **Narration:** "The reply includes source references. The public search combines BM25 with BGE-M3 embeddings; backend checks handle policy precedence and tool permissions." |
| 1:15-1:38 | Demonstrate one handover | **Customer:** "I'd like a human to review this." Use voice or the actual human-review control. Show the real returned outcome. If creation is confirmed: **Narration:** "This is a local mock ticket, not a real support request or a refund approval." If it fails, say so; do not claim success. |
| 1:38-1:52 | Briefly show README results and a saved output folder | **Narration:** "The prompt-only versus E5-RAG comparison improved decision agreement from 32.7 to 48.1 percent; this isn't overall accuracy. BGE later improved top-five evidence retrieval. Six recorded turns completed the voice pipeline." |
| 1:52-1:58 | Repository URL / report | **Narration:** "The repository includes setup, a one-command audio-folder runner, recorded samples and the report." |

If a handover is unavailable, the brief permits an honest unsupported-answer
example instead. Ask a question not covered by the documents, such as a future
unannounced product release date. Show the agent's actual uncertainty/refusal;
do not prepare a fake "I don't know" response. Choose **one ending**, not both.

## If provider latency makes this too long

Rehearse once; shorten narration before cutting the actual conversation. Keep
the grounded question, its follow-up and a real handover/unsupported outcome.
Do not speed up speech or splice fabricated replies to imply real-time behaviour.
If you shorten idle waiting, visibly label that cut. A truthful short demo is
better than an overpacked tour of every feature.

## Ticket option, in plain language

- **Off:** the assistant can recommend human review but must say no ticket was created.
- **On:** the application may call the supplied mock ticket tool when a handover
  is requested. It only claims success after the tool confirms a ticket ID.
- **Not an approval:** the switch cannot approve a refund, cancel an order, notify
  a real team or automatically create a ticket.
- **Guided demo orders:** a separate setting that supplies invented tutorial
  orders/proofs. It is not the same as ticket permission and is not real authentication.

## Finish

Save the final recording as `demo.mp4` in the repository root. Then run the release
packager documented in `SUBMISSION.md`. The demo script is preparation material
and is deliberately excluded from the submission ZIP; the actual MP4 is required.
