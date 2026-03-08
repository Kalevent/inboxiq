"""
Merge agent pipeline decisions with DSPy triage decisions.
Agent decisions can override DSPy when confidence is higher or when
detecting non-actionable email types (spam, marketing, auto-replies).
"""
from __future__ import annotations

from typing import Any, Dict


# Email types that should be auto-handled without human review
NON_ACTIONABLE_EMAIL_TYPES = {
    "spam", "marketing", "newsletter", "transactional",
    "auto_reply", "out_of_office", "promotional", "notification"
}


def merge_decisions(
    dspy_decision: Dict[str, Any],
    agent_decision: Dict[str, Any] | None,
    confidence_threshold: float = 0.7
) -> Dict[str, Any]:
    """
    Merge DSPy and agent pipeline decisions.

    Agent decision takes precedence when:
    - Agent explicitly sets action_required=False for spam/marketing
    - Agent confidence > threshold
    - Agent identifies a non-actionable email type

    Args:
        dspy_decision: The decision from DSPy triage
        agent_decision: The decision from agent pipeline (may be None)
        confidence_threshold: Minimum confidence for agent to override DSPy

    Returns:
        Merged decision dictionary
    """
    if not agent_decision:
        return dspy_decision

    merged = dict(dspy_decision)
    decision_trace = list(merged.get("decision_trace") or [])

    # Extract agent classifications
    agent_action = agent_decision.get("action_required")
    agent_email_type = str(agent_decision.get("email_type") or "").lower().strip()
    agent_is_automated = agent_decision.get("is_automated")
    agent_confidence = agent_decision.get("confidence", {})

    # Check if agent identified a non-actionable email type
    if agent_email_type in NON_ACTIONABLE_EMAIL_TYPES:
        merged["action_required"] = False
        merged["email_type"] = agent_email_type
        merged["is_automated"] = True
        decision_trace.append(f"agent_override:email_type={agent_email_type}")

    # Check if agent explicitly marked as not requiring action
    elif agent_action is False:
        merged["action_required"] = False
        decision_trace.append("agent_override:action_required=false")

    # Check if agent marked as automated
    elif agent_is_automated in (True, "true", "True", "yes", "1"):
        # Automated emails typically don't need action unless high priority
        dspy_priority = str(merged.get("priority") or "").upper()
        if dspy_priority != "P1":  # Only P1 is urgent enough to override auto-handling
            merged["action_required"] = False
            merged["is_automated"] = True
            decision_trace.append("agent_override:is_automated")

    # Check high-confidence agent overrides
    if isinstance(agent_confidence, dict):
        for field, conf in agent_confidence.items():
            if isinstance(conf, (int, float)) and conf >= confidence_threshold:
                agent_value = agent_decision.get(field)
                if agent_value is not None:
                    merged[field] = agent_value
                    decision_trace.append(f"agent_high_conf:{field}={conf:.2f}")

    # Merge confidence scores
    if agent_confidence:
        existing_confidence = merged.get("confidence", {})
        if isinstance(existing_confidence, dict):
            merged["confidence"] = {
                **existing_confidence,
                "agent": agent_confidence,
            }
        else:
            merged["confidence"] = {"dspy": existing_confidence, "agent": agent_confidence}

    # Update decision trace
    merged["decision_trace"] = decision_trace

    # Update decision_outcome based on final action_required
    action_required = merged.get("action_required")
    if action_required is False:
        merged["decision_outcome"] = "auto_handled"
    elif action_required == "optional":
        merged["decision_outcome"] = "needs_review"
    else:
        merged["decision_outcome"] = "action_required"

    return merged


def should_skip_triage(payload: Dict[str, Any]) -> tuple[bool, str | None, str | None]:
    """
    Quick pre-check to determine if full triage can be skipped.

    Checks (in order):
    1. Gmail/Outlook native category labels — CATEGORY_UPDATES etc. are free and accurate
    2. Sender pattern heuristics (noreply@, newsletter@, ...)
    3. Subject/body content patterns (spam, auto-reply, marketing)

    Args:
        payload: Normalized email payload

    Returns:
        Tuple of (should_skip, email_type, reason)
    """
    # ── Layer 0: Gmail native category labels ──────────────────────────────────
    # Gmail runs its own ML classification and surfaces results as system label IDs.
    # We trust these signals — they are free, accurate, and avoid unnecessary LLM calls.
    #
    # Labels that mean "skip triage, auto-handle":
    _GMAIL_SKIP_CATEGORIES = {
        # pre_filter_type matches the InboxIQ category so _writeback_to_provider
        # applies the right canonical label (e.g. "social" → InboxIQ/Social).
        "CATEGORY_UPDATES":    ("updates",       "Gmail categorised as Updates"),
        "CATEGORY_PROMOTIONS": ("promotions",    "Gmail categorised as Promotions"),
        "CATEGORY_SOCIAL":     ("social",        "Gmail categorised as Social"),
        "CATEGORY_FORUMS":     ("forums",        "Gmail categorised as Forums"),
        "CATEGORY_PURCHASES":  ("transactional", "Gmail categorised as Purchases/Transactions"),
    }
    provider_label_ids: list = payload.get("provider_label_ids") or []
    for label_id, (email_type, reason) in _GMAIL_SKIP_CATEGORIES.items():
        if label_id in provider_label_ids:
            return True, email_type, reason

    # CATEGORY_PERSONAL = Gmail confirmed this is a human email in the Primary tab.
    # Do NOT skip triage — but surface the signal so DSPy and draft reply can trust it.
    if "CATEGORY_PERSONAL" in provider_label_ids:
        payload["_gmail_primary"] = True  # picked up by run_dspy_decision as a hint

    subject = (payload.get("subject") or "").lower()
    from_email = (payload.get("from_email") or payload.get("from") or "").lower()
    body = (payload.get("body") or "").lower()

    # Automated sender patterns
    automated_senders = [
        "noreply@", "no-reply@", "donotreply@", "do-not-reply@",
        "mailer-daemon", "postmaster@", "notifications@", "alerts@",
        "newsletter@", "marketing@", "promo@", "bounce@"
    ]

    # Spam subject patterns
    spam_subjects = [
        "you've won", "congratulations", "act now", "limited time",
        "click here", "free gift", "winner", "claim your", "urgent action"
    ]

    # Marketing patterns
    marketing_patterns = [
        "unsubscribe", "view in browser", "email preferences",
        "weekly digest", "monthly newsletter", "special offer"
    ]

    # Auto-reply patterns
    auto_reply_patterns = [
        "out of office", "automatic reply", "auto:", "currently unavailable",
        "on vacation", "away from", "i am currently out"
    ]

    # Check for spam
    if any(pattern in subject for pattern in spam_subjects):
        return True, "spam", "Spam subject pattern detected"

    # Check for automated sender
    if any(pattern in from_email for pattern in automated_senders):
        # Could be transactional or notification
        return True, "notification", "Automated sender (no-reply)"

    # Check for marketing/newsletter
    if any(pattern in body for pattern in marketing_patterns):
        return True, "newsletter", "Newsletter/marketing pattern in body"

    # Check for auto-reply
    if any(pattern in subject for pattern in auto_reply_patterns):
        return True, "auto_reply", "Auto-reply subject pattern"
    if any(pattern in body for pattern in auto_reply_patterns):
        return True, "auto_reply", "Auto-reply body pattern"

    return False, None, None
