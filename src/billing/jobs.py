from datetime import datetime, timedelta, timezone
from typing import Optional
from src.extensions import db
import src.models.billing as models
from src.billing.emailing import send_dunning_notice
from src.billing.service import BillingService


def run_trial_checker(billing: BillingService, now: Optional[datetime] = None, days_notice: int = 3):
    return billing.process_trial_expirations(now=now, days_notice=days_notice)


def run_retry_processor(billing: BillingService, now: Optional[datetime] = None):
    return billing.retry_past_due(now=now)


def run_dunning_sender(billing: BillingService, now: Optional[datetime] = None):
    billing._table_guard()
    now = now or datetime.now(timezone.utc)
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


def run_billing_profile_backfill(now: Optional[datetime] = None) -> dict:
    """
    Create CustomerBillingProfile rows for activated users who don't have one.

    This heals accounts where profile creation failed silently at activation.
    If the user's natural 7-day window already closed, they get a fresh 7 days
    from now so they can experience the full trial.
    """
    from src.models.core import User
    import src.models.billing as models

    now = now or datetime.now(timezone.utc)

    orphans = (
        db.session.query(User)
        .outerjoin(models.CustomerBillingProfile, models.CustomerBillingProfile.account_id == User.account_id)
        .filter(
            User.password_hash.isnot(None),
            models.CustomerBillingProfile.id.is_(None),
        )
        .all()
    )

    created = 0
    skipped = 0
    for user in orphans:
        trial_start = user.created_at or now
        if trial_start.tzinfo is None:
            trial_start = trial_start.replace(tzinfo=timezone.utc)
        trial_end = trial_start + timedelta(days=7)
        if trial_end < now:
            trial_start = now
            trial_end = now + timedelta(days=7)

        profile = models.CustomerBillingProfile(
            account_id=user.account_id,
            email=user.email,
            trial_start=trial_start,
            trial_end=trial_end,
            trial_status="active",
            subscription_status="trialing",
        )
        try:
            db.session.add(profile)
            db.session.commit()
            created += 1
        except Exception:
            db.session.rollback()
            skipped += 1

    return {"backfilled": created, "skipped": skipped}
