"""
Finance Add-on — inbound Stripe webhook handler.

URL: POST /api/v1/finance/webhook/stripe/<provider_id>

The provider_id identifies a WebhookProvider record (provider_type="stripe")
that belongs to a specific InboxIQ account and stores the Stripe signing secret.
This endpoint is unauthenticated — security is via Stripe signature verification.
"""
import json
import logging
import os
from functools import lru_cache

from celery import Celery
from flask import request, jsonify, current_app

from src.api.v1 import v1
from src.models.automation import WebhookProvider
from src.models.addons import AccountAddOn
from src.crypto import decrypt_value

_log = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _celery_client() -> Celery:
    broker_url = current_app.config.get("CELERY_BROKER_URL") or os.getenv("CELERY_BROKER_URL")
    backend_url = current_app.config.get("CELERY_RESULT_BACKEND") or os.getenv("CELERY_RESULT_BACKEND")
    return Celery("inboxiq", broker=broker_url, backend=backend_url)


@v1.route("/finance/webhook/stripe/<provider_id>", methods=["POST"])  # nosemgrep: semgrep.inboxiq.auth.unprotected-write-endpoint
def finance_stripe_webhook(provider_id):
    """Receive Stripe payment events for a Finance add-on account."""
    raw_body = request.get_data()

    provider = WebhookProvider.query.filter_by(
        id=provider_id,
        provider_type="stripe",
        enabled=True,
    ).first()
    if not provider:
        return jsonify({"error": "not_found"}), 404

    if provider.webhook_signing_secret_encrypted:
        sig_header = request.headers.get("Stripe-Signature", "")
        secret = decrypt_value(provider.webhook_signing_secret_encrypted)
        try:
            import stripe as _stripe
            _stripe.Webhook.construct_event(raw_body, sig_header, secret)
        except Exception:
            _log.warning(
                "finance_webhook: invalid Stripe signature for provider_id=%s", provider_id
            )
            return jsonify({"error": "invalid_signature"}), 400

    addon = AccountAddOn.query.filter_by(
        account_id=provider.account_id,
        addon_type="finance",
        status="active",
    ).first()
    if not addon:
        return jsonify({"error": "addon_not_active"}), 403

    try:
        payload = json.loads(raw_body)
    except Exception:
        return jsonify({"error": "invalid_json"}), 400

    event_type = payload.get("type", "")
    supported = {"checkout.session.completed", "payment_intent.succeeded"}

    if event_type in supported:
        _celery_client().send_task(
            "finance_addon.process_stripe_event",
            kwargs={
                "account_id": provider.account_id,
                "provider_id": str(provider.id),
                "event": payload,
            },
            queue="inbox",
        )

    return jsonify({"received": True}), 200
