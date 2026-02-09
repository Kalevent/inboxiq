import os
import hashlib
import hmac
import time
import json
from collections import defaultdict
from functools import lru_cache
from flask import jsonify, request, g, current_app
from flask_jwt_extended import get_jwt_identity, jwt_required
from celery import Celery
import requests

from src.api.v1 import v1
from src.inboxiq_logic import normalize_email_payload
from src.models import IntakeToken, InboxConnection, User
from src.extensions import db, limiter
from src.sanitize import sanitize_html
from datetime import datetime, timezone
from src.api.v1.inboxiq import _get_account_id
from src.api.v1.access_control import account_allows_api


_RATE_LIMIT_WINDOW = 60  # seconds
_RATE_LIMIT_MAX = 120  # requests per token per window
_RATE_LIMITS = defaultdict(list)

@lru_cache(maxsize=1)
def _celery_client() -> Celery:
    broker_url = current_app.config.get("CELERY_BROKER_URL")
    backend_url = current_app.config.get("CELERY_RESULT_BACKEND")
    return Celery("inboxiq", broker=broker_url, backend=backend_url)


def _require_intake_token():
    header = request.headers.get("X-Intake-Token") or request.headers.get("X-InboxIQ-Token")
    signature = request.headers.get("X-Signature")
    timestamp = request.headers.get("X-Timestamp")

    if not header or not signature or not timestamp:
        return jsonify({"error": "unauthorized", "message": "missing token/signature/timestamp"}), 401

    header_hash = hashlib.sha256(header.encode("utf-8")).hexdigest()
    token_row = IntakeToken.query.filter_by(token_hash=header_hash, revoked_at=None).first()
    if not token_row:
        return jsonify({"error": "unauthorized"}), 401

    if token_row.expires_at and token_row.expires_at < datetime.now(timezone.utc):
        return jsonify({"error": "unauthorized", "message": "token expired"}), 401

    if token_row.allowed_ips:
        remote_ip = request.remote_addr
        if not remote_ip or remote_ip not in token_row.allowed_ips:
            return jsonify({"error": "forbidden", "message": "ip_not_allowed"}), 403

    try:
        ts_val = int(timestamp)
    except ValueError:
        return jsonify({"error": "unauthorized", "message": "invalid timestamp"}), 401
    now = int(time.time())
    if abs(now - ts_val) > 300:
        return jsonify({"error": "unauthorized", "message": "stale timestamp"}), 401

    body_bytes = request.get_data() or b""
    expected = hmac.new(header.encode("utf-8"), msg=(str(ts_val).encode("utf-8") + b"." + body_bytes), digestmod=hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature.lower()):
        return jsonify({"error": "unauthorized", "message": "invalid signature"}), 401

    # Rate limit per token
    window_start = now - _RATE_LIMIT_WINDOW
    entries = _RATE_LIMITS[header_hash]
    entries[:] = [t for t in entries if t >= window_start]
    if len(entries) >= _RATE_LIMIT_MAX:
        return jsonify({"error": "rate_limited"}), 429
    entries.append(now)

    g.intake_account_id = token_row.account_id

    # Enforce plan: API/webhook allowed only for eligible accounts.
    if not account_allows_api(token_row.account_id):
        return (
            jsonify(
                {
                    "error": "plan_required",
                    "message": "API/webhooks require Business plan or active trial. Contact sales to upgrade.",
                }
            ),
            403,
        )
    return None


