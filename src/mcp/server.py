"""
InboxIQ MCP server (ported from legacy kalevent_mcp).
Provides lightweight tools for health and triage without pulling legacy imports.
"""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from src.inboxiq_logic import normalize_email_payload, run_dspy_decision

mcp = FastMCP("inboxiq")


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


if __name__ == "__main__":
    mcp.run(transport="stdio")
