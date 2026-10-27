"""Run independent agent sessions and save aggregate, redacted evaluation reports."""

from collections.abc import Callable
from collections import Counter
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from statistics import mean
from time import perf_counter
from uuid import uuid4

from zentromart.config import Settings
from zentromart.contracts import Agent, AgentRequest, AgentResponse, Message
from zentromart.dataset import read_table
from zentromart.grounding import GroundingTrace
from .cases import load_cases
from .scoring import score_response


class ClarificationBaseline:
    """Deliberately unskilled wiring check; no retrieval, tools, or model calls."""

    def respond(self, request: AgentRequest) -> AgentResponse:
        return AgentResponse(
            decision="clarify", language="en",
            reply="I need more information to help with that.",
        )


METRICS = (
    "decision_correct", "declared_language_match", "citation_precision", "citation_recall",
    "retrieval_hit_at_k", "retrieval_recall_at_k", "reciprocal_rank_at_k",
    "required_fact_lexical_coverage", "forbidden_claim_lexical_clear", "tool_calls_correct",
)


def summarize(rows: list[dict]) -> dict:
    successful = [row for row in rows if row["error_type"] is None]
    metrics = {}
    for name in METRICS:
        values = [row["scores"][name] for row in successful if row["scores"][name] is not None]
        metrics[name] = {"mean": mean(values) if values else None, "scored_rows": len(values)}
    return {
        "total_rows": len(rows), "completed_rows": len(successful),
        "error_rows": len(rows) - len(successful),
        "invalid_citations": sum(row["scores"]["invalid_citation_count"] for row in successful),
        "forbidden_claim_lexical_hits": sum(
            row["scores"]["forbidden_claim_lexical_hits"] for row in successful
        ),
        "latency_ms": {
            "mean": mean(row["latency_ms"] for row in rows) if rows else None,
            "max": max((row["latency_ms"] for row in rows), default=None),
        },
        "metrics": metrics,
        "grounding_outcomes": dict(Counter(
            row["grounding"]["outcome"] + (":" + row["grounding"]["reason"] if row["grounding"]["reason"] else "")
            for row in rows if "grounding" in row
        )),
    }


def evidence_inventory(root: Path) -> set[str]:
    identifiers = set()
    for path in (root / "kb").glob("*.md"):
        identifiers.update(re.findall(r"^##\s*\[([^\]]+)\]", path.read_text(encoding="utf-8"), re.M))
    _, products = read_table(root / "data/products.csv")
    identifiers.update(f"products.csv:{row['sku']}" for row in products)
    return identifiers


def fingerprint(root: Path) -> str:
    digest = hashlib.sha256()
    for folder, extension in (("practice", "*.csv"), ("data", "*.csv"), ("kb", "*.md")):
        for path in sorted((root / folder).glob(extension)):
            digest.update(path.relative_to(root).as_posix().encode())
            digest.update(b"\0")
            digest.update(path.read_bytes())
            digest.update(b"\0")
    return digest.hexdigest()