@v1.route("/intake", methods=["POST"])
@jwt_required(optional=True)
def intake():
    """
    General webhook/API intake: forms, chat, CRM events, internal tools.
    Auth: X-Intake-Token header (if configured) or logged-in JWT.
    """
    token_err = _require_intake_token()
    if token_err:
        return token_err

    user_id = get_jwt_identity()
    payload = request.get_json(silent=True) or {}

    # Sanitize incoming webhook data to prevent XSS from external providers
    raw_subject = payload.get("subject") or payload.get("title") or "Inbound request"
    raw_body = payload.get("body") or payload.get("message") or ""
    raw_summary = payload.get("summary") or ""

    subject = sanitize_html(str(raw_subject).strip())[:500]
    body = sanitize_html(str(raw_body).strip())
    summary = sanitize_html(str(raw_summary).strip())

    if not body and not summary:
        return jsonify({"error": "validation_error", "message": "body or message required"}), 400

    from_email = (payload.get("from_email") or payload.get("sender") or "intake@webhook.local").strip()
    provider = (payload.get("source") or payload.get("provider") or "webhook").strip()
    thread_url = payload.get("provider_thread_url") or payload.get("thread_url")
    account_id = payload.get("account_id") or getattr(g, "intake_account_id", None) or _get_account_id(user_id)

    # Sanitize metadata if present (can contain data from external APIs like Sage, QuickBooks)
    sanitized_context = payload.get("context")
    if sanitized_context and isinstance(sanitized_context, dict):
        for key, value in list(sanitized_context.items()):
            if isinstance(value, str):
                sanitized_context[key] = sanitize_html(value.strip())

    triage_input = {
        "subject": subject,
        "from_email": from_email,
        "body": body or summary,
        "provider": provider,
        "source": payload.get("source") or provider,
        "channel": payload.get("channel") or payload.get("source") or provider,
        "use_case": payload.get("use_case"),
        "provider_thread_url": thread_url,
        "message_id": payload.get("message_id"),
        "received_at": payload.get("received_at"),
        "context": sanitized_context,
    }

    try:
        normalized = normalize_email_payload(triage_input)
    except Exception as exc:
        current_app.logger.warning("intake validation failed: %s", exc)
        return jsonify({"error": "validation_error", "message": str(exc)}), 400

    try:
        task = _celery_client().send_task(
            "inboxiq.process_incoming_email",
            args=[{"email": normalized, "user_id": user_id, "account_id": account_id}],
            queue="inbox",
        )
    except Exception as exc:
        current_app.logger.exception("failed to enqueue intake payload", exc_info=exc)
        return jsonify({"error": "enqueue_failed", "message": str(exc)}), 502

    return jsonify({"success": True, "status": "queued", "task_id": task.id}), 202


def _ensure_forms_connection(account_id: int | None, user_id: int | None, form_name: str | None = None) -> None:
    if not account_id and not user_id:
        return
    query = InboxConnection.query
    if account_id:
        query = query.filter_by(account_id=account_id)
    else:
        query = query.filter_by(user_id=user_id)
    conn = query.filter_by(provider="forms").order_by(InboxConnection.updated_at.desc()).first()
    meta = {}
    if conn:
        meta = conn.metadata_json or {}
        meta.setdefault("channel", "forms")
        if form_name:
            forms = meta.get("forms") or []
            if form_name not in forms:
                forms.append(form_name)
            meta["forms"] = forms
        conn.metadata_json = meta
        conn.status = "connected"
        db.session.commit()
        return
    meta = {"channel": "forms"}
    if form_name:
        meta["forms"] = [form_name]
    conn = InboxConnection(
        user_id=user_id,
        account_id=account_id,
        provider="forms",
        status="connected",
        metadata_json=meta,
    )
    db.session.add(conn)
    db.session.commit()


@v1.route("/inboxiq/forms/submit", methods=["POST"])
@jwt_required()
@limiter.limit("30 per minute")  # Rate limit: 30 submissions per minute per user
def submit_form():
    """
    In-app form intake: accepts JSON from authenticated users and routes
    through the same intake/triage pipeline as external forms.
    """
    user_id = get_jwt_identity()
    user = User.query.get(user_id) if user_id else None
    if not user:
        return jsonify({"error": "not_authenticated"}), 401

    payload = request.get_json(silent=True) or {}
    form_name = (payload.get("form_name") or payload.get("form") or payload.get("source") or "form").strip()
    raw_message = payload.get("message") or payload.get("body") or payload.get("summary") or ""
    raw_context = payload.get("context") or ""
    message = sanitize_html(str(raw_message)).strip()
    context = sanitize_html(str(raw_context)).strip()
    if not message:
        return jsonify({"error": "validation_error", "message": "message/body required"}), 400

    raw_subject = payload.get("subject") or f"Form: {form_name}"
    subject = sanitize_html(str(raw_subject)).strip()[:500]
    body = message if not context else f"{message}\n\nContext: {context}"
    account_id = _get_account_id(user_id)

    triage_input = {
        "subject": subject,
        "from_email": user.email or "forms@inboxiq.local",
        "body": body,
        "provider": "forms",
        "source": "forms",
        "channel": "forms",
        "use_case": payload.get("use_case") or form_name,
        "context": context or payload.get("context"),
        "provider_thread_url": payload.get("provider_thread_url"),
        "message_id": payload.get("message_id"),
        "received_at": payload.get("received_at"),
    }

    try:
        normalized = normalize_email_payload(triage_input)
    except Exception as exc:
        current_app.logger.warning("forms intake validation failed: %s", exc)
        return jsonify({"error": "validation_error", "message": str(exc)}), 400

    try:
        task = _celery_client().send_task(
            "inboxiq.process_incoming_email",
            args=[{"email": normalized, "user_id": user_id, "account_id": account_id}],
            queue="inbox",
        )
    except Exception as exc:
        current_app.logger.exception("failed to enqueue form payload", exc_info=exc)
        return jsonify({"error": "enqueue_failed", "message": str(exc)}), 502

    _ensure_forms_connection(account_id, user_id, form_name=form_name)
    return jsonify({"success": True, "status": "queued", "task_id": task.id}), 202


