"""Load practice labels separately from the agent's customer-facing input."""

from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
import re

from zentromart.contracts import DECISIONS, ToolCall
from zentromart.dataset import read_table, require_columns


def split_items(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in value.split(" ; ") if item.strip())


def parse_tool_calls(value: str) -> tuple[ToolCall, ...]:
    """Parse the pack's simple call notation without eval or executing tools."""
    calls = []
    for item in split_items(value):
        match = re.fullmatch(r"(lookup_order|create_ticket)\((.*)\)", item)
        if not match:
            raise ValueError("Unrecognized expected tool call format")
        arguments = {}
        if match[2].strip():
            for part in match[2].split(","):
                argument = re.fullmatch(r"\s*(order_id|verification_value)\s*=\s*([0-9]+)\s*", part)
                if not argument or argument[1] in arguments:
                    raise ValueError("Unrecognized expected tool arguments")
                arguments[argument[1]] = argument[2]
        calls.append(ToolCall(match[1], arguments))
    return tuple(calls)


@dataclass(frozen=True)
class Target:
    decisions: tuple[str, ...]
    language: str
    evidence: tuple[str, ...]
    required_facts: tuple[str, ...] = field(repr=False)
    forbidden_claims: tuple[str, ...] = field(repr=False)
    tool_calls: tuple[ToolCall, ...] | None = field(repr=False)


@dataclass(frozen=True)
class Case:
    case_id: str
    session_id: str
    turn: int
    message: str = field(repr=False)
    target: Target = field(repr=False)


def load_cases(root: Path, suite: str, asr: bool = False) -> list[list[Case]]:
    """Return independent sessions; each question gets a separate one-turn session."""
    if suite not in {"questions", "conversations"}:
        raise ValueError("Choose questions or conversations")
    if asr and suite != "questions":
        raise ValueError("ASR text is available only for single questions")
    columns, rows = read_table(root / "practice" / f"{suite}.csv")
    question = suite == "questions"
    prompt_field = ("asr_text" if asr else "question") if question else "customer_message"
    required = (prompt_field, "language", "expected_decision", "gold_evidence",
                "must_include", "must_not_include")
    required += (("id", "acceptable_decisions", "reply_language") if question else
                 ("conversation_id", "turn", "expected_tool_calls"))
    require_columns(columns, required, f"practice/{suite}.csv")
    groups = defaultdict(list)
    seen = set()
    for row in rows:
        identifier = row["id"] if question else row["conversation_id"]
        if not re.fullmatch(r"PQ\d+" if question else r"PC\d+", identifier):
            raise ValueError("Invalid practice identifier")
        turn = 1 if question else int(row["turn"])
        if turn < 1 or (identifier, turn) in seen or not row[prompt_field].strip():
            raise ValueError("Duplicate practice key, invalid turn, or empty customer message")
        seen.add((identifier, turn))
        decisions = (split_items(row["acceptable_decisions"]) or
                     (row["expected_decision"],)) if question else (row["expected_decision"],)
        if not set(decisions) <= DECISIONS or row["expected_decision"] not in decisions:
            raise ValueError("Invalid expected decisions")
        target = Target(
            decisions=decisions,
            language=row["reply_language"] if question else row["language"],
            evidence=split_items(row["gold_evidence"]),
            required_facts=split_items(row["must_include"]),
            forbidden_claims=split_items(row["must_not_include"]),
            tool_calls=None if question else parse_tool_calls(row["expected_tool_calls"]),
        )
        groups[identifier].append(Case(
            case_id=identifier if question else f"{identifier}:{turn}",
            session_id=f"{suite}:{identifier}", turn=turn,
            message=row[prompt_field], target=target,
        ))
    sessions = []
    for identifier in sorted(groups):
        cases = sorted(groups[identifier], key=lambda case: case.turn)
        if [case.turn for case in cases] != list(range(1, len(cases) + 1)):
            raise ValueError("Conversation turns must be consecutive starting at one")
        sessions.append(cases)
    if not sessions:
        raise ValueError("Practice suite is empty")
    return sessions
