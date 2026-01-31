"""
Feature access control for account-level features.
Handles plan-based gating, feature flags, and trial access.
"""
import os
from typing import Optional
from src.extensions import db
from src.models import Account, AccountFeatureFlags
from src.billing.models import CustomerBillingProfile


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


def check_draft_reply_access(account_id: int, context: Optional[dict] = None) -> bool:
    """
    Check if an account has access to the draft reply feature.

    Access is granted if:
    1. Global feature flag DSPY_DRAFT_REPLY_ENABLED is true, AND
    2. One of the following:
       - Account has Business or Enterprise plan
       - Account has active trial

    Note: This checks ELIGIBILITY only, not whether the feature is currently enabled.
    The AccountFeatureFlags.draft_reply_enabled field stores the user's preference.

    Args:
        account_id: The account ID to check
        context: Optional context dict with features override

    Returns:
        True if account has access, False otherwise
    """
    # Check global kill switch
    if not _env_bool("DSPY_DRAFT_REPLY_ENABLED", False):
        return False

    # Check explicit context override (useful for testing)
    if context and isinstance(context, dict):
        features = context.get("features")
        if isinstance(features, dict):
            draft_reply_setting = features.get("draft_reply")
            if draft_reply_setting is not None:
                return bool(draft_reply_setting)

    # Check billing plan
    plan = get_account_plan(account_id)
    if plan and plan.lower() in {"business", "enterprise"}:
        return True

    # Check if account is in active trial
    profile = (
        CustomerBillingProfile.query
        .filter_by(account_id=account_id)
        .first()
    )
    if profile and profile.trial_status == "active":
        return True

    # Default: no access
    return False


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
        # Return defaults
        return {
            "enabled": check_draft_reply_access(account_id),
            "auto_approve": False,
            "min_confidence": 0.7,
        }

    return {
        "enabled": feature_flags.draft_reply_enabled,
        "auto_approve": feature_flags.draft_reply_auto_approve,
        "min_confidence": feature_flags.draft_reply_min_confidence,
    }
