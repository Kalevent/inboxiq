import pytest
import json
from unittest.mock import patch, MagicMock


def test_webhook_provider_not_found(client):
    with patch("src.api.v1.finance_webhook.WebhookProvider") as mock_wp_cls:
        mock_wp_cls.query.filter_by.return_value.first.return_value = None

        resp = client.post(
            "/api/v1/finance/webhook/stripe/nonexistent-id",
            data=b"{}",
            content_type="application/json",
        )
    assert resp.status_code == 404


def test_webhook_addon_not_active(client, app):
    with app.app_context():
        mock_provider = MagicMock()
        mock_provider.account_id = 1
        mock_provider.webhook_signing_secret_encrypted = None

        mock_addon = None  # no active addon

        with patch("src.api.v1.finance_webhook.WebhookProvider") as mock_wp_cls, \
             patch("src.api.v1.finance_webhook.AccountAddOn") as mock_addon_cls:
            mock_wp_cls.query.filter_by.return_value.first.return_value = mock_provider
            mock_addon_cls.query.filter_by.return_value.first.return_value = mock_addon

            resp = client.post(
                "/api/v1/finance/webhook/stripe/prov-123",
                data=b'{"type":"payment_intent.succeeded"}',
                content_type="application/json",
            )
        assert resp.status_code == 403


def test_webhook_dispatches_task(client, app):
    with app.app_context():
        mock_provider = MagicMock()
        mock_provider.account_id = 1
        mock_provider.webhook_signing_secret_encrypted = None  # skip sig verification

        mock_addon = MagicMock()
        mock_addon.is_active.return_value = True

        event_payload = json.dumps({
            "type": "checkout.session.completed",
            "id": "evt_xxx",
            "data": {"object": {}},
        }).encode()

        mock_celery = MagicMock()
        with patch("src.api.v1.finance_webhook.WebhookProvider") as mock_wp_cls, \
             patch("src.api.v1.finance_webhook.AccountAddOn") as mock_addon_cls, \
             patch("src.api.v1.finance_webhook._celery_client", return_value=mock_celery):
            mock_wp_cls.query.filter_by.return_value.first.return_value = mock_provider
            mock_addon_cls.query.filter_by.return_value.first.return_value = mock_addon

            resp = client.post(
                "/api/v1/finance/webhook/stripe/prov-123",
                data=event_payload,
                content_type="application/json",
            )
        assert resp.status_code == 200
        mock_celery.send_task.assert_called_once()
