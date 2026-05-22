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
        "byol":            "byol_enabled",
        "audit_log":       "audit_log_enabled",
        "kb_drafts":       "kb_drafts_enabled",
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


def get_plan_count_limit(limit_col: str, account_id: int) -> Optional[int]:
    """
    Return the plan's count limit for a resource column, or None if unlimited.
    Returns None (unlimited) when there is no billing profile or no plan row.
    """
    from src.models.billing import CustomerBillingProfile, Plan

    profile = CustomerBillingProfile.query.filter_by(account_id=account_id).first()
    if not profile or not profile.plan_choice:
        return None
    plan = Plan.query.filter_by(code=profile.plan_choice).first()
    if not plan:
        return None
    return getattr(plan, limit_col, None)


def get_draft_reply_config(account_id: int) -> dict:
    """
    Get draft reply configuration for an account.

    Returns:
        Dict with: enabled, auto_approve, min_confidence, kb_enabled
    """
    kb_enabled = feature_enabled("kb_drafts", account_id)

    feature_flags = (
        AccountFeatureFlags.query
        .filter_by(account_id=account_id)
        .first()
    )

    if not feature_flags:
        return {
            "enabled": True,
            "auto_approve": False,
            "min_confidence": 0.7,
            "kb_enabled": kb_enabled,
        }

    return {
        "enabled": feature_flags.draft_reply_enabled,
        "auto_approve": feature_flags.draft_reply_auto_approve,
        "min_confidence": feature_flags.draft_reply_min_confidence,
        "kb_enabled": kb_enabled,
    }


def check_approval_policies(
    account_id: int,
    category: str,
    email_type: str | None,
    sentiment: str | None,
    reply_confidence: float | None,
) -> bool:
    """
    Check whether a reply should be auto-sent (prior auth).

    Returns True if ALL of the following hold:
    - At least one enabled ApprovalPolicy for the account has conditions
      that match the ticket context
    - The DSPy reply_confidence meets or exceeds the policy's min_confidence

    Called just before writeback_to_provider decides whether to create a
    draft or send directly. Returns False (safe default) on any error.
    """
    try:
        from src.models.automation import ApprovalPolicy

        policies = ApprovalPolicy.query.filter_by(
            account_id=account_id,
            enabled=True,
        ).all()

        if not policies:
            return False

        ctx = {
            "category": (category or "").lower(),
            "email_type": (email_type or "").lower(),
            "sentiment": (sentiment or "").lower(),
        }

        for policy in policies:
            if _policy_conditions_match(policy, ctx):
                min_conf = policy.min_confidence or 0.85
                if reply_confidence is not None and reply_confidence >= min_conf:
                    return True

        return False

    except Exception:
        # Never block normal draft creation on an unexpected error
        return False


def _policy_conditions_match(policy, ctx: dict) -> bool:
    """Evaluate a policy's conditions against the ticket context dict."""
    conditions = policy.conditions or []
    if not conditions:
        return False

    logic = (policy.condition_logic or "AND").upper()
    results = [_eval_condition(c, ctx) for c in conditions]

    if logic == "OR":
        return any(results)
    return all(results)


def _eval_condition(condition: dict, ctx: dict) -> bool:
    """Evaluate a single condition against context. Mirrors AutomationRule DSL."""
    field = condition.get("field", "")
    operator = condition.get("operator", "equals")
    value = str(condition.get("value", "")).lower()
    actual = str(ctx.get(field, "")).lower()

    if operator == "equals":
        return actual == value
    if operator == "not_equals":
        return actual != value
    if operator == "contains":
        return value in actual
    if operator == "not_contains":
        return value not in actual
    if operator == "in_list":
        items = [v.strip().lower() for v in value.split(",")]
        return actual in items
    return False


def finance_addon_active(account_id: int) -> bool:
    """Return True if the Finance add-on is active for this account."""
    from src.models.addons import AccountAddOn
    addon = AccountAddOn.query.filter_by(
        account_id=account_id,
        addon_type="finance",
        status="active",
    ).first()
    return addon is not None
