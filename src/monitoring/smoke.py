"""Reusable HTTP smoke-test helper.

The deploy-time smoke test (scripts/smoke_test.py) and the periodic Celery
beat task (src/tasks/smoke.py) both call check_routes(). Keeping the logic
in one place avoids drift between what CI checks and what runs every 15 min.
"""
from __future__ import annotations

import urllib.error
import urllib.request
from typing import List, Dict, Any

# Routes mirror scripts/smoke_test.py — keep in sync.
DEFAULT_ROUTES: List[str] = [
    "/",
    "/privacy",
    "/terms",
    "/contact",
    "/sitemap.xml",
    "/robots.txt",
    "/support-automation",
    "/solutions/email/triage-automation",
    "/login",
    "/dashboard",
    "/upgrade",
    "/onboarding",
    "/settings",
    "/health",
]

# 2xx OK, 3xx redirect (login wall counts as pass), 401/403 auth-required pass.
PASS_CODES = set(range(200, 400)) | {401, 403}
TIMEOUT_SECONDS = 15


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: PLR0913
        return None


def _do_request(url: str) -> int:
    """Return HTTP status code for a single GET. Raises on connection error."""
    req = urllib.request.Request(url, method="GET")
    req.add_header("User-Agent", "InboxIQ-SmokeTest/1.0")
    opener = urllib.request.build_opener(_NoRedirectHandler)
    try:
        with opener.open(req, timeout=TIMEOUT_SECONDS) as resp:
            return resp.status
    except urllib.error.HTTPError as exc:
        return exc.code


def check_routes(base_url: str, routes: List[str] | None = None) -> List[Dict[str, Any]]:
    """Probe each route and return a list of {route, status, outcome} dicts.

    outcome is "pass" if the status is in PASS_CODES, otherwise "fail".
    Connection errors are reported as outcome="fail" with status=None.
    """
    base = base_url.rstrip("/")
    targets = routes if routes is not None else DEFAULT_ROUTES
    results: List[Dict[str, Any]] = []
    for route in targets:
        url = base + route
        try:
            code: int | None = _do_request(url)
        except urllib.error.URLError:
            code = None
        outcome = "pass" if code in PASS_CODES else "fail"
        results.append({"route": route, "status": code, "outcome": outcome})
    return results
