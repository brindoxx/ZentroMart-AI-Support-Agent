# Submission readiness and report

This code-backed audit follows the supplied VoiceOps 2026 capstone brief.
It is not a declaration that the project is submission-ready.

## Required implementation

| Requirement | Current implementation | Remaining work |
| --- | --- | --- |
| LLM API and support role | Gemini transport, structured dialogue and grounded prompts | Implemented; access depends on configuration and account |
| First reply identifies AI | UI banner/planner and tested batch first-reply disclosure | Batch disclosure is enforced; guarantee first returned reply in all live UI/voice paths as well, since a banner alone is insufficient for audio |
| Prompt-only baseline versus RAG | Completed paired 52-question experiment; real LLM baseline, hybrid RAG, same model/cases and rate guards | Decision agreement 32.7% vs 48.1%; lexical fact coverage 12.2% vs 38.8%; see ../evals/results.md; wider quality improvement remains |
| Document chunks and vector index | Main app defaults to cached BM25 + BGE-M3 hybrid retrieval; E5-small alternative retained | BGE improved text Hit@5 from 39/47 to 41/47; tested cross-encoder regressed and stays off; see ../evals/retrieval-experiments.md; end-to-end answer quality remains unmeasured for BGE |
| Grounded answers and sources | Policy precedence, evidence bundle, citations and source panel | Implemented; wider factual evaluation and entailment review needed |
| Conversation and tools | Shared create_agent factory for UI, voice, CLI chat, support evaluation and batch audio | Fresh per-conversation private state; ordered batch turns retain one agent within a case |
| Gnani STT and TTS with the same agent | Live relay, UI dialogue submission, speech generation and listening loop | Implemented; user reported successful loop, not broad reliability evidence |
| Spoken dates and long order numbers | Reply text goes directly to TTS | Add presentation-only normalization and pronunciation tests without changing facts |
| Unclear audio and failure recovery | Bounded capture, safe errors and explicit voice restart | Partial; Gemini generic failure/pause needs safe categories and explicit recovery |

The four implementation areas exist, but the required steps are not all complete
in one reproducible, evaluated pipeline. Unit-test success does not close these gaps.

## Required deliverables

| Deliverable | Current status |
| --- | --- |
| Public repository with setup and key-free configuration | README/dependencies/template exist; publication is user-controlled |
| One command accepting an audio folder | Implemented and live checked on six recordings: python -m zentromart.audio_batch INPUT_FOLDER --manifest audio_cases.json --live --offline; see root README for preflight/setup |
| Saved reply text, speech and source chunks per input | Six real completed turns saved in sample_outputs/audio_demo; six Gemini and twelve Gnani attempts, no retries; human speech review remains |
| Four-page maximum report | Not produced; this file is preparation only |
| Two-minute maximum demo | Not produced |
| Sample outputs and reproducible ZIP | Real audio outputs assembled in sample_outputs/; ZIP and clean external-dataset setup validation remain |

Do not silently publish the repository or rewrite Git history. Keep the working
dataset intact until external dataset setup is verified.

## Recommended completion order

1. Use the completed paired comparison as measured evidence, not a readiness
   claim. Review its eight citation fallbacks and wrong decisions. Shared agent
   construction and vector integration are implemented.
2. Evaluate the shared support controller on complete conversations, preserving
   verification, language continuity, calculations and executor-recorded tools.
3. Verify the implemented audio-folder runner live with Gnani. Review saved reply
   text, speech, public sources and per-file outcomes before selecting samples.
4. Guarantee first-response AI disclosure, normalize spoken dates/long IDs and
   test complete order journeys, safe failure reporting and explicit recovery.
5. Tune retrieval, prompts, latency and call count against measured quality;
   keep regressions and failed cases visible.
6. Prepare the final report/demo and validate a clean installation and ZIP.

## Report: maximum four pages

Cover the problem, dataset, chosen model, the four required implementation areas,
actual architecture, baseline versus RAG results, failures, improvements, limits
and bonus work. Distinguish retrieval scores from answer accuracy and unit tests.

The completed 52-question prompt-only-versus-RAG experiment is documented in
`evals/results.md`, with zero provider errors and explicit limitations. It is
practice-set development evidence, not a held-out benchmark or a full UI-agent
score. Never fabricate results or promote lexical agreement to semantic accuracy.

## Demo: maximum two minutes

Show a spoken grounded question, a meaningful follow-up, and a confirmed handover
or an honest unsupported-answer response. Use synthetic data and consented
recordings. Keep keys and proofs out of the video. Optional UI/language features
must not displace the required grounded conversation and voice demonstration.

## Submission package

```text
team_name_voiceops.zip
  README.md
  .env.example
  requirements.txt
  run.py / run.sh (or equivalent batch entry point)
  src/
  report.pdf
  demo.mp4
  sample_outputs/
```

Include the public repository URL, exact installation instructions and the actual
batch command. Retain supporting files needed by that command. Exclude `.env`,
API keys, virtual environments and a dataset copy. Obtain the dataset separately,
select it with `DATASET_DIR`, and verify that setup during release packaging.
