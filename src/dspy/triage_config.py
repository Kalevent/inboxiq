"""
Centralized triage configuration with per-account overrides and Redis caching.

This module consolidates all hardcoded triage values into one place and supports
per-account customization via the TriageConfig database model.

Usage:
    from src.dspy.triage_config import get_triage_config

    config = get_triage_config(account_id)
    sla = config.get_sla_display("P1")  # "4h"
    reason = config.get_fallback_message("action_required")  # "Action required — customer needs help."
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any, Dict, Optional

from src.extensions import cache, db

logger = logging.getLogger(__name__)

# Cache timeout: 5 minutes (config changes are infrequent)
CONFIG_CACHE_TIMEOUT = 300


# =============================================================================
# System-wide defaults (used when no account-specific config exists)
# =============================================================================

DEFAULT_SLA_MAPPINGS: Dict[str, str] = {
    "P0": "2h",
    "P1": "4h",
    "P2": "24h",
    "P3": "48h",
    "P4": "1w",
}

DEFAULT_SLA_HOURS: Dict[str, int] = {
    "P0": 1,
    "P1": 4,
    "P2": 24,
    "P3": 48,
    "P4": 168,  # 1 week
}

DEFAULT_FALLBACK_MESSAGES: Dict[str, str] = {
    "action_required": "Action required — customer needs help.",
    "optional": "Optional follow-up when capacity allows.",
    "auto_handled": "Informational / auto-handled.",
    "needs_review": "Queued for review.",
}

DEFAULT_OWNER = "Support"
DEFAULT_TEAM = None
DEFAULT_CATEGORY = "support"
DEFAULT_PRIORITY = "P2"

DEFAULT_CONFIDENCE_THRESHOLD = 0.7
DEFAULT_P2_NEUTRAL_AUTO_HANDLE = True

DEFAULT_BODY_PREVIEW_LIMIT = 240
DEFAULT_SUMMARY_LIMIT = 280

DEFAULT_TRAIN_MIN_SAMPLES = 20
DEFAULT_POLL_STALE_MINUTES = 30


# =============================================================================
# TriageConfigView - Immutable config object with helper methods
# =============================================================================

@dataclass(frozen=True)
class TriageConfigView:
    """
    Immutable view of triage configuration with helper methods.
    Merges account-specific overrides with system defaults.
    """
    account_id: Optional[int]
    sla_mappings: Dict[str, str] = field(default_factory=lambda: DEFAULT_SLA_MAPPINGS.copy())
    sla_hours: Dict[str, int] = field(default_factory=lambda: DEFAULT_SLA_HOURS.copy())
    fallback_messages: Dict[str, str] = field(default_factory=lambda: DEFAULT_FALLBACK_MESSAGES.copy())
    default_owner: str = DEFAULT_OWNER
    default_team: Optional[str] = DEFAULT_TEAM
    default_category: str = DEFAULT_CATEGORY
    default_priority: str = DEFAULT_PRIORITY
    confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD
    p2_neutral_auto_handle: bool = DEFAULT_P2_NEUTRAL_AUTO_HANDLE
    body_preview_limit: int = DEFAULT_BODY_PREVIEW_LIMIT
    summary_limit: int = DEFAULT_SUMMARY_LIMIT
    train_min_samples: int = DEFAULT_TRAIN_MIN_SAMPLES
    poll_stale_minutes: int = DEFAULT_POLL_STALE_MINUTES

    def get_sla_display(self, priority: Optional[str]) -> str:
        """Get human-readable SLA string for a priority level."""
        key = (priority or "").upper()
        return self.sla_mappings.get(key, self.sla_mappings.get("P2", "24h"))

    def get_sla_timedelta(self, priority: Optional[str]) -> timedelta:
        """Get timedelta for due_at calculation based on priority."""
        key = (priority or "").upper()
        hours = self.sla_hours.get(key, self.sla_hours.get("P2", 24))
        return timedelta(hours=hours)

    def get_fallback_message(self, action_type: str) -> str:
        """
        Get fallback "Why this decision" message for an action type.

        Args:
            action_type: One of "action_required", "optional", "auto_handled", "needs_review"
        """
        return self.fallback_messages.get(action_type, self.fallback_messages.get("needs_review", ""))

    def get_action_reason_text(self, action_required: Any) -> str:
        """
        Get fallback reason text based on action_required flag.

        Args:
            action_required: True, False, "optional", or None
        """
        if action_required is True:
            return self.get_fallback_message("action_required")
        if action_required == "optional":
            return self.get_fallback_message("optional")
        if action_required is False:
            return self.get_fallback_message("auto_handled")
        return self.get_fallback_message("needs_review")

    def should_auto_handle_p2_neutral(self, priority: str, sentiment: str, risk_flag: bool = False) -> bool:
        """
        Check if a P2/neutral/no-risk email should be auto-handled.

        This implements the heuristic: P2 + neutral sentiment + no risk = auto-handle
        """
        if not self.p2_neutral_auto_handle:
            return False
        return (
            (priority or "").upper() == "P2"
            and (sentiment or "").lower() == "neutral"
            and not risk_flag
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "account_id": self.account_id,
            "sla_mappings": self.sla_mappings,
            "sla_hours": self.sla_hours,
            "fallback_messages": self.fallback_messages,
            "default_owner": self.default_owner,
            "default_team": self.default_team,
            "default_category": self.default_category,
            "default_priority": self.default_priority,
            "confidence_threshold": self.confidence_threshold,
            "p2_neutral_auto_handle": self.p2_neutral_auto_handle,
            "body_preview_limit": self.body_preview_limit,
            "summary_limit": self.summary_limit,
            "train_min_samples": self.train_min_samples,
            "poll_stale_minutes": self.poll_stale_minutes,
        }


# =============================================================================
# System default config (singleton)
# =============================================================================

_SYSTEM_DEFAULT_CONFIG = TriageConfigView(account_id=None)


def get_system_defaults() -> TriageConfigView:
    """Get the system-wide default configuration (no account overrides)."""
    return _SYSTEM_DEFAULT_CONFIG


# =============================================================================
# Per-account config loading with caching
# =============================================================================

def _cache_key(account_id: Optional[int]) -> str:
    """Generate cache key for triage config."""
    return f"triage_config:{account_id or 'system'}"


def _build_config_from_model(model, account_id: Optional[int]) -> TriageConfigView:
    """Build TriageConfigView from database model, merging with defaults."""
    # Start with defaults
    sla_mappings = DEFAULT_SLA_MAPPINGS.copy()
    sla_hours = DEFAULT_SLA_HOURS.copy()
    fallback_messages = DEFAULT_FALLBACK_MESSAGES.copy()

    # Merge account overrides
    if model.sla_mappings:
        sla_mappings.update(model.sla_mappings)
    if model.sla_hours:
        sla_hours.update(model.sla_hours)
    if model.fallback_messages:
        fallback_messages.update(model.fallback_messages)

    return TriageConfigView(
        account_id=account_id,
        sla_mappings=sla_mappings,
        sla_hours=sla_hours,
        fallback_messages=fallback_messages,
        default_owner=model.default_owner or DEFAULT_OWNER,
        default_team=model.default_team or DEFAULT_TEAM,
        default_category=model.default_category or DEFAULT_CATEGORY,
        default_priority=model.default_priority or DEFAULT_PRIORITY,
        confidence_threshold=model.confidence_threshold if model.confidence_threshold is not None else DEFAULT_CONFIDENCE_THRESHOLD,
        p2_neutral_auto_handle=model.p2_neutral_auto_handle if model.p2_neutral_auto_handle is not None else DEFAULT_P2_NEUTRAL_AUTO_HANDLE,
        body_preview_limit=model.body_preview_limit or DEFAULT_BODY_PREVIEW_LIMIT,
        summary_limit=model.summary_limit or DEFAULT_SUMMARY_LIMIT,
        train_min_samples=model.train_min_samples or DEFAULT_TRAIN_MIN_SAMPLES,
        poll_stale_minutes=model.poll_stale_minutes or DEFAULT_POLL_STALE_MINUTES,
    )


def get_triage_config(account_id: Optional[int] = None) -> TriageConfigView:
    """
    Get triage configuration for an account.

    Uses Redis caching to avoid repeated database queries.
    Falls back to system defaults if no account config exists.

    Args:
        account_id: Account ID to get config for, or None for system defaults

    Returns:
        TriageConfigView with merged account overrides and defaults
    """
    if account_id is None:
        return _SYSTEM_DEFAULT_CONFIG

    cache_key = _cache_key(account_id)

    # Try cache first
    cached = cache.get(cache_key)
    if cached is not None:
        try:
            return TriageConfigView(**cached)
        except Exception as exc:
            logger.warning("Failed to deserialize cached triage config: %s", exc)
            cache.delete(cache_key)

    # Load from database
    try:
        from src.models import TriageConfig
        model = TriageConfig.query.filter_by(account_id=account_id).first()

        if model:
            config = _build_config_from_model(model, account_id)
        else:
            # No config for this account, use defaults
            config = TriageConfigView(account_id=account_id)

        # Cache the result
        try:
            cache.set(cache_key, config.to_dict(), timeout=CONFIG_CACHE_TIMEOUT)
        except Exception as exc:
            logger.warning("Failed to cache triage config: %s", exc)

        return config

    except Exception as exc:
        logger.error("Failed to load triage config for account %s: %s", account_id, exc)
        return TriageConfigView(account_id=account_id)


def invalidate_triage_config(account_id: Optional[int] = None) -> None:
    """
    Invalidate cached triage config for an account.

    Call this after updating TriageConfig in the database.

    Args:
        account_id: Account ID to invalidate, or None to invalidate system config
    """
    cache_key = _cache_key(account_id)
    try:
        cache.delete(cache_key)
        logger.info("Invalidated triage config cache for account %s", account_id)
    except Exception as exc:
        logger.warning("Failed to invalidate triage config cache: %s", exc)


def save_triage_config(
    account_id: int,
    **kwargs,
) -> "TriageConfig":
    """
    Create or update triage config for an account.

    Automatically invalidates the cache after saving.

    Args:
        account_id: Account ID to save config for
        **kwargs: Config fields to update (sla_mappings, fallback_messages, etc.)

    Returns:
        Updated TriageConfig model instance
    """
    from src.models import TriageConfig

    model = TriageConfig.query.filter_by(account_id=account_id).first()

    if not model:
        from uuid import uuid4
        model = TriageConfig(id=str(uuid4()), account_id=account_id)
        db.session.add(model)

    # Update fields
    for field_name, value in kwargs.items():
        if hasattr(model, field_name) and value is not None:
            setattr(model, field_name, value)

    db.session.commit()
    invalidate_triage_config(account_id)

    return model


# =============================================================================
# Convenience functions for common operations
# =============================================================================

def get_sla_display(priority: Optional[str], account_id: Optional[int] = None) -> str:
    """Get SLA display string for a priority level."""
    return get_triage_config(account_id).get_sla_display(priority)


def get_sla_timedelta(priority: Optional[str], account_id: Optional[int] = None) -> timedelta:
    """Get SLA timedelta for due_at calculation."""
    return get_triage_config(account_id).get_sla_timedelta(priority)


def get_fallback_message(action_type: str, account_id: Optional[int] = None) -> str:
    """Get fallback reason message for an action type."""
    return get_triage_config(account_id).get_fallback_message(action_type)


def get_action_reason_text(action_required: Any, account_id: Optional[int] = None) -> str:
    """Get fallback reason text based on action_required flag."""
    return get_triage_config(account_id).get_action_reason_text(action_required)


def get_default_owner(account_id: Optional[int] = None) -> str:
    """Get default owner for tickets."""
    return get_triage_config(account_id).default_owner


def get_default_category(account_id: Optional[int] = None) -> str:
    """Get default category for tickets."""
    return get_triage_config(account_id).default_category


def get_default_priority(account_id: Optional[int] = None) -> str:
    """Get default priority for tickets."""
    return get_triage_config(account_id).default_priority


def get_body_preview_limit(account_id: Optional[int] = None) -> int:
    """Get body preview character limit."""
    return get_triage_config(account_id).body_preview_limit


def should_auto_handle_p2_neutral(
    priority: str,
    sentiment: str,
    risk_flag: bool = False,
    account_id: Optional[int] = None,
) -> bool:
    """Check if P2/neutral/no-risk should be auto-handled."""
    return get_triage_config(account_id).should_auto_handle_p2_neutral(priority, sentiment, risk_flag)
