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

    Uses centralized features.check_draft_reply_access for consistency.

    Args:
        context: Request context dict with features/plan info
        account_id: Account ID for feature access control

    Returns:
        True if draft reply should be generated
    """
    if not _env_bool("DSPY_DRAFT_REPLY_ENABLED", False):
        return False

    if not account_id:
        # Fallback to legacy context-based check if no account_id
        if not context:
            return False
        features = context.get("features") if isinstance(context, dict) else None
        if isinstance(features, dict):
            if features.get("draft_reply") is True:
                return True
            if features.get("draft_reply") is False:
                return False
        plan = str(context.get("plan") or "").lower() if isinstance(context, dict) else ""
        return plan in {"business", "enterprise"}

    # Use centralized feature access control
    try:
        from src.features import check_draft_reply_access
        return check_draft_reply_access(account_id, context)
    except Exception as exc:
        logger.warning("Failed to check draft_reply access: %s", exc)
        return False


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


# Aliases for backward compatibility
_draft_reply_enabled = draft_reply_enabled
_fetch_kb_context = fetch_kb_context
_sanitize_reply = sanitize_reply
_compute_reply_confidence = compute_reply_confidence
