"""Application-owned verified mock workflows. Private facts never enter the LLM.

This is educational synthetic verification, not real authentication. All private
replies and calculations are deterministic; models cannot choose or execute tools.
"""

from dataclasses import dataclass, field, replace
from datetime import date
import re

from .calculations import (BusinessCalendar, POLICY_SHA256, RULE_VERSION, item_for, pickup_fee,
                           refund_estimate, refund_timing, return_window, validate_policy_snapshot)
from .contracts import AgentRequest, AgentResponse, ToolCall
from .config import FROZEN_REFERENCE_DATE
from .conversation import ConversationalAgent, SKU_PATTERN, TOPIC_PATTERNS, normalize
from .grounding import GroundingTrace
from .tools import ToolExecutionError, ToolGateway
from .localization import DIGITS, VERSION as LOCALIZATION_VERSION, TRANSLATION_FALLBACK, choose_language, localize


ORDER_ID = re.compile(r"(?:\border(?:\s+(?:id|number|no\.?))?|/order|ऑर्डर|आर्डर)\s*(?:नंबर|आईडी)?\s*(?:hai|है|is)?\s*[:#-]?\s*([0-9]{4}[ -]?[0-9]{4})(?![0-9])", re.I)
PROOF = re.compile(r"(?:(?:phone(?:\s+last\s*4)?|last\s*4|pincode|pin|suffix)\s*[:=-]?\s*)?([0-9]{4}|[0-9]{6})", re.I)
GROUPED_ORDER = re.compile(r"(?<![0-9])([0-9]{4}[ -]?[0-9]{4})(?![0-9])")


def submitted_proof(text: str) -> str | None:
    match = PROOF.fullmatch(text.strip())
    if match:
        return match[1]
    if re.search(r"\bnot\b|\bnahi\b|नहीं", text, re.I):
        return None
    # Accept conversational labeling, never an arbitrary number plucked from a message.
    if not re.search(r"\b(?:last\s*(?:four|4)|phone|mobile|pincode|pin|suffix|digits)\b|पिनकोड|फ़ोन|फोन|आखिरी|अंतिम|अंक", text, re.I):
        return None
    runs = re.findall(r"[0-9]+", text)
    values = [value for value in runs if len(value) in (4, 6)]
    other = [value for value in runs if len(value) not in (4, 6)]
    if len(values) != 1 or any(value not in {"4", "6"} for value in other):
        return None
    return values[0]
IMMEDIATE = (
    ("safety_risk", r"swelling battery|swollen battery|burning smell|\bsparks\b|\binjury\b|battery.{0,15}swelling|बैटरी.{0,15}फूल|जलने की गंध|चिंगारी|battery.{0,15}phool|jalne ki (?:smell|badbu)"),
    ("unauthorized_activity", r"unauthori[sz]ed|did(?:n't| not) (?:place|make)|not (?:my|mine)|मैंने.{0,15}ऑर्डर नहीं|maine.{0,15}order nahi"),
    ("legal_request", r"legal action|consumer court|police complaint|कानूनी कार्रवाई|पुलिस शिकायत"),
    ("human_requested", r"\bhuman\b|\bsupervisor\b|/human|इंसान|सपोर्ट टीम|एजेंट से|agent se baat"),
)


@dataclass
class WorkflowState:
    session_id: str | None = field(default=None, repr=False)
    order_id: str | None = field(default=None, repr=False)
    order: dict | None = field(default=None, repr=False)
    intent: str = "order_status"
    phase: str = "public"
    line_no: int | None = None
    quantity: int | None = None
    requested_sku: str | None = field(default=None, repr=False)
    requested_reason: str | None = None
    refund_not_received: bool = False
    failures: dict = field(default_factory=dict, repr=False)
    ticket_ledger: dict = field(default_factory=dict, repr=False)

    @property
    def verified(self):
        return self.order is not None


