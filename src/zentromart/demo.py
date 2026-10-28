"""Public, invented tutorial orders, isolated from the supplied practice dataset.

These credentials are intentionally visible. Demo mode is not authentication.
The normal SupportAgent still performs its verification sequence and calculations.
"""

from copy import deepcopy
import re


SCENARIOS = (
    {"id": "81000001", "proof": "4242", "title": "Track a shipped order", "question": "Where is my order?",
     "followup": "What is the delivery status?"},
    {"id": "81000002", "proof": "1515", "title": "Return estimate with a coupon", "question": "I want to return my order",
     "followup": "Return window please"},
    {"id": "81000003", "proof": "3030", "title": "Check an initiated UPI refund", "question": "When will my refund arrive?",
     "followup": "Refund timing please"},
    {"id": "81000004", "proof": "9090", "title": "Damaged high-value item", "question": "My order arrived damaged",
     "followup": "My item is damaged"},
)


def demo_order(order_id):
    order = {"order_id": order_id, "status": "delivered", "payment_method": "upi", "delivery_type": "standard",
             "placed_at": "2026-10-10T12:00", "delivered_on": "2026-10-15", "shipped_on": "2026-10-11",
             "promised_date": "2026-10-14", "subtotal_inr": 1000, "coupon_discount_inr": 100,
             "coupon_min_order_inr": 750, "delivery_fee_inr": 40, "cod_fee_inr": 0, "is_plus": False,
             "contacts_last_7_days": 0, "return_reason": "changed_mind", "return_line_no": 1, "return_qty": 1,
             "items": [{"line_no": 1, "sku": "DMO-0001", "return_category": "fashion", "qty": 2, "unit_price_inr": 500}]}
    if order_id == "81000001":
        order.update(status="shipped", delivered_on=None, promised_date="2026-10-22", return_reason=None)
    elif order_id == "81000003":
        order.update(status="return_refund_initiated", return_refund_initiated_on="2026-10-16",
                     return_refund_method="upi", return_refund_amount_inr=351, return_rrn="DEMOREF0003")
    elif order_id == "81000004":
        order.update(subtotal_inr=15000, coupon_discount_inr=0, coupon_min_order_inr=0,
                     return_reason=None, damage_sku="DMO-0004", damage_hours_after_delivery=12)
        order["items"] = [{"line_no": 1, "sku": "DMO-0004", "return_category": "electronics", "qty": 1, "unit_price_inr": 15000}]
    return order


class DemoGateway:
    def __init__(self, ticket_gateway):
        self.ticket_gateway = ticket_gateway
        self.allow_ticket_writes = False

    @property
    def allow_ticket_writes(self):
        return self.ticket_gateway.allow_ticket_writes

    @allow_ticket_writes.setter
    def allow_ticket_writes(self, enabled):
        if type(enabled) is not bool:
            raise ValueError("Ticket consent must be boolean")
        self.ticket_gateway.allow_ticket_writes = enabled

    def lookup_order(self, order_id, verification_value=None):
        if not isinstance(order_id, str) or not re.fullmatch(r"[0-9]{8}", order_id):
            raise ValueError("Use an eight-digit order ID")
        if verification_value is None:
            return {"verification_required": True}
        if not isinstance(verification_value, str) or not re.fullmatch(r"[0-9]{4}|[0-9]{6}", verification_value):
            raise ValueError("Provide one verification value")
        case = next((case for case in SCENARIOS if case["id"] == order_id), None)
        if not case or verification_value != case["proof"]:
            return {"verified": False, "verification_required": True}
        return {"verified": True, "found": True, **deepcopy(demo_order(order_id))}

    def create_ticket(self, **arguments):
        if not self.allow_ticket_writes:
            return {"created": False, "disabled": True}
        return self.ticket_gateway.create_ticket(**arguments)
