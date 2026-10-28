"""One in-memory conversation per agent; customer claims are never verification.

Conservative deterministic routing/slot rules, not general NLU. No private tables,
tool imports, disk persistence, transcript replay, or evaluation labels.
"""

from collections import deque
from dataclasses import dataclass, field, replace
from datetime import date
import re
import unicodedata

from .contracts import AgentRequest, AgentResponse
from .grounding import (GroundedAgent, GroundingTrace, MEMORY_PROMPT_SHA256,
                        validate_answer_options, grounded_configuration, ask_for_context)
from .privacy import minimize
from .llm import StructuredModel
from .policy import PolicyContext, PolicyEngine
from .retrieval import SearchIndex


CONVERSATION_VERSION = "zentromart-conversation-v3"
CATEGORY_WORDS = {
    "electronics": r"\belectronics?\b|\bheadphones?\b|इलेक्ट्रॉनिक्स",
    "fashion": r"\bfashion\b|\bclothes\b|\bclothing\b|\bfootwear\b|\b(?:shirts?|jeans|kurta|saree|kapde)\b|कपड़े|कपड़ों|कपड़[ेों]+|कमीज़|कमीज",
    "home_kitchen": r"\bhome_kitchen\b|\bfurniture\b|\bkitchen\b",
    "beauty_sealed": r"\bbeauty(?:_sealed)?\b|\bcosmetics?\b",
    "books_media": r"\bbooks?(?:_media)?\b|\bstationery\b|किताब",
    "grocery": r"\bgrocer(?:y|ies)\b|\bfresh produce\b|किराना",
    "innerwear": r"\binnerwear\b|\blingerie\b|\bswimwear\b",
    "digital": r"\bdigital\b|\bgift cards?\b",
}
# Most specific topics first. Patterns express public support concepts, not case IDs.
TOPIC_PATTERNS = (
    ("return_fee", r"(?:pickup|return|पिकअप|रिटर्न).{0,30}(?:fee|charge|free|फीस|शुल्क)|(?:fee|फीस).{0,30}(?:pickup|return|रिटर्न)"),
    ("damage", r"\bdamag(?:ed|e)\b|\bdefective\b|\bwrong item\b|\bmissing item\b|टूटा|खराब"),
    ("warranty", r"\bwarranty\b|\bassured\b|वारंटी"),
    ("cancellations", r"\bcancel(?:lation|led|ing)?\b|कैंसल|रद्द"),
    ("refunds", r"\brefund\w*\b|रिफंड|पैसे वापस"),
    ("coupons", r"\bcoupons?\b|\bdiscount\b|कूपन"),
    ("membership", r"\bplus\b|\bmembership\b|सदस्यता"),
    ("pickup", r"\bpickup\b|\bpick.up\b|पिकअप"),
    ("return_window", r"\breturn(?:s|able)?\b|रिटर्न|वापसी"),
    ("delivery", r"\bdelivery\b|\bshipping\b|डिलीवरी"),
)
SKU_PATTERN = re.compile(r"\b[A-Z]{3}-[0-9]{4}\b", re.I)
ORDER_PATTERN = re.compile(r"\border(?:\s+(?:id|number|no\.?))?\s*[:#-]?\s*(\d{6,20})\b", re.I)
DATE_PATTERN = r"(\d{4}-\d{2}-\d{2})"
DATE_LABELS = {
    "delivered_on": r"(?:delivered(?:\s+on)?|delivery\s+date|डिलीवरी\s+की\s+तारीख|डिलीवर)",
    "placed_on": r"(?:placed(?:\s+on)?|ordered(?:\s+on)?|order\s+date|ऑर्डर\s+की\s+तारीख)",
}


def normalize(text: str) -> str:
    return unicodedata.normalize("NFKC", text).casefold()


