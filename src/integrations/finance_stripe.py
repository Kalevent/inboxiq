"""
Normalise Stripe webhook events into a common FinanceTransaction dict.

Output dict keys (all events):
    stripe_event_id             str
    stripe_payment_intent_id    str | None
    stripe_customer_id          str | None
    amount_cents                int
    currency                    str    — uppercase ISO code e.g. "GBP"
    customer_email              str | None
    customer_name               str | None
    description                 str | None
    metadata                    dict
    event_type                  str
    event_created               int | None  — Unix timestamp from Stripe
"""
from __future__ import annotations

SUPPORTED_EVENTS = frozenset({
    "checkout.session.completed",
    "payment_intent.succeeded",
})


def normalize_stripe_event(event: dict) -> dict:
    """Convert a raw Stripe event dict into a FinanceTransaction dict."""
    event_type = event.get("type", "")
    if event_type not in SUPPORTED_EVENTS:
        raise ValueError(f"Unsupported Stripe event type: {event_type!r}")

    obj = event.get("data", {}).get("object", {})
    stripe_event_id = event.get("id", "")

    if event_type == "checkout.session.completed":
        return _from_checkout_session(obj, stripe_event_id)
    return _from_payment_intent(obj, stripe_event_id)


def _from_checkout_session(obj: dict, stripe_event_id: str) -> dict:
    customer_details = obj.get("customer_details") or {}
    return {
        "stripe_event_id": stripe_event_id,
        "stripe_payment_intent_id": obj.get("payment_intent"),
        "stripe_customer_id": obj.get("customer"),
        "amount_cents": obj.get("amount_total", 0),
        "currency": (obj.get("currency") or "usd").upper(),
        "customer_email": customer_details.get("email"),
        "customer_name": customer_details.get("name"),
        "description": None,
        "metadata": obj.get("metadata") or {},
        "event_type": "checkout.session.completed",
        "event_created": obj.get("created"),
    }


def _from_payment_intent(obj: dict, stripe_event_id: str) -> dict:
    return {
        "stripe_event_id": stripe_event_id,
        "stripe_payment_intent_id": obj.get("id"),
        "stripe_customer_id": obj.get("customer"),
        "amount_cents": obj.get("amount", 0),
        "currency": (obj.get("currency") or "usd").upper(),
        "customer_email": None,
        "customer_name": None,
        "description": obj.get("description"),
        "metadata": obj.get("metadata") or {},
        "event_type": "payment_intent.succeeded",
        "event_created": obj.get("created"),
    }
