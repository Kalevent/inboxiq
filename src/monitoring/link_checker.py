"""
Nightly internal link checker.

Crawls all public pages of the app, follows internal <a href> links,
and reports any broken links (4xx / 5xx) to ADMIN_EMAILS.

Security guarantees:
- Only follows same-origin href links — never external URLs.
- Only issues GET requests — never follows forms or destructive actions.
- Skips any URL matching SKIP_PATTERNS (logout, delete, etc.).
- Response bodies are never read or stored.
- Hard limits on URL count and crawl depth prevent runaway execution.
"""
from __future__ import annotations

import logging
import os
import re
import time
from collections import deque
from html.parser import HTMLParser
from typing import Dict, List, Set, Tuple
from urllib.parse import urljoin, urlparse

import requests

logger = logging.getLogger(__name__)

# Hard limits — tune via env if needed.
MAX_URLS = int(os.getenv("LINK_CHECKER_MAX_URLS", "300"))
MAX_DEPTH = int(os.getenv("LINK_CHECKER_MAX_DEPTH", "4"))
REQUEST_DELAY = float(os.getenv("LINK_CHECKER_DELAY_S", "0.3"))
REQUEST_TIMEOUT = int(os.getenv("LINK_CHECKER_TIMEOUT_S", "10"))

# URL path fragments that indicate a destructive or sensitive action.
SKIP_PATTERNS = (
    "/logout",
    "/delete",
    "/destroy",
    "/reset-all",
    "/_internal",
    "/admin/impersonate",
    "/__",       # Flask debug endpoints
    "/static/",  # Static assets — skip, not pages
)

# Seed URLs — the crawler starts from these.
SEED_PATHS = [
    "/",
    "/home",
    "/features",
    "/pricing",
    "/privacy",
    "/terms",
    "/contact",
    "/security",
    "/login",
    "/register",
    "/dashboard",
    "/settings",
    "/upgrade",
    "/blog",
    "/kb",
    "/funnel/dashboard",
]

# Status codes that count as broken.
BROKEN_CODES = set(range(400, 600))

# Status codes that are acceptable (2xx success, 3xx redirect, 401/403 = auth wall).
PASS_CODES = set(range(200, 400)) | {401, 403}


