"""Tests for Stripe subscription webhook handling in BillingService."""
import pytest
from unittest.mock import MagicMock, patch, PropertyMock
from datetime import datetime, timezone


# ---------------------------------------------------------------------------
# Helpers to build Stripe webhook payloads
# ---------------------------------------------------------------------------

def _sub_payload(event_type, sub_id="sub_123", customer_id="cus_abc",
                 status="active", plan_choice=None, price_id="price_pro",
                 period_end=1800000000, cancel_at_period_end=False):
    metadata = {"plan_choice": plan_choice} if plan_choice else {}
    return {
        "type": event_type,
        "data": {
            "object": {
                "id": sub_id,
                "customer": customer_id,
                "status": status,
                "metadata": metadata,
                "items": {"data": [{"price": {"id": price_id}}]},
                "current_period_end": period_end,
                "cancel_at_period_end": cancel_at_period_end,
            }
        },
    }


def _invoice_paid_payload(inv_id="in_123", sub_id="sub_123",
                           amount=3900, currency="gbp",
                           hosted_url="https://invoice.stripe.com/i/xxx"):
    return {
        "type": "invoice.paid",
        "data": {
            "object": {
                "id": inv_id,
                "subscription": sub_id,
                "amount_paid": amount,
                "currency": currency,
                "hosted_invoice_url": hosted_url,
            }
        },
    }


def _invoice_failed_payload(inv_id="in_fail", sub_id="sub_123"):
    return {
        "type": "invoice.payment_failed",
        "data": {"object": {"id": inv_id, "subscription": sub_id}},
    }


# ---------------------------------------------------------------------------
# StripeProvider.handle_webhook normalisation
# ---------------------------------------------------------------------------

class TestStripeProviderNormalisation:
    def _provider(self):
        from src.billing.providers.stripe import StripeProvider
        return StripeProvider(api_key=None)

    def test_subscription_created_extracts_fields(self):
        p = self._provider()
        event_type, data = p.handle_webhook(_sub_payload("customer.subscription.created", plan_choice="enterprise"), {})
        assert event_type == "customer.subscription.created"
        assert data["stripe_subscription_id"] == "sub_123"
        assert data["stripe_customer_id"] == "cus_abc"
        assert data["status"] == "active"
        assert data["plan_choice"] == "enterprise"
        assert data["price_id"] == "price_pro"

    def test_subscription_updated_extracts_cancel_flag(self):
        p = self._provider()
        _, data = p.handle_webhook(_sub_payload("customer.subscription.updated", cancel_at_period_end=True), {})
        assert data["cancel_at_period_end"] is True

    def test_subscription_deleted_maps_status(self):
        p = self._provider()
        event_type, data = p.handle_webhook(_sub_payload("customer.subscription.deleted", status="canceled"), {})
        assert event_type == "customer.subscription.deleted"
        assert data["status"] == "canceled"

    def test_invoice_paid_extracts_amount_and_url(self):
        p = self._provider()
        event_type, data = p.handle_webhook(_invoice_paid_payload(), {})
        assert event_type == "invoice.paid"
        assert data["stripe_invoice_id"] == "in_123"
        assert data["stripe_subscription_id"] == "sub_123"
        assert data["amount_paid"] == 3900
        assert data["currency"] == "GBP"
        assert data["hosted_invoice_url"] == "https://invoice.stripe.com/i/xxx"

    def test_invoice_payment_failed_extracts_ids(self):
        p = self._provider()
        event_type, data = p.handle_webhook(_invoice_failed_payload(), {})
        assert event_type == "invoice.payment_failed"
        assert data["stripe_invoice_id"] == "in_fail"
        assert data["stripe_subscription_id"] == "sub_123"

    def test_unknown_event_returns_raw_payload(self):
        p = self._provider()
        raw = {"type": "customer.created", "data": {"object": {}}}
        event_type, data = p.handle_webhook(raw, {})
        assert event_type == "customer.created"
        assert data is raw


# ---------------------------------------------------------------------------
# BillingService._stripe_plan_from_price_id
# ---------------------------------------------------------------------------

