"""
Publishing MCP server that wraps the publishing HTTP endpoints so agents can invoke
blog/newsletter/whitepaper tools over MCP.

Env:
- PUBLISHING_API_BASE: base URL including /api/v1 (default: http://localhost:8000/api/v1)
- PUBLISHING_API_TOKEN: Bearer token for auth
"""
from __future__ import annotations

import os
from typing import Any, Dict

import requests

try:
    from mcp.server.fastmcp import FastMCP, ToolError
except ImportError:
    from mcp.server.fastmcp import FastMCP

    class ToolError(Exception):  # type: ignore
        pass


mcp = FastMCP("publishing-mcp")

API_BASE = os.getenv("PUBLISHING_API_BASE", "http://localhost:8000/api/v1").rstrip("/")
API_TOKEN = os.getenv("PUBLISHING_API_TOKEN")
HTTP_TIMEOUT = float(os.getenv("PUBLISHING_HTTP_TIMEOUT", "15"))


def _headers() -> Dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if API_TOKEN:
        headers["Authorization"] = f"Bearer {API_TOKEN}"
    return headers


def _post(path: str, json_body: Dict[str, Any]) -> Dict[str, Any]:
    url = f"{API_BASE}/{path.lstrip('/')}"
    try:
        resp = requests.post(url, headers=_headers(), json=json_body, timeout=HTTP_TIMEOUT)
    except Exception as exc:
        raise ToolError(f"HTTP request failed: {exc}")
    if resp.status_code >= 400:
        raise ToolError(f"HTTP {resp.status_code}: {resp.text}")
    try:
        return resp.json()
    except Exception:
        return {"status": resp.status_code, "text": resp.text}


@mcp.tool()
def create_blog_draft(title: str, audience: str, brief: str, sync: bool = True) -> Dict[str, Any]:
    """
    Create a blog draft via publishing API.
    """
    payload = {"title": title, "audience": audience, "brief": brief, "sync": sync}
    return _post("/publishing/blog/draft", payload)


@mcp.tool()
def publish_blog(draft_id: str) -> Dict[str, Any]:
    """
    Publish a blog draft.
    """
    return _post(f"/publishing/blog/publish/{draft_id}", {})


@mcp.tool()
def create_newsletter_draft(campaign_title: str, audience: str, brief: str, sync: bool = True) -> Dict[str, Any]:
    """
    Create a newsletter draft via publishing API.
    """
    payload = {"campaign_title": campaign_title, "audience": audience, "brief": brief, "sync": sync}
    return _post("/publishing/newsletter/draft", payload)


@mcp.tool()
def publish_newsletter(draft_id: str) -> Dict[str, Any]:
    """
    Publish a newsletter draft.
    """
    return _post(f"/publishing/newsletter/publish/{draft_id}", {})


@mcp.tool()
def create_whitepaper_draft(title: str, audience: str, brief: str, sync: bool = True) -> Dict[str, Any]:
    """
    Create a whitepaper draft via publishing API.
    """
    payload = {"title": title, "audience": audience, "brief": brief, "sync": sync}
    return _post("/publishing/whitepaper/draft", payload)


@mcp.tool()
def publish_whitepaper(draft_id: str) -> Dict[str, Any]:
    """
    Publish a whitepaper draft.
    """
    return _post(f"/publishing/whitepaper/publish/{draft_id}", {})


if __name__ == "__main__":
    mcp.run(transport="stdio")
