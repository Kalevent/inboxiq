from typing import Dict, Any, Tuple
from src.billing.providers.base import PaymentProvider


class SecondaryProvider(PaymentProvider):
    """
    Lightweight placeholder provider (e.g., Adyen/Braintree). Implement calls when credentials are available.
    """

    name = "secondary"

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or ""

    def _guard(self):
        if not self.api_key:
            raise RuntimeError("secondary provider api key missing")

    def create_payment_method_from_token(self, token: str, email: str) -> Dict[str, Any]:
        self._guard()
        # Map token to provider PM id. Placeholder returns token as id for now.
        return {"id": token, "brand": None, "last4": None}

    def attach_payment_method_to_customer(self, payment_method_id: str, customer_ref: str) -> Dict[str, Any]:
        self._guard()
        return {"id": payment_method_id}

    def create_subscription(self, customer_ref: str, plan_code: str) -> Dict[str, Any]:
        self._guard()
        return {"id": f"{customer_ref}-sub", "status": "active"}

    def create_invoice(self, customer_ref: str, amount_cents: int, currency: str) -> Dict[str, Any]:
        self._guard()
        return {"id": f"inv-{customer_ref}", "status": "open"}

    def pay_invoice(self, invoice_provider_id: str) -> Dict[str, Any]:
        self._guard()
        return {"id": invoice_provider_id, "status": "paid"}

    def handle_webhook(self, payload: Dict[str, Any], headers: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
        event_type = payload.get("event") or "unknown"
        return event_type, payload
