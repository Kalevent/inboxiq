# Minimal accounts blueprint
from flask import Blueprint, jsonify, request

from datetime import datetime, timezone

from src.extensions import db, limiter
from src.models.core import Account

bp = Blueprint("accounts", __name__, url_prefix='/accounts')


@bp.route("", methods=["POST"])  # nosemgrep: inboxiq.auth.unprotected-write-endpoint
@limiter.limit("10 per hour", override_defaults=False)
def create_account():
    """Create an account with optional seats_limit."""
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    seats_limit = data.get("seats_limit", 1)
    try:
        seats_limit = int(seats_limit)
    except (TypeError, ValueError):
        return jsonify({"error": "seats_limit must be an integer"}), 400

    if not name:
        return jsonify({"error": "name is required"}), 400
    if seats_limit < 1:
        return jsonify({"error": "seats_limit must be >= 1"}), 400

    now = datetime.now(timezone.utc)
    account = Account(
        name=name,
        seats_limit=seats_limit,
        seats_used=0,
        created_at=now,
        updated_at=now,
    )
    db.session.add(account)
    db.session.commit()
    return (
        jsonify(
            {
                "id": account.id,
                "name": account.name,
                "seats_limit": account.seats_limit,
                "seats_used": account.seats_used,
            }
        ),
        201,
    )
