from datetime import datetime, timedelta
from typing import Optional
from src.extensions import db
from src.billing import models
from src.billing.emailing import send_dunning_notice
from src.billing.service import BillingService


def run_trial_checker(billing: BillingService, now: Optional[datetime] = None, days_notice: int = 3):
    return billing.process_trial_expirations(now=now, days_notice=days_notice)


def run_retry_processor(billing: BillingService, now: Optional[datetime] = None):
    return billing.retry_past_due(now=now)


def run_dunning_sender(billing: BillingService, now: Optional[datetime] = None):
    billing._table_guard()
    now = now or datetime.utcnow()
    retry_cutoff = now - timedelta(hours=24)

    overdue_invoices = models.Invoice.query.filter(
        models.Invoice.status == "open",
        models.Invoice.due_at != None,  # noqa: E711
        models.Invoice.due_at <= now,
        (models.Invoice.last_attempt_at == None) | (models.Invoice.last_attempt_at <= retry_cutoff),  # noqa: E711
    ).all()

    by_profile = {}
    for inv in overdue_invoices:
        by_profile.setdefault(inv.profile_id, []).append(inv)

    sent = 0
    skipped = 0
    for profile_id, invoices in by_profile.items():
        profile = models.CustomerBillingProfile.query.get(profile_id)
        if not profile or not profile.email:
            skipped += 1
            continue

        summaries = [
            {
                "id": inv.id,
                "amount_cents": inv.amount_cents,
                "currency": inv.currency,
                "due_at": inv.due_at,
            }
            for inv in invoices
        ]
        send_dunning_notice(profile.email, summaries)
        if profile.subscription_status != "past_due":
            profile.subscription_status = "past_due"
        sent += 1

    if sent:
        db.session.commit()

    return {
        "sent": sent,
        "skipped": skipped,
        "profiles": len(by_profile),
        "timestamp": now.isoformat(),
    }
