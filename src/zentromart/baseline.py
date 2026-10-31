"""Evaluation-only LLM baseline: no documents, index, history, tools or gold labels."""

import hashlib
import json
from .contracts import AgentRequest, AgentResponse
from .grounding import GroundingTrace
from .llm import ModelRequest, ModelError, parse_draft
from .privacy import minimize

INSTRUCTIONS = """You are ZentroMart's AI customer-support assistant.
Answer the customer's support question briefly and honestly. Identify yourself
as an AI assistant in this first reply. Match English, Hindi or Hinglish to the
customer. Ask for clarification when necessary; admit uncertainty rather than
invent facts. Refuse unsafe or unsupported action requests politely.
This is a prompt-only evaluation: you have no company documents, order records,
retrieval or tools. Never claim a lookup, verification, ticket, cancellation or
refund has happened. Do not invent citations. Return decision, reply, language
and evidence according to the schema; evidence must be an empty array.
"""


class PromptOnlyAgent:
    def __init__(self, model):
        self.model = model
        self.last_trace = GroundingTrace()

    def configuration(self):
        return {"agent": "prompt_only", "prompt_sha256": hashlib.sha256(INSTRUCTIONS.encode()).hexdigest(),
                "retrieval_enabled": False, "tools_enabled": False, "history_forwarded": False}

    def respond(self, request: AgentRequest):
        if not isinstance(request.message, str) or not 1 <= len(request.message.strip()) <= 12000:
            raise ValueError("Invalid baseline question")
        # Deliberately ignore external history and all evaluation labels.
        result = self.model.generate(ModelRequest(INSTRUCTIONS, minimize(request.message)))
        draft = parse_draft(json.dumps({"decision": result.draft.decision, "reply": result.draft.reply,
                                       "language": result.draft.language, "evidence": list(result.draft.evidence)}))
        if draft.evidence:
            raise ModelError("invalid_response")
        self.last_trace = GroundingTrace("accepted", "prompt_only", result.attempts,
                                        result.usage.get("prompt_token_count"),
                                        result.usage.get("candidates_token_count"),
                                        result.usage.get("total_token_count"))
        return AgentResponse(draft.decision, draft.reply, draft.language)