class SupportAgent:
    def __init__(self, index, model, reference_date: date, *, calendar: BusinessCalendar,
                 gateway: ToolGateway, top_k=5, reply_language=None, allow_ticket_writes=False):
        validate_policy_snapshot(index)
        if reference_date != FROZEN_REFERENCE_DATE:
            raise ValueError("Verified workflows require the frozen dataset reference date")
        calendar_source = next(doc.text for doc in index.documents if doc.evidence_id == "KB-00.3")
        expected_holidays = frozenset(date.fromisoformat(value) for value in re.findall(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", calendar_source))
        if calendar.holidays != expected_holidays:
            raise ValueError("Holiday table disagrees with the policy calendar")
        self.public = ConversationalAgent(index, model, reference_date, top_k=top_k, reply_language=reply_language)
        self.calendar, self.gateway, self.reference_date = calendar, gateway, reference_date
        self.allow_ticket_writes = allow_ticket_writes
        self.state = WorkflowState()
        self.last_trace = GroundingTrace()
        self._calls = []
        self.preferred_language = reply_language
        self.language = reply_language or "en"

    def set_language(self, language):
        """UI preference changes must not recreate the agent or clear lockouts."""
        self.language = choose_language("", self.language, language)
        self.preferred_language = language
        self.public.default_language = language
        self.public.state.language = language

    def configuration(self):
        import hashlib
        return {**self.public.configuration(), "workflow_version": "zentromart-support-v2",
                "calculation_version": RULE_VERSION, "calculation_policy_sha256": POLICY_SHA256,
                "verification_connected": True, "authentication_kind": "synthetic_mock_only",
                "private_data_sent_to_model": False, "ticket_writes_enabled": self.allow_ticket_writes,
                "verification_attempt_limit": 2, "tools_enabled": True,
                "localization_version": LOCALIZATION_VERSION,
                "business_calendar_sha256": hashlib.sha256(
                    "\n".join(sorted(day.isoformat() for day in self.calendar.holidays)).encode()).hexdigest()}

    def reset(self):
        # Reset private data, but do not let a customer reset erase a failed-proof lockout.
        session, failures, tickets = self.state.session_id, self.state.failures, self.state.ticket_ledger
        self.state = WorkflowState(session_id=session, failures=failures, ticket_ledger=tickets)
        self.public.reset()
        self.last_trace = GroundingTrace()
        self._calls = []

    def _reply(self, decision, text, evidence=(), reason="private_workflow"):
        self.last_trace = GroundingTrace("workflow", reason)
        try:
            text = localize(text, self.language)
        except ValueError:
            text = TRANSLATION_FALLBACK[self.language]
            decision = "escalate" if decision == "escalate" else "clarify"
            evidence = ()
            self.last_trace = GroundingTrace("workflow", "translation_unavailable")
        suffix = " " + " ".join(f"[{identifier}]" for identifier in evidence) if evidence else ""
        return AgentResponse(decision, text + suffix, self.language, tuple(evidence), tool_calls=tuple(self._calls))

    def _lookup(self, proof=None):
        arguments = {"order_id": self.state.order_id}
        if proof is not None:
            arguments["verification_value"] = proof
        self._calls.append(ToolCall("lookup_order", arguments))
        return self.gateway.lookup_order(self.state.order_id, verification_value=proof)

    def _public_reply(self, request):
        text = request.message.strip()
        numeric_only = bool(re.fullmatch(r"[+()0-9\s-]{4,}", text)) and not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", text)
        labeled_proof = re.search(r"[0-9]", text) and re.search(r"phone|mobile|pincode|pin\b|suffix|last (?:four|4)|फ़ोन|फोन|पिनकोड|आखिरी.{0,12}अंक", text, re.I)
        if numeric_only or labeled_proof or re.search(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", text):
            return self._reply("clarify", "Please keep phone numbers, pincodes and verification values out of public-policy questions.", reason="public_privacy_guard")
        self.public.state.language = self.language
        result = self.public.respond(request)
        self.last_trace = self.public.last_trace
        return result

    def _handover(self, reason):
        oid = self.state.order_id if self.state.verified else None
        key = oid or "unverified:" + reason
        if reason == "safety_risk":
            warning = "Stop using the product immediately. "
        else:
            warning = ""
        if not self.allow_ticket_writes:
            return self._reply("escalate", warning + "Human review is required. Ticket writing is disabled; no ticket was created.",
                               ("ESC-1", "ESC-2"), "ticket_writes_disabled")
        if key not in self.state.ticket_ledger:
            if len(self.state.ticket_ledger) >= 32:
                return self._reply("escalate", "Human review is required; the session ticket limit was reached. No new ticket was created.", ("ESC-2",))
            self.state.ticket_ledger[key] = None  # Mark before execution; uncertain writes must not auto-retry.
            summary = (f"Customer issue: {reason}; detected intent: {self.state.intent}. "
                       f"Order reference: {oid or 'omitted because caller is unverified'}. "
                       f"Checks: {'verified mock lookup completed' if oid else 'no private order data accessed'}. "
                       f"Escalation reason: {reason}. Customer reports this issue; no outcome approved.")
            arguments = {"summary": summary, "reason": reason, "intent": self.state.intent}
            if oid:
                arguments["order_id"] = oid
            self._calls.append(ToolCall("create_ticket", arguments))
            try:
                result = self.gateway.create_ticket(**arguments)
                identifier = result.get("ticket_id")
                if result.get("created") is True and isinstance(identifier, str) and re.fullmatch(r"TKT[A-Za-z0-9-]{8,80}", identifier):
                    self.state.ticket_ledger[key] = identifier
            except ToolExecutionError:
                pass
        ticket = self.state.ticket_ledger[key]
        if not ticket:
            return self._reply("escalate", warning + "Human review is needed, but ticket creation could not be confirmed. No automatic retry was made.",
                               ("ESC-2", "ESC-4"), "ticket_unconfirmed")
        return self._reply("escalate", warning + f"Ticket {ticket} is confirmed for human follow-up. No refund, compensation or cancellation has been approved.",
                           ("ESC-1", "ESC-2"), "ticket_confirmed")

    def _begin_order(self, oid):
        if self.state.order_id not in (None, oid):
            self.state.refund_not_received = False
            self.state.requested_sku = None
            self.state.requested_reason = None
        self.state.order_id, self.state.order = oid, None
        self.state.line_no = self.state.quantity = None
        self.public.reset()
        if self.state.failures.get(oid, 0) >= 2:
            self.state.phase = "locked"
            return self._reply("refuse", "Verification could not be completed. I cannot share order details. Please contact support from your registered phone; general policy help is still available.", ("IDV-3",))
        if oid not in self.state.failures and len(self.state.failures) >= 32:
            self.state.phase = "locked"
            return self._reply("refuse", "The session verification limit was reached. Please use support from your registered phone.", ("IDV-3",))
        self.state.failures.setdefault(oid, 0)
        self.state.phase = "proof"
        self._lookup()  # Required initial unverified lookup; existence is never disclosed.
        return self._reply("clarify", "Please provide one value: the last four digits of your registered phone OR the six-digit delivery pincode. Do not send the full phone number.", ("IDV-1", "IDV-2"), "verification_required")

    def _verify(self, message):
        oid = self.state.order_id
        if self.state.failures[oid] >= 2:
            return self._begin_order(oid)
        proof = submitted_proof(message)
        self.state.failures[oid] += 1  # Malformed submissions also consume an attempt; never sanitize into valid proof.
        result = self._lookup(proof) if proof else {"verified": False}
        if result.get("verified") is True and result.get("found") is True and result.get("order_id") == oid:
            self.state.failures[oid] -= 1  # Successful proof is not a failed attempt.
            self.state.order = result
            self.state.phase = "verified"
            self.public.reset()
            return self._answer_private()
        if self.state.failures[oid] >= 2:
            self.state.phase = "locked"
            return self._reply("refuse", "Verification failed or could not be completed. No order details can be shared. Contact support from your registered phone.", ("IDV-3",), "verification_locked")
        return self._reply("clarify", "I could not verify that value. You have one retry: provide one four-digit phone suffix or six-digit delivery pincode.", ("IDV-3",), "verification_retry")

    def _selected_item(self):
        order = self.state.order
        if self.state.requested_sku and self.state.line_no is None:
            return item_for(order, sku=self.state.requested_sku)
        item = item_for(order, self.state.line_no)
        if item is None and self.state.line_no is None:
            if self.state.intent == "damage" and order.get("damage_sku"):
                item = item_for(order, sku=order["damage_sku"])
        return item

    def _answer_private(self):
        order = self.state.order
        if not order:
            raise ValueError("Private rendering requires a verified tool result")
        if (order.get("contacts_last_7_days") or 0) >= 2:
            return self._handover("repeat_contact")
        intent = self.state.intent
        item = self._selected_item()
        if intent == "damage":
            if item is None:
                return self._reply("clarify", "Which item line is affected? Use /item LINE QTY; I will not guess between items.", ("DWM-1",))
            if item["unit_price_inr"] > 10000:
                return self._handover("high_value_damage")
            hours = order.get("damage_hours_after_delivery")
            if hours is None:
                return self._reply("clarify", "How many hours after delivery was the issue reported, and are photos of the item and packaging available? No claim is approved yet.", ("DWM-1", "DWM-2"))
            return self._reply("answer", f"The recorded report was {hours} hours after delivery. " +
                               ("It is within the 48-hour reporting window; photos and claim review are still required."
                                if hours <= 48 else "It is outside 48 hours; normal return-window or warranty review is needed. No refund is approved."),
                               ("DWM-1", "DWM-4"))
        if intent == "refunds":
            timing = refund_timing(order, self.calendar, self.reference_date)
            status = timing["status"]
            if status == "not_initiated":
                return self._reply("answer", "No refund initiation is recorded. Return refunds depend on pickup and QC; Plus initiation is at pickup. COD bank transfers require verified bank details. I cannot initiate a refund.", ("REF-1", "REF-3"))
            if status == "review_required":
                return self._reply("clarify", "The recorded refund route needs review; I cannot calculate a reliable deadline from it.", ("REF-1", "REF-2"))
            facts = ""
            if type(timing.get("amount_inr")) is int:
                facts += f"Recorded refund amount: INR {timing['amount_inr']}. "
            if timing.get("rrn"):
                facts += f"Refund reference: {timing['rrn']}. "
            if status == "completed":
                return self._reply("answer", facts + f"Completion is recorded on {timing['completed_on']}.", ("REF-2", "REF-6"))
            if status == "wallet_timing":
                return self._reply("answer", facts + "Wallet refunds are instant, within two hours. Only an initiation date is recorded, so I cannot calculate the exact hourly deadline or assert completion.", ("REF-2", "REF-3", "REF-6"))
            if timing["escalation_threshold_exceeded"] and self.state.refund_not_received:
                return self._handover("refund_overdue")
            return self._reply("answer", facts + f"The recorded initiation gives an expected window of {timing['earliest']} through {timing['latest']}. "
                               "Business days are Monday-Saturday excluding listed holidays. An absent completion field is not proof that the bank has not paid.", ("REF-2", "REF-6", "KB-00.3"))
        if intent == "return_window":
            if item is None:
                return self._reply("clarify", "Please select one item line using /item LINE QTY; I will not choose between multiple items.", ("RET-2",))
            recorded_reason = order.get("return_reason")
            reason = self.state.requested_reason or ("change_of_mind" if recorded_reason == "changed_mind" else recorded_reason)
            result = return_window(self.public.engine, order, item, reason=reason or "change_of_mind")
            status = result["status"]
            if status in {"not_delivered", "not_returnable", "review_required", "damage_review"}:
                explanations = {"not_delivered": "No delivery date is recorded, so the return window cannot be calculated.",
                                "not_returnable": "This category is not returnable for change of mind. Damage/wrong-item cases use a separate review.",
                                "review_required": "The delivery date falls outside supported policy coverage; human review is needed.",
                                "damage_review": "This is a damage/wrong-item case; the 48-hour reporting rules and claim review apply, not automatic change-of-mind approval."}
                return self._reply("clarify" if status in {"damage_review", "review_required"} else "answer", explanations[status], result["evidence"])
            text = f"The {result['days']}-calendar-day window ends on {result['deadline']}; it is {'within' if status == 'within_window' else 'past'} the date window when evaluated on {result['evaluated_on']}. Item-condition rules still apply. "
            evidence = list(result["evidence"]) + ["RET-4"]
            quantity = self.state.quantity
            if quantity is None and order.get("return_line_no") == item["line_no"]:
                quantity = order.get("return_qty")
            if status == "within_window" and quantity and reason in {"change_of_mind", "damaged", "defective", "wrong"}:
                estimate = refund_estimate(order, item, quantity, reason=reason)
                if estimate["status"] == "estimate_only":
                    text += f"For {quantity} unit(s), the arithmetic estimate is INR {estimate['amount_inr']}, including INR {estimate['pickup_fee_inr']} pickup deduction. This is not approval or a payout."
                    evidence += list(estimate["evidence"])
                else:
                    text += "The refund arithmetic needs human review."
            elif status == "within_window":
                text += "A selected line, quantity, and clearly classified return reason are required for an estimate; no reason or fee will be guessed."
            return self._reply("answer", text, tuple(dict.fromkeys(evidence)))
        if intent == "cancellations":
            if order.get("status") == "cancelled":
                return self._reply("answer", "The order is already recorded as cancelled. This assistant did not cancel it; ask about refunds to check the recorded refund route.", ("CAN-1", "REF-1"))
            if order.get("status") in {"placed", "packed"} and not order.get("shipped_on"):
                if order.get("delivery_type") == "slot":
                    return self._reply("clarify", "Please check the chosen grocery slot start time in My Orders. It is not recorded, so I cannot confirm whether its two-hour cancellation cutoff passed.", ("CAN-3",))
                text = "The order is recorded as not shipped. Cancel it yourself from My Orders; this assistant cannot cancel it. For a completed prepaid cancellation, refund initiation is immediate."
                evidence = ["CAN-1", "REF-1"]
                if order.get("payment_method") == "cod":
                    text += " This is COD; no prepaid refund is implied."
                elif item and self.state.quantity:
                    estimate = refund_estimate(order, item, self.state.quantity, cancellation=True)
                    if estimate["status"] == "estimate_only":
                        text += f" Selected-line arithmetic estimate: INR {estimate['amount_inr']}; this is not a cancellation or refund approval."
                        evidence.extend(("CAN-4", "REF-4", "REF-5"))
                return self._reply("answer", text, tuple(evidence))
            return self._reply("answer", "A shipped order cannot be cancelled by the assistant. Refusal at the door or an eligible return may apply; prepaid refusal refunds wait for warehouse receipt.", ("CAN-2", "REF-1"))
        if intent == "delivery":
            text = f"Recorded status: {order['status']}. Promised date: {order.get('promised_date') or 'not recorded'}. "
            if order.get("delivery_type") == "express" and order.get("delivered_on") and order.get("promised_date") and order["delivered_on"] > order["promised_date"]:
                if order.get("is_plus") or not order.get("delivery_fee_inr"):
                    text += "No paid Express fee is eligible for a credit."
                elif order.get("express_late_credit_on"):
                    text += f"Wallet credit of INR {order['express_late_credit_inr']} is recorded on {order['express_late_credit_on']}."
                else:
                    text += "The paid Express fee is covered by the automatic 48-hour wallet-credit rule; I cannot assert it has posted."
            elif order.get("delivery_type") == "standard":
                text += "Late Standard delivery has no compensation under this policy."
            return self._reply("answer", text, ("DEL-1", "DEL-4"))
        return self._reply("answer", f"Verified order status: {order['status']}. You can ask about delivery, returns, refunds, cancellation or an item issue.", ("IDV-1",))

    def respond(self, request: AgentRequest):
        self._calls = []
        self.last_trace = GroundingTrace()
        if not isinstance(request.session_id, str) or not request.session_id.strip():
            raise ValueError("A backend-owned session ID is required")
        if self.state.session_id is not None and request.session_id != self.state.session_id:
            raise ValueError("Support agent belongs to a different session; create a new instance")
        if not isinstance(request.message, str) or not request.message.strip() or len(request.message) > 12000:
            raise ValueError("Use a nonempty support message of at most 12000 characters")
        self.state.session_id = request.session_id
        self.language = choose_language(request.message, self.language, self.preferred_language)
        request = replace(request, message=request.message.translate(DIGITS))
        text = normalize(request.message).strip()
        if text == "/reset":
            self.reset()
            return self._reply("clarify", "Conversation details cleared. Verification attempt limits remain active in this session.", reason="workflow_reset")
        if text.startswith("/policy "):
            self.reset()
            return self._public_reply(AgentRequest(request.session_id, request.message[8:]))
        if re.search(r"\b(?:another|different|new)\s+order\b|दूसर[ेा] ऑर्डर|(?:doosra|dusra) order", text):
            self.reset()
            self.state.phase = "order"
        explicit = {value.replace(" ", "").replace("-", "") for value in ORDER_ID.findall(request.message)}
        if len(explicit) > 1:
            self.state.order = None
            self.state.order_id = None
            self.state.phase = "order"
            self.public.reset()
            return self._reply("clarify", "Please provide one eight-digit order ID. No order is verified.", ("IDV-1",))
        if explicit and next(iter(explicit)) != self.state.order_id:
            self.state.order = None
            self.state.order_id = next(iter(explicit))
            self.state.phase = "public"
            self.state.line_no = self.state.quantity = None
            self.state.requested_sku = None
            self.state.requested_reason = None
            self.state.refund_not_received = False
            self.public.reset()
        topics = [name for name, pattern in TOPIC_PATTERNS if re.search(pattern, text)]
        if topics:
            self.state.intent = {"return_fee": "return_window", "pickup": "return_window"}.get(topics[0], topics[0])
        skus = {sku.upper() for sku in SKU_PATTERN.findall(request.message)}
        if len(skus) > 1:
            self.state.requested_sku = None
            self.state.line_no = self.state.quantity = None
            return self._reply("clarify", "Please discuss one SKU at a time, or select an item line after verification.")
        if skus:
            self.state.requested_sku = next(iter(skus))
            self.state.line_no = self.state.quantity = None
        if re.search(r"not received|not arrived|hasn't arrived|where.{0,20}refund|refund.{0,20}(?:late|pending)|(?:रिफंड|पैसे).{0,20}नहीं (?:मिल|आ)|refund.{0,20}nahi (?:mil|aay|aay|aya)", text):
            self.state.refund_not_received = True
        try:
            for reason, pattern in IMMEDIATE:
                if re.search(pattern, text):
                    return self._handover(reason)
            if explicit:
                oid = next(iter(explicit))
                if oid != self.state.order_id or not self.state.verified:
                    return self._begin_order(oid)
            if self.state.phase != "proof" and re.fullmatch(r"[0-9]{4}[ -]?[0-9]{4}", text):
                return self._begin_order(text.replace(" ", "").replace("-", ""))
            if self.state.phase == "order":
                candidates = GROUPED_ORDER.findall(request.message)
                if len(candidates) == 1:
                    return self._begin_order(candidates[0].replace(" ", "").replace("-", ""))
                return self._reply("clarify", "Please provide the eight-digit order ID first. Do not send verification proof yet.", ("IDV-1", "IDV-2"))
            if self.state.phase == "proof":
                return self._verify(request.message)
            if self.state.phase == "locked":
                return self._reply("refuse", "Verification could not be completed; no specific-order details can be shared. Use /policy for general help.", ("IDV-3",))
            if self.state.verified:
                if text.startswith("/reason "):
                    reason = text[8:].strip()
                    if reason not in {"change_of_mind", "damaged", "defective", "wrong", "missing", "expired"}:
                        return self._reply("clarify", "Use /reason followed by change_of_mind, damaged, defective, wrong, missing, or expired. The estimate is conditional, not claim approval.")
                    self.state.requested_reason = reason
                    self.state.intent = "return_window" if reason == "change_of_mind" else "damage"
                if text == "/items":
                    lines = [f"line {item['line_no']}: {item['sku']}, quantity {item['qty']}" for item in self.state.order["items"]]
                    return self._reply("answer", "Verified order items: " + "; ".join(lines), ("IDV-1",))
                selected = re.fullmatch(r"/item\s+([0-9]{1,3})\s+([0-9]{1,3})", text)
                if selected:
                    self.state.line_no, self.state.quantity = int(selected[1]), int(selected[2])
                    self.state.requested_sku = None
                    item = item_for(self.state.order, self.state.line_no)
                    if item is None or not 1 <= self.state.quantity <= item["qty"]:
                        self.state.line_no = self.state.quantity = None
                        return self._reply("clarify", "That line or quantity is not valid for this order. Please use /item LINE QTY.")
                return self._answer_private()
            if submitted_proof(request.message) or PROOF.fullmatch(text) or re.search(r"\b(?:my|mera|meri|mere)\s+(?:order|refund|return|delivery)|\border\s+(?:status|id|number|[0-9])|\border\b.{0,25}[0-9]|\border\b.{0,50}\b(?:help|status|baare)\b|/order|(?:मेर[ाेी]|अपने).{0,15}(?:ऑर्डर|रिफंड|डिलीवरी)|ऑर्डर.{0,20}(?:मदद|स्थिति|नंबर)", text):
                self.state.phase = "order"
                return self._reply("clarify", "Please provide the eight-digit order ID first. Do not send verification proof yet.", ("IDV-1", "IDV-2"))
        except ToolExecutionError:
            return self._reply("clarify", "The mock tool could not complete safely. No private details or action success can be confirmed.", reason="tool_error")
        except (ValueError, KeyError, TypeError):
            return self._reply("clarify", "The verified record does not support a safe calculation for this request. Human review is needed; no amount or action is approved.", reason="calculation_review")
        return self._public_reply(request)
