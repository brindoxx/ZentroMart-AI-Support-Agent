"""Offline setup, inspection, ingestion, and evaluation commands."""

import argparse
from datetime import date
import json
import subprocess
import sys

from .config import load_settings
from .dataset import format_inspection, inspect_dataset


def scenario_date(value: str) -> date:
    try:
        parsed = date.fromisoformat(value)
        if parsed.isoformat() != value:
            raise ValueError
        return parsed
    except ValueError:
        raise argparse.ArgumentTypeError("Use a date in YYYY-MM-DD format") from None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command")
    inspection = commands.add_parser("inspect", help="Show dataset schema and counts")
    inspection.add_argument("--json", action="store_true", help="Print the inspection as JSON")
    commands.add_parser("validate", help="Run the supplied offline dataset validator")
    ingestion = commands.add_parser("ingest", help="Parse kb/*.md into searchable section chunks")
    ingestion.add_argument("--section", help="Preview one exact section ID, for example RET-2")
    search = commands.add_parser("search", help="Rank public policy/catalog evidence")
    search.add_argument("query")
    search.add_argument("--top-k", type=int, default=5)
    search.add_argument("--json", action="store_true", help="Show full passages, metadata, and score contributions")
    from .policy import CATEGORIES, TOPIC_ANCHORS
    policy_search = commands.add_parser("policy-search", help="Prepare policy evidence with explicit scenario context")
    policy_search.add_argument("query")
    policy_search.add_argument("--topic", choices=tuple(TOPIC_ANCHORS), default="general")
    policy_search.add_argument("--category", choices=sorted(CATEGORIES))
    policy_search.add_argument("--sku")
    policy_search.add_argument("--delivered-on", type=scenario_date)
    policy_search.add_argument("--placed-on", type=scenario_date)
    policy_search.add_argument("--top-k", type=int, default=5)
    policy_search.add_argument("--json", action="store_true", help="Show the complete evidence bundle and provenance")
    retrieval_eval = commands.add_parser("evaluate-retrieval", help="Score evidence retrieval on questions")
    retrieval_eval.add_argument("--top-k", type=int, default=5)
    retrieval_eval.add_argument("--asr", action="store_true")
    comparison = commands.add_parser("compare-retrieval", help="Compare BM25, semantic, and hybrid on text and ASR")
    comparison.add_argument("--top-k", type=int, default=5)
    for command in (search, retrieval_eval, policy_search):
        command.add_argument("--retriever", choices=("bm25", "semantic", "hybrid"), default="bm25")
    for command in (search, retrieval_eval, comparison, policy_search):
        command.add_argument("--offline", action="store_true", help="Use only previously downloaded model files")
        command.add_argument("--rebuild-embeddings", action="store_true", help="Recompute document embeddings")
    evaluation = commands.add_parser("evaluate", help="Run offline practice evaluation")
    evaluation.add_argument("--suite", choices=("all", "questions", "conversations"), default="all")
    evaluation.add_argument("--agent", choices=("baseline",), default="baseline")
    evaluation.add_argument("--asr", action="store_true", help="Use ASR-style text for questions")
    evaluation.add_argument("--top-k", type=int, default=5)
    args = parser.parse_args()
    try:
        settings = load_settings()
        settings.validate_dataset_layout()
        if args.command in {"search", "evaluate-retrieval", "compare-retrieval", "policy-search"}:
            from .retrieval import build_indexes, load_search_documents
            if args.top_k < 1:
                raise ValueError("top-k must be positive")
            methods = ("bm25", "semantic", "hybrid") if args.command == "compare-retrieval" else (args.retriever,)
            if set(methods) & {"semantic", "hybrid"}:
                print("Preparing local semantic model and document embeddings...", file=sys.stderr)
            indexes = build_indexes(load_search_documents(settings.dataset_dir), settings.artifacts_dir,
                                    methods, offline=args.offline, rebuild=args.rebuild_embeddings)
            if args.command == "compare-retrieval":
                from .evaluation.retrieval import evaluate_retrieval, format_retrieval_summary
                from .evaluation.runner import save_report
                runs = []
                for asr in (False, True):
                    for method, index in indexes.items():
                        report = evaluate_retrieval(settings, index, top_k=args.top_k, asr=asr)
                        path = save_report(report, settings.artifacts_dir)
                        print(format_retrieval_summary(report), flush=True)
                        runs.append({"input_variant": report["input_variant"], "index": report["index"],
                                     "practice_sha256": report["practice_sha256"], "summary": report["summary"],
                                     "by_language": report["by_language"], "report": str(path)})
                path = save_report({"schema_version": 1, "run_kind": "retrieval_comparison",
                                    "top_k": args.top_k, "runs": runs}, settings.artifacts_dir)
                print(f"Comparison report: {path}")
                return
            index = indexes[args.retriever]
            if args.command == "policy-search":
                from .policy import PolicyContext, PolicyEngine
                context = PolicyContext(topic=args.topic, category=args.category, sku=args.sku,
                                        delivered_on=args.delivered_on, placed_on=args.placed_on)
                bundle = PolicyEngine(index, settings.reference_date).assemble(args.query, context, args.top_k)
                if args.json:
                    print(json.dumps(bundle, indent=2))
                else:
                    print(f"Policy evidence: {bundle['resolution']} (topic={bundle['topic']})")
                    print(f"Applicability: {bundle['applicability']}")
                    print(f"Required context: {', '.join(bundle['required_context']) or 'none'}")
                    for item in bundle["evidence"]:
                        print(f"  [{item['evidence_id']}] {item['role']}; source={item['source']}")
                    for item in bundle["excluded"]:
                        print(f"  Excluded [{item['evidence_id']}]: {item['reason']}")
                    print("Scenario fields are not identity proof. This command prepares evidence, not a final answer.")
                return
            if args.command == "search":
                hits = index.search(args.query, args.top_k)
                if args.json:
                    print(json.dumps({"index": index.configuration(),
                                      "results": [hit.to_dict() for hit in hits]}, indent=2))
                else:
                    lines = []
                    for rank, hit in enumerate(hits, 1):
                        metadata = hit.document.metadata
                        lines.append(f"{rank}. [{hit.document.evidence_id}] {hit.score:.4f} - {hit.document.title}")
                        lines.append(f"   {hit.document.source}; type={metadata['doc_type']}; "
                                     f"status={metadata.get('status', 'not applicable')}; "
                                     f"score_type={hit.score_kind}; matches={', '.join(hit.term_scores) or 'semantic'}")
                    lines.append("Retrieval scores are not confidence or policy authority." if hits else
                                 "No matching terms found. Try different wording.")
                    output = "\n".join(lines)
                    encoding = sys.stdout.encoding or "utf-8"
                    print(output.encode(encoding, errors="backslashreplace").decode(encoding))
                return
            from .evaluation.retrieval import evaluate_retrieval, format_retrieval_summary
            from .evaluation.runner import save_report
            report = evaluate_retrieval(settings, index, top_k=args.top_k, asr=args.asr)
            path = save_report(report, settings.artifacts_dir)
            print(format_retrieval_summary(report))
            print(f"Redacted report: {path}")
            return
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
    except (ValueError, OSError, ImportError, RuntimeError) as exc:
        raise SystemExit(f"Dataset command failed: {exc}") from exc
    print("ZentroMart project setup is ready.")
    print(f"Dataset: {settings.dataset_dir}")
    print(f"Reference date: {settings.reference_date}")
    print("Use 'python -m zentromart --help' to see dataset, search, and evaluation commands.")


if __name__ == "__main__":
    main()