# Shim for sources that cannot set JSON + HMAC headers directly.
_SHIM_INTAKE_TOKEN = os.getenv("INTAKE_TOKEN")
_SHIM_TARGET_URL = os.getenv("INTAKE_URL")  # Optional override; defaults to local /api/v1/intake


@v1.route("/intake/shim", methods=["POST"])
def intake_shim():
    """
    Compatibility adapter: accept simple form or JSON, sign with IntakeToken, forward to /intake.
    If your source can already send JSON with X-Intake-Token/X-Timestamp/X-Signature, call /intake directly.
    """
    if not _SHIM_INTAKE_TOKEN:
        return jsonify({"error": "config_error", "message": "INTAKE_TOKEN not configured for shim"}), 500

    incoming = request.get_json(silent=True) or request.form.to_dict(flat=True)
    payload = {
        "subject": incoming.get("subject") or incoming.get("title") or "Inbound request",
        "body": incoming.get("body") or incoming.get("message") or incoming.get("summary") or "",
        "source": incoming.get("source") or "shim",
        "provider_thread_url": incoming.get("provider_thread_url"),
        "message_id": incoming.get("message_id"),
        "received_at": incoming.get("received_at"),
    }

    if not payload["body"]:
        return jsonify({"error": "validation_error", "message": "body/message required"}), 400

    body_str = json.dumps(payload, separators=(",", ":"))
    ts_val = str(int(time.time()))
    signature = hmac.new(
        _SHIM_INTAKE_TOKEN.encode("utf-8"),
        msg=f"{ts_val}.{body_str}".encode("utf-8"),
        digestmod=hashlib.sha256,
    ).hexdigest()

    target_url = _SHIM_TARGET_URL or request.url_root.rstrip("/") + "/api/v1/intake"
    headers = {
        "Content-Type": "application/json",
        "X-Intake-Token": _SHIM_INTAKE_TOKEN,
        "X-Timestamp": ts_val,
        "X-Signature": signature,
    }

    try:
        resp = requests.post(target_url, headers=headers, data=body_str, timeout=5)
        # Try to mirror upstream response for clarity
        resp_json = {}
        try:
            resp_json = resp.json()
        except Exception:
            resp_json = {"error": "invalid_upstream_response", "status": resp.status_code}
        return jsonify(resp_json), resp.status_code
    except requests.RequestException as exc:
        return jsonify({"error": "forward_failed", "message": str(exc)}), 502


# Rate limiting for chat endpoint (per IP)
_CHAT_RATE_LIMIT_WINDOW = 60  # seconds
_CHAT_RATE_LIMIT_MAX = 10  # messages per IP per window
_CHAT_RATE_LIMITS = defaultdict(list)


