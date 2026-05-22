import pytest
from unittest.mock import patch, MagicMock

import src.tasks.finance_addon  # ensure module is in sys.modules before patching


def test_process_stripe_event_mode1_creates_sales_receipt(app):
    """Mode 1: direct QB sync — should call QB create_sales_receipt."""
    with app.app_context():
        mock_addon = MagicMock()
        mock_addon.is_active.return_value = True
        mock_addon.config_json = {
            "mode": "direct_sync",
            "stripe_provider_id": "sprov-1",
            "qb_provider_id": "qbprov-1",
        }
        mock_addon.transactions_this_month = 0
        mock_addon.billing_month = None

        mock_qb_client = MagicMock()
        mock_qb_client.find_or_create_customer.return_value = "cust-42"

        event = {
            "id": "evt_test",
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "payment_intent": "pi_test",
                    "customer": "cus_test",
                    "amount_total": 4999,
                    "currency": "gbp",
                    "customer_details": {"email": "a@b.com", "name": "Alice"},
                    "metadata": {},
                }
            },
        }

        with patch("src.tasks.finance_addon.AccountAddOn") as mock_model, \
             patch("src.tasks.finance_addon.client_from_provider", return_value=mock_qb_client), \
             patch("src.tasks.finance_addon.WebhookProvider") as mock_wp, \
             patch("src.tasks.finance_addon.db"):
            mock_model.query.filter_by.return_value.first.return_value = mock_addon
            mock_wp.query.filter_by.return_value.first.return_value = MagicMock()

            from src.tasks.finance_addon import _run_mode1_sync
            _run_mode1_sync(mock_addon, event, account_id=1)

        mock_qb_client.find_or_create_customer.assert_called_once_with(name="Alice", email="a@b.com")
        mock_qb_client.create_sales_receipt.assert_called_once_with(
            customer_id="cust-42",
            amount_cents=4999,
            currency="GBP",
            description="Stripe payment pi_test",
        )


def test_process_stripe_event_addon_inactive(app):
    """If add-on is inactive, _run_mode1_sync should return early without processing."""
    with app.app_context():
        mock_addon = MagicMock()
        mock_addon.is_active.return_value = False

        with patch("src.tasks.finance_addon.AccountAddOn") as mock_model, \
             patch("src.tasks.finance_addon.client_from_provider") as mock_qb:
            mock_model.query.filter_by.return_value.first.return_value = mock_addon

            from src.tasks.finance_addon import _run_mode1_sync
            _run_mode1_sync(mock_addon, {}, account_id=1)

        mock_qb.assert_not_called()
