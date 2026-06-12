from typing import Protocol, Tuple, Dict, Any


class PaymentProvider(Protocol):
    """Interface for PSP adapters."""

    name: str

    def create_payment_method_from_token(self, token: str, email: str) -> Dict[str, Any]:
        ...

    def attach_payment_method_to_customer(self, payment_method_id: str, customer_ref: str) -> Dict[str, Any]:
        ...

    def create_subscription(self, customer_ref: str, plan_code: str) -> Dict[str, Any]:
        ...

    def create_invoice(self, customer_ref: str, amount_cents: int, currency: str) -> Dict[str, Any]:
        ...

    def pay_invoice(self, invoice_provider_id: str) -> Dict[str, Any]:
        ...

    def handle_webhook(self, payload: Dict[str, Any], headers: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
        """Returns (event_type, normalized_payload)."""
        ...
