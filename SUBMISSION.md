# Submission checklist

Author: **Mrinal Subudhi**, individual participant. `Hello_There` is used for the
brief's team-named ZIP convention; it is not presented as a multi-person team.

Repository: https://github.com/brindoxx/ZentroMart-AI-Support-Agent

## Required files and current evidence

| Requirement | Status |
| --- | --- |
| Public Git repository and setup README | Code and key-free setup are present; owner will make the repository public |
| One-command audio-folder processing | `python run.py AUDIO_FOLDER --live`; optional manifest keeps ordered conversation turns together |
| Text, speech and used public chunks | Real six-turn examples are in `sample_outputs/audio_demo/` |
| Step 1 versus Step 2 evidence | `evals/results.md`; historical E5/prompt-v3 experiment, with limitations |
| Retriever/reranker selection | `evals/retrieval-experiments.md`; BGE selected, measured cross-encoder disabled |
| Report, at most four pages | Root `report.pdf`: four rendered/visually checked pages, author and clickable repository link verified; editable source in `report/report.tex` |
| Demo, at most two minutes | Owner must record and add root `demo.mp4`; see `DEMO_SCRIPT.md` for preparation |
| Reviewed speech samples | Owner listened and approved inclusion of input recordings and generated replies |

## Final behaviour status and release checks

Implemented and checked offline:

1. Shared first-reply AI disclosure, plus browser enforcement for local-first replies.
2. Bounded public follow-up context in retrieval and retained scenario claims;
   private exchanges are excluded and subject changes clear unrelated context.
3. One bounded source-reference correction generation, with unchanged guards;
   safe diagnostics and recovery after a rejected draft. Exact reported exchange tested.
4. Speech-only explicit ISO date formatting and labelled order-ID grouping,
   preserving written facts/prices and not guessing missing years.

The 339-test suite passed, including startup cache reuse/no-provider-call checks.
The server now warms shared public resources and the selected encoder before
readiness, without initializing private conversations or making provider requests.
An approved four-turn live Gemini text rehearsal also
passed with five generations, no citation correction needed and zero Gnani calls;
the actual output is in `sample_outputs/final_demo_text_rehearsal.json`. This does
not replace a voice rehearsal or constitute a new accuracy benchmark.
Before final recording/upload:

1. Rehearse a real grounded question/follow-up and mock handover. Wider unclear-audio
   testing and category-specific provider-error recovery remain limitations.
2. Validate a truly clean install with a separately obtained dataset. The current
   checks validate code, local dependencies and sample outputs, not a fresh machine.

No more model/framework experiments or fine-tuning are planned before release.
The report discloses these limitations; a ZIP being structurally complete does
not establish that every behaviour or evaluation score is correct.

## Build the ZIP

From the repository root, after adding the final `demo.mp4`:

```powershell
python tools/package_submission.py
```

This creates `dist/Hello_There_voiceops.zip`. An existing ZIP is not overwritten;
use `--output` with a new name after revisions. Each archive includes a SHA-256
file manifest and explicit delivery status. The default refuses to package a
release without `report.pdf` and `demo.mp4`.

To inspect a clearly labelled **preview** before the video is ready:

```powershell
python tools/package_submission.py --allow-incomplete
```

It creates `dist/Hello_There_voiceops_preview.zip`, reports missing deliverables
and marks itself incomplete. **Do not submit that preview as the final ZIP.**
The packager does not inspect the video's content or certify its duration; check
the actual MP4 is at most 120 seconds before final packaging.

## What is included

- Root README, `.env.example`, dependency files and `pyproject.toml`.
- `run.py`, the current UI entry points, theme, `src/` and regression tests.
  The legacy UI file is retained only because some regression tests exercise it.
- Evaluator-facing result summaries, consented `audio_samples/`, the case
  manifest, actual generated `sample_outputs/`, `report.pdf`, LaTeX source and
  the final `demo.mp4` when present.

The report is **at the ZIP root**, not merely linked to GitHub. `report/report.tex`
is editable source; only the PDF counts toward the four-page report limit.
Compile it using XeLaTeX or Tectonic. No compilation tools are needed to run the agent.

For example, from the repository root: `tectonic --outdir . report/report.tex`.
This rebuilds `report.pdf`; check the page count and layout after editing.

## What is excluded

`docs/`, this project's internal report audit, demo preparation script, all
`artifacts/`, screenshots, model downloads, vector caches, evaluation scratch
reports, `.git/`, `.env`, secrets, environments, bytecode and the supplied dataset
copy. The local files are not deleted; packaging uses an explicit allowlist.

Obtain the course dataset separately; set `DATASET_DIR` to its extracted folder.
Never add a key to source or a real customer recording to the examples. The
owner's original test voice will be public with the repository by explicit consent.

## Owner actions before upload

1. Record/review the demo; ensure speech is audible and duration is at most two minutes.
2. Review the report and its link; make the GitHub repository public yourself.
3. Run the final packaging command and inspect `SUBMISSION_STATUS.json` inside it.
4. Upload the final ZIP and use the requested public repository URL in the portal.

No repository visibility changes or external submission happen automatically.
