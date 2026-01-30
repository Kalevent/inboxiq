"""
InboxIQ MCP server (ported from legacy kalevent_mcp).
Provides lightweight tools for health, triage, and email classification.
"""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from src.inboxiq_logic import normalize_email_payload, run_dspy_decision
from src.decision_merger import should_skip_triage

mcp = FastMCP("inboxiq")

# Email types that should be auto-handled
NON_ACTIONABLE_TYPES = {
    "spam", "marketing", "newsletter", "transactional",
    "auto_reply", "out_of_office", "promotional", "notification"
}


@mcp.tool()
def ping() -> str:
    """Simple healthcheck tool."""
    return "pong"


@mcp.tool()
def add(a: int, b: int) -> int:
    """Add two integers and return the result."""
    return a + b


@mcp.tool()
def triage_email_ticket(subject: str, body: str, from_email: str = "", message_id: str | None = None, provider: str = "mcp") -> dict:
    """
    Run InboxIQ LLM triage against an email payload and return the decision.
    """
    payload = {
        "subject": subject,
        "body": body,
        "from_email": from_email or "unknown@example.com",
        "message_id": message_id,
        "provider": provider,
    }
    normalized = normalize_email_payload(payload)
    decision = run_dspy_decision(normalized)
    return decision.to_dict()


@mcp.tool()
def classify_email_type(subject: str, body: str, from_email: str = "") -> dict:
    """
    Quick classification of email type without full triage.
    Returns email_type, is_automated, and whether to skip full triage.
    Use this for fast pre-filtering of spam, marketing, and auto-replies.
    """
    payload = {
        "subject": subject,
        "body": body,
        "from_email": from_email,
    }

    # Use the pre-filter heuristics
    skip_triage, email_type, reason = should_skip_triage(payload)

    return {
        "email_type": email_type or "unknown",
        "is_automated": skip_triage,
        "skip_triage": skip_triage,
        "skip_reason": reason,
        "action_required": not skip_triage,
        "confidence": 0.85 if skip_triage else 0.5,
    }


@mcp.tool()
def is_actionable_email(subject: str, body: str, from_email: str = "") -> dict:
    """
    Quick check if an email requires human action.
    Returns true for support requests, false for spam/marketing/auto-replies.
    """
    payload = {
        "subject": subject,
        "body": body,
        "from_email": from_email,
    }

    skip_triage, email_type, reason = should_skip_triage(payload)

    if skip_triage:
        return {
            "actionable": False,
            "reason": reason or f"Auto-handled: {email_type}",
            "email_type": email_type,
            "suggested_status": "auto_handled",
        }

    return {
        "actionable": True,
        "reason": "Email requires human review",
        "email_type": email_type or "support_request",
        "suggested_status": "needs_review",
    }


@mcp.tool()
def batch_classify_emails(emails: list) -> dict:
    """
    Classify multiple emails at once. Each email should have subject, body, from_email.
    Returns classification results for each email.
    """
    results = []
    auto_handled_count = 0
    actionable_count = 0

    for email in emails:
        subject = email.get("subject", "")
        body = email.get("body", "")
        from_email = email.get("from_email", "")

        payload = {"subject": subject, "body": body, "from_email": from_email}
        skip_triage, email_type, reason = should_skip_triage(payload)

        if skip_triage:
            auto_handled_count += 1
            status = "auto_handled"
        else:
            actionable_count += 1
            status = "needs_review"

        results.append({
            "subject": subject[:100],
            "email_type": email_type or "unknown",
            "skip_triage": skip_triage,
            "status": status,
            "reason": reason,
        })

    return {
        "total": len(emails),
        "auto_handled": auto_handled_count,
        "actionable": actionable_count,
        "auto_handle_rate": round(auto_handled_count / len(emails) * 100, 1) if emails else 0,
        "results": results,
    }


if __name__ == "__main__":
    mcp.run(transport="stdio")
