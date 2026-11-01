# Final demo script: ZentroMart AI support

Aim for 1:45-1:55, not exactly two minutes. This is a demonstration plan, not a
set of assistant answers to paste into the app. Let the actual agent answer.
Use the current code, not the older saved reply with the obsolete lookup sentence.
Author: **Mrinal Subudhi**. The final fixes passed **335 offline tests** and a
four-turn live Gemini text rehearsal: greeting, damage policy, pickup follow-up
and confirmed mock handover. That used five generations and no speech calls.
Rehearse once in voice mode before filming; the text check is not a voice benchmark.

## Before recording

1. Restart the app with `python -m streamlit run streamlit_app.py` to load the final
   fixes. Let BGE finish loading and test the mic/speaker beforehand.
2. Open the app directly in Chrome/Edge at localhost. Allow microphone access.
3. Clear the conversation; confirm the in-chat cloud-processing notice.
4. In **Demo options**, leave guided orders off for the public-policy portion.
   Enable **demo handover tickets** if you want the confirmed mock-ticket ending.
   This permission is not a refund approval. It only allows a local CSV write.
5. Hide terminals, `.env`, provider dashboards, browser notifications and real
   personal data. Do not speak verification proofs or show real customer records.
6. Record system audio and your microphone, with headphones to avoid feedback.
   Only record your own voice. Keep the final MP4 at or below 120 seconds.
7. If the assistant needs an item, say **"A pair of headphones."** If it needs a
   concrete hypothetical delivery date, use **19 October 2026**: the dataset's
   reference date is 20 October 2026, not the current date.
8. Do one actual rehearsal; this consumes Gemini/Gnani quota. If a guard blocks a
   draft, inspect the safe diagnostic before recording. Do not paste a prepared
   assistant answer or disable source validation to make the demo pass.

## Timed script and actions

| Time | What to show | What to say / do |
| --- | --- | --- |
| 0:00-0:10 | App title and composer; voice OFF | **Narration:** "I'm Mrinal Subudhi. This is ZentroMart's AI support assistant. It combines document-grounded Gemini answers with Gnani speech recognition and speech output." |
| 0:10-0:38 | Start voice mode; let its real reply play | **Customer:** "What is ZentroMart's policy when a product arrives damaged?" The first reply should identify it as AI. Do not narrate while the mic is listening. |
| 0:38-1:00 | Continue the SAME voice session | **Customer follow-up:** "Do I need to pay for the pickup in that situation?" Let the reply play. If it asks for clarification, use the synthetic details above rather than inventing an assistant answer. |
| 1:00-1:12 | STOP voice; expand policy sources | **Narration:** "These document sections support the reply. Search combines BM25 with BGE-M3 embeddings, while the application checks sources and permissions." |
| 1:12-1:38 | Restart voice and demonstrate one handover | **Customer:** "I request human support, please." Let the actual result play, then STOP voice. Only if the executor confirms an ID: **Narration:** "The backend confirmed a local mock handover ticket. This does not contact a real team or approve a refund." |
| 1:38-1:51 | Voice OFF; briefly show README results | **Narration:** "The historical prompt-only versus E5-RAG comparison improved decision agreement from 32.7 to 48.1 percent, not overall accuracy. Six recorded turns also completed the voice pipeline." |
| 1:51-1:58 | Repository URL / report | **Narration:** "The submission includes code, the report, audio examples, generated outputs and a one-command audio-folder runner." |

If a handover is unavailable, the brief permits an honest unsupported-answer
example instead. Ask a question not covered by the documents, such as a future
unannounced product release date. Show the agent's actual uncertainty/refusal;
do not prepare a fake "I don't know" response. Choose **one ending**, not both.

The six-turn run predates the final release fixes. Do not imply it measured the
current release, or that 335 offline tests are live answer-accuracy scores.
One citation failure can use one extra correction generation; a still-invalid
draft is withheld. Provider/quota errors do not trigger that correction path.

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
