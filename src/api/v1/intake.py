import hmac
import os
import json
import time
import hashlib
from collections import defaultdict
from functools import lru_cache
from flask import jsonify, request, g, current_app
from flask_jwt_extended import get_jwt_identity, jwt_required
from celery import Celery
import requests

from src.api.v1 import v1
from src.funnel.stages import VISITS, DISCOVERY
from src.inbox.logic import normalize_email_payload
from src.models.core import Account, InboxConnection, User
from src.models.leads import Lead, LeadFunnelStage
from src.extensions import db, limiter
from src.sanitize import sanitize_html
from datetime import datetime, timezone
from src.api.v1.inboxiq import _get_account_id
from src.api.v1.access_control import account_allows_api
from src.api.v1.app_auth import _require_registered_app, _NO_BASIC_AUTH
from src.models.developer import RegisteredApp, AppProductAccess


@lru_cache(maxsize=1)
def _celery_client() -> Celery:
    broker_url = current_app.config.get("CELERY_BROKER_URL")
    backend_url = current_app.config.get("CELERY_RESULT_BACKEND")
    return Celery("inboxiq", broker=broker_url, backend=backend_url)


def _require_intake_token():
    """Authenticate via RegisteredApp Basic Auth (client_id:client_secret)."""
    result = _require_registered_app("intake:write")
    if result is _NO_BASIC_AUTH:
        return jsonify({"error": "unauthorized", "message": "credentials required — use HTTP Basic Auth with your client_id and client_secret"}), 401
    return result  # None = success, tuple = error response


def _intake_rate_key():
    """Rate limit per registered app (client_id), falling back to IP."""
    auth = request.authorization
    return auth.username if (auth and auth.username) else (request.remote_addr or "unknown")


@v1.route("/intake", methods=["POST"])
@limiter.limit("60 per minute", key_func=_intake_rate_key)
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

    registered_app_id = getattr(g, "intake_app", None) and g.intake_app.id

    try:
        task = _celery_client().send_task(
            "inboxiq.process_incoming_email",
            args=[{"email": normalized, "user_id": user_id, "account_id": account_id,
                   "registered_app_id": registered_app_id}],
            queue="inbox",
        )
    except Exception as exc:
        current_app.logger.exception("failed to enqueue intake payload", exc_info=exc)
        return jsonify({"error": "enqueue_failed", "message": str(exc)}), 502

    # Track raw incoming signal volume for ROI reporting (best-effort)
    if account_id:
        try:
            from src.billing.quota import increment_signals
            increment_signals(int(account_id))
        except Exception:
            pass

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


@v1.route("/intake/shim", methods=["POST"])  # nosemgrep: inboxiq.auth.unprotected-write-endpoint
def intake_shim():
    """
    Compatibility adapter: accept simple form or JSON and forward to /intake.
    If your source can already send JSON with Basic Auth, call /intake directly.
    """
    if not _SHIM_INTAKE_TOKEN or not _SHIM_TARGET_URL:
        return jsonify({"error": "config_error", "message": "INTAKE_TOKEN and INTAKE_URL must be configured"}), 500

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

    target_url = _SHIM_TARGET_URL
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


