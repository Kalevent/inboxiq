import os
from datetime import datetime, timedelta, timezone
from typing import Set

from src.models import Account


def _parse_id_set(raw: str) -> Set[int]:
    ids: Set[int] = set()
    for part in (raw or "").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            ids.add(int(part))
        except ValueError:
            continue
    return ids


_API_EXEMPT_ACCOUNT_IDS = _parse_id_set(os.getenv("API_EXEMPT_ACCOUNT_IDS", ""))
_API_BUSINESS_ACCOUNT_IDS = _parse_id_set(os.getenv("API_BUSINESS_ACCOUNT_IDS", ""))
_API_TRIAL_DAYS = int(os.getenv("API_TRIAL_DAYS", "7"))


def account_allows_api(account_id: int) -> bool:
    """
    Determine if the account can access API/webhooks.
    Rules:
    - Exempt ids (e.g., owner/dev) always allowed.
    - Active or trialing paid subscriptions are allowed.
    - Within trial window (created_at + trial_days) allowed.
    - Business accounts (allowlist env) allowed.
    - Otherwise blocked.
    """
    if not account_id:
        return False
    if account_id in _API_EXEMPT_ACCOUNT_IDS:
        return True

    # If billing is enabled and the account already has an active/trialing subscription,
    # allow API access regardless of the trial window or business allowlist.
    try:
        from src.billing.models import CustomerBillingProfile  # local import to avoid cycles

        profile = CustomerBillingProfile.query.filter_by(account_id=account_id).first()
        if profile and profile.subscription_status in ("active", "trialing"):
            return True
        # For internal accounts without Stripe, check plan_choice field
        if profile and profile.plan_choice in ("business", "enterprise"):
            return True
    except Exception:
        # If billing tables are unavailable (e.g., during migrations), fall through to the older rules.
        pass

    account = Account.query.get(account_id)
    if not account:
        return False

    now = datetime.now(timezone.utc)
    created = account.created_at
    if created and created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    created = created or now
    trial_window_end = created + timedelta(days=_API_TRIAL_DAYS)
    if now <= trial_window_end:
        return True

    if account_id in _API_BUSINESS_ACCOUNT_IDS:
        return True

    return False
