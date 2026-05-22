"""
Finance Add-on — inbound Stripe webhook handler.

URL: POST /api/v1/finance/webhook/stripe/<provider_id>

The provider_id identifies a WebhookProvider record (provider_type="stripe")
that belongs to a specific InboxIQ account and stores the Stripe signing secret.
This endpoint is unauthenticated — security is via Stripe signature verification.
"""
import json
import logging

from flask import request, jsonify

from src.api.v1 import v1
from src.models.automation import WebhookProvider
from src.models.addons import AccountAddOn
from src.crypto import decrypt_value

_log = logging.getLogger(__name__)


@v1.route("/finance/webhook/stripe/<provider_id>", methods=["POST"])
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
        from src.tasks.finance_addon import process_stripe_event  # local to avoid circular import
        process_stripe_event.delay(
            account_id=provider.account_id,
            provider_id=str(provider.id),
            event=payload,
        )

    return jsonify({"received": True}), 200
