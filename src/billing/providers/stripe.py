from typing import Dict, Any, Tuple

try:
    import stripe  # type: ignore
except Exception:
    stripe = None

from src.billing.providers.base import PaymentProvider


class StripeProvider(PaymentProvider):
    name = "stripe"

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or ""
        if stripe and api_key:
            stripe.api_key = api_key

    def _guard(self):
        if not stripe:
            raise RuntimeError("stripe SDK not installed")
        if not self.api_key:
            raise RuntimeError("stripe api key missing")

    def create_payment_method_from_token(self, token: str, email: str) -> Dict[str, Any]:
        self._guard()
        pm = stripe.PaymentMethod.create(type="card", card={"token": token}, billing_details={"email": email})
        card = getattr(pm, "card", None)
        return {
            "id": pm["id"],
            "brand": getattr(card, "brand", None) if card else None,
            "last4": getattr(card, "last4", None) if card else None,
        }

    def attach_payment_method_to_customer(self, payment_method_id: str, customer_ref: str) -> Dict[str, Any]:
        self._guard()
        stripe.PaymentMethod.attach(payment_method_id, customer=customer_ref)
        return {"id": payment_method_id}

    def create_customer(self, email: str, payment_method_id: str | None = None) -> Dict[str, Any]:
        self._guard()
        kwargs = {"email": email}
        if payment_method_id:
            kwargs["payment_method"] = payment_method_id
            kwargs["invoice_settings"] = {"default_payment_method": payment_method_id}
        cust = stripe.Customer.create(**kwargs)
        return {"id": cust["id"]}

    def create_subscription(self, customer_ref: str, plan_code: str) -> Dict[str, Any]:
        self._guard()
        # Assumes plan_code maps to a Stripe price id
        sub = stripe.Subscription.create(customer=customer_ref, items=[{"price": plan_code}], expand=["latest_invoice.payment_intent"])
        latest_invoice = getattr(sub, "latest_invoice", None)
        payment_intent = getattr(latest_invoice, "payment_intent", None) if latest_invoice else None
        return {
            "id": sub["id"],
            "status": getattr(sub, "status", None),
            "client_secret": getattr(payment_intent, "client_secret", None) if payment_intent else None,
        }

    def create_invoice(self, customer_ref: str, amount_cents: int, currency: str) -> Dict[str, Any]:
        self._guard()
        invoice = stripe.Invoice.create(customer=customer_ref, auto_advance=True, collection_method="charge_automatically")
        return {"id": invoice["id"], "status": getattr(invoice, "status", None)}

    def pay_invoice(self, invoice_provider_id: str) -> Dict[str, Any]:
        self._guard()
        inv = stripe.Invoice.pay(invoice_provider_id)
        return {
            "id": inv["id"],
            "status": getattr(inv, "status", None),
            "payment_intent": getattr(inv, "payment_intent", None),
        }

    def handle_webhook(self, payload: Dict[str, Any], headers: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
        # Do not verify signature here; leave to caller to keep this adapter simple.
        event_type = payload.get("type") or "unknown"
        return event_type, payload
