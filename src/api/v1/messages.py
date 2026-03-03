"""
In-app message API for dashboard broadcast banners.

User-facing endpoints:
  GET  /api/v1/messages/unread       — active, non-dismissed messages for the caller
  POST /api/v1/messages/<id>/dismiss — mark a message as dismissed

Admin endpoints are in admin_marketing.py.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from flask import jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity

from src.api.v1 import v1
from src.extensions import db
from src.models.core import User
from src.models.marketing import InAppMessage, InAppMessageDismissal

logger = logging.getLogger(__name__)


def _get_user_and_account(user_id: int):
    user = db.session.get(User, user_id)
    if not user:
        return None, None
    return user, user.account_id


@v1.route("/messages/unread", methods=["GET"])
@jwt_required()
def get_unread_messages():
    """
    Return active in-app messages for the current user that haven't been dismissed.

    Filters:
    - published_at is set and <= now
    - expires_at is NULL or > now
    - Not dismissed by this user
    - target matches user's plan ("all" always matches; "trial"/"paid" checked against account)

    Returns:
        {"messages": [{id, title, body, type, cta_text, cta_url, published_at}]}
    """
    user_id = get_jwt_identity()
    user, account_id = _get_user_and_account(user_id)
    if not user:
        return jsonify({"messages": []}), 200

    now = datetime.now(timezone.utc)

    # Get dismissed message IDs for this user
    dismissed_ids = {
        row.message_id
        for row in db.session.query(InAppMessageDismissal.message_id).filter_by(user_id=user_id).all()
    }

    # Determine user's plan type
    plan_type = _get_plan_type(account_id)

    # Fetch active messages
    query = db.session.query(InAppMessage).filter(
        InAppMessage.published_at.isnot(None),
        InAppMessage.published_at <= now,
        db.or_(InAppMessage.expires_at.is_(None), InAppMessage.expires_at > now),
    ).order_by(InAppMessage.published_at.desc()).limit(20)

    messages = []
    for msg in query.all():
        if msg.id in dismissed_ids:
            continue
        # Check target filter
        if msg.target_account_id is not None and msg.target_account_id != account_id:
            continue
        if msg.target == "trial" and plan_type != "trial":
            continue
        if msg.target == "paid" and plan_type != "paid":
            continue
        messages.append({
            "id": msg.id,
            "title": msg.title,
            "body": msg.body,
            "type": msg.type,
            "cta_text": msg.cta_text,
            "cta_url": msg.cta_url,
            "published_at": msg.published_at.isoformat() if msg.published_at else None,
        })

    return jsonify({"messages": messages}), 200


@v1.route("/messages/<message_id>/dismiss", methods=["POST"])
@jwt_required()
def dismiss_message(message_id: str):
    """
    Dismiss a message for the current user.

    Returns:
        {"status": "dismissed"}
    """
    user_id = get_jwt_identity()

    msg = db.session.get(InAppMessage, message_id)
    if not msg:
        return jsonify({"error": "message not found"}), 404

    existing = db.session.get(InAppMessageDismissal, (message_id, user_id))
    if not existing:
        dismissal = InAppMessageDismissal(message_id=message_id, user_id=user_id)
        db.session.add(dismissal)
        db.session.commit()

    return jsonify({"status": "dismissed"}), 200


# ── helpers ───────────────────────────────────────────────────────────────────

def _get_plan_type(account_id: int | None) -> str:
    """Return 'trial', 'paid', or 'unknown' for the given account."""
    if not account_id:
        return "unknown"
    try:
        from src.models import Account
        acct = db.session.get(Account, account_id)
        if not acct:
            return "unknown"
        plan = (getattr(acct, "plan", None) or "").lower()
        if "trial" in plan or plan == "free":
            return "trial"
        if plan:
            return "paid"
        # Fall back to trial_ends_at field if plan isn't set
        trial_ends = getattr(acct, "trial_ends_at", None)
        if trial_ends and trial_ends > datetime.now(timezone.utc):
            return "trial"
        return "paid"
    except Exception:
        return "unknown"