class TestPlanFromPriceId:
    def _service(self, config=None):
        from src.billing.service import BillingService
        svc = BillingService.__new__(BillingService)
        svc.providers = {"stripe": MagicMock(api_key="sk_test")}
        svc._cfg = config or {}
        return svc

    def test_maps_pro_price_id(self):
        from src.billing.service import BillingService
        svc = BillingService.__new__(BillingService)
        svc.providers = {"stripe": MagicMock(api_key="sk_test")}
        with patch("src.billing.service.logger"):
            from flask import Flask
            app = Flask(__name__)
            app.config["STRIPE_PRICE_PRO"] = "price_pro_gbp"
            app.config["STRIPE_PRICE_PRO_EUR"] = "price_pro_eur"
            with app.app_context():
                assert svc._stripe_plan_from_price_id("price_pro_gbp") == "pro"
                assert svc._stripe_plan_from_price_id("price_pro_eur") == "pro"

    def test_maps_business_annual(self):
        from src.billing.service import BillingService
        svc = BillingService.__new__(BillingService)
        svc.providers = {"stripe": MagicMock(api_key="sk_test")}
        from flask import Flask
        app = Flask(__name__)
        app.config["STRIPE_PRICE_BUSINESS_ANNUAL"] = "price_biz_annual"
        with app.app_context():
            assert svc._stripe_plan_from_price_id("price_biz_annual") == "business"

    def test_unknown_price_returns_none(self):
        from src.billing.service import BillingService
        svc = BillingService.__new__(BillingService)
        svc.providers = {"stripe": MagicMock(api_key="sk_test")}
        from flask import Flask
        app = Flask(__name__)
        with app.app_context():
            assert svc._stripe_plan_from_price_id("price_unknown") is None


# ---------------------------------------------------------------------------
# BillingService._sync_stripe_subscription
# ---------------------------------------------------------------------------

class TestSyncStripeSubscription:
    def _make_service_and_mocks(self):
        from src.billing.service import BillingService
        svc = BillingService.__new__(BillingService)
        svc.providers = {"stripe": MagicMock(api_key="sk_test")}

        profile = MagicMock()
        profile.id = "prof_1"
        profile.plan_choice = None
        profile.subscription_status = "trialing"
        profile.trial_status = "active"

        existing_sub = MagicMock()
        existing_sub.profile_id = "prof_1"
        existing_sub.status = "trialing"
        existing_sub.current_period_end = None
        existing_sub.cancel_at_period_end = False

        return svc, profile, existing_sub

    def test_updates_existing_subscription_row(self):
        from src.billing.service import BillingService
        import src.models.billing as models
        from flask import Flask

        svc, profile, existing_sub = self._make_service_and_mocks()

        data = {
            "stripe_subscription_id": "sub_123",
            "stripe_customer_id": "cus_abc",
            "status": "active",
            "plan_choice": "enterprise",
            "price_id": None,
            "current_period_end": 1800000000,
            "cancel_at_period_end": False,
        }

        app = Flask(__name__)
        with app.app_context():
            with patch.object(models.Subscription, "query") as mock_sub_q, \
                 patch.object(models.CustomerBillingProfile, "query") as mock_prof_q, \
                 patch("src.billing.service.db") as mock_db:

                mock_sub_q.filter_by.return_value.first.return_value = existing_sub
                mock_prof_q.get.return_value = profile
                mock_db.session.commit.return_value = None

                svc._sync_stripe_subscription(data)

        assert existing_sub.status == "active"
        assert existing_sub.current_period_end == datetime.fromtimestamp(1800000000, tz=timezone.utc)
        assert profile.subscription_status == "active"
        assert profile.plan_choice == "enterprise"
        assert profile.trial_status == "ended"

    def test_creates_new_subscription_for_quote_flow(self):
        from src.billing.service import BillingService
        import src.models.billing as models
        from flask import Flask

        svc, profile, _ = self._make_service_and_mocks()

        data = {
            "stripe_subscription_id": "sub_new",
            "stripe_customer_id": "cus_abc",
            "status": "active",
            "plan_choice": "enterprise",
            "price_id": None,
            "current_period_end": 1800000000,
            "cancel_at_period_end": False,
        }

        added = []
        app = Flask(__name__)
        with app.app_context():
            with patch.object(models.Subscription, "query") as mock_sub_q, \
                 patch("src.billing.service.db") as mock_db:

                mock_sub_q.filter_by.return_value.first.return_value = None
                mock_db.session.add.side_effect = added.append
                mock_db.session.commit.return_value = None

                with patch.object(svc, "_profile_for_stripe_customer", return_value=profile):
                    svc._sync_stripe_subscription(data)

        assert len(added) == 1
        new_sub = added[0]
        assert new_sub.provider_subscription_id == "sub_new"
        assert new_sub.status == "active"
        assert profile.plan_choice == "enterprise"

    def test_skips_when_no_profile_found(self):
        from src.billing.service import BillingService
        from flask import Flask

        svc, _, _ = self._make_service_and_mocks()
        data = {
            "stripe_subscription_id": "sub_orphan",
            "stripe_customer_id": "cus_nobody",
            "status": "active",
            "plan_choice": None,
            "price_id": None,
            "current_period_end": None,
            "cancel_at_period_end": False,
        }

        app = Flask(__name__)
        with app.app_context():
            with patch.object(svc, "_profile_for_stripe_customer", return_value=None), \
                 patch("src.billing.service.db") as mock_db:

                svc._sync_stripe_subscription(data)

        mock_db.session.commit.assert_not_called()


