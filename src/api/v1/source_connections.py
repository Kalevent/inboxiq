from functools import lru_cache
from flask import jsonify, request, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
from celery import Celery

from src.api.v1 import v1
from src.extensions import db
from src.models import InboxConnection, User
from src.inbox.logic import normalize_email_payload

ALLOWED_CHANNELS = {
    "email",
    "voice",
    "social",
    "forms",
    "chat",
    "crm",
    "api",
    "webhook",
}


def _resolve_account_id(user_id: int | None) -> int | None:
    if not user_id:
        return None
    user = User.query.get(user_id)
    acct = user.account if user else None
    return getattr(acct, "id", None)


@lru_cache(maxsize=1)
def _celery_client() -> Celery:
    broker_url = current_app.config.get("CELERY_BROKER_URL")
    backend_url = current_app.config.get("CELERY_RESULT_BACKEND")
    return Celery("inboxiq", broker=broker_url, backend=backend_url)


@v1.route("/inboxiq/source-connections", methods=["GET"])
@jwt_required()
def list_source_connections():
    user_id = get_jwt_identity()
    account_id = _resolve_account_id(user_id)

    query = InboxConnection.query
    if account_id:
        query = query.filter(InboxConnection.account_id == account_id)
    else:
        query = query.filter(InboxConnection.user_id == user_id)

    connections = query.order_by(InboxConnection.updated_at.desc()).all()
    return jsonify({"connections": [c.to_dict() for c in connections]})


@v1.route("/inboxiq/source-connections", methods=["POST"])
@jwt_required()
def upsert_source_connection():
    user_id = get_jwt_identity()
    account_id = _resolve_account_id(user_id)
    payload = request.get_json(silent=True) or {}
    channel = (payload.get("channel") or payload.get("provider") or "").strip().lower()
    provider = (payload.get("provider") or channel or "api").strip().lower()
    status = (payload.get("status") or "connected").strip().lower()
    metadata = payload.get("metadata") or {}
    metadata.setdefault("channel", channel)

    if not channel:
        return jsonify({"error": "validation_error", "message": "channel is required"}), 400
    if channel not in ALLOWED_CHANNELS:
        return jsonify({"error": "validation_error", "message": f"unsupported channel: {channel}"}), 400

    existing = (
        InboxConnection.query.filter_by(account_id=account_id, provider=provider)
        .order_by(InboxConnection.updated_at.desc())
        .first()
    )
    if existing:
        existing.status = status
        meta = existing.metadata_json or {}
        meta.update(metadata)
        existing.metadata_json = meta
        conn = existing
    else:
        conn = InboxConnection(
            user_id=user_id,
            account_id=account_id,
            provider=provider,
            status=status,
            metadata_json=metadata,
        )
        db.session.add(conn)

    db.session.commit()
    return jsonify({"connection": conn.to_dict()})


@v1.route("/inboxiq/connection-test", methods=["POST"])
@jwt_required()
def connection_test():
    user_id = get_jwt_identity()
    account_id = _resolve_account_id(user_id)
    payload = request.get_json(silent=True) or {}

    channel = (payload.get("channel") or payload.get("source") or "api").strip().lower()
    if channel not in ALLOWED_CHANNELS:
        return jsonify({"error": "validation_error", "message": f"unsupported channel: {channel}"}), 400

    message = payload.get("payload") or payload.get("message") or {}
    subject = (message.get("subject") or payload.get("subject") or f"Connection test ({channel})")[:500]
    body = (message.get("body") or message.get("message") or payload.get("body") or "Test event").strip()
    from_email = (message.get("from_email") or payload.get("from_email") or "intake@webhook.local").strip()
    provider = (message.get("provider") or payload.get("provider") or channel).strip()

    if not body:
        return jsonify({"error": "validation_error", "message": "body or message required"}), 400

    triage_input = {
        "subject": subject,
        "from_email": from_email,
        "body": body,
        "provider": provider,
        "source": channel,
        "channel": channel,
        "message_id": message.get("message_id"),
        "received_at": message.get("received_at"),
        "context": payload.get("context"),
    }

    try:
        normalized = normalize_email_payload(triage_input)
    except Exception as exc:
        return jsonify({"error": "validation_error", "message": str(exc)}), 400

    try:
        task = _celery_client().send_task(
            "inboxiq.process_incoming_email",
            args=[{"email": normalized, "user_id": user_id, "account_id": account_id}],
            queue="inbox",
        )
    except Exception as exc:
        current_app.logger.exception("failed to enqueue connection test", exc_info=exc)
        return jsonify({"error": "enqueue_failed", "message": str(exc)}), 502

    existing = (
        InboxConnection.query.filter_by(account_id=account_id, provider=provider)
        .order_by(InboxConnection.updated_at.desc())
        .first()
    )
    if not existing:
        existing = InboxConnection(
            user_id=user_id,
            account_id=account_id,
            provider=provider,
            status="connected",
            metadata_json={},
        )
        db.session.add(existing)

    meta = existing.metadata_json or {}
    meta.update({"last_test_status": "queued", "last_test_task_id": task.id, "last_test_channel": channel})
    meta.setdefault("channel", channel)
    existing.metadata_json = meta
    db.session.commit()

    return jsonify({"status": "queued", "task_id": task.id, "connection": existing.to_dict()}), 202
