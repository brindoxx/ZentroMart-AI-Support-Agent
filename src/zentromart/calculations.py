"""Deterministic arithmetic for the frozen synthetic policy snapshot, not financial advice."""

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import json

from .config import FROZEN_REFERENCE_DATE
from .dataset import read_table
from .policy import PolicyContext, PolicyEngine


RULE_VERSION = "zentromart-calculations-v1"
RULE_SOURCES = frozenset({"RET-2", "RET-3", "RET-6", "RET-8", "RETv3-2", "REF-1", "REF-2", "REF-3",
                         "REF-4", "REF-5", "CAN-1", "CAN-2", "CAN-3", "DEL-4", "DWM-1", "DWM-3",
                         "DWM-5", "ESC-1", "ESC-2", "IDV-1", "IDV-3", "PLS-2",
                         "IDV-2", "IDV-4", "RET-4", "RET-5", "RET-7", "REF-6", "DEL-1",
                         "ESC-3", "ESC-4", "DWM-2", "DWM-4", "KB-00.3", "CAN-4"})
POLICY_SHA256 = "39eb96b4d20e55ebc25bec61fde55c60f9967d71d64a66d84768e5a76ba70aba"
WINDOWS = {"electronics": 7, "fashion": 15, "home_kitchen": 10, "beauty_sealed": 7, "books_media": 10,
           "grocery": None, "innerwear": None, "digital": None}
REFUND_DAYS = {"upi": (1, 3), "card": (5, 7), "netbanking": (3, 5), "cod_bank": (5, 7)}


