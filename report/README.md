# Submission readiness and report

This code-backed audit follows the supplied VoiceOps 2026 capstone brief.
It is not a declaration that the project is submission-ready.

## Required implementation

| Requirement | Current implementation | Remaining work |
| --- | --- | --- |
| LLM API and support role | Gemini transport, structured dialogue and grounded prompts | Implemented; access depends on configuration and account |
| First reply identifies AI | UI banner identifies AI; planner says it is AI | First returned response is not explicitly guaranteed/tested to disclose AI; banner alone is insufficient for audio |
| Prompt-only baseline versus RAG | ClarificationBaseline never calls an LLM | Add actual prompt-only adapter and paired measured comparison |
| Document chunks and vector index | Metadata-preserving chunks, E5 cosine index and hybrid fusion | Optional CLI implementation exists; connect vector-backed retrieval to main chat, which currently uses BM25 |
| Grounded answers and sources | Policy precedence, evidence bundle, citations and source panel | Implemented; wider factual evaluation and entailment review needed |
| Conversation and tools | UI LLMConversation wraps SupportAgent with verification and actual tools | Implemented, but CLI/evaluation use different controllers; unify the tested pipeline |
| Gnani STT and TTS with the same agent | Live relay, UI dialogue submission, speech generation and listening loop | Implemented; user reported successful loop, not broad reliability evidence |
| Spoken dates and long order numbers | Reply text goes directly to TTS | Add presentation-only normalization and pronunciation tests without changing facts |
| Unclear audio and failure recovery | Bounded capture, safe errors and explicit voice restart | Partial; Gemini generic failure/pause needs safe categories and explicit recovery |

The four implementation areas exist, but the required steps are not all complete
in one reproducible, evaluated pipeline. Unit-test success does not close these gaps.

## Required deliverables

| Deliverable | Current status |
| --- | --- |
| Public repository with setup and key-free configuration | README/dependencies/template exist; publication is user-controlled |
| One command accepting an audio folder | Missing; current CLI handles text/retrieval/evaluation, not required batch audio |
| Saved reply text, speech and source chunks per input | Missing batch-output contract; redacted evaluation JSON is not a substitute |
| Four-page maximum report | Not produced; this file is preparation only |
| Two-minute maximum demo | Not produced |
| Sample outputs and reproducible ZIP | Not assembled; tracked dataset copy/external setup must be addressed |

Do not silently publish the repository or rewrite Git history. Keep the working
dataset intact until external dataset setup is verified.

## Recommended completion order

1. Use one agent factory/controller for UI, evaluation and batch audio. Preserve
   verification, language continuity, deterministic calculations and tool-success
   checks. Integrate the existing semantic/hybrid implementation.
2. Add the real prompt-only LLM baseline and evaluate it against RAG on the same
   questions. Record results before choosing architectural optimizations.
3. Build the audio-folder runner using Gnani only. Save reply text, speech,
   retrieved source chunks and per-file outcomes in a reproducible layout.
4. Guarantee first-response AI disclosure, normalize spoken dates/long IDs and
   test complete order journeys, safe failure reporting and explicit recovery.
5. Tune retrieval, prompts, latency and call count against measured quality;
   keep regressions and failed cases visible.
6. Prepare the final report/demo and validate a clean installation and ZIP.

## Report: maximum four pages

Cover the problem, dataset, chosen model, the four required implementation areas,
actual architecture, baseline versus RAG results, failures, improvements, limits
and bonus work. Distinguish retrieval scores from answer accuracy and unit tests.

Existing local evaluation artifacts are development evidence. They are not the
required complete prompt-only-versus-RAG experiment. Never fabricate results or
present repeatedly inspected small prefixes as comprehensive benchmarks.

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
