"""
Monthly Enterprise value report emails.

Runs on the 1st of each month, sends each Enterprise account a summary:
  - AI decisions handled last month
  - Estimated hours saved (ai_decisions × MINS_PER_DECISION / 60)
  - Estimated £ value (hours × HOURLY_RATE)

Assumptions are conservative defaults tuned to B2B SaaS / support teams.
Both can be overridden via env vars.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Dict, Any

from src.celery_inboxiq import celery
from src.extensions import db

logger = logging.getLogger(__name__)

# Conservative defaults: 3 min per triage decision, £30/hr average team cost
_MINS_PER_DECISION = float(os.getenv("VALUE_REPORT_MINS_PER_DECISION", "3"))
_HOURLY_RATE_GBP = float(os.getenv("VALUE_REPORT_HOURLY_RATE", "30"))


def _previous_billing_month() -> str:
    """Return 'YYYY-MM' string for last month."""
    now = datetime.now(timezone.utc)
    month = now.month - 1
    year = now.year
    if month == 0:
        month = 12
        year -= 1
    return f"{year:04d}-{month:02d}"


def _month_label(billing_month: str) -> str:
    """Convert '2026-02' → 'February 2026'."""
    try:
        dt = datetime.strptime(billing_month, "%Y-%m")
        return dt.strftime("%B %Y")
    except ValueError:
        return billing_month


@celery.task(name="marketing.send_enterprise_value_reports")
def send_enterprise_value_reports() -> Dict[str, Any]:
    """
    Send monthly value/ROI summary emails to all Enterprise accounts.
    Skips accounts with 0 AI decisions last month (nothing to report).
    """
    from src.models import AccountUsageCounter, Account, User
    from src.models.billing import CustomerBillingProfile
    from src.notifications.emails import send_enterprise_value_report_email

    billing_month = _previous_billing_month()
    month_label = _month_label(billing_month)

    # Find all accounts on the Enterprise plan
    enterprise_profiles = (
        CustomerBillingProfile.query
        .filter_by(plan_choice="enterprise")
        .all()
    )

    sent = 0
    skipped_no_usage = 0
    skipped_no_email = 0
    errors = 0

    for profile in enterprise_profiles:
        account_id = profile.account_id

        # Get last month's usage
        counter = (
            AccountUsageCounter.query
            .filter_by(account_id=account_id, billing_month=billing_month)
            .first()
        )
        ai_decisions = (counter.ai_decisions or 0) if counter else 0

        if ai_decisions == 0:
            skipped_no_usage += 1
            continue

        # Calculate value
        hours_saved = (ai_decisions * _MINS_PER_DECISION) / 60.0
        value_gbp = hours_saved * _HOURLY_RATE_GBP

        # Get account name + primary user email
        account = db.session.get(Account, account_id)
        if not account:
            skipped_no_email += 1
            continue

        # Use the billing profile email, falling back to first active user
        to_email = profile.email
        if not to_email:
            user = (
                User.query
                .filter_by(account_id=account_id)
                .order_by(User.id)
                .first()
            )
            to_email = user.email if user else None

        if not to_email:
            logger.warning("No email for Enterprise account_id=%s, skipping value report", account_id)
            skipped_no_email += 1
            continue

        account_name = getattr(account, "name", None) or to_email.split("@")[0].title()

        try:
            ok = send_enterprise_value_report_email(
                to_email=to_email,
                account_name=account_name,
                month_label=month_label,
                ai_decisions=ai_decisions,
                hours_saved=hours_saved,
                value_gbp=value_gbp,
            )
            if ok:
                sent += 1
                logger.info(
                    "Enterprise value report sent: account=%s month=%s decisions=%d value=£%.0f",
                    account_id, billing_month, ai_decisions, value_gbp,
                )
            else:
                errors += 1
        except Exception as exc:
            logger.error("Value report failed for account=%s: %s", account_id, exc)
            errors += 1

    return {
        "month": billing_month,
        "sent": sent,
        "skipped_no_usage": skipped_no_usage,
        "skipped_no_email": skipped_no_email,
        "errors": errors,
    }