def validate_policy_snapshot(index) -> str:
    selected = sorted((doc for doc in index.documents if doc.evidence_id in RULE_SOURCES), key=lambda doc: doc.evidence_id)
    values = [{"id": doc.evidence_id, "text": "\n".join(doc.text.splitlines()),
               "status": doc.metadata["status"], "version": doc.metadata["version"],
               "effective_from": doc.metadata["effective_from"]} for doc in selected]
    digest = hashlib.sha256(json.dumps(values, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
    if digest != POLICY_SHA256:
        raise ValueError("Policy sources changed; review the deterministic workflow/calculation adapter")
    return digest


def integer(value, *, minimum=0) -> int:
    if type(value) is not int or value < minimum:
        raise ValueError("Expected a nonnegative integer amount or count")
    return value


@dataclass(frozen=True)
class BusinessCalendar:
    holidays: frozenset[date]

    @classmethod
    def load(cls, dataset_dir):
        _, rows = read_table(dataset_dir / "data/holidays.csv")
        return cls(frozenset(date.fromisoformat(row["date"]) for row in rows))

    def is_business_day(self, day: date) -> bool:
        return day.weekday() != 6 and day not in self.holidays  # Monday-Saturday, not Monday-Friday.

    def add(self, start: date, days: int) -> date:
        integer(days)
        if days > 366:
            raise ValueError("Business-day range exceeds the calculation budget")
        current = start
        while days:
            current += timedelta(days=1)
            if self.is_business_day(current):
                days -= 1
        return current

    def elapsed(self, start: date, end: date) -> int:
        if end < start or (end - start).days > 3660:
            raise ValueError("Invalid or over-budget business-day range")
        return sum(self.is_business_day(start + timedelta(days=i)) for i in range(1, (end - start).days + 1))


def item_for(order: dict, line_no: int | None = None, sku: str | None = None) -> dict | None:
    """Do not guess between repeated SKUs or multiple lines."""
    items = order.get("items", [])
    selected = [item for item in items if (line_no is None or item.get("line_no") == line_no)
                and (sku is None or item.get("sku") == sku)]
    return selected[0] if len(selected) == 1 else None


def return_window(engine: PolicyEngine, order: dict, item: dict, *, reason="change_of_mind") -> dict:
    delivered = order.get("delivered_on")
    if not delivered:
        return {"status": "not_delivered", "evidence": ("RET-2",)}
    delivery = date.fromisoformat(delivered)
    placed = date.fromisoformat(order["placed_at"][:10])
    if delivery > engine.reference_date or placed > delivery:
        raise ValueError("Inconsistent verified order dates")
    category = item["return_category"]
    if category not in WINDOWS:
        raise ValueError("Unknown return category")
    if reason in {"damaged", "defective", "wrong", "missing", "expired"}:
        return {"status": "damage_review", "evidence": ("DWM-1", "DWM-3", "DWM-4")}
    context = PolicyContext("return_window", category=category, delivered_on=delivery, placed_on=placed)
    bundle = engine.assemble("return window", context)
    if bundle["resolution"] != "evidence_prepared":
        return {"status": "review_required", "evidence": ("RET-3",)}
    days = WINDOWS[category]
    evidence = ["RET-2"]
    if days is None:
        return {"status": "not_returnable", "evidence": ("RET-2", "RET-5")}
    if bundle["applicability"]["historical_electronics_window"] == "applicable":
        days, evidence = 10, ["RETv3-2", "RET-3"]
    if bundle["applicability"]["festive_fashion_extension"] == "applicable":
        days, evidence = 30, ["RET-8"]
    deadline = delivery + timedelta(days=days)
    evaluated_on = engine.reference_date
    if order.get("return_line_no") == item["line_no"] and order.get("return_requested_on"):
        evaluated_on = date.fromisoformat(order["return_requested_on"])
        if not delivery <= evaluated_on <= engine.reference_date:
            raise ValueError("Invalid recorded return-request date")
    return {"status": "within_window" if evaluated_on <= deadline else "window_passed",
            "days": days, "deadline": deadline.isoformat(), "evidence": tuple(evidence),
            "evaluated_on": evaluated_on.isoformat(),
            "convention": "delivery is day zero; calendar deadline is inclusive"}


def pickup_fee(category: str, reason: str, is_plus: bool) -> int:
    if type(is_plus) is not bool or category not in WINDOWS:
        raise ValueError("Missing membership or category fact")
    if reason not in {"change_of_mind", "damaged", "defective", "wrong", "missing", "expired"}:
        raise ValueError("Unknown return reason; no fee is guessed")
    return 49 if category == "fashion" and reason == "change_of_mind" and not is_plus else 0


def refund_estimate(order: dict, item: dict, quantity: int, *, reason="change_of_mind", cancellation=False) -> dict:
    """A quote, never a refund approval or mutation. Round once, half-up, at the end."""
    quantity = integer(quantity, minimum=1)
    if quantity > integer(item["qty"], minimum=1):
        raise ValueError("Return quantity exceeds the verified line quantity")
    subtotal = integer(order["subtotal_inr"], minimum=1)
    discount = integer(order.get("coupon_discount_inr") or 0)
    if discount > subtotal:
        raise ValueError("Coupon exceeds the verified subtotal")
    if cancellation and (order.get("shipped_on") or order.get("status") not in {"placed", "packed"}):
        raise ValueError("Cancellation arithmetic is only for unshipped orders")
    gross = integer(item["unit_price_inr"]) * quantity
    if gross > subtotal:
        raise ValueError("Selected item exceeds the verified subtotal")
    remaining = subtotal - gross
    allocated = Decimal(discount) * Decimal(gross) / Decimal(subtotal)
    clawback = Decimal(0)
    if remaining and remaining < integer(order.get("coupon_min_order_inr") or 0):
        clawback = Decimal(discount) - allocated
    fee = 0 if cancellation else pickup_fee(item["return_category"], reason, order["is_plus"])
    fees = 0
    if not remaining and (cancellation or reason in {"damaged", "defective", "wrong"}):
        fees = integer(order.get("delivery_fee_inr") or 0) + integer(order.get("cod_fee_inr") or 0)
    net = Decimal(gross) - allocated - clawback - Decimal(fee) + Decimal(fees)
    if net < 0:
        return {"status": "review_required", "evidence": ("REF-4", "RET-6")}
    return {"status": "estimate_only", "amount_inr": int(net.quantize(Decimal("1"), rounding=ROUND_HALF_UP)),
            "pickup_fee_inr": fee, "fees_refunded_inr": fees,
            "coupon_clawback": clawback > 0, "evidence": ("REF-4", "REF-5", "RET-6")}


def refund_timing(order: dict, calendar: BusinessCalendar, reference=FROZEN_REFERENCE_DATE) -> dict:
    prefixes = [name for name in ("return", "cancellation", "rto") if order.get(f"{name}_refund_initiated_on")]
    if len(prefixes) != 1:
        return {"status": "not_initiated" if not prefixes else "review_required", "evidence": ("REF-1",)}
    prefix = prefixes[0]
    initiated = date.fromisoformat(order[f"{prefix}_refund_initiated_on"])
    if initiated > reference:
        raise ValueError("Refund initiation follows the dataset reference date")
    method = order.get(f"{prefix}_refund_method")
    completed = order.get("return_refund_completed_on") if prefix == "return" else None
    common = {"prefix": prefix, "method": method, "amount_inr": order.get(f"{prefix}_refund_amount_inr"),
              "rrn": order.get(f"{prefix}_rrn"), "completed_on": completed,
              "evidence": ("REF-2", "REF-3", "REF-6")}
    if completed:
        if date.fromisoformat(completed) < initiated or date.fromisoformat(completed) > reference:
            raise ValueError("Invalid refund-completion date")
        return {**common, "status": "completed"}
    if method in {"wallet", "cod_wallet"}:
        return {**common, "status": "wallet_timing", "hours": 2}
    if method not in REFUND_DAYS:
        return {**common, "status": "review_required"}
    minimum, maximum = REFUND_DAYS[method]
    earliest, latest = calendar.add(initiated, minimum), calendar.add(initiated, maximum)
    late_days = calendar.elapsed(latest, reference) if reference > latest else 0
    return {**common, "status": "dated_timing", "earliest": earliest.isoformat(), "latest": latest.isoformat(),
            "late_business_days": late_days, "escalation_threshold_exceeded": late_days > 3}
