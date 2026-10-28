"""A model proposes conversation steps, never verification or tool results."""

from dataclasses import dataclass, field
from datetime import date
import json
import re

from .config import FROZEN_REFERENCE_DATE
from .policy import CATEGORIES, TOPIC_ANCHORS


ACTIONS = ("respond", "clarify", "search", "order", "handover")
TOPICS = tuple(sorted(set(TOPIC_ANCHORS) | {"order_status"}))


def nullable(schema):
    return {"anyOf": [schema, {"type": "null"}]}


PLAN_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "action": {"type": "string", "enum": list(ACTIONS)},
        "topic": {"type": "string", "enum": list(TOPICS)},
        "category": nullable({"type": "string", "enum": sorted(CATEGORIES)}),
        "sku": nullable({"type": "string"}),
        "placed_on": nullable({"type": "string"}),
        "delivered_on": nullable({"type": "string"}),
        "reply": {"type": "string"},
        "language": {"type": "string", "enum": ["en", "hi", "hi-en"]},
        "new_subject": {"type": "boolean"},
    },
}
PLAN_SCHEMA["required"] = list(PLAN_SCHEMA["properties"])


@dataclass(frozen=True)
class DialoguePlan:
    action: str
    topic: str
    category: str | None
    sku: str | None
    placed_on: str | None
    delivered_on: str | None
    reply: str = field(repr=False)
    language: str
    new_subject: bool


def _object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("Duplicate dialogue field")
        value[key] = item
    return value


def parse_plan(text):
    if not isinstance(text, str) or len(text) > 12000:
        raise ValueError("Invalid dialogue proposal")
    value = json.loads(text, object_pairs_hook=_object)
    if not isinstance(value, dict) or set(value) != set(PLAN_SCHEMA["required"]):
        raise ValueError("Invalid dialogue fields")
    if value["action"] not in ACTIONS or value["topic"] not in TOPICS or value["language"] not in {"en", "hi", "hi-en"}:
        raise ValueError("Invalid dialogue choice")
    if value["category"] is not None and value["category"] not in CATEGORIES:
        raise ValueError("Invalid item category")
    if value["sku"] is not None and (not isinstance(value["sku"], str) or not re.fullmatch(r"[A-Z]{3}-[0-9]{4}", value["sku"])):
        raise ValueError("Invalid catalog ID")
    for name in ("placed_on", "delivered_on"):
        if value[name] is not None:
            if not isinstance(value[name], str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value[name]):
                raise ValueError("Invalid scenario date")
            if date.fromisoformat(value[name]) > FROZEN_REFERENCE_DATE:
                raise ValueError("Scenario follows dataset reference date")
    if value["placed_on"] and value["delivered_on"] and value["placed_on"] > value["delivered_on"]:
        raise ValueError("Conflicting scenario dates")
    if not isinstance(value["reply"], str) or len(value["reply"]) > 1200 or type(value["new_subject"]) is not bool:
        raise ValueError("Invalid dialogue wording")
    if value["action"] in {"respond", "clarify"} and not value["reply"].strip():
        raise ValueError("Missing conversational reply")
    return DialoguePlan(**value)