def run_evaluation(
    settings: Settings,
    factory: Callable[[], Agent] = ClarificationBaseline,
    agent_name: str = "clarification_baseline",
    suite: str = "all", asr: bool = False, top_k: int = 5,
    max_cases: int | None = None, stop_on_error: bool = False,
) -> dict:
    """No gold labels cross the respond() boundary. State resets between sessions.

    Raw prompts, replies, history, reference answers, verification arguments, and
    exception messages are never included in reports. Metrics exclude failed
    calls; their count is reported explicitly rather than disguising failures.
    """
    if suite not in {"all", "questions", "conversations"} or top_k < 1:
        raise ValueError("Choose a valid suite and a positive top-k")
    if asr and suite == "conversations":
        raise ValueError("ASR text is available only for single questions")
    if max_cases is not None and (type(max_cases) is not int or max_cases < 1):
        raise ValueError("max-cases must be a positive integer")
    suites = ("questions", "conversations") if suite == "all" else (suite,)
    plans = {selected: load_cases(settings.dataset_dir, selected, asr=asr and selected == "questions")
             for selected in suites}
    available_rows = sum(len(cases) for sessions in plans.values() for cases in sessions)
    valid_evidence = evidence_inventory(settings.dataset_dir)
    results = []
    session_count = 0
    stopped_early = False
    for selected in suites:
        sessions = plans[selected]
        for cases in sessions:
            if stopped_early or (max_cases is not None and len(results) >= max_cases):
                break
            session_count += 1
            # A fresh instance prevents verified orders or other mutable state
            # leaking from one customer's conversation to another.
            agent = factory()
            history: tuple[Message, ...] = ()
            for case in cases:
                if max_cases is not None and len(results) >= max_cases:
                    break
                start = perf_counter()
                row = {
                    "case_id": case.case_id, "suite": selected,
                    "input_variant": "asr_text" if asr and selected == "questions" else "text",
                    "error_type": None, "scores": None,
                }
                try:
                    response = agent.respond(AgentRequest(case.session_id, case.message, history))
                    if not isinstance(response, AgentResponse):
                        raise TypeError("Agent must return AgentResponse")
                    row["scores"] = score_response(case.target, response, valid_evidence, top_k)
                    assistant_message = response.reply
                except Exception as exc:
                    # Exception messages can contain credentials or submitted proofs.
                    row["error_type"] = type(exc).__name__
                    assistant_message = "[Agent response unavailable.]"
                row["latency_ms"] = round((perf_counter() - start) * 1000, 3)
                trace = getattr(agent, "last_trace", None)
                if isinstance(trace, GroundingTrace):
                    row["grounding"] = asdict(trace)
                history += (Message("user", case.message), Message("assistant", assistant_message))
                results.append(row)
                if stop_on_error and row["error_type"] is not None:
                    stopped_early = True
                    break
    return {
        "schema_version": 1,
        "agent": agent_name,
        "run_kind": "wiring_baseline" if factory is ClarificationBaseline else "agent_evaluation",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "reference_date": settings.reference_date.isoformat(),
        "dataset_sha256": fingerprint(settings.dataset_dir),
        "top_k": top_k,
        "sessions": session_count,
        "available_rows": available_rows, "max_cases": max_cases,
        "planned_rows": min(available_rows, max_cases) if max_cases is not None else available_rows,
        "stopped_early_on_error": stopped_early,
        "summary": summarize(results),
        "by_suite": {
            selected: summarize([row for row in results if row["suite"] == selected])
            for selected in suites
        },
        "limitations": [
            "Lexical fact and forbidden-claim checks are diagnostics, not semantic correctness.",
            "Language match compares the agent-declared code, not independent language detection.",
            "Citation IDs do not prove claim support; retrieval metrics use returned ranked IDs.",
            "Tool checks require executor-recorded traces; they do not prove action success or privacy.",
            "No automatic privacy-violation score or overall quality/pass score is provided.",
            "Failed calls are counted separately and excluded from metric means.",
            "A max-cases run is a deterministic prefix sample, not a full-suite result.",
        ],
        "rows": results,
    }


def save_report(report: dict, artifacts_dir: Path) -> Path:
    """Create a unique run folder so subsequent evaluations never overwrite a run."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    directory = artifacts_dir / "evals" / f"{stamp}-{uuid4().hex[:8]}"
    directory.mkdir(parents=True, exist_ok=False)
    path = directory / "report.json"
    with path.open("x", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, ensure_ascii=False, allow_nan=False)
        handle.write("\n")
    return path


def format_summary(report: dict) -> str:
    summary = report["summary"]
    lines = [f"Evaluation: {report['agent']} ({report['run_kind']})",
             f"{report['sessions']} sessions; {summary['completed_rows']}/{summary['total_rows']} rows completed; "
             f"{summary['error_rows']} errors"]
    for metric, result in summary["metrics"].items():
        value = "N/A" if result["mean"] is None else f"{result['mean']:.3f}"
        lines.append(f"  {metric}: {value} (n={result['scored_rows']})")
    lines.append("Lexical checks and language declarations require manual review.")
    if report.get("max_cases") is not None:
        lines.append(f"Limited run: at most {report['max_cases']} cases, selected in dataset/session order.")
    if summary.get("grounding_outcomes"):
        lines.append(f"Grounding outcomes: {summary['grounding_outcomes']}")
    if report.get("stopped_early_on_error"):
        lines.append("Stopped on the first agent error; the remainder was not attempted.")
    if report["run_kind"] == "wiring_baseline":
        lines.append("This baseline only checks the evaluation plumbing; it is not a working support agent.")
    return "\n".join(lines)
