"""
Lead enrichment MCP server: extract contacts from HTML/text and verify email deliverability.
Designed to complement existing search/http/sql MCP servers for the Lead Sourcing Agent.
"""
from __future__ import annotations

import re
import smtplib
import socket
import ssl
import os
from typing import Any, Dict, List, Optional

try:
    import dns.resolver
except ImportError:  # pragma: no cover
    dns = None  # type: ignore

try:
    from mcp.server.fastmcp import FastMCP, ToolError
except ImportError:
    from mcp.server.fastmcp import FastMCP

    class ToolError(Exception):  # type: ignore
        pass


mcp = FastMCP("lead-enrichment-mcp")


EMAIL_REGEX = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.IGNORECASE)
NAME_TITLE_REGEX = re.compile(
    r"(?P<name>[A-Z][a-z]+(?: [A-Z][a-z]+)?)\\s*[,|-]?\\s*(?P<title>(head|vp|director|lead|manager)[^,<\\n\\r]{0,60})",
    re.IGNORECASE,
)


@mcp.tool()
def extract_contacts(text: str, domain_hint: Optional[str] = None) -> Dict[str, Any]:
    """
    Extract candidate contacts (name/title/email) from HTML or plain text.
    If no explicit email is present and domain_hint is provided, synthesize first.last@domain_hint.
    """
    if not text or not isinstance(text, str):
        raise ToolError("text is required")

    emails = set(EMAIL_REGEX.findall(text))
    contacts: List[Dict[str, Any]] = []
    seen_pairs = set()

    for match in NAME_TITLE_REGEX.finditer(text):
        name = match.group("name").strip()
        title = match.group("title").strip()
        pair_key = (name.lower(), title.lower())
        if pair_key in seen_pairs:
            continue
        seen_pairs.add(pair_key)
        contacts.append({"name": name, "title": title, "email": None})

    # Attach any explicit emails to nearest contact if possible
    for email in emails:
        if contacts:
            contacts[0].setdefault("email", email)
        else:
            contacts.append({"name": None, "title": None, "email": email})

    # Synthesize email if missing and domain hint exists
    if domain_hint:
        domain_hint = domain_hint.strip().lower()
        for c in contacts:
            if not c.get("email") and c.get("name"):
                parts = c["name"].split()
                if len(parts) >= 2:
                    candidate = f"{parts[0].lower()}.{parts[-1].lower()}@{domain_hint}"
                    c["email"] = candidate

    return {"contacts": contacts}


def _mx_hosts(domain: str) -> List[str]:
    if not dns:
        return []
    try:
        answers = dns.resolver.resolve(domain, "MX")
    except Exception:
        return []
    hosts = []
    for r in answers:
        host = str(getattr(r, "exchange", "")).rstrip(".")
        if host:
            hosts.append(host)
    return hosts


def _smtp_check(host: str, from_addr: str, to_addr: str, timeout: float = 5.0) -> bool:
    try:
        server = smtplib.SMTP(host=host, timeout=timeout)
        server.ehlo_or_helo_if_needed()
        server.mail(from_addr)
        code, _ = server.rcpt(to_addr)
        server.quit()
        return 200 <= code < 300 or code == 250
    except (smtplib.SMTPServerDisconnected, smtplib.SMTPConnectError, smtplib.SMTPRecipientsRefused, socket.timeout):
        return False
    except Exception:
        return False


@mcp.tool()
def verify_email(email: str, from_address: str = "noreply@example.com") -> Dict[str, Any]:
    """
    Lightweight deliverability check: syntax + MX + SMTP RCPT (best-effort).
    """
    if not email or not isinstance(email, str):
        raise ToolError("email is required")

    email = email.strip()
    if not EMAIL_REGEX.fullmatch(email):
        return {"email": email, "valid": False, "reason": "invalid_format"}

    domain = email.split("@")[-1].lower()
    mx_hosts = _mx_hosts(domain)
    if not mx_hosts:
        return {"email": email, "valid": False, "reason": "no_mx"}

    for host in mx_hosts[:3]:  # limit attempts
        if _smtp_check(host, from_address, email):
            return {"email": email, "valid": True, "reason": "smtp_ok", "mx_host": host}

    return {"email": email, "valid": False, "reason": "smtp_failed", "mx_hosts": mx_hosts[:3]}


@mcp.tool()
def send_probe_email(
    to_email: str,
    from_email: Optional[str] = None,
    subject: str = "InboxIQ probe email",
    body: str = "This is a delivery probe from InboxIQ to validate reachability.",
) -> Dict[str, Any]:
    """
    Send a lightweight probe email to test real delivery. Uses PROBE_SMTP_* env or falls back to SMTP_*.
    """
    if not to_email:
        raise ToolError("to_email is required")

    host = os.getenv("PROBE_SMTP_HOST") or os.getenv("SMTP_HOST")
    port = int(os.getenv("PROBE_SMTP_PORT") or os.getenv("SMTP_PORT") or "587")
    user = os.getenv("PROBE_SMTP_USER") or os.getenv("SMTP_USER")
    password = os.getenv("PROBE_SMTP_PASSWORD") or os.getenv("SMTP_PASSWORD")
    use_tls = os.getenv("PROBE_SMTP_USE_TLS") or os.getenv("SMTP_USE_TLS") or "true"
    use_ssl = os.getenv("PROBE_SMTP_USE_SSL") or os.getenv("SMTP_USE_SSL") or "false"
    mail_from = from_email or os.getenv("PROBE_MAIL_FROM") or os.getenv("MAIL_FROM") or "probe@inboxiq.local"

    if not host:
        raise ToolError("SMTP host not configured (set PROBE_SMTP_HOST or SMTP_HOST)")

    msg = f"From: {mail_from}\r\nTo: {to_email}\r\nSubject: {subject}\r\n\r\n{body}"

    try:
        if use_ssl.lower() in ("1", "true", "yes"):
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(host, port, context=context, timeout=10) as server:
                if user and password:
                    server.login(user, password)
                server.sendmail(mail_from, [to_email], msg)
        else:
            with smtplib.SMTP(host, port, timeout=10) as server:
                if use_tls.lower() in ("1", "true", "yes"):
                    server.starttls()
                if user and password:
                    server.login(user, password)
                server.sendmail(mail_from, [to_email], msg)
        return {"sent": True, "to": to_email, "from": mail_from, "smtp_host": host}
    except Exception as exc:
        return {"sent": False, "to": to_email, "from": mail_from, "error": str(exc)}


if __name__ == "__main__":
    mcp.run(transport="stdio")
