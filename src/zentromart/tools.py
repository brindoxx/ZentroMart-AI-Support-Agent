"""Boundary around the supplied synthetic tools, with no model-selected execution."""

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import re
from typing import Protocol


ORDER_FIELDS = frozenset("""order_id status placed_at payment_method delivery_type promised_date
shipped_on delivered_on delivery_attempts subtotal_inr delivery_fee_inr cod_fee_inr total_inr
coupon_code coupon_discount_inr coupon_min_order_inr contacts_last_7_days
cancellation_refund_initiated_on cancellation_refund_method cancellation_refund_amount_inr cancellation_rrn
rto_refund_initiated_on rto_refund_method rto_refund_amount_inr rto_rrn
express_late_credit_inr express_late_credit_on return_sku return_reason return_status return_line_no return_qty
return_requested_on return_pickup_on return_qc_passed_on return_refund_initiated_on return_refund_method
return_refund_amount_inr return_refund_completed_on return_rrn return_reverse_pickup_fee_inr
damage_sku damage_issue damage_reported_at damage_hours_after_delivery damage_photos_attached damage_status is_plus""".split())
ITEM_FIELDS = frozenset({"line_no", "sku", "return_category", "qty", "unit_price_inr"})


class ToolExecutionError(RuntimeError):
    def __init__(self):
        super().__init__("The mock tool could not complete safely; no action is confirmed.")


class ToolGateway(Protocol):
    def lookup_order(self, order_id: str, verification_value: str | None = None) -> dict: ...
    def create_ticket(self, summary: str, order_id: str | None = None,
                      reason: str | None = None, intent: str | None = None) -> dict: ...


class MockToolGateway:
    def __init__(self, dataset_dir: Path, ticket_dir: Path, *, allow_ticket_writes: bool = False):
        self.dataset_dir, self.ticket_dir = dataset_dir.resolve(), ticket_dir.resolve()
        self.allow_ticket_writes = allow_ticket_writes
        self._module = None

    def _backend(self):
        if self._module is None:
            try:
                spec = spec_from_file_location("zentromart_supplied_mock_tools", self.dataset_dir / "tools/tools.py")
                if spec is None or spec.loader is None:
                    raise ValueError
                module = module_from_spec(spec)
                spec.loader.exec_module(module)
                module._TICKETS = str(self.ticket_dir / "tickets_created.csv")
                self._module = module
            except Exception:
                raise ToolExecutionError() from None
        return self._module

    def lookup_order(self, order_id: str, verification_value: str | None = None) -> dict:
        if not isinstance(order_id, str) or not re.fullmatch(r"[0-9]{8}", order_id):
            raise ValueError("Use an eight-digit order ID")
        if verification_value is not None and (not isinstance(verification_value, str) or not re.fullmatch(r"(?:[0-9]{4}|[0-9]{6})", verification_value)):
            raise ValueError("Provide one four-digit phone suffix or six-digit delivery pincode")
        try:
            result = self._backend().lookup_order(order_id, verification_value=verification_value)
            if verification_value is None:
                return {"verification_required": True}  # Never disclose existence before proof.
            if result.get("verified") is not True or result.get("found") is not True:
                return {"verified": False, "verification_required": True}
            if result.get("order_id") != order_id or not isinstance(result.get("items"), list):
                raise ValueError
            # Drop addresses, contact fields, customer identity and the verification pincode.
            order = {key: result[key] for key in ORDER_FIELDS if key in result}
            order["items"] = [{key: item[key] for key in ITEM_FIELDS if key in item} for item in result["items"]]
            return {"verified": True, "found": True, **order}
        except Exception:
            raise ToolExecutionError() from None

    def create_ticket(self, summary: str, order_id: str | None = None,
                      reason: str | None = None, intent: str | None = None) -> dict:
        if not self.allow_ticket_writes:
            return {"created": False, "disabled": True}
        try:
            self.ticket_dir.mkdir(parents=True, exist_ok=True)
            result = self._backend().create_ticket(summary, order_id=order_id, reason=reason, intent=intent)
            identifier = result.get("ticket_id")
            if result.get("created") is True and isinstance(identifier, str) and re.fullmatch(r"TKT[A-Za-z0-9-]{8,80}", identifier):
                return {"created": True, "ticket_id": identifier}
            return {"created": False}
        except Exception:
            raise ToolExecutionError() from None