def memory_text(text: str) -> str:
    """Basic minimization, not a complete PII detector or production redactor."""
    text = minimize(text)
    # Drop an overlong turn as a unit; do not pretend a chopped clause is complete.
    return text if len(text) <= 1500 else ""


@dataclass(slots=True)
class ConversationState:
    session_id: str | None = field(default=None, repr=False)
    context: PolicyContext = field(default_factory=PolicyContext, repr=False)
    claimed_order_id: str | None = field(default=None, repr=False)
    language: str | None = None
    awaiting: tuple[str, ...] = ()
    turns: int = 0
    recent_customer_messages: deque = field(default_factory=lambda: deque(maxlen=4), repr=False)

class ConversationalAgent:
    def __init__(self, index: SearchIndex, model: StructuredModel, reference_date: date,
                 *, context: PolicyContext = PolicyContext(), top_k: int = 5,
                 reply_language: str | None = None):
        self.index, self.model, self.reference_date = index, model, reference_date
        self.top_k, self.default_language = top_k, reply_language
        self.engine = PolicyEngine(index, reference_date)
        category = self.engine.validate_context(context)
        if context.sku:
            context = replace(context, category=category)
        validate_answer_options(top_k, reply_language)
        self.state = ConversationState(context=context, language=reply_language)
        self.state.awaiting = self._required(context)
        self.last_trace = GroundingTrace()

    def configuration(self) -> dict:
        return {**grounded_configuration(self.index, self.top_k, self.default_language),
                "conversation_version": CONVERSATION_VERSION, "memory_prompt_sha256": MEMORY_PROMPT_SHA256,
                "memory_customer_turn_limit": 4, "memory_turn_character_limit": 1500,
                "external_history_trusted": False, "customer_memory_forwarded": True,
                "verification_connected": False, "reply_language": self.default_language}

    def reset(self) -> None:
        """Erase all session claims and memory; a subsequent request can bind a new session."""
        self.state = ConversationState(language=self.default_language)
        self.last_trace = GroundingTrace()

    def _clear_scenario(self, topic="general") -> None:
        self.state.context = PolicyContext(topic)
        self.state.awaiting = ()
        self.state.recent_customer_messages.clear()

    def _language(self, text: str) -> None:
        if self.default_language:
            self.state.language = self.default_language
            return
        lowered = normalize(text)
        for code, pattern in (("hi-en", r"\bhinglish\b"), ("hi", r"(?:reply|answer|respond)\s+in\s+hindi|hindi\s+mein|हिंदी\s+में"),
                              ("en", r"(?:reply|answer|respond)\s+in\s+english|english\s+mein|अंग्रेज़ी\s+में")):
            if re.search(pattern, lowered):
                self.state.language = code
                return
        if re.search(r"[\u0900-\u097f]", text):
            self.state.language = "hi"

    def _slots(self, text: str) -> tuple[PolicyContext, str | None]:
        lowered = normalize(text)
        old = self.state.context
        topics = [topic for topic, pattern in TOPIC_PATTERNS if re.search(pattern, lowered)]
        if not topics and old.topic in {"return_window", "pickup", "return_fee"} and re.search(r"\bfees?\b|फीस|शुल्क", lowered):
            topics = ["return_fee"]
        # Delivery-date answers must not accidentally switch a pending return topic.
        slot_only = bool(self.state.awaiting and
                         (re.search(DATE_PATTERN, lowered) or any(re.search(label, lowered) for label in DATE_LABELS.values())) and
                         all(topic in {old.topic, "delivery"} for topic in topics))
        topic = old.topic if slot_only else (topics[0] if topics else old.topic)
        if topic != old.topic:
            self._clear_scenario(topic)
            old = self.state.context
        orders = set(ORDER_PATTERN.findall(text))
        if len(orders) > 1:
            self._clear_scenario(topic)
            self.state.claimed_order_id = None
            return self.state.context, "one_item"
        if orders:
            order = next(iter(orders))
            if self.state.claimed_order_id and order != self.state.claimed_order_id:
                self._clear_scenario(topic)
                old = self.state.context
            self.state.claimed_order_id = order
        if re.search(r"\b(?:another|different|new)\s+(?:item|product|order)\b|दूसरा\s+(?:ऑर्डर|उत्पाद)|naya\s+order", lowered):
            self._clear_scenario(topic)
            self.state.claimed_order_id = next(iter(orders), None)
            old = self.state.context
        categories = {category for category, pattern in CATEGORY_WORDS.items() if re.search(pattern, lowered)}
        skus = {sku.upper() for sku in SKU_PATTERN.findall(text)}
        if len(categories) > 1 or len(skus) > 1:
            self._clear_scenario(topic)
            return self.state.context, "one_item"
        category = next(iter(categories), None)
        sku = next(iter(skus), None)
        if (category and old.category and category != old.category) or (sku and sku != old.sku):
            self._clear_scenario(topic)
            old = self.state.context
        updates = {}
        if category:
            updates["category"] = category
        if sku:
            updates["sku"] = sku
        invalid_date = False
        for name, label in DATE_LABELS.items():
            values = re.findall(label + r"\s*[:=-]?\s*" + DATE_PATTERN, lowered)
            if not values and name in self.state.awaiting and re.fullmatch(DATE_PATTERN, lowered.strip()):
                values = [lowered.strip()]
            if not values and re.search(label, lowered):
                updates[name] = None
                invalid_date = True
            if values:
                try:
                    if len(set(values)) != 1:
                        raise ValueError
                    value = date.fromisoformat(values[0])
                    if value > self.reference_date:
                        raise ValueError
                    updates[name] = value
                except ValueError:
                    updates[name] = None
                    invalid_date = True
        context = replace(old, **updates)
        if invalid_date:
            return context, "date_format"
        if old.topic == "return_window" and re.search(DATE_PATTERN, lowered) and not any(name in updates for name in DATE_LABELS):
            return replace(context, placed_on=None, delivered_on=None), "date_format"
        if context.placed_on and context.delivered_on and context.placed_on > context.delivered_on:
            # A conflicting correction must not fall back to an earlier remembered date.
            return replace(context, placed_on=None, delivered_on=None), "date_order"
        try:
            actual_category = self.engine.validate_context(context)
        except ValueError:
            return PolicyContext(topic), "catalog_context"
        if context.sku:
            context = replace(context, category=actual_category)
        # Numeric/ambiguous date responses are not interpreted by the LLM as slot facts.
        if self.state.awaiting and not updates and not categories and not topics:
            return context, "date_format" if any(x.endswith("_on") for x in self.state.awaiting) else "category"
        return context, None

    @staticmethod
    def _required(context: PolicyContext) -> tuple[str, ...]:
        if context.topic != "return_window":
            return ()
        if context.category is None:
            return ("category",)
        if context.category == "electronics" and context.delivered_on is None:
            return ("delivered_on",)
        if context.category == "fashion" and context.placed_on is None:
            return ("placed_on",)
        return ()

    def _clarify(self, reason: str) -> AgentResponse:
        language = self.state.language or "en"
        labels = {
            "en": {"one_item": "Please discuss one product or order at a time. Earlier item facts have been cleared.",
                   "input_budget": "This request is too long. Please send one shorter support question.",
                   "date_format": "Please provide the requested date as YYYY-MM-DD, on or before 2026-10-20.",
                   "date_order": "The placement and delivery dates conflict. Please provide both dates again as YYYY-MM-DD.",
                   "catalog_context": "I couldn't match that SKU/category to the public catalog. Please confirm one valid SKU or category.",
                   "category": "Please specify one product category, for example electronics or fashion."},
            "hi": {"one_item": "कृपया एक समय में एक उत्पाद या ऑर्डर की बात करें। पुराने उत्पाद की जानकारी हटा दी गई है।",
                   "input_budget": "यह अनुरोध बहुत लंबा है। कृपया एक छोटा सवाल भेजें।",
                   "date_format": "कृपया तारीख YYYY-MM-DD में दें, जो 2026-10-20 के बाद की न हो।",
                   "date_order": "ऑर्डर और डिलीवरी की तारीखों में विरोध है। कृपया दोनों तारीखें YYYY-MM-DD में दोबारा दें।",
                   "catalog_context": "SKU या श्रेणी सार्वजनिक कैटलॉग से मेल नहीं खाती। कृपया एक सही SKU या श्रेणी दें।",
                   "category": "कृपया एक उत्पाद श्रेणी बताएं, जैसे इलेक्ट्रॉनिक्स या कपड़े।"},
            "hi-en": {"one_item": "Please ek product ya order discuss karein. Purane item ki details clear kar di hain.",
                      "input_budget": "Request bahut lambi hai. Please ek chhota sawaal bhejein.",
                      "date_format": "Please date YYYY-MM-DD mein dein, 2026-10-20 tak ki.",
                      "date_order": "Order aur delivery dates conflict karti hain. Dono dates YYYY-MM-DD mein dobara dein.",
                      "catalog_context": "SKU/category public catalog se match nahi hui. Please ek valid SKU ya category dein.",
                      "category": "Please ek product category batayein, jaise electronics ya fashion."},
        }
        self.last_trace = GroundingTrace("fallback", "conversation_" + reason)
        reply = ask_for_context(("category",), language) if reason == "category" else labels[language][reason]
        return AgentResponse("clarify", reply, language)

    def respond(self, request: AgentRequest) -> AgentResponse:
        self.last_trace = GroundingTrace()
        if not isinstance(request.session_id, str) or not request.session_id.strip():
            raise ValueError("Conversation requires a nonempty application-owned session ID")
        if self.state.session_id is not None and request.session_id != self.state.session_id:
            raise ValueError("Conversation agent is bound to another session; reset it or create a new instance")
        if not isinstance(request.message, str) or not request.message.strip():
            raise ValueError("Customer message must be nonempty text")
        if len(request.message) > 12000:
            return self._clarify("input_budget")
        self.state.session_id = request.session_id
        if normalize(request.message).strip() in {"/reset", "start over", "reset conversation"}:
            self.reset()
            self.state.session_id = request.session_id
            self.last_trace = GroundingTrace("fallback", "conversation_reset")
            language = self.state.language or "en"
            reply = {"en": "Conversation cleared. What can I help you with?",
                     "hi": "बातचीत की जानकारी हटा दी गई है। मैं आपकी क्या मदद कर सकता हूँ?",
                     "hi-en": "Conversation clear ho gayi. Aapko kis baat mein help chahiye?"}[language]
            return AgentResponse("clarify", reply, language)
        self._language(request.message)
        context, issue = self._slots(request.message)
        self.state.context = context
        self.state.awaiting = self._required(context)
        self.state.turns += 1
        if issue:
            return self._clarify(issue)
        language = self.state.language
        prior = tuple(self.state.recent_customer_messages)
        # Carry earlier wording into retrieval only for a short, same-scenario follow-up.
        query = request.message
        if prior and len(request.message.split()) <= 12:
            query = prior[-1] + "\nFollow-up: " + request.message
        if context.sku:
            query += "\nPublic SKU: " + context.sku
        agent = GroundedAgent(self.index, self.model, self.reference_date, context=context, top_k=self.top_k,
                              reply_language=language, prior_customer_messages=prior, retrieval_query=query,
                              engine=self.engine)
        try:
            result = agent.respond(AgentRequest(request.session_id, request.message))
        finally:
            self.last_trace = agent.last_trace
        if language is None:
            self.state.language = result.language
        safe_text = memory_text(request.message)
        if safe_text:
            self.state.recent_customer_messages.append(safe_text)
        return result
