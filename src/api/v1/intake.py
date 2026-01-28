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
from src.models import IntakeToken
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
        "channel": payload.get("channel") or payload.get("source") or provider,
        "use_case": payload.get("use_case"),
        "provider_thread_url": thread_url,
        "message_id": payload.get("message_id"),
        "received_at": payload.get("received_at"),
        "context": payload.get("context"),
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
