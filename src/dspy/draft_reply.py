"""
Draft reply generation pipeline.

Handles KB context fetching, reply generation, sanitization, and confidence scoring.
"""
from __future__ import annotations

import os
import re
import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


def _env_bool(name: str, default: bool = False) -> bool:
    """Parse boolean from environment variable."""
    val = os.getenv(name)
    if val is None:
        return default
    return val.lower() in ("1", "true", "yes", "on")


def draft_reply_enabled(context: Dict[str, Any] | None, account_id: int | None = None) -> bool:
    """
    Check if draft reply generation is enabled for this request.

    Global kill switch: DSPY_DRAFT_REPLY_ENABLED=false disables for all accounts.
    Per-account: respects AccountFeatureFlags.draft_reply_enabled (defaults True
    when no row exists — all new accounts get drafts out of the box).

    Args:
        context: Request context dict (checked for an explicit override first)
        account_id: Account ID for per-account preference lookup

    Returns:
        True if draft reply should be generated
    """
    # Global kill switch
    if not _env_bool("DSPY_DRAFT_REPLY_ENABLED", True):
        return False

    # Explicit context override (useful for tests / celery task context)
    if context and isinstance(context, dict):
        features = context.get("features")
        if isinstance(features, dict) and "draft_reply" in features:
            return bool(features["draft_reply"])

    if account_id:
        try:
            from src.models.core import AccountFeatureFlags
            flags = AccountFeatureFlags.query.filter_by(account_id=account_id).first()
            # No row → feature not yet configured → default ON
            if flags is None:
                return True
            return bool(flags.draft_reply_enabled)
        except Exception as exc:
            logger.warning("draft_reply_enabled db lookup failed: %s", exc)

    return True


def fetch_kb_context(
    subject: str,
    body: str,
    account_id: int | None = None,
    limit: int = 3
) -> list[dict]:
    """
    Retrieve relevant knowledge base articles using semantic search.

    Returns a list of dicts with: {"id": str, "title": str, "snippet": str, "similarity_score": float}

    Args:
        subject: Email subject line
        body: Email body text
        account_id: Optional account ID for scoped KB search
        limit: Maximum number of articles to return

    Returns:
        List of relevant KB articles with title, content snippet, and similarity scores
    """
    if not account_id:
        return []

    # Combine subject and body for semantic search
    query = f"{subject}\n\n{body}"

    # Search KB using semantic similarity
    from src.retrieval.kb_search import search_kb_articles

    articles = search_kb_articles(
        query=query,
        account_id=account_id,
        limit=limit,
        similarity_threshold=0.6,  # Medium relevance
    )

    # Transform to expected format with snippet instead of full content
    results = []
    for article in articles:
        snippet = article["content"][:200] + "..." if len(article["content"]) > 200 else article["content"]
        results.append({
            "id": article["id"],
            "title": article["title"],
            "snippet": snippet,
            "url": article.get("url"),
            "similarity_score": article["similarity_score"],
        })

    return results


def sanitize_reply(reply_text: str, account_id: int | None = None) -> str:
    """
    Sanitize and improve draft reply text.

    Cleaning operations:
    - Removes internal markers like [INTERNAL: ...]
    - Ensures professional tone
    - Adds signature placeholder if missing
    - Applies account-specific tone preferences (future enhancement)

    Args:
        reply_text: The raw reply text from DSPy
        account_id: Optional account ID for account-specific preferences

    Returns:
        Sanitized reply text ready for human review
    """
    if not reply_text:
        return ""

    # Remove internal markers and notes
    reply_text = re.sub(r'\[INTERNAL:.*?\]', '', reply_text, flags=re.IGNORECASE | re.DOTALL)
    reply_text = re.sub(r'\[NOTE:.*?\]', '', reply_text, flags=re.IGNORECASE | re.DOTALL)

    # Clean up excessive whitespace
    reply_text = re.sub(r'\n{3,}', '\n\n', reply_text)
    reply_text = reply_text.strip()

    # Ensure signature placeholder if not present
    signature_markers = ["best regards", "sincerely", "thanks", "thank you", "regards"]
    has_signature = any(marker in reply_text.lower() for marker in signature_markers)

    if not has_signature and len(reply_text) > 20:
        reply_text += "\n\nBest regards"

    return reply_text


def compute_reply_confidence(result: Any) -> float:
    """
    Compute confidence score for generated draft reply.

    Currently returns a default confidence of 0.8.
    Future enhancement: analyze reply quality, length, specificity, etc.

    Args:
        result: The DSPy prediction result

    Returns:
        Confidence score between 0.0 and 1.0

    Future implementation should consider:
    - Reply length (too short or too long = lower confidence)
    - Presence of specific answers vs vague responses
    - KB article relevance scores
    - Entity extraction confidence
    """
    # TODO: Implement actual confidence calculation
    return 0.8


def fetch_calendar_slots(
    subject: str,
    body: str,
    account_id: int | None,
    ticket_id: str | None = None,
    requester_email: str | None = None,
    requester_name: str | None = None,
) -> str:
    """
    If the email looks like a meeting request AND the account has Google Calendar
    connected, return a formatted available-slots string to include in the draft.

    When ticket_id and requester_email are provided, returns a booking link instead
    of a text-based slot list so the visitor can self-schedule.

    Returns empty string when:
    - account_id is None
    - email is not a meeting request
    - gcal not connected for this account
    - Calendar API call fails (non-fatal)

    Args:
        subject: Email subject line
        body: Email body text
        account_id: Account ID to look up gcal connection
        ticket_id: Ticket ID for generating a booking link (optional)
        requester_email: Email of the meeting requester (optional)
        requester_name: Name of the meeting requester (optional)

    Returns:
        Human-readable availability string or booking link, or ""
    """
    if not account_id:
        return ""
    try:
        from src.integrations.gcal import is_meeting_request
        if not is_meeting_request(subject, body):
            return ""

        from src.models.core import AccountFeatureFlags
        flags = AccountFeatureFlags.query.filter_by(account_id=account_id).first()

        # Dynamic expiring booking URL — plan-gated (compute cost).
        # If disabled, no booking link is included in the draft — upsell path.
        if not (flags is None or flags.dynamic_booking_enabled):
            return ""

        if ticket_id and requester_email:
            # Prefer the short booking_handle URL; fall back to static URL; last resort dynamic JWT
            if flags and flags.booking_handle:
                booking_url = f"https://kalevent.com/book/{flags.booking_handle}"
            elif flags and flags.static_booking_url:
                booking_url = flags.static_booking_url
            else:
                from src.booking.service import generate_booking
                booking_url = generate_booking(
                    account_id=account_id,
                    ticket_id=ticket_id,
                    subject=subject,
                    requester_email=requester_email,
                    requester_name=requester_name or "",
                )
            return f"\n\nSCHEDULE_CTA:{booking_url}"

        from src.integrations.gcal import get_available_slots_text as gcal_slots
        from src.integrations.outlook_cal import get_available_slots_text as outlook_slots
        slots = gcal_slots(account_id)
        if not slots:
            slots = outlook_slots(account_id)
        return slots or ""
    except Exception as exc:
        logger.warning("fetch_calendar_slots failed account=%s: %s", account_id, exc)
        return ""


# Aliases for backward compatibility
_draft_reply_enabled = draft_reply_enabled
_fetch_kb_context = fetch_kb_context
_sanitize_reply = sanitize_reply
_compute_reply_confidence = compute_reply_confidence
