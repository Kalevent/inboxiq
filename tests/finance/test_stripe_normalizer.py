import pytest
from src.integrations.finance_stripe import (
    normalize_stripe_event,
    SUPPORTED_EVENTS,
)


CHECKOUT_EVENT = {
    "id": "evt_abc123",
    "type": "checkout.session.completed",
    "data": {
        "object": {
            "id": "cs_test_xxx",
            "payment_intent": "pi_abc",
            "customer": "cus_xyz",
            "amount_total": 4999,
            "currency": "gbp",
            "customer_details": {
                "email": "john@example.com",
                "name": "John Doe",
            },
            "metadata": {"order_id": "1234"},
        }
    },
}

PAYMENT_INTENT_EVENT = {
    "id": "evt_def456",
    "type": "payment_intent.succeeded",
    "data": {
        "object": {
            "id": "pi_def",
            "customer": "cus_abc",
            "amount": 2000,
            "currency": "usd",
            "description": "Subscription renewal",
            "metadata": {},
        }
    },
}


def test_normalize_checkout_session():
    tx = normalize_stripe_event(CHECKOUT_EVENT)
    assert tx["stripe_event_id"] == "evt_abc123"
    assert tx["stripe_payment_intent_id"] == "pi_abc"
    assert tx["stripe_customer_id"] == "cus_xyz"
    assert tx["amount_cents"] == 4999
    assert tx["currency"] == "GBP"
    assert tx["customer_email"] == "john@example.com"
    assert tx["customer_name"] == "John Doe"
    assert tx["event_type"] == "checkout.session.completed"


def test_normalize_payment_intent():
    tx = normalize_stripe_event(PAYMENT_INTENT_EVENT)
    assert tx["stripe_event_id"] == "evt_def456"
    assert tx["stripe_payment_intent_id"] == "pi_def"
    assert tx["amount_cents"] == 2000
    assert tx["currency"] == "USD"
    assert tx["customer_name"] is None  # not in payment_intent event
    assert tx["event_type"] == "payment_intent.succeeded"


def test_unsupported_event_raises():
    with pytest.raises(ValueError, match="Unsupported"):
        normalize_stripe_event({"type": "customer.created", "id": "evt_x", "data": {"object": {}}})


def test_supported_events_list():
    assert "checkout.session.completed" in SUPPORTED_EVENTS
    assert "payment_intent.succeeded" in SUPPORTED_EVENTS
