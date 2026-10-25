"""Exact label checks and deliberately limited lexical answer diagnostics."""

from datetime import date
import re
import unicodedata

from zentromart.contracts import AgentResponse, ToolCall
from .cases import Target


MONTHS = (
    ("january", "जनवरी"), ("february", "फरवरी"), ("march", "मार्च"),
    ("april", "अप्रैल"), ("may", "मई"), ("june", "जून"),
    ("july", "जुलाई"), ("august", "अगस्त"), ("september", "सितंबर"),
    ("october", "अक्टूबर"), ("november", "नवंबर"), ("december", "दिसंबर"),
)
SMALL_NUMBERS = dict(zip(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen "
    "fourteen fifteen sixteen seventeen eighteen nineteen".split(), range(20)
))
TENS = dict(zip("twenty thirty forty fifty sixty seventy eighty ninety".split(), range(20, 100, 10)))


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).casefold().replace("’", "'")
    text = "".join(str(unicodedata.decimal(char)) if char.isdecimal() else char for char in text)
    # Normalize grouped amounts, but do not strip digits from identifiers.
    text = re.sub(r"\b\d{1,3}(?:,\d{2,3})+\b", lambda m: m[0].replace(",", ""), text)
    for month, names in enumerate(MONTHS, start=1):
        pattern = r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(?:" + "|".join(names) + r")\s+(\d{4})\b"
        def format_date(match, month=month):
            try:
                return date(int(match[2]), month, int(match[1])).isoformat()
            except ValueError:
                return match[0]
        text = re.sub(pattern, format_date, text)
    text = re.sub(r"\b(" + "|".join(TENS) + r")[ -]+(" + "|".join(SMALL_NUMBERS) + r")\b",
                  lambda m: str(TENS[m[1]] + SMALL_NUMBERS[m[2]])
                  if 0 < SMALL_NUMBERS[m[2]] < 10 else m[0], text)
    text = re.sub(r"\b(" + "|".join({**SMALL_NUMBERS, **TENS}) + r")\b",
                  lambda m: str({**SMALL_NUMBERS, **TENS}[m[0]]), text)
    return " ".join(text.split())


def matches_fact(reply: str, fact: str) -> bool:
    """Accept listed alternatives, with token boundaries (12 must not match 120)."""
    normalized = normalize(reply)
    return any(
        re.search(r"(?<!\w)" + re.escape(normalize(option)) + r"(?!\w)", normalized)
        is not None
        for option in fact.split(" / ") if option.strip()
    )


def tool_calls_match(expected: tuple[ToolCall, ...], actual: tuple[ToolCall, ...]) -> bool:
    # Exact sequence/count; expected arguments must match, extra summary/reason
    # fields are allowed because create_ticket() labels do not specify them.
    return len(expected) == len(actual) and all(
        wanted.name == got.name and all(got.arguments.get(key) == value
                                       for key, value in wanted.arguments.items())
        and (wanted.name != "lookup_order" or wanted.arguments == got.arguments)
        for wanted, got in zip(expected, actual)
    )


def score_response(target: Target, response: AgentResponse, valid_evidence: set[str], top_k: int) -> dict:
    gold, cited = set(target.evidence), set(response.evidence)
    retrieved = list(dict.fromkeys(response.retrieved_evidence))[:top_k]
    required = [matches_fact(response.reply, fact) for fact in target.required_facts]
    forbidden = [matches_fact(response.reply, claim) for claim in target.forbidden_claims]
    rank = next((i for i, identifier in enumerate(retrieved, 1) if identifier in gold), None)
    return {
        "decision_correct": response.decision in target.decisions,
        "declared_language_match": response.language == target.language,
        "citation_precision": len(gold & cited) / len(cited) if cited else None,
        "citation_recall": len(gold & cited) / len(gold) if gold else None,
        "invalid_citation_count": len(cited - valid_evidence),
        "retrieval_hit_at_k": bool(rank) if gold else None,
        "retrieval_recall_at_k": len(gold & set(retrieved)) / len(gold) if gold else None,
        "reciprocal_rank_at_k": 1 / rank if rank else (0.0 if gold else None),
        "required_fact_lexical_coverage": sum(required) / len(required) if required else None,
        "required_fact_count": len(required),
        "required_fact_lexical_matches": sum(required),
        "forbidden_claim_lexical_hits": sum(forbidden),
        "forbidden_claim_count": len(forbidden),
        "forbidden_claim_lexical_clear": not any(forbidden) if forbidden else None,
        "tool_calls_correct": tool_calls_match(target.tool_calls, response.tool_calls)
        if target.tool_calls is not None else None,
        "manual_review_required": True,
    }