@v1.route("/chat/submit", methods=["POST"])  # nosemgrep: inboxiq.auth.unprotected-write-endpoint
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
    branch = str(context.get("branch", "demo")).strip()[:20]  # Max 20 chars
    branch = branch if branch in ("demo", "talk") else "demo"
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

    # ── Registered app origin check ────────────────────────────────────────
    req_client_id = str(context.get("client_id", "") or "").strip()[:64]
    reg_app = None
    if req_client_id:
        reg_app = RegisteredApp.query.filter_by(
            client_id=req_client_id, status="active"
        ).first()
        if not reg_app:
            return jsonify({"error": "forbidden", "message": "invalid client_id"}), 403
        # Require approved chat product access
        chat_access = AppProductAccess.query.filter_by(
            app_id=reg_app.id, product_slug="chat", status="approved"
        ).first()
        if not chat_access:
            return jsonify({"error": "forbidden", "message": "chat access not approved"}), 403
        # Enforce allowed_origins when the list is non-empty
        if reg_app.allowed_origins:
            request_origin = (request.headers.get("Origin") or "").rstrip("/")
            if request_origin not in [o.rstrip("/") for o in reg_app.allowed_origins]:
                return jsonify({"error": "forbidden", "message": "origin_not_allowed"}), 403
        # Use account_id from the app record (more trustworthy than caller-supplied value)
        account_id_int = reg_app.account_id

    # Feature gate + usage counter
    try:
        from src.features import feature_enabled
        from src.billing.quota import check_and_increment, increment_signals, FeatureDisabled
        if not feature_enabled("chat", account_id_int):
            return jsonify({"error": "feature_disabled", "message": "Chat widget is not available on your current plan."}), 403
        check_and_increment("chat_conversations", account_id_int)
        increment_signals(account_id_int)
    except FeatureDisabled as _fd:
        return jsonify({"error": "feature_disabled", "message": str(_fd)}), 403
    except Exception as _qe:
        import logging as _log
        _log.getLogger(__name__).warning("Quota check failed for chat account=%d: %s", account_id_int, _qe)

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

    # Queue to Celery for processing (best-effort — never fail the chat if the queue is down)
    chat_app_id = reg_app.id if reg_app else None
    task_id = None
    try:
        task = _celery_client().send_task(
            "inboxiq.process_incoming_email",
            args=[{"email": normalized, "user_id": None, "account_id": account_id_int,
                   "registered_app_id": chat_app_id}],
            queue="inbox",
        )
        task_id = task.id

        # Ensure chat connection exists (non-blocking)
        try:
            _ensure_chat_connection(account_id_int)
        except Exception:
            pass

        current_app.logger.info(
            f"Chat message queued: account={account_id_int}, task={task_id}, ip={remote_ip}"
        )

    except Exception as exc:
        # Log the queue failure but continue — visitor still gets the AI reply
        current_app.logger.warning("Chat Celery enqueue failed (non-fatal): %s", exc)

    # Capture lead into funnel if email provided and capture_lead is set
    if email and context.get("capture_lead", True):
        try:
            existing = Lead.query.filter_by(email=email, account_id=account_id_int).first()
            if not existing:
                now_dt = datetime.now(timezone.utc)
                lead = Lead(
                    account_id=account_id_int,
                    name=name or email.split("@")[0],
                    email=email,
                    company_name=company or None,
                    source="chat",
                    status="New Lead",
                    current_funnel_stage=DISCOVERY,
                    stage_entered_at=now_dt,
                    last_engagement_at=now_dt,
                    engagement_count=1,
                    created_at=now_dt,
                    updated_at=now_dt,
                )
                db.session.add(lead)
                db.session.flush()  # get lead.id before commit
                funnel_stage = LeadFunnelStage(
                    lead_id=lead.id,
                    stage=DISCOVERY,
                    sub_stage="chat_widget",
                    metadata_json={"page_url": context.get("page_url"), "message_preview": message[:100]},
                )
                db.session.add(funnel_stage)
                db.session.commit()
                current_app.logger.info("Chat lead created: lead_id=%s email=%s account=%s", lead.id, email, account_id_int)
            else:
                # Return visitor — update engagement and promote stage if still at visits
                now_dt = datetime.now(timezone.utc)
                existing.last_engagement_at = now_dt
                existing.engagement_count = (existing.engagement_count or 0) + 1
                if existing.current_funnel_stage == VISITS:
                    existing.current_funnel_stage = DISCOVERY
                    existing.stage_entered_at = now_dt
                    funnel_stage = LeadFunnelStage(
                        lead_id=existing.id,
                        stage=DISCOVERY,
                        sub_stage="chat_widget",
                        metadata_json={"page_url": context.get("page_url"), "message_preview": message[:100]},
                    )
                    db.session.add(funnel_stage)
                    current_app.logger.info("Chat promoted lead to discovery: lead_id=%s email=%s", existing.id, email)
                db.session.commit()
        except Exception as exc:
            db.session.rollback()
            current_app.logger.warning("Chat lead capture failed (non-fatal): %s", exc)

    # Extract and sanitize conversation history (cap at 10 turns)
    raw_history = context.get("history") or []
    chat_history = []
    for entry in raw_history[-10:]:
        role = str(entry.get("role", ""))
        content = sanitize_html(str(entry.get("text", entry.get("content", ""))))[:800]
        if role in ("user", "assistant", "bot") and content:
            normalized_role = "assistant" if role == "bot" else role
            chat_history.append({"role": normalized_role, "content": content})

    # Generate AI reply regardless of whether Celery succeeded
    reply = _generate_chat_reply(account_id_int, message, name, company, history=chat_history, branch=branch)
    if not reply:
        reply = "Thanks for reaching out! A member of our team will get back to you shortly."

    return jsonify({"success": True, "status": "queued" if task_id else "ai_only", "task_id": task_id, "reply": reply}), 200


def _generate_chat_reply(account_id_int: int, message: str, name: str, company: str, history: list | None = None, branch: str = "demo") -> str | None:
    """Generate a contextual AI reply for the chat widget. Returns None if AI is unavailable."""
    import json as _json
    from src.dspy.config import _configure_dspy
    from src.dspy.signatures import build_chat_widget_reply

    try:
        account = Account.query.get(account_id_int)
        account_name = (account.display_name or account.name or "InboxIQ") if account else "InboxIQ"
    except Exception:
        account_name = "InboxIQ"

    try:
        _, _, dspy = _configure_dspy()
        module = build_chat_widget_reply(dspy)
        result = module(
            account_name=account_name,
            visitor_name=name or "",
            branch=branch,
            conversation_history=_json.dumps(history or []),
            message=message,
        )
        reply = sanitize_html((result.reply or "").strip())
        return reply or None
    except Exception as exc:
        current_app.logger.debug("Chat AI reply failed: %s", exc)
        return None


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