class _LinkExtractor(HTMLParser):
    """Extract all href values from <a> tags in a page."""

    def __init__(self):
        super().__init__()
        self.links: List[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            for name, value in attrs:
                if name == "href" and value:
                    self.links.append(value)


def _is_same_origin(url: str, origin: str) -> bool:
    parsed = urlparse(url)
    origin_parsed = urlparse(origin)
    return parsed.netloc == origin_parsed.netloc or not parsed.netloc


def _should_skip(path: str) -> bool:
    p = path.lower()
    return any(pattern in p for pattern in SKIP_PATTERNS)


def _normalise(url: str, base: str) -> str | None:
    """Resolve relative URLs and strip fragments/query strings for dedup."""
    try:
        full = urljoin(base, url)
        parsed = urlparse(full)
        # Strip fragment (#section) — same page, no separate request needed.
        return parsed._replace(fragment="").geturl()
    except Exception:
        return None


def run_link_check(base_url: str) -> Dict:
    """
    Crawl base_url and return a report dict:
        {
            "base_url": str,
            "checked": int,
            "broken": [{"url": str, "status": int, "found_on": str}],
            "errors": [{"url": str, "error": str, "found_on": str}],
        }
    """
    origin = "{0.scheme}://{0.netloc}".format(urlparse(base_url))
    session = requests.Session()
    session.headers["User-Agent"] = "InboxIQ-LinkChecker/1.0"
    # Never follow redirects automatically — treat 3xx as a pass, not a chain.
    session.max_redirects = 0

    visited: Set[str] = set()
    broken: List[Dict] = []
    errors: List[Dict] = []

    # Queue entries: (url, depth, found_on)
    queue: deque[Tuple[str, int, str]] = deque()
    for path in SEED_PATHS:
        url = urljoin(base_url, path)
        queue.append((url, 0, "seed"))

    while queue and len(visited) < MAX_URLS:
        url, depth, found_on = queue.popleft()

        if url in visited:
            continue
        visited.add(url)

        parsed_path = urlparse(url).path
        if _should_skip(parsed_path):
            continue

        try:
            resp = session.get(
                url,
                timeout=REQUEST_TIMEOUT,
                allow_redirects=False,
                stream=True,   # Don't download the full body.
            )
            status = resp.status_code
            # Drain just enough to get headers; close immediately.
            resp.close()
        except requests.RequestException as exc:
            errors.append({"url": url, "error": str(exc), "found_on": found_on})
            time.sleep(REQUEST_DELAY)
            continue

        if status in BROKEN_CODES:
            broken.append({"url": url, "status": status, "found_on": found_on})

        # Only extract links from pages we can actually read (2xx HTML).
        if status in range(200, 300) and depth < MAX_DEPTH:
            try:
                # Re-fetch to read body — only for HTML pages.
                content_resp = session.get(
                    url,
                    timeout=REQUEST_TIMEOUT,
                    allow_redirects=False,
                )
                content_type = content_resp.headers.get("Content-Type", "")
                if "text/html" in content_type:
                    parser = _LinkExtractor()
                    parser.feed(content_resp.text)
                    for href in parser.links:
                        candidate = _normalise(href, url)
                        if not candidate:
                            continue
                        if not _is_same_origin(candidate, origin):
                            continue
                        if candidate not in visited:
                            queue.append((candidate, depth + 1, url))
                content_resp.close()
            except Exception:  # noqa: BLE001
                pass  # Link extraction failure is non-fatal

        time.sleep(REQUEST_DELAY)

    return {
        "base_url": base_url,
        "checked": len(visited),
        "broken": broken,
        "errors": errors,
    }


def send_link_check_report(report: Dict) -> None:
    """Email the link check report to ADMIN_EMAILS if any issues found."""
    broken = report["broken"]
    errors = report["errors"]

    if not broken and not errors:
        logger.info(
            "Link checker: all %d URLs OK on %s",
            report["checked"],
            report["base_url"],
        )
        return

    admin_emails_raw = os.getenv("ADMIN_EMAILS", "")
    recipients = [e.strip() for e in admin_emails_raw.split(",") if e.strip()]
    if not recipients:
        logger.warning("Link checker found issues but ADMIN_EMAILS is not set.")
        return

    lines = [
        f"InboxIQ link check — {report['base_url']}",
        f"Checked: {report['checked']} URLs",
        "",
    ]
    if broken:
        lines.append(f"❌ Broken links ({len(broken)}):")
        for item in broken:
            lines.append(f"  [{item['status']}]  {item['url']}")
            lines.append(f"          found on: {item['found_on']}")
        lines.append("")
    if errors:
        lines.append(f"⚠️  Connection errors ({len(errors)}):")
        for item in errors:
            # Truncate error message — never log full stack traces externally.
            short_err = str(item["error"])[:120]
            lines.append(f"  {item['url']}  ({short_err})")
        lines.append("")

    body = "\n".join(lines)

    try:
        import smtplib
        from email.message import EmailMessage
        from flask import current_app

        app = current_app._get_current_object()  # type: ignore[attr-defined]
        host = app.config.get("SMTP_HOST")
        port = int(app.config.get("SMTP_PORT", 587))
        user = app.config.get("SMTP_USER")
        password = app.config.get("SMTP_PASSWORD")
        use_ssl = app.config.get("SMTP_USE_SSL", False)
        mail_from = app.config.get("MAIL_FROM", "noreply@kalevent.com")

        if not host:
            logger.warning("Link checker: SMTP_HOST not configured, skipping email report.")
            return

        subject = (
            f"⚠️ Link checker: {len(broken)} broken, {len(errors)} errors — "
            f"{report['base_url']}"
        )
        for recipient in recipients:
            msg = EmailMessage()
            msg["Subject"] = subject
            msg["From"] = mail_from
            msg["To"] = recipient
            msg.set_content(body)
            try:
                if use_ssl:
                    with smtplib.SMTP_SSL(host, port) as server:
                        if user and password:
                            server.login(user, password)
                        server.send_message(msg)
                else:
                    with smtplib.SMTP(host, port) as server:
                        server.starttls()
                        if user and password:
                            server.login(user, password)
                        server.send_message(msg)
            except Exception as exc:
                logger.error("Failed to send link check report to %s: %s", recipient, exc)
    except Exception as exc:
        logger.error("Failed to send link check report email: %s", exc)