@v1.route("/chat/submit", methods=["POST"])
def chat_submit():
    """
    Public endpoint for InboxIQ native chat widget submissions.
    Security: Rate limited, input sanitized, size restricted.
    """
    # Rate limit by IP address
    remote_ip = request.remote_addr or "unknown"
    now = int(time.time())
    window_start = now - _CHAT_RATE_LIMIT_WINDOW

    entries = _CHAT_RATE_LIMITS[remote_ip]
    entries[:] = [t for t in entries if t >= window_start]

    if len(entries) >= _CHAT_RATE_LIMIT_MAX:
        return jsonify({"error": "rate_limited", "message": "Too many messages. Please wait a moment."}), 429

    entries.append(now)

    # Parse and validate payload
    payload = request.get_json(silent=True) or {}
    context = payload.get("context") or {}

    # Extract and sanitize inputs
    account_id = str(context.get("account_id", "2")).strip()[:20]  # Limit length
    name = sanitize_html(str(context.get("name", "")).strip())[:100]  # Max 100 chars
    email = str(context.get("email", "")).strip().lower()[:200]  # Max 200 chars
    company = sanitize_html(str(context.get("company", "")).strip())[:100]  # Max 100 chars
    message = sanitize_html(str(payload.get("body", "")).strip())[:5000]  # Max 5000 chars

    # Validate required fields
    if not message:
        return jsonify({"error": "validation_error", "message": "Message is required"}), 400

    if len(message) < 2:
        return jsonify({"error": "validation_error", "message": "Message too short"}), 400

    # Validate email format if provided
    if email and ("@" not in email or "." not in email.split("@")[-1]):
        return jsonify({"error": "validation_error", "message": "Invalid email format"}), 400

    # Validate account_id is numeric
    try:
        account_id_int = int(account_id)
        if account_id_int < 1:
            return jsonify({"error": "validation_error", "message": "Invalid account"}), 400
    except (ValueError, TypeError):
        return jsonify({"error": "validation_error", "message": "Invalid account"}), 400

    # Build subject from visitor info
    if name and email:
        subject = f"Chat from {name} ({email})"
    elif email:
        subject = f"Chat from {email}"
    elif name:
        subject = f"Chat from {name}"
    else:
        subject = "Chat from visitor"

    # Sanitize subject
    subject = sanitize_html(subject)[:500]

    # Create from_email (sanitized)
    if email:
        from_email = email
    else:
        # Use IP-based identifier if no email provided
        from_email = f"chat-{hashlib.md5(remote_ip.encode()).hexdigest()[:8]}@inboxiq.local"

    # Build triage input with sanitized data
    triage_input = {
        "subject": subject,
        "from_email": from_email,
        "body": message,  # Already sanitized above
        "provider": "inboxiq",
        "source": "chat",
        "channel": "chat",
        "use_case": "support",
        "provider_thread_url": None,
        "message_id": payload.get("message_id", f"chat-{now}-{hashlib.md5(message.encode()).hexdigest()[:8]}"),
        "received_at": None,
        "context": {
            "name": name,  # Already sanitized
            "email": email,
            "company": company,  # Already sanitized
            "capture_lead": context.get("capture_lead", True),
            "remote_ip": remote_ip,  # Store for audit
        },
    }

    # Normalize payload
    try:
        normalized = normalize_email_payload(triage_input)
    except Exception as exc:
        current_app.logger.warning("chat intake validation failed: %s", exc)
        return jsonify({"error": "validation_error", "message": "Invalid message format"}), 400

    # Queue to Celery for processing
    try:
        task = _celery_client().send_task(
            "inboxiq.process_incoming_email",
            args=[{"email": normalized, "user_id": None, "account_id": account_id_int}],
            queue="inbox",
        )

        # Ensure chat connection exists (non-blocking)
        try:
            _ensure_chat_connection(account_id_int)
        except Exception:
            pass  # Don't fail submission if connection update fails

        current_app.logger.info(
            f"Chat message queued: account={account_id_int}, task={task.id}, ip={remote_ip}"
        )

    except Exception as exc:
        current_app.logger.exception("failed to enqueue chat message", exc_info=exc)
        return jsonify({"error": "server_error", "message": "Unable to send message"}), 500

    return jsonify({"success": True, "status": "queued", "task_id": task.id}), 202


def _ensure_chat_connection(account_id: int) -> None:
    """Ensure a chat connection exists for the account."""
    if not account_id:
        return

    conn = InboxConnection.query.filter_by(
        account_id=account_id,
        provider="chat"
    ).first()

    if conn:
        # Update existing connection
        conn.status = "connected"
        metadata = conn.metadata_json or {}
        metadata["last_message_at"] = datetime.now(timezone.utc).isoformat()
        metadata.setdefault("channel", "chat")
        metadata.setdefault("platform", "inboxiq")
        conn.metadata_json = metadata
        db.session.commit()
        return

    # Create new chat connection
    conn = InboxConnection(
        user_id=None,
        account_id=account_id,
        provider="chat",
        status="connected",
        metadata_json={
            "channel": "chat",
            "platform": "inboxiq",
            "last_message_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    db.session.add(conn)
    db.session.commit()
