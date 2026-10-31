"""Agent inputs and outputs shared by evaluation and application code.

No expected answer, evidence label, or verification secret is added to requests
by the evaluator. Tool traces must be supplied by the executor, not invented by
the language model. Conversation text and arguments must not be logged via repr.
"""

from dataclasses import dataclass, field
from typing import Protocol


DECISIONS = frozenset({"answer", "clarify", "escalate", "refuse"})


@dataclass(frozen=True)
class Message:
    role: str
    text: str = field(repr=False)


@dataclass(frozen=True)
class AgentRequest:
    session_id: str
    message: str = field(repr=False)
    history: tuple[Message, ...] = field(default=(), repr=False)


@dataclass(frozen=True)
class ToolCall:
    name: str
    arguments: dict[str, str] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name:
            raise ValueError("Tool name must be nonempty text")
        if not isinstance(self.arguments, dict) or not all(
            isinstance(key, str) and isinstance(value, str)
            for key, value in self.arguments.items()
        ):
            raise ValueError("Tool arguments must be text keys and values")


@dataclass(frozen=True)
class AgentResponse:
    decision: str
    reply: str = field(repr=False)
    language: str
    evidence: tuple[str, ...] = ()
    retrieved_evidence: tuple[str, ...] = ()
    tool_calls: tuple[ToolCall, ...] = ()

    def __post_init__(self) -> None:
        if self.decision not in DECISIONS:
            raise ValueError("Agent decision must be answer, clarify, escalate, or refuse")
        if not isinstance(self.reply, str) or not self.reply.strip():
            raise ValueError("Agent reply must be nonempty text")
        if not isinstance(self.language, str) or not self.language.strip():
            raise ValueError("Agent language must be nonempty text")
        for evidence in (self.evidence, self.retrieved_evidence):
            if not isinstance(evidence, tuple) or not all(isinstance(x, str) for x in evidence):
                raise ValueError("Evidence must be a tuple of section or catalog IDs")
        if not isinstance(self.tool_calls, tuple) or not all(
            isinstance(call, ToolCall) for call in self.tool_calls
        ):
            raise ValueError("Tool calls must be a tuple of executor-recorded ToolCall objects")


class Agent(Protocol):
    def respond(self, request: AgentRequest) -> AgentResponse:
        """Respond using customer messages and application-owned state only."""
        ...
