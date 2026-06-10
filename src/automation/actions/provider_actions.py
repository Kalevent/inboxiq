"""
Provider Actions — execute operations directly in Gmail or Outlook after triage.

These run post-triage so they have full AI context (category, priority, sentiment)
that native Gmail filters and Outlook rules cannot access.

All actions use scopes already granted:
  Gmail:   gmail.modify  (addLabelIds, removeLabelIds, messages.trash, messages.send)
  Outlook: Mail.ReadWrite (PATCH /me/messages, POST /move, POST /forward)

Action config schema:
    { "type": "provider_action", "action": "archive" }
    { "type": "provider_action", "action": "forward", "to": "engineering@company.com" }
    { "type": "provider_action", "action": "move_to_folder", "folder": "Support/Billing" }
    { "type": "provider_action", "action": "apply_label", "label": "Needs Review" }
    { "type": "provider_action", "action": "mark_read" }
    { "type": "provider_action", "action": "star" }
    { "type": "provider_action", "action": "trash" }

Security hardening:
  - Email addresses validated before use in MIME headers (prevents header injection)
  - MIME header values CRLF-stripped (prevents header injection)
  - message_id validated against path traversal before URL interpolation
  - label/folder names stripped of control characters
  - forward and trash emit audit log entries (data exfiltration / irreversible action)
  - forward is rate-limited per account per day (prevents inbox exfiltration via rules)
"""
from __future__ import annotations

import base64
import logging
import re
from email.mime.text import MIMEText
from typing import Any, Dict

import requests
from opentelemetry import trace

_log = logging.getLogger(__name__)

# Gmail API base
_GMAIL = "https://gmail.googleapis.com/gmail/v1/users/me"
# Outlook Graph API base
_GRAPH = "https://graph.microsoft.com/v1.0/me"

# Actions that are sensitive enough to require an audit log entry
_AUDIT_ACTIONS = {"forward", "trash"}

# Maximum forwards per account per day — prevents inbox exfiltration via automation rules
_FORWARD_DAILY_LIMIT = 50

# Whitelist of allowed actions — explicit rather than pass-through
_ALLOWED_ACTIONS = {"archive", "mark_read", "star", "trash", "forward", "apply_label", "move_to_folder"}

# Regex for validating a plain email address (no display name, no brackets)
_EMAIL_RE = re.compile(r'^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$')


# ── Input validation helpers ──────────────────────────────────────────────────

def _validate_email(addr: str) -> str:
    """
    Return a clean, validated email address or raise ValueError.

    Strips whitespace and CRLF to prevent MIME header injection.
    Rejects anything that doesn't match a simple RFC 5321 local@domain pattern.
    """
    clean = re.sub(r'[\r\n\t\x00-\x1f\x7f]', '', addr.strip())
    if not _EMAIL_RE.match(clean):
        raise ValueError(f"Invalid email address for forward: {addr!r}")
    return clean


def _validate_message_id(message_id: str) -> str:
    """
    Validate a provider message ID before interpolating into a URL path.

    Rejects path traversal sequences, whitespace, and control characters.
    Gmail IDs are hex; Outlook IDs are base64-like. Both are safe after this check.
    """
    clean = message_id.strip()
    if not clean:
        raise ValueError("Empty message_id")
    if len(clean) > 512:
        raise ValueError("message_id exceeds maximum length")
    # Reject path traversal and whitespace
    if re.search(r'[\s\x00-\x1f\x7f]', clean) or '..' in clean or clean.startswith('/'):
        raise ValueError("message_id contains invalid characters")
    return clean


def _sanitize_header(value: str, max_len: int = 256) -> str:
    """Strip CRLF and control characters from a MIME header value."""
    return re.sub(r'[\r\n\x00-\x1f\x7f]', '', value)[:max_len]


def _sanitize_name(name: str, field: str) -> str:
    """Strip control characters from a label or folder name."""
    clean = re.sub(r'[\r\n\x00-\x1f\x7f]', '', name.strip())
    if not clean:
        raise ValueError(f"Empty {field}")
    if len(clean) > 200:
        raise ValueError(f"{field} too long (max 200 chars)")
    return clean


# ── Rate limiting ─────────────────────────────────────────────────────────────

