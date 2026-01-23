from flask import Blueprint, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
from datetime import datetime
from src.models import Ticket


feedback_bp = Blueprint("feedback_export", __name__)


@feedback_bp.route("/inboxiq/feedback/export", methods=["GET"])
@jwt_required()
def export_feedback():
    """
    Export manual overrides/feedback as a portable labeled dataset.
    Returns JSONL-like array for downstream training/fine-tuning.
    """
    user_id = get_jwt_identity()
    # Limit to tickets with manual overrides/feedback
    tickets = (
        Ticket.query.filter(Ticket.manual_override.is_(True))
        .order_by(Ticket.updated_at.desc())
        .limit(1000)
        .all()
    )
    out = []
    for t in tickets:
        fb = (t.override_metadata or {}).get("feedback") or {}
        record = {
            "ticket_id": t.id,
            "subject": t.subject,
            "body_preview": t.body_preview,
            "from_email": t.from_email,
            "provider": t.provider,
            "created_at": t.created_at.isoformat() if t.created_at else None,
            "updated_at": t.updated_at.isoformat() if t.updated_at else None,
            "category_final": t.category,
            "priority_final": t.priority,
            "team_final": t.team,
            "assigned_to_final": t.assigned_to,
            "intent_final": (t.decision or {}).get("intent"),
            "sentiment_final": t.sentiment,
            "override_feedback": fb,
            "decision_trace": (t.decision or {}).get("decision_trace"),
            "manual_override": t.manual_override,
            "user_id": user_id,
        }
        out.append(record)
    return jsonify({"count": len(out), "data": out})
