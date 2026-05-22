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
        event_type = payload.get("type") or "unknown"
        obj = (payload.get("data") or {}).get("object") or {}

        if event_type in ("customer.subscription.created", "customer.subscription.updated", "customer.subscription.deleted"):
            period_end = obj.get("current_period_end")
            return event_type, {
                "stripe_subscription_id": obj.get("id"),
                "stripe_customer_id": obj.get("customer"),
                "status": obj.get("status"),
                "plan_choice": (obj.get("metadata") or {}).get("plan_choice"),
                "price_id": ((obj.get("items") or {}).get("data") or [{}])[0].get("price", {}).get("id"),
                "current_period_end": period_end,
                "cancel_at_period_end": obj.get("cancel_at_period_end", False),
            }

        if event_type == "invoice.paid":
            return event_type, {
                "stripe_invoice_id": obj.get("id"),
                "stripe_subscription_id": obj.get("subscription"),
                "amount_paid": obj.get("amount_paid") or obj.get("total") or 0,
                "currency": (obj.get("currency") or "gbp").upper(),
                "hosted_invoice_url": obj.get("hosted_invoice_url"),
            }

        if event_type == "invoice.payment_failed":
            return event_type, {
                "stripe_invoice_id": obj.get("id"),
                "stripe_subscription_id": obj.get("subscription"),
            }

        return event_type, payload
