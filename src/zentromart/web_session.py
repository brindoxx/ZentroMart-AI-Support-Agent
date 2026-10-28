"""Per-browser application state; no Streamlit dependency or transcript persistence."""

from dataclasses import dataclass, field
import re
from uuid import uuid4

from .config import load_llm_settings
from .contracts import AgentRequest
from .llm import GeminiModel, ModelError


class PublicAccessError(RuntimeError):
    """Static reason code only; never include a prompt or provider payload."""


class ConsentModel:
    """Lazy, session-local model. Consent is checked on every generation."""

    def __init__(self, settings_loader=None):
        self.enabled = False
        self.calls = 0
        self.limit = 20
        self.blocked = False
        self._client = None
        self._settings_loader = settings_loader

    def generate(self, request):
        if self.enabled is not True:
            raise PublicAccessError("cloud_disabled")
        if self.blocked or self.calls >= self.limit:
            raise PublicAccessError("cloud_paused")
        try:
            if self._client is None:
                self._client = GeminiModel((self._settings_loader or load_llm_settings)())
            self.calls += 1  # Includes failed requests; provider retries stay bounded separately.
            return self._client.generate(request)
        except (ModelError, ValueError):
            self.blocked = True
            raise PublicAccessError("cloud_failed") from None


def display_message(text):
    """Minimize user display history; not a production PII detector."""
    text = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "[email hidden]", text)
    text = re.sub(r"https?://\S+", "[link hidden]", text)
    text = re.sub(r"\d(?:[\s()+-]*\d){3,}", "[number hidden]", text)
    return text[:2000]


@dataclass
class BrowserSession:
    agent: object = field(repr=False)
    model: ConsentModel = field(repr=False)
    identifier: str = field(default_factory=lambda: uuid4().hex, repr=False)
    messages: list = field(default_factory=list, repr=False)

    def preferences(self, language, cloud=False, tickets=False):
        if type(cloud) is not bool or type(tickets) is not bool:
            raise ValueError("Consent flags must be boolean")
        self.agent.set_language(language)
        self.model.enabled = cloud
        self.agent.allow_ticket_writes = tickets
        self.agent.gateway.allow_ticket_writes = tickets

    def clear(self):
        self.agent.reset()
        self.messages.clear()

    def submit(self, message, *, proof=False):
        if not isinstance(message, str) or not 1 <= len(message.strip()) <= 12000:
            raise ValueError("Invalid message size")
        if proof and self.agent.state.phase != "proof":
            raise ValueError("Verification is not pending")
        hidden = proof or self.agent.state.phase == "proof"
        shown = {"en": "Verification submitted (hidden)", "hi": "सत्यापन जानकारी भेजी गई (छिपी हुई)",
                 "hi-en": "Verification bheji gayi (hidden)"}[self.agent.language] if hidden else display_message(message)
        self.messages.append({"role": "user", "text": shown, "evidence": ()})
        try:
            response = self.agent.respond(AgentRequest(self.identifier, message))
            self.messages.append({"role": "assistant", "text": response.reply, "evidence": response.evidence})
        finally:
            # Never retain the last executor's proof arguments in UI session state.
            self.agent._calls = []
            self.messages[:] = self.messages[-24:]
        # No AgentResponse/tool traces are retained or returned to the page.

