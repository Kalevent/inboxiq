"""
Feature access control for account-level features.
Handles plan-based gating, feature flags, and trial access.
"""
import os
from typing import Optional
from src.models.core import AccountFeatureFlags
from src.models.billing import CustomerBillingProfile


def _env_bool(key: str, default: bool = False) -> bool:
    """Parse boolean from environment variable."""
    val = os.getenv(key, "").lower()
    if val in ("1", "true", "yes", "on"):
        return True
    if val in ("0", "false", "no", "off"):
        return False
    return default


def get_account_plan(account_id: int) -> Optional[str]:
    """
    Get the billing plan for an account.
    Returns: plan_choice string (e.g., "pro", "business", "enterprise") or None
    """
    profile = (
        CustomerBillingProfile.query
        .filter_by(account_id=account_id)
        .first()
    )
    if not profile:
        return None
    return profile.plan_choice



def feature_enabled(feature: str, account_id: int) -> bool:
    """
    Return True if the account's plan has the given feature enabled,
    OR if the account is on an active trial (full access during trial).

    Features: "chat", "automation", "content_gen", "lead_discovery",
              "nurture", "distribution", "api_access"

    Raises:
        KeyError: if feature is not a recognised feature name.
    """
    _FEATURE_FLAG_MAP = {
        "chat":            "chat_enabled",
        "automation":      "automation_enabled",
        "content_gen":     "content_gen_enabled",
        "lead_discovery":  "lead_discovery_enabled",
        "nurture":         "nurture_enabled",
        "distribution":    "distribution_enabled",
        "api_access":      "api_access_enabled",
    }
    flag_col = _FEATURE_FLAG_MAP.get(feature)
    if flag_col is None:
        raise KeyError(f"Unknown feature: {feature!r}")

    from src.models.billing import Plan

    profile = (
        CustomerBillingProfile.query
        .filter_by(account_id=account_id)
        .first()
    )

    # Active trial → full access
    if profile and profile.trial_status == "active":
        return True

    if not profile or not profile.plan_choice:
        return False

    plan = Plan.query.filter_by(code=profile.plan_choice).first()
    if not plan:
        return False

    return bool(getattr(plan, flag_col, False))


def get_draft_reply_config(account_id: int) -> dict:
    """
    Get draft reply configuration for an account.

    Returns:
        Dict with: enabled, auto_approve, min_confidence
    """
    feature_flags = (
        AccountFeatureFlags.query
        .filter_by(account_id=account_id)
        .first()
    )

    if not feature_flags:
        # Return defaults (draft reply is on by default for all accounts)
        return {
            "enabled": True,
            "auto_approve": False,
            "min_confidence": 0.7,
        }

    return {
        "enabled": feature_flags.draft_reply_enabled,
        "auto_approve": feature_flags.draft_reply_auto_approve,
        "min_confidence": feature_flags.draft_reply_min_confidence,
    }
