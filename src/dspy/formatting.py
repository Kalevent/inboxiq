"""
Payload formatting utilities for DSPy prompts.

Converts email/case payloads into formatted text for LLM consumption.
"""
from __future__ import annotations

from typing import Any, Dict


def format_payload(payload: Dict[str, Any], context: Dict[str, Any] | None) -> str:
    """
    Format email payload into structured text for DSPy prompt.

    Extracts key fields (subject, from, body, etc.) and formats them
    into a consistent structure for LLM processing.

    Args:
        payload: Email/case payload dict
        context: Optional context dict with additional metadata

    Returns:
        Formatted text string for prompt
    """
    subject = (payload.get("subject") or "").strip()
    body = (payload.get("body") or "").strip()
    from_email = (payload.get("from_email") or payload.get("from") or "").strip()
    provider = (payload.get("provider") or payload.get("source") or "").strip()
    source = (payload.get("source") or "").strip()
    received_at = payload.get("received_at") or ""

    lines = [
        f"subject: {subject}",
        f"from: {from_email}",
        f"provider: {provider}",
        f"source: {source}",
        f"received_at: {received_at}",
        "body:",
        body,
    ]

    if context:
        lines.append(f"context: {context}")

    return "\n".join(line for line in lines if line is not None)


def label_desc(labels: Dict[str, Any], key: str, fallback: str) -> str:
    """
    Generate label description for DSPy field descriptor.

    If labels dict contains a list of values for the key, formats them
    as "One of: value1, value2, ...". Otherwise returns fallback text.

    Args:
        labels: Label configuration dict
        key: Key to lookup (e.g., "categories", "priorities")
        fallback: Fallback description if no labels found

    Returns:
        Formatted description string
    """
    values = labels.get(key) if labels else None
    if isinstance(values, list) and values:
        return f"One of: {', '.join(str(v) for v in values)}"
    return fallback


def decision_outcome(action_required: Any) -> str:
    """
    Convert action_required value to standardized outcome string.

    Args:
        action_required: boolean, "optional", "needs_review", etc.

    Returns:
        One of: "auto_handled", "needs_review", "action_required"
    """
    if isinstance(action_required, str):
        lowered = action_required.lower()
        if lowered in {"optional", "needs_review"}:
            return "needs_review"
        if lowered in {"false", "no", "none"}:
            return "auto_handled"

    if action_required is True:
        return "action_required"
    if action_required in ("optional", "needs_review"):
        return "needs_review"
    if action_required is False:
        return "auto_handled"

    return "action_required"


# Aliases for backward compatibility
_format_payload = format_payload
_label_desc = label_desc
_decision_outcome = decision_outcome
