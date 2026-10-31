"""Paired question-only evaluation with identical cases, model settings and scoring."""

from .runner import run_evaluation


def compare_answers(settings, baseline_factory, rag_factory, *, max_cases, top_k=5, asr=False):
    if type(max_cases) is not int or not 1 <= max_cases <= 52:
        raise ValueError("Comparison requires max-cases from 1 to 52")
    options = dict(suite="questions", max_cases=max_cases, top_k=top_k, asr=asr, stop_on_error=True)
    baseline = run_evaluation(settings, factory=baseline_factory, agent_name="prompt_only", **options)
    # Do not continue spending quota after a provider failure.
    rag = None if baseline["summary"]["error_rows"] else run_evaluation(
        settings, factory=rag_factory, agent_name="rag", **options)
    comparable = bool(rag and not rag["summary"]["error_rows"] and
                      [r["case_id"] for r in baseline["rows"]] == [r["case_id"] for r in rag["rows"]])
    return {"schema_version": 1, "run_kind": "prompt_only_vs_rag", "comparable": comparable,
            "complete_practice_set": comparable and max_cases == 52,
            "baseline": baseline, "rag": rag,
            "limitations": ["Practice data, not a held-out test.",
                            "Decision, lexical and citation metrics require semantic review.",
                            "No overall accuracy score is inferred from lexical checks."]}
