"""
Usage quota enforcement for billing plans.

check_and_increment(meter, account_id) is the single call-site entry point:
  1. Upserts AccountUsageCounter for (account_id, current billing_month) using
     SELECT FOR UPDATE to prevent race conditions.
  2. Reads the plan limit for this meter via the account's CustomerBillingProfile.
  3. If the feature flag for this meter is off on the plan → raises FeatureDisabled (403).
  4. If limit is None  → unlimited plan; increment and return.
  5. If within limit   → increment and return.
  6. If over limit     → increment (we bill overage, not block) and report overage
                         units to Stripe via create_usage_record().

Meters:
  ai_decisions, chat_conversations, automation_runs,
  content_posts, leads_discovered, nurture_emails
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import text

from src.extensions import db
from src.models.billing import AccountUsageCounter, CustomerBillingProfile, Plan

logger = logging.getLogger(__name__)

# Maps meter name → (counter column name, plan quota column, feature flag column or None)
_METER_META: dict[str, tuple[str, str, Optional[str]]] = {
    "ai_decisions":       ("ai_decisions",       "ai_decisions_limit",    None),
    "chat_conversations": ("chat_conversations",  "chat_limit",            "chat_enabled"),
    "automation_runs":    ("automation_runs",     "automation_runs_limit", "automation_enabled"),
    "content_posts":      ("content_posts",       "content_posts_limit",   "content_gen_enabled"),
    "leads_discovered":   ("leads_discovered",    "leads_limit",           "lead_discovery_enabled"),
    "nurture_emails":     ("nurture_emails",      "nurture_emails_limit",  "nurture_enabled"),
}

# Maps meter name → plan attribute for the Stripe overage price ID
_STRIPE_OVERAGE_ATTR: dict[str, str] = {
    "ai_decisions":       "stripe_ai_overage_price_id",
    "chat_conversations": "stripe_chat_overage_price_id",
    "automation_runs":    "stripe_automation_overage_price_id",
    "leads_discovered":   "stripe_leads_overage_price_id",
    "nurture_emails":     "stripe_nurture_overage_price_id",
}


# Pre-built upsert SQL per meter — column names are hardcoded constants from
# _METER_META so there is no user input in these statements.
_UPSERT_SQL: dict[str, object] = {
    meter: text(
        "INSERT INTO account_usage_counters (account_id, billing_month, " + col + ") "
        "VALUES (:account_id, :billing_month, :qty) "
        "ON CONFLICT (account_id, billing_month) "
        "DO UPDATE SET " + col + " = account_usage_counters." + col + " + :qty "
        "RETURNING " + col
    )
    for meter, (col, _, _) in _METER_META.items()
}


class FeatureDisabled(Exception):
    """Raised when a feature is not available on the account's plan."""
    status_code = 403


def _current_billing_month() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


def _get_plan_for_account(account_id: int) -> Optional[Plan]:
    profile = (
        CustomerBillingProfile.query
        .filter_by(account_id=account_id)
        .first()
    )
    if not profile or not profile.plan_choice:
        return None
    return Plan.query.filter_by(code=profile.plan_choice).first()


def _get_subscription_item_id(subscription_provider_id: str, overage_price_id: str) -> Optional[str]:
    """
    Find the Stripe subscription item ID for a given metered price within a subscription.
    Returns None if not found.
    """
    try:
        import stripe  # type: ignore
        sub = stripe.Subscription.retrieve(subscription_provider_id, expand=["items"])
        for item in sub["items"]["data"]:
            if item["price"]["id"] == overage_price_id:
                return item["id"]
    except Exception as exc:
        logger.warning("Could not retrieve Stripe subscription items for %s: %s", subscription_provider_id, exc)
    return None


