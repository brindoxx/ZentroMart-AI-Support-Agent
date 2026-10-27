"""Measure ranked evidence on single questions, separately from answer generation."""

from datetime import datetime, timezone
import hashlib
from statistics import mean
from time import perf_counter

from zentromart.config import Settings
from zentromart.retrieval import SearchIndex
from .cases import load_cases
from .scoring import score_retrieval


def summarize_retrieval(rows: list[dict]) -> dict:
    scored = [row for row in rows if row["gold_evidence_count"]]
    return {
        "questions": len(rows), "scored_questions": len(scored),
        "no_gold_questions": len(rows) - len(scored),
        "empty_result_questions": sum(row["returned_count"] == 0 for row in rows),
        "metrics": {
            key: {"mean": mean(row["metrics"][key] for row in scored) if scored else None,
                  "scored_rows": len(scored)}
            for key in ("retrieval_hit_at_k", "retrieval_recall_at_k", "reciprocal_rank_at_k")
        },
        "mean_search_latency_ms": mean(row["latency_ms"] for row in rows) if rows else None,
    }


def evaluate_retrieval(settings: Settings, index: SearchIndex, top_k: int = 5, asr: bool = False) -> dict:
    if not isinstance(top_k, int) or isinstance(top_k, bool) or top_k < 1:
        raise ValueError("top-k must be a positive integer")
    sessions = load_cases(settings.dataset_dir, "questions", asr=asr)
    indexed_ids = {doc.evidence_id for doc in index.documents}
    rows = []
    for (case,) in sessions:
        start = perf_counter()
        # The retriever receives only the query, never gold evidence or reference answers.
        hits = index.search(case.message, top_k=top_k)
        latency_ms = round((perf_counter() - start) * 1000, 3)
        evidence = tuple(hit.document.evidence_id for hit in hits)
        rows.append({
            "case_id": case.case_id, "language": case.target.language,
            "gold_evidence_count": len(set(case.target.evidence)),
            "gold_evidence_not_in_index": sorted(set(case.target.evidence) - indexed_ids),
            "returned_count": len(hits), "ranked_evidence": list(evidence),
            "scores": [hit.score for hit in hits],
            "metrics": score_retrieval(case.target.evidence, evidence, top_k),
            "latency_ms": latency_ms,
        })
    return {
        "schema_version": 1, "run_kind": "retrieval_evaluation",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "reference_date": settings.reference_date.isoformat(),
        "practice_sha256": hashlib.sha256(
            (settings.dataset_dir / "practice/questions.csv").read_bytes()
        ).hexdigest(),
        "input_variant": "asr_text" if asr else "question", "top_k": top_k,
        "index": index.configuration(),
        "summary": summarize_retrieval(rows),
        "by_language": {
            code: summarize_retrieval([row for row in rows if row["language"] == code])
            for code in sorted({row["language"] for row in rows})
        },
        "limitations": [
            "Retrieval metrics are not answer correctness or a customer-support quality score.",
            "No-gold questions are excluded from relevance metrics, not treated as correct rejections.",
            "Retrieval can return matches for unsupported questions; no abstention is implemented.",
            "This baseline does not enforce policy precedence or historical applicability.",
            "Practice questions are development data; no hidden-test performance is claimed.",
            "ASR text is supplied simulated transcript text, not real speech recognition.",
        ],
        "rows": rows,
    }


def format_retrieval_summary(report: dict) -> str:
    summary = report["summary"]
    method = report["index"]["algorithm"].upper()
    lines = [f"{method} retrieval ({report['input_variant']}, top-k={report['top_k']})",
             f"Index: {report['index']['document_count']} policy/catalog entries",
             f"{summary['questions']} questions; {summary['scored_questions']} with gold evidence; "
             f"{summary['no_gold_questions']} without gold evidence"]
    for name, metric in summary["metrics"].items():
        value = "N/A" if metric["mean"] is None else f"{metric['mean']:.3f}"
        lines.append(f"  {name}: {value} (n={metric['scored_rows']})")
    for code, group in report["by_language"].items():
        metric = group["metrics"]["retrieval_hit_at_k"]
        value = "N/A" if metric["mean"] is None else f"{metric['mean']:.3f}"
        lines.append(f"  {code}: Hit@K={value} (n={metric['scored_rows']})")
    lines.append("Search relevance only: no generated answers or policy precedence checks.")
    return "\n".join(lines)
