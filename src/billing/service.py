from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional
from sqlalchemy.exc import OperationalError
from src.extensions import db
from src.billing import models
from src.billing.idempotency import ensure_idempotency
from src.billing.providers.stripe import StripeProvider
from src.billing.providers.secondary import SecondaryProvider
from src.billing.providers.barclay import BarclayHostedProvider
from src.billing.emailing import send_payment_receipt, send_payment_failure, send_trial_reminder, send_trial_ended


class BillingService:
    """
    Orchestrates trial conversion, payment method capture, subscription activation, retries, and dunning.
    Minimal, provider-agnostic surface; relies on provider adapters.
    """

    def __init__(self, stripe_key: Optional[str] = None, secondary_key: Optional[str] = None):
        self.providers = {
            "stripe": StripeProvider(stripe_key),
            "secondary": SecondaryProvider(secondary_key),
            "barclay": BarclayHostedProvider(),
        }

    def _provider(self, name: str):
        provider = self.providers.get(name)
        if not provider:
            raise ValueError(f"Unsupported provider: {name}")
        return provider

    def _table_guard(self):
        required = [
            models.CustomerBillingProfile,
            models.PaymentMethod,
            models.Subscription,
            models.Invoice,
            models.ChargeAttempt,
        ]
        for model in required:
            if not models.table_exists(model):
                raise RuntimeError(f"Missing table for {model.__tablename__}. Run migrations before using billing.")

    # Public API
    def add_payment_method(self, profile: models.CustomerBillingProfile, token: str, provider_name: str, idempotency_key: Optional[str] = None) -> Dict[str, Any]:
        self._table_guard()
        ensure_idempotency(idempotency_key, "payment_method")
        provider = self._provider(provider_name)
        pm_info = provider.create_payment_method_from_token(token, profile.email)
        db_pm = models.PaymentMethod(
            profile_id=profile.id,
            provider=provider_name,
            provider_payment_method_id=pm_info["id"],
            brand=pm_info.get("brand"),
            last4=pm_info.get("last4"),
        )
        db.session.add(db_pm)
        db.session.flush()
        profile.default_payment_method_id = db_pm.id
        db.session.commit()
        return {"payment_method": {"id": db_pm.id, "brand": db_pm.brand, "last4": db_pm.last4}}

    def activate_subscription(self, profile: models.CustomerBillingProfile, plan_code: str, provider_name: str, idempotency_key: Optional[str] = None) -> Dict[str, Any]:
        self._table_guard()
        ensure_idempotency(idempotency_key, "activate")
        provider = self._provider(provider_name)
        sub = provider.create_subscription(customer_ref=profile.id, plan_code=plan_code)
        db_sub = models.Subscription(
            profile_id=profile.id,
            plan_id=None,
            provider=provider_name,
            provider_subscription_id=sub.get("id"),
            status=sub.get("status") or "active",
            current_period_end=datetime.utcnow() + timedelta(days=30),
        )
        db.session.add(db_sub)

        inv = models.Invoice(
            profile_id=profile.id,
            subscription_id=db_sub.id,
            amount_cents=0,
            currency="GBP",
            status="paid" if db_sub.status == "active" else "open",
            provider=provider_name,
            provider_invoice_id=sub.get("latest_invoice"),
        )
        db.session.add(inv)
        profile.subscription_status = "active"
        profile.plan_choice = plan_code
        profile.trial_status = "ended"
        db.session.commit()
        return {"subscription": {"id": db_sub.id, "status": db_sub.status}, "invoice": {"id": inv.id, "status": inv.status}, "client_secret": sub.get("client_secret")}

    def list_invoices(self, profile: models.CustomerBillingProfile):
        self._table_guard()
        invoices = models.Invoice.query.filter_by(profile_id=profile.id).order_by(models.Invoice.created_at.desc()).all()
        return [
            {
                "id": inv.id,
                "status": inv.status,
                "amount_cents": inv.amount_cents,
                "currency": inv.currency,
                "due_at": inv.due_at.isoformat() if inv.due_at else None,
                "pdf_url": inv.pdf_url,
                "provider": inv.provider,
            }
            for inv in invoices
        ]

    def retry_invoice(self, invoice: models.Invoice, use_provider: Optional[str] = None) -> Dict[str, Any]:
        self._table_guard()
        provider_name = use_provider or invoice.provider or "stripe"
        provider = self._provider(provider_name)
        result = provider.pay_invoice(invoice.provider_invoice_id or invoice.id)
        status = result.get("status") or "processing"
        invoice.status = "paid" if status in ("paid", "succeeded") else invoice.status
        invoice.last_attempt_at = datetime.utcnow()
        attempt = models.ChargeAttempt(
            invoice_id=invoice.id,
            provider=provider_name,
            provider_payment_intent_id=result.get("payment_intent"),
            status=status,
            attempt_number=1,
            used_fallback=provider_name != (invoice.provider or provider_name),
        )
        db.session.add(attempt)
        db.session.commit()
        if status in ("paid", "succeeded"):
            send_payment_receipt(to_email=self._profile_email(invoice.profile_id), invoice_id=invoice.id)
        else:
            send_payment_failure(to_email=self._profile_email(invoice.profile_id), invoice_id=invoice.id, reason=status)
        return {"invoice_id": invoice.id, "status": status}

    def handle_webhook(self, provider_name: str, payload: Dict[str, Any], headers: Dict[str, Any]) -> Dict[str, Any]:
        provider = self._provider(provider_name)
        event_type, normalized = provider.handle_webhook(payload, headers)
        return {"event": event_type, "data": normalized}

    # Jobs
    def process_trial_expirations(self, now: Optional[datetime] = None, days_notice: int = 3) -> Dict[str, int]:
        self._table_guard()
        now = now or datetime.now(tz=timezone.utc)
        ending_soon = models.CustomerBillingProfile.query.filter(models.CustomerBillingProfile.trial_end <= now + timedelta(days=days_notice), models.CustomerBillingProfile.trial_status == "active").all()
        ended = models.CustomerBillingProfile.query.filter(models.CustomerBillingProfile.trial_end <= now, models.CustomerBillingProfile.trial_status != "ended").all()
        for profile in ending_soon:
            profile.trial_status = "ending_soon"
            trial_end = profile.trial_end
            if trial_end and trial_end.tzinfo is None:
                trial_end = trial_end.replace(tzinfo=timezone.utc)
            days_left = max((trial_end - now).days, 0) if trial_end else days_notice
            if profile.email:
                send_trial_reminder(profile.email, days_left or 1)
        for profile in ended:
            profile.trial_status = "ended"
            if profile.subscription_status in ("none", "trialing", "canceled") and profile.email:
                send_trial_ended(profile.email)
        db.session.commit()
        return {"ending_soon": len(ending_soon), "ended": len(ended)}

    def retry_past_due(self, now: Optional[datetime] = None) -> Dict[str, int]:
        self._table_guard()
        now = now or datetime.utcnow()
        past_due = models.Invoice.query.filter(models.Invoice.status == "open", (models.Invoice.last_attempt_at == None) | (models.Invoice.last_attempt_at <= now - timedelta(hours=12))).all()  # noqa: E711
        attempted = 0
        for inv in past_due:
            self.retry_invoice(inv)
            attempted += 1
        return {"attempted": attempted}

    # Internal helpers
    def _profile_email(self, profile_id: str) -> str:
        profile = models.CustomerBillingProfile.query.get(profile_id)
        return getattr(profile, "email", "")


def guard_missing_tables(exc: Exception) -> tuple[int, Dict[str, str]]:
    if isinstance(exc, RuntimeError) and "Missing table" in str(exc):
        return 503, {"error": str(exc)}
    if isinstance(exc, OperationalError):
        return 503, {"error": "Billing tables not migrated yet"}
    return 500, {"error": str(exc)}
