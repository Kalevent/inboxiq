import os
import hashlib
import hmac
import time
import json
from collections import defaultdict
from flask import jsonify, request, g, current_app
from flask_jwt_extended import get_jwt_identity, jwt_required
import requests

from src.api.v1 import v1
from src.extensions import db
from src.inboxiq_logic import triage_email, compute_due_at
from src.models import Feedback, Ticket, IntakeToken
from datetime import datetime, timezone
from src.api.v1.inboxiq import _get_account_id
from src.api.v1.access_control import account_allows_api


_RATE_LIMIT_WINDOW = 60  # seconds
_RATE_LIMIT_MAX = 120  # requests per token per window
_RATE_LIMITS = defaultdict(list)


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

    subject = (payload.get("subject") or payload.get("title") or "Inbound request")[:500]
    body = (payload.get("body") or payload.get("message") or "").strip()
    if not body and not payload.get("summary"):
        return jsonify({"error": "validation_error", "message": "body or message required"}), 400

    from_email = (payload.get("from_email") or payload.get("sender") or "intake@webhook.local").strip()
    provider = (payload.get("source") or payload.get("provider") or "webhook").strip()
    thread_url = payload.get("provider_thread_url") or payload.get("thread_url")
    account_id = payload.get("account_id") or getattr(g, "intake_account_id", None) or _get_account_id(user_id)

    triage_input = {
        "subject": subject,
        "from_email": from_email,
        "body": body or payload.get("summary", ""),
        "provider": provider,
        "source": payload.get("source") or provider,
        "provider_thread_url": thread_url,
        "message_id": payload.get("message_id"),
        "received_at": payload.get("received_at"),
        "context": payload.get("context"),
    }

    try:
        decision = triage_email(triage_input, account_id=account_id)
    except Exception as exc:
        current_app.logger.warning("triage failed in intake: %s", exc)
        return jsonify({"error": "triage_failed", "message": str(exc)}), 503
    action_required = decision.action_required
    action_required_str = "true" if action_required is True else ("false" if action_required is False else "optional")

    ticket_record = None
    feedback_record = None

    if action_required is True:
        ticket_record = Ticket(
            account_id=account_id,
            user_id=user_id,
            subject=subject,
            from_email=from_email,
            body_preview=body[:500],
            category=decision.category,
            priority=decision.priority,
            sentiment=decision.sentiment,
            entities=decision.entities,
            status="new",
            message_id=triage_input.get("message_id") or None,
            provider=provider,
            provider_thread_url=thread_url,
            decision=decision.to_dict(),
            team=decision.team,
            assigned_to=decision.assigned_to,
            owner=decision.owner,
            due_at=compute_due_at(decision.priority),
        )
        db.session.add(ticket_record)
    else:
        feedback_record = Feedback(
            account_id=account_id,
            user_id=user_id,
            message=body or subject,
            context=payload.get("context"),
            urgency=3,
            source=provider or "intake",
            status="auto_handled" if action_required is False else "optional",
            action_required=action_required_str,
            metadata_json=decision.entities or {},
            ai_decision_json=decision.to_dict(),
        )
        db.session.add(feedback_record)

    db.session.commit()

    if feedback_record and ticket_record:
        feedback_record.ticket_id = ticket_record.id
        db.session.commit()

    return jsonify(
        {
            "success": True,
            "decision": decision.to_dict(),
            "ticket": ticket_record.to_dict() if ticket_record else None,
            "feedback": feedback_record.to_dict() if feedback_record else None,
        }
    )


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