# ---------------------------------------------------------------------------
# BillingService._sync_stripe_invoice_paid
# ---------------------------------------------------------------------------

class TestSyncStripeInvoicePaid:
    def test_upserts_invoice_on_new_payment(self):
        from src.billing.service import BillingService
        import src.models.billing as models
        from flask import Flask

        svc = BillingService.__new__(BillingService)
        svc.providers = {"stripe": MagicMock(api_key="sk_test")}

        db_sub = MagicMock()
        db_sub.id = "dbsub_1"
        db_sub.profile_id = "prof_1"

        added = []

        data = {
            "stripe_invoice_id": "in_new",
            "stripe_subscription_id": "sub_123",
            "amount_paid": 3900,
            "currency": "GBP",
            "hosted_invoice_url": "https://example.com/inv",
        }

        app = Flask(__name__)
        with app.app_context():
            with patch.object(models.Subscription, "query") as mock_sub_q, \
                 patch.object(models.Invoice, "query") as mock_inv_q, \
                 patch("src.billing.service.db") as mock_db:

                mock_sub_q.filter_by.return_value.first.return_value = db_sub
                mock_inv_q.filter_by.return_value.first.return_value = None
                mock_db.session.add.side_effect = added.append
                mock_db.session.commit.return_value = None

                svc._sync_stripe_invoice_paid(data)

        assert len(added) == 1
        inv = added[0]
        assert inv.amount_cents == 3900
        assert inv.status == "paid"
        assert inv.pdf_url == "https://example.com/inv"

    def test_updates_existing_invoice(self):
        from src.billing.service import BillingService
        import src.models.billing as models
        from flask import Flask

        svc = BillingService.__new__(BillingService)
        svc.providers = {"stripe": MagicMock(api_key="sk_test")}

        existing_inv = MagicMock()
        existing_inv.status = "open"
        existing_inv.amount_cents = 0

        data = {
            "stripe_invoice_id": "in_existing",
            "stripe_subscription_id": "sub_123",
            "amount_paid": 5900,
            "currency": "GBP",
            "hosted_invoice_url": None,
        }

        app = Flask(__name__)
        with app.app_context():
            with patch.object(models.Subscription, "query") as mock_sub_q, \
                 patch.object(models.Invoice, "query") as mock_inv_q, \
                 patch("src.billing.service.db") as mock_db:

                mock_sub_q.filter_by.return_value.first.return_value = MagicMock()
                mock_inv_q.filter_by.return_value.first.return_value = existing_inv
                mock_db.session.commit.return_value = None

                svc._sync_stripe_invoice_paid(data)

        assert existing_inv.status == "paid"
        assert existing_inv.amount_cents == 5900


# ---------------------------------------------------------------------------
# BillingService._handle_stripe_invoice_failed
# ---------------------------------------------------------------------------

class TestHandleStripeInvoiceFailed:
    def test_marks_subscription_past_due(self):
        from src.billing.service import BillingService
        import src.models.billing as models

        svc = BillingService.__new__(BillingService)
        svc.providers = {"stripe": MagicMock(api_key="sk_test")}

        db_sub = MagicMock()
        db_sub.id = "dbsub_1"
        db_sub.profile_id = "prof_1"
        db_sub.status = "active"

        profile = MagicMock()
        profile.subscription_status = "active"

        inv = MagicMock()
        inv.status = "open"

        data = {"stripe_invoice_id": "in_fail", "stripe_subscription_id": "sub_123"}

        from flask import Flask
        app = Flask(__name__)
        with app.app_context():
            with patch.object(models.Subscription, "query") as mock_sub_q, \
                 patch.object(models.Invoice, "query") as mock_inv_q, \
                 patch.object(models.CustomerBillingProfile, "query") as mock_prof_q, \
                 patch("src.billing.service.db") as mock_db:

                mock_sub_q.filter_by.return_value.first.return_value = db_sub
                mock_inv_q.filter_by.return_value.first.return_value = inv
                mock_prof_q.get.return_value = profile
                mock_db.session.commit.return_value = None

                svc._handle_stripe_invoice_failed(data)

        assert db_sub.status == "past_due"
        assert profile.subscription_status == "past_due"
