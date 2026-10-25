"""Offline setup, inspection, ingestion, and evaluation commands."""

import argparse
import json
import subprocess
import sys

from .config import load_settings
from .dataset import format_inspection, inspect_dataset


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command")
    inspection = commands.add_parser("inspect", help="Show dataset schema and counts")
    inspection.add_argument("--json", action="store_true", help="Print the inspection as JSON")
    commands.add_parser("validate", help="Run the supplied offline dataset validator")
    ingestion = commands.add_parser("ingest", help="Parse kb/*.md into searchable section chunks")
    ingestion.add_argument("--section", help="Preview one exact section ID, for example RET-2")
    evaluation = commands.add_parser("evaluate", help="Run offline practice evaluation")
    evaluation.add_argument("--suite", choices=("all", "questions", "conversations"), default="all")
    evaluation.add_argument("--agent", choices=("baseline",), default="baseline")
    evaluation.add_argument("--asr", action="store_true", help="Use ASR-style text for questions")
    evaluation.add_argument("--top-k", type=int, default=5)
    args = parser.parse_args()
    try:
        settings = load_settings()
        settings.validate_dataset_layout()
        if args.command == "ingest":
            from .ingestion import build_corpus, save_corpus, summarize_corpus
            chunks = build_corpus(settings.dataset_dir)
            if args.section:
                chunk = next((chunk for chunk in chunks if chunk.section_id == args.section), None)
                if chunk is None:
                    raise ValueError("Section ID not found in knowledge base")
                # Escape non-ASCII in the console preview for Windows encodings.
                # Saved JSONL uses native Unicode for Hindi and rupee symbols.
                print(json.dumps(chunk.to_dict(), indent=2))
            else:
                path = save_corpus(chunks, settings.artifacts_dir, settings.reference_date)
                print(json.dumps(summarize_corpus(chunks), indent=2))
                print(f"Knowledge chunks and manifest: {path}")
            return
        if args.command == "evaluate":
            from .evaluation.runner import format_summary, run_evaluation, save_report
            report = run_evaluation(settings, suite=args.suite, asr=args.asr, top_k=args.top_k)
            path = save_report(report, settings.artifacts_dir)
            print(format_summary(report))
            print(f"Redacted report: {path}")
            raise SystemExit(1 if report["summary"]["error_rows"] else 0)
        if args.command == "inspect":
            report = inspect_dataset(settings.dataset_dir)
            print(json.dumps(report, indent=2) if args.json else format_inspection(report))
            raise SystemExit(1 if report["issues"] else 0)
        if args.command == "validate":
            validator = settings.dataset_dir / "validate_dataset.py"
            if not validator.is_file():
                raise ValueError("Dataset validator is missing")
            # Isolate the supplied validator's imports and global state. It tests
            # rejected ticket creation only, so it does not create ticket records.
            result = subprocess.run(
                [sys.executable, "-X", "utf8", str(validator)],
                cwd=settings.dataset_dir, check=False,
            )
            raise SystemExit(result.returncode)
    except (ValueError, OSError) as exc:
        raise SystemExit(f"Dataset command failed: {exc}") from exc
    print("ZentroMart project setup is ready.")
    print(f"Dataset: {settings.dataset_dir}")
    print(f"Reference date: {settings.reference_date}")
    print("Use 'python -m zentromart inspect', 'validate', 'ingest', or 'evaluate'.")


if __name__ == "__main__":
    main()
