"""
Post-deploy smoke test.

Hits every key public route and verifies no 5xx responses.
Auth-required routes are expected to return 302 (redirect to login) — that passes.
Only checks HTTP status codes; response bodies are never read or logged.

Usage:
    python scripts/smoke_test.py https://kalevent.com

Exit code 0 = all clear, 1 = one or more failures.
"""
import sys
import time
import urllib.request
import urllib.error

# Maximum seconds to wait for each request.
TIMEOUT = 15

# Routes to check. Grouped for readability.
# Auth-required routes will 302 → login, which counts as a pass.
ROUTES = [
    # Public marketing pages
    "/",
    "/privacy",
    "/terms",
    "/contact",
    "/security",
    "/sitemap.xml",
    "/robots.txt",
    # Product pages
    "/features",
    "/pricing",
    "/support-automation",
    "/solutions/email/triage-automation",
    # Auth pages (unauthenticated)
    "/login",
    # Auth-required pages (expect 302 redirect, not 5xx)
    "/dashboard",
    "/upgrade",
    "/onboarding",
    "/settings",
    # Health
    "/health",
]

# Status codes that count as a pass.
# 2xx = OK, 3xx = redirect (e.g. login wall), 401/403 = auth required (expected).
PASS_CODES = set(range(200, 400)) | {401, 403}

# URL patterns that indicate a destructive or sensitive action — skip entirely.
SKIP_PATTERNS = {"/logout", "/delete", "/destroy", "/reset-all", "/_internal"}


def _do_request(url: str) -> int:
    """Fire one GET and return the HTTP status code. Raises on network error."""
    req = urllib.request.Request(url, method="GET")
    req.add_header("User-Agent", "InboxIQ-SmokeTest/1.0")
    opener = urllib.request.build_opener(NoRedirectHandler)
    try:
        with opener.open(req, timeout=TIMEOUT) as resp:
            return resp.status
    except urllib.error.HTTPError as exc:
        return exc.code


def check(base_url: str, route: str) -> tuple[int | None, str]:
    """
    Return (status_code, outcome) where outcome is 'pass', 'fail', or 'skip'.
    Never reads the response body.
    Retries once on 5xx (rolling-deploy transient failures).
    """
    for pattern in SKIP_PATTERNS:
        if pattern in route:
            return None, "skip"

    url = base_url.rstrip("/") + route

    try:
        code = _do_request(url)
        if code >= 500:
            # One retry after a short wait — rolling deploys can cause transient 5xx
            time.sleep(10)
            code = _do_request(url)
    except urllib.error.URLError as exc:
        return None, f"fail (connection error: {exc.reason})"
    except Exception as exc:  # noqa: BLE001
        return None, f"fail (unexpected: {type(exc).__name__})"

    outcome = "pass" if code in PASS_CODES else "fail"
    return code, outcome


class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Return the redirect response directly instead of following it."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: PLR0913
        return None


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python scripts/smoke_test.py <base_url>")
        print("Example: python scripts/smoke_test.py https://kalevent.com")
        return 1

    base_url = sys.argv[1].rstrip("/")
    print(f"Smoke test: {base_url}")
    print("-" * 60)

    failures = []
    for route in ROUTES:
        code, outcome = check(base_url, route)
        status_str = str(code) if code is not None else "N/A"
        marker = "✅" if outcome == "pass" else ("⏭️ " if outcome == "skip" else "❌")
        print(f"{marker}  {status_str:>4}  {route}")
        if outcome == "fail":
            failures.append((route, status_str))
        # Small delay to avoid hammering the server.
        time.sleep(0.2)

    print("-" * 60)
    if failures:
        print(f"\n❌ {len(failures)} route(s) failed:")
        for route, code in failures:
            print(f"   {code}  {route}")
        return 1

    print(f"\n✅ All {len(ROUTES)} routes passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
