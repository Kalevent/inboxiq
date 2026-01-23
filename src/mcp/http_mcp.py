"""
Minimal HTTP MCP server: only allows GET/POST and does not handle integration credential flows.
Config:
  SAFE_HTTP_ALLOWED_METHODS (default: GET,POST)
  SAFE_HTTP_TIMEOUT_SECONDS (default: 15)
"""
from __future__ import annotations

import os
from typing import Any, Dict, Optional

import requests

try:
    from mcp.server.fastmcp import FastMCP, ToolError
except ImportError:
    from mcp.server.fastmcp import FastMCP

    class ToolError(Exception):  # type: ignore
        pass


mcp = FastMCP("http-mcp")


def _parse_methods(raw: Optional[str], default: list[str]) -> set[str]:
    raw = raw or ""
    parts = [p.strip().upper() for p in raw.replace(" ", "").split(",") if p.strip()]
    if not parts:
        parts = default
    return {p for p in parts if p}


ALLOWED_METHODS = _parse_methods(os.getenv("SAFE_HTTP_ALLOWED_METHODS"), ["GET", "POST"])
REQUEST_TIMEOUT = float(os.getenv("SAFE_HTTP_TIMEOUT_SECONDS", "15"))


def _execute_http_request(
    url: str,
    method: str,
    headers: Optional[Dict[str, str]] = None,
    params: Optional[Dict[str, Any]] = None,
    data: Optional[str] = None,
    json_body: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    method_clean = method.strip().upper()
    if method_clean not in ALLOWED_METHODS:
        allowed_list = ",".join(sorted(ALLOWED_METHODS))
        raise ToolError(f"Method {method_clean} not allowed. Allowed: {allowed_list}")

    try:
        response = requests.request(
            method_clean,
            url,
            headers=headers,
            params=params,
            data=data,
            json=json_body,
            timeout=REQUEST_TIMEOUT,
        )
    except Exception as exc:
        raise ToolError(f"HTTP request failed: {exc}")

    max_body_bytes = 20000
    body_text = response.text
    truncated = False
    if len(body_text.encode("utf-8", errors="ignore")) > max_body_bytes:
        body_text = body_text.encode("utf-8", errors="ignore")[:max_body_bytes].decode("utf-8", errors="ignore")
        truncated = True

    return {
        "url": response.url,
        "status": response.status_code,
        "headers": dict(response.headers),
        "body": body_text,
        "truncated": truncated,
    }


@mcp.tool()
def http_request(
    url: str,
    method: str = "GET",
    headers: Optional[Dict[str, str]] = None,
    params: Optional[Dict[str, Any]] = None,
    data: Optional[str] = None,
    json_body: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Perform an HTTP request (GET/POST only by default).
    """
    return _execute_http_request(
        url=url,
        method=method,
        headers=headers,
        params=params,
        data=data,
        json_body=json_body,
    )


if __name__ == "__main__":
    mcp.run(transport="stdio")
