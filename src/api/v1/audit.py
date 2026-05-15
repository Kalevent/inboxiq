"""
Audit log query API.

GET /api/v1/audit-logs
  Returns paginated audit log entries scoped to the current account.
  Query params:
    page      (int, default 1)
    per_page  (int, default 50, max 200)
    action    (str, optional filter)
    user_id   (int, optional filter)
    format    ("json" | "csv", default "json")
"""
from __future__ import annotations

import csv
import io

from flask import Blueprint, g, jsonify, request, Response
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt

from src.extensions import db
from src.models.auth import AuditLog
from src.models.core import User

audit_bp = Blueprint("audit", __name__, url_prefix="/api/v1")

ACTION_LABELS = {
    "auth.login_success": "Signed in",
    "auth.passkey_login": "Signed in with passkey",
    "auth.social_login": "Signed in with social",
    "auth.logout": "Signed out",
    "auth.totp_enabled": "Two-factor authentication enabled",
    "auth.totp_disabled": "Two-factor authentication disabled",
    "auth.passkey_registered": "Passkey added",
    "auth.passkey_deleted": "Passkey removed",
    "auth.password_reset_completed": "Password changed",
    "inbox.connected": "Email inbox connected",
    "inbox.disconnected": "Email inbox disconnected",
    "user.role_changed": "Team member role changed",
    "user.invited": "Team member invited",
    "ai_provider.configured": "AI provider configured",
    "ai_provider.removed": "AI provider removed",
    "account.deleted": "Account deleted",
}


def _get_account_id() -> int | None:
    claims = get_jwt() or {}
    raw = claims.get("account_id")
    try:
        return int(raw) if raw is not None else None
    except (TypeError, ValueError):
        return None


@audit_bp.get("/audit-logs")
@jwt_required()
def get_audit_logs():
    account_id = _get_account_id()
    if not account_id:
        return jsonify({"error": "account not found"}), 400

    try:
        page = max(1, int(request.args.get("page", 1)))
    except (TypeError, ValueError):
        page = 1
    try:
        per_page = min(200, max(1, int(request.args.get("per_page", 50))))
    except (TypeError, ValueError):
        per_page = 50

    action_filter = request.args.get("action")
    user_id_filter = request.args.get("user_id")
    fmt = request.args.get("format", "json")

    query = AuditLog.query.filter_by(account_id=account_id)
    if action_filter:
        query = query.filter(AuditLog.action == action_filter)
    if user_id_filter:
        try:
            query = query.filter(AuditLog.user_id == int(user_id_filter))
        except (TypeError, ValueError):
            pass

    query = query.order_by(AuditLog.created_at.desc())

    if fmt == "csv":
        rows = query.limit(10000).all()
        return _build_csv(rows, account_id)

    paginated = query.paginate(page=page, per_page=per_page, error_out=False)

    # Enrich with user emails for display
    user_ids = {r.user_id for r in paginated.items if r.user_id}
    users = {u.id: u.email for u in User.query.filter(User.id.in_(user_ids)).all()} if user_ids else {}

    items = []
    for entry in paginated.items:
        d = entry.to_dict()
        d["action_label"] = ACTION_LABELS.get(entry.action, entry.action)
        d["user_email"] = users.get(entry.user_id)
        items.append(d)

    return jsonify({
        "items": items,
        "total": paginated.total,
        "page": paginated.page,
        "pages": paginated.pages,
        "per_page": per_page,
    }), 200


def _build_csv(rows: list[AuditLog], account_id: int) -> Response:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["timestamp", "action", "action_label", "resource_type", "resource_id",
                     "user_id", "ip_address", "metadata"])
    for entry in rows:
        writer.writerow([
            entry.created_at.isoformat() if entry.created_at else "",
            entry.action,
            ACTION_LABELS.get(entry.action, entry.action),
            entry.resource_type or "",
            entry.resource_id or "",
            entry.user_id or "",
            entry.ip_address or "",
            str(entry.metadata_json or {}),
        ])
    output = buf.getvalue()
    return Response(
        output,
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename=activity-log-{account_id}.csv"},
    )