def _check_forward_rate_limit(account_id: int) -> None:
    """
    Enforce the per-account daily forward limit.

    Uses the existing cache (Redis) so the counter survives across workers.
    Raises ValueError if the limit is exceeded — caller returns success=False.
    """
    try:
        from src.extensions import cache
        key = f"provider_action:forward:{account_id}:{_today_utc()}"
        count = cache.get(key) or 0
        if count >= _FORWARD_DAILY_LIMIT:
            raise ValueError(
                f"Forward limit reached ({_FORWARD_DAILY_LIMIT}/day). "
                "Rule execution blocked to prevent inbox data exfiltration."
            )
        cache.set(key, count + 1, timeout=86400)  # expires after 24 h
    except ValueError:
        raise
    except Exception as exc:
        # Cache unavailable — fail open with a warning rather than blocking legitimate use
        _log.warning("forward rate-limit check failed (cache unavailable): account=%s error=%s", account_id, exc)


def _today_utc() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


# ── Audit logging ─────────────────────────────────────────────────────────────

def _audit(action: str, account_id: int, provider: str, message_id: str, extra: dict | None = None) -> None:
    """Emit an audit log entry for sensitive provider actions."""
    try:
        from src.security import log_audit
        details = {"provider": provider, "message_id": message_id, **(extra or {})}
        log_audit(
            f"automation.provider_action.{action}",
            resource_type="inbox_message",
            resource_id=message_id,
            account_id=account_id,
            extra=details,
        )
    except Exception as exc:
        # Audit failure must not block the action — but do log it
        _log.error("audit log failed for provider_action.%s account=%s: %s", action, account_id, exc)


# ── Connection helper ─────────────────────────────────────────────────────────

def _get_connection(account_id: int, provider: str):
    """Return the connected InboxConnection for this account/provider, or None."""
    from src.models.core import InboxConnection
    return InboxConnection.query.filter_by(
        account_id=account_id,
        provider=provider,
        status="connected",
    ).first()


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


# ── Gmail actions ─────────────────────────────────────────────────────────────

def _gmail_modify(token: str, message_id: str, add: list = None, remove: list = None) -> bool:
    ops = {}
    if add:
        ops["addLabelIds"] = add
    if remove:
        ops["removeLabelIds"] = remove
    resp = requests.post(
        f"{_GMAIL}/messages/{message_id}/modify",
        headers=_auth(token),
        json=ops,
        timeout=8,
    )
    if resp.status_code >= 300:
        raise ValueError(f"Gmail modify failed: {resp.status_code} {resp.text[:200]}")
    return True


def _gmail_archive(token: str, message_id: str) -> dict:
    _gmail_modify(token, message_id, remove=["INBOX"])
    return {"action": "archive", "provider": "gmail"}


def _gmail_mark_read(token: str, message_id: str) -> dict:
    _gmail_modify(token, message_id, remove=["UNREAD"])
    return {"action": "mark_read", "provider": "gmail"}


def _gmail_star(token: str, message_id: str) -> dict:
    _gmail_modify(token, message_id, add=["STARRED"])
    return {"action": "star", "provider": "gmail"}


def _gmail_trash(token: str, message_id: str) -> dict:
    resp = requests.post(
        f"{_GMAIL}/messages/{message_id}/trash",
        headers=_auth(token),
        json={},
        timeout=8,
    )
    if resp.status_code >= 300:
        raise ValueError(f"Gmail trash failed: {resp.status_code} {resp.text[:200]}")
    return {"action": "trash", "provider": "gmail"}


def _gmail_apply_label(token: str, message_id: str, label_name: str, conn) -> dict:
    from src.inbox.poll import ensure_gmail_label
    label_cache = (conn.metadata_json or {}).get("label_ids", {})
    label_id = label_cache.get(label_name) or ensure_gmail_label(token, label_name)
    _gmail_modify(token, message_id, add=[label_id])
    return {"action": "apply_label", "label": label_name, "provider": "gmail"}


def _gmail_forward(token: str, message_id: str, to_address: str) -> dict:
    """Forward a Gmail message. to_address must already be validated by caller."""
    resp = requests.get(
        f"{_GMAIL}/messages/{message_id}",
        headers={"Authorization": f"Bearer {token}"},
        params={"format": "full"},
        timeout=10,
    )
    if resp.status_code != 200:
        raise ValueError(f"Gmail fetch for forward failed: {resp.status_code}")

    msg_data = resp.json()
    raw_headers = {h["name"].lower(): h["value"] for h in msg_data.get("payload", {}).get("headers", [])}

    # Sanitize header values sourced from external email content — prevents MIME header injection
    original_subject = _sanitize_header(raw_headers.get("subject", "(no subject)"))
    original_from = _sanitize_header(raw_headers.get("from", ""))
    original_date = _sanitize_header(raw_headers.get("date", ""))
    snippet = _sanitize_header(msg_data.get("snippet", ""), max_len=1000)

    fwd_subject = original_subject if original_subject.lower().startswith("fwd:") else f"Fwd: {original_subject}"

    fwd_body = (
        "\n---------- Forwarded message ---------\n"
        f"From: {original_from}\n"
        f"Date: {original_date}\n"
        f"Subject: {original_subject}\n\n"
        f"{snippet}"
    )

    message = MIMEText(fwd_body)
    # to_address already validated — assign as plain string (no display name)
    message["to"] = to_address
    message["subject"] = fwd_subject
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()

    send_resp = requests.post(
        f"{_GMAIL}/messages/send",
        headers=_auth(token),
        json={"raw": raw},
        timeout=10,
    )
    if send_resp.status_code >= 300:
        raise ValueError(f"Gmail forward failed: {send_resp.status_code} {send_resp.text[:200]}")
    return {"action": "forward", "to": to_address, "provider": "gmail"}


