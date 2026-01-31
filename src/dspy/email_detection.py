"""
Heuristic email type detection.

Fast pattern-based classification before LLM processing.
Identifies spam, marketing, auto-replies, and transactional emails.
"""
from __future__ import annotations

from typing import Any, Dict


# Email types that should be auto-handled without human review
NON_ACTIONABLE_EMAIL_TYPES = {
    "spam", "marketing", "newsletter", "transactional",
    "auto_reply", "out_of_office", "promotional", "notification"
}

# Sender patterns that indicate automated emails
AUTOMATED_SENDER_PATTERNS = [
    "noreply@", "no-reply@", "donotreply@", "do-not-reply@",
    "mailer-daemon", "postmaster@", "notifications@", "alerts@",
    "newsletter@", "marketing@", "promo@", "bounce@", "auto@"
]

# Subject patterns indicating non-actionable emails
SPAM_SUBJECT_PATTERNS = [
    "you've won", "congratulations", "act now", "limited time",
    "click here", "free gift", "winner", "claim your"
]

MARKETING_SUBJECT_PATTERNS = [
    "newsletter", "unsubscribe", "weekly digest", "monthly update",
    "special offer", "% off", "sale ends", "don't miss"
]

AUTO_REPLY_SUBJECT_PATTERNS = [
    "out of office", "automatic reply", "auto:", "re: automatic",
    "away from", "on vacation", "currently unavailable"
]


def detect_email_type(payload: Dict[str, Any]) -> tuple[str, bool, str | None]:
    """
    Detect email type using heuristics before LLM classification.

    Fast pattern matching for common non-actionable email types:
    - Spam (phishing, scams, unwanted promotion)
    - Marketing (newsletters, promotions, sales emails)
    - Auto-replies (out of office, automated responses)
    - Transactional (shipping confirmations, receipts from no-reply)

    Args:
        payload: Email payload with subject, from_email, body

    Returns:
        Tuple of (email_type, is_automated, skip_reason)
        - email_type: Classification (spam, marketing, auto_reply, etc.)
        - is_automated: Whether this is an automated email
        - skip_reason: Human-readable explanation if should skip triage
    """
    subject = (payload.get("subject") or "").lower()
    from_email = (payload.get("from_email") or payload.get("from") or "").lower()
    body = (payload.get("body") or "").lower()

    # Check for automated sender patterns
    is_automated = any(pattern in from_email for pattern in AUTOMATED_SENDER_PATTERNS)

    # Check for spam patterns
    if any(pattern in subject for pattern in SPAM_SUBJECT_PATTERNS):
        return "spam", True, "Spam subject pattern detected"

    # Check for marketing patterns
    if any(pattern in subject for pattern in MARKETING_SUBJECT_PATTERNS):
        return "marketing", True, "Marketing email pattern detected"
    if "unsubscribe" in body and ("view in browser" in body or "email preferences" in body):
        return "newsletter", True, "Newsletter pattern detected"

    # Check for auto-reply patterns
    if any(pattern in subject for pattern in AUTO_REPLY_SUBJECT_PATTERNS):
        return "auto_reply", True, "Auto-reply detected"
    if "i am currently out" in body or "automatic response" in body:
        return "auto_reply", True, "Auto-reply body pattern detected"

    # Check for transactional/notification emails
    if is_automated:
        if any(word in subject for word in ["shipped", "delivered", "confirmation", "receipt", "invoice"]):
            return "transactional", True, "Transactional email from no-reply sender"
        return "notification", True, "Automated notification from no-reply sender"

    return "unknown", False, None


# Alias for backward compatibility
_detect_email_type = detect_email_type