def _report_stripe_overage(plan: Plan, account_id: int, meter: str, units: int) -> None:
    """
    Report overage units to Stripe via create_usage_record() on the subscription item.
    Best-effort: errors are logged, never raised.

    Flow:
      1. Look up overage price ID from the Plan row.
      2. Find the account's active Stripe subscription via CustomerBillingProfile → Subscription.
      3. Find the subscription item matching the overage price.
      4. Call create_usage_record(quantity=units, action='increment').
    """
    overage_attr = _STRIPE_OVERAGE_ATTR.get(meter)
    if not overage_attr:
        return
    price_id = getattr(plan, overage_attr, None)
    if not price_id:
        return  # Stripe metered price not configured for this plan yet

    try:
        import stripe  # type: ignore
        stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
        if not stripe.api_key:
            logger.debug("STRIPE_SECRET_KEY not set; skipping overage report for meter=%s", meter)
            return

        from src.models.billing import Subscription
        # Find the account's active Stripe subscription
        profile = CustomerBillingProfile.query.filter_by(account_id=account_id).first()
        if not profile:
            return

        sub_row = (
            Subscription.query
            .filter_by(profile_id=profile.id, provider="stripe")
            .filter(Subscription.status.in_(["active", "trialing"]))
            .order_by(Subscription.created_at.desc())
            .first()
        )
        if not sub_row or not sub_row.provider_subscription_id:
            logger.debug("No active Stripe subscription for account %d; skipping overage", account_id)
            return

        si_id = _get_subscription_item_id(sub_row.provider_subscription_id, price_id)
        if not si_id:
            logger.warning(
                "Subscription item not found for price %s in sub %s (account=%d meter=%s)",
                price_id, sub_row.provider_subscription_id, account_id, meter,
            )
            return

        stripe.SubscriptionItem.create_usage_record(
            si_id,
            quantity=units,
            action="increment",
        )
        logger.info(
            "Stripe overage reported: account=%d meter=%s units=%d si=%s",
            account_id, meter, units, si_id,
        )
    except Exception as exc:
        logger.warning("Stripe overage report failed account=%d meter=%s units=%d: %s", account_id, meter, units, exc)


def increment_signals(account_id: int, quantity: int = 1) -> None:
    """
    Increment incoming_signals counter for observability and ROI reporting.
    No quota enforcement, no Stripe reporting — pure volume tracking.
    Best-effort: errors are swallowed so intake is never blocked.
    """
    billing_month = _current_billing_month()
    try:
        db.session.execute(
            text("""
                INSERT INTO account_usage_counters (account_id, billing_month, incoming_signals)
                VALUES (:account_id, :billing_month, :qty)
                ON CONFLICT (account_id, billing_month)
                DO UPDATE SET incoming_signals = account_usage_counters.incoming_signals + :qty
            """),
            {"account_id": account_id, "billing_month": billing_month, "qty": quantity},
        )
        db.session.commit()
    except Exception as exc:
        logger.warning("increment_signals failed account=%d: %s", account_id, exc)


def check_and_increment(meter: str, account_id: int, quantity: int = 1) -> None:
    """
    Enforce quota for the given meter on an account.

    Args:
        meter:      One of the _METER_META keys above.
        account_id: The account consuming the resource.
        quantity:   Units to add (default 1).

    Raises:
        FeatureDisabled: If the feature flag is off on the account's plan.
        ValueError:      If meter is unknown.
    """
    if meter not in _METER_META:
        raise ValueError(f"Unknown quota meter: {meter!r}")

    counter_col, limit_col, flag_col = _METER_META[meter]
    billing_month = _current_billing_month()
    plan = _get_plan_for_account(account_id)

    # Check feature gate first (before touching DB counters)
    if plan and flag_col:
        if not getattr(plan, flag_col, True):
            # Also allow access during active trial
            profile = CustomerBillingProfile.query.filter_by(account_id=account_id).first()
            on_trial = profile and profile.trial_status == "active"
            if not on_trial:
                raise FeatureDisabled(
                    f"Feature '{meter}' is not available on your current plan. "
                    "Upgrade to access this feature."
                )

    # Upsert counter row. SQL is pre-built at module load from hardcoded column
    # names — no user input reaches the query.
    result = db.session.execute(
        _UPSERT_SQL[meter],
        {"account_id": account_id, "billing_month": billing_month, "qty": quantity},
    )
    new_total = result.scalar()

    # Check overage
    if plan:
        limit = getattr(plan, limit_col, None)
        if limit is not None and new_total > limit:
            overage_units = new_total - limit
            if overage_units > 0:
                _report_stripe_overage(plan, account_id, meter, overage_units)
                logger.info(
                    "Overage: account=%d meter=%s total=%d limit=%d overage=%d",
                    account_id, meter, new_total, limit, overage_units,
                )