def _gmail_move_to_folder(token: str, message_id: str, folder: str, conn) -> dict:
    from src.inbox.poll import ensure_gmail_label
    label_cache = (conn.metadata_json or {}).get("label_ids", {})
    label_id = label_cache.get(folder) or ensure_gmail_label(token, folder)
    _gmail_modify(token, message_id, add=[label_id], remove=["INBOX"])
    return {"action": "move_to_folder", "folder": folder, "provider": "gmail"}


# ── Outlook actions ───────────────────────────────────────────────────────────

def _outlook_archive(token: str, message_id: str) -> dict:
    resp = requests.post(
        f"{_GRAPH}/messages/{message_id}/move",
        headers=_auth(token),
        json={"destinationId": "archive"},
        timeout=8,
    )
    if resp.status_code >= 300:
        raise ValueError(f"Outlook archive failed: {resp.status_code} {resp.text[:200]}")
    return {"action": "archive", "provider": "outlook"}


def _outlook_mark_read(token: str, message_id: str) -> dict:
    resp = requests.patch(
        f"{_GRAPH}/messages/{message_id}",
        headers=_auth(token),
        json={"isRead": True},
        timeout=8,
    )
    if resp.status_code >= 300:
        raise ValueError(f"Outlook mark_read failed: {resp.status_code} {resp.text[:200]}")
    return {"action": "mark_read", "provider": "outlook"}


def _outlook_star(token: str, message_id: str) -> dict:
    resp = requests.patch(
        f"{_GRAPH}/messages/{message_id}",
        headers=_auth(token),
        json={"flag": {"flagStatus": "flagged"}},
        timeout=8,
    )
    if resp.status_code >= 300:
        raise ValueError(f"Outlook star failed: {resp.status_code} {resp.text[:200]}")
    return {"action": "star", "provider": "outlook"}


def _outlook_trash(token: str, message_id: str) -> dict:
    resp = requests.post(
        f"{_GRAPH}/messages/{message_id}/move",
        headers=_auth(token),
        json={"destinationId": "deletedItems"},
        timeout=8,
    )
    if resp.status_code >= 300:
        raise ValueError(f"Outlook trash failed: {resp.status_code} {resp.text[:200]}")
    return {"action": "trash", "provider": "outlook"}


def _outlook_apply_label(token: str, message_id: str, label_name: str) -> dict:
    resp = requests.patch(
        f"{_GRAPH}/messages/{message_id}",
        headers=_auth(token),
        json={"categories": [label_name]},
        timeout=8,
    )
    if resp.status_code >= 300:
        raise ValueError(f"Outlook apply_label failed: {resp.status_code} {resp.text[:200]}")
    return {"action": "apply_label", "label": label_name, "provider": "outlook"}


def _outlook_forward(token: str, message_id: str, to_address: str) -> dict:
    """Forward an Outlook message. to_address must already be validated by caller."""
    resp = requests.post(
        f"{_GRAPH}/messages/{message_id}/forward",
        headers=_auth(token),
        json={"toRecipients": [{"emailAddress": {"address": to_address}}]},
        timeout=10,
    )
    if resp.status_code >= 300:
        raise ValueError(f"Outlook forward failed: {resp.status_code} {resp.text[:200]}")
    return {"action": "forward", "to": to_address, "provider": "outlook"}


def _outlook_move_to_folder(token: str, message_id: str, folder: str) -> dict:
    resp = requests.post(
        f"{_GRAPH}/messages/{message_id}/move",
        headers=_auth(token),
        json={"destinationId": folder},
        timeout=8,
    )
    if resp.status_code >= 300:
        raise ValueError(f"Outlook move_to_folder failed: {resp.status_code} {resp.text[:200]}")
    return {"action": "move_to_folder", "folder": folder, "provider": "outlook"}


# ── Main dispatcher ───────────────────────────────────────────────────────────

def execute_provider_action(
    context: Dict[str, Any],
    config: Dict[str, Any],
    span: trace.Span,
) -> Dict[str, Any]:
    """
    Execute a provider action directly in Gmail or Outlook.

    Security contract:
      - action is checked against an explicit whitelist before dispatch
      - message_id is validated for path traversal before URL interpolation
      - email addresses are validated and CRLF-stripped before MIME header use
      - label/folder names are stripped of control characters
      - forward is rate-limited per account per day
      - forward and trash emit audit log entries
      - access token is resolved from InboxConnection at runtime, never in config
    """
    action = (config.get("action") or "").strip()
    span.set_attribute("provider_action.action", action)

    # Whitelist check — reject anything not in the allowed set
    if action not in _ALLOWED_ACTIONS:
        return {"success": False, "error": f"Unknown provider action: {action!r}", "result": None}

    email = context.get("email") or {}
    provider = (email.get("provider") or "").strip()
    raw_message_id = email.get("provider_message_id") or ""
    account_id = context.get("account_id")

    span.set_attribute("provider_action.provider", provider)

    if provider not in ("gmail", "outlook"):
        return {"success": False, "error": f"Unsupported provider: {provider!r}", "result": None}
    if not account_id:
        return {"success": False, "error": "No account_id in context", "result": None}

    # Validate message_id before URL interpolation
    try:
        message_id = _validate_message_id(raw_message_id)
    except ValueError as exc:
        return {"success": False, "error": str(exc), "result": None}

    conn = _get_connection(int(account_id), provider)
    if not conn or not conn.access_token:
        return {"success": False, "error": f"No connected {provider} inbox for account {account_id}", "result": None}

    token = conn.access_token

    # Pre-flight checks for sensitive actions
    if action == "forward":
        try:
            _check_forward_rate_limit(int(account_id))
        except ValueError as exc:
            _log.warning("forward blocked by rate limit: account=%s", account_id)
            return {"success": False, "error": str(exc), "result": None}

    try:
        if provider == "gmail":
            result = _dispatch_gmail(token, message_id, action, config, conn)
        else:
            result = _dispatch_outlook(token, message_id, action, config)

        # Audit sensitive actions after successful execution
        if action in _AUDIT_ACTIONS:
            extra = {}
            if action == "forward":
                extra["to"] = config.get("to", "")
            _audit(action, int(account_id), provider, message_id, extra)

        span.set_attribute("provider_action.success", True)
        return {"success": True, "result": result, "error": None}

    except Exception as exc:
        _log.warning(
            "provider_action failed: action=%s provider=%s account=%s error=%s",
            action, provider, account_id, exc,
        )
        span.record_exception(exc)
        return {"success": False, "error": str(exc), "result": None}


def _dispatch_gmail(token: str, message_id: str, action: str, config: dict, conn) -> dict:
    if action == "archive":
        return _gmail_archive(token, message_id)
    elif action == "mark_read":
        return _gmail_mark_read(token, message_id)
    elif action == "star":
        return _gmail_star(token, message_id)
    elif action == "trash":
        return _gmail_trash(token, message_id)
    elif action == "forward":
        to = _validate_email(config.get("to") or "")
        return _gmail_forward(token, message_id, to)
    elif action == "apply_label":
        label = _sanitize_name(config.get("label") or "", "label")
        return _gmail_apply_label(token, message_id, label, conn)
    elif action == "move_to_folder":
        folder = _sanitize_name(config.get("folder") or "", "folder")
        return _gmail_move_to_folder(token, message_id, folder, conn)
    else:
        raise ValueError(f"Unknown provider action: {action!r}")


def _dispatch_outlook(token: str, message_id: str, action: str, config: dict) -> dict:
    if action == "archive":
        return _outlook_archive(token, message_id)
    elif action == "mark_read":
        return _outlook_mark_read(token, message_id)
    elif action == "star":
        return _outlook_star(token, message_id)
    elif action == "trash":
        return _outlook_trash(token, message_id)
    elif action == "forward":
        to = _validate_email(config.get("to") or "")
        return _outlook_forward(token, message_id, to)
    elif action == "apply_label":
        label = _sanitize_name(config.get("label") or "", "label")
        return _outlook_apply_label(token, message_id, label)
    elif action == "move_to_folder":
        folder = _sanitize_name(config.get("folder") or "", "folder")
        return _outlook_move_to_folder(token, message_id, folder)
    else:
        raise ValueError(f"Unknown provider action: {action!r}")
