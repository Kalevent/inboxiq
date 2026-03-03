from flask import jsonify, request, current_app
from flask_jwt_extended import get_jwt_identity, jwt_required

from src.api.v1 import v1
from src.extensions import db
from src.inbox.logic import run_dspy_decision, compute_due_at
from src.models import Feedback, Ticket, User


@v1.route("/feedback", methods=["POST"])
@jwt_required()
def submit_feedback():
    """
    Collect logged-in user feedback (message + optional context + urgency 1-5).
    """
    user_id = get_jwt_identity()
    user = User.query.get(user_id) if user_id else None
    if not user:
        return jsonify({"error": "not_authenticated"}), 401

    payload = request.get_json(silent=True) or {}
    message = (payload.get("message") or "").strip()
    context = (payload.get("context") or "").strip() or None
    try:
        urgency = int(payload.get("urgency") or 3)
    except ValueError:
        urgency = 3
    urgency = max(1, min(5, urgency))

    if not message:
        return jsonify({"error": "validation_error", "message": "message_required"}), 400

    # Run the same triage logic used for email/webhook, but tag as feedback.
    body = message if not context else f"{message}\n\nContext: {context}"
    subject = (payload.get("subject") or f"Feedback from {user.email or 'user'}")[:180]
    triage_input = {
        "subject": subject,
        "from_email": user.email or "feedback@inboxiq.local",
        "body": body,
        "provider": "feedback",
        "source": "feedback",
    }
    try:
        decision = run_dspy_decision(triage_input, account_id=user.account_id)
    except Exception as exc:
        current_app.logger.warning("triage failed in feedback: %s", exc)
        return jsonify({"error": "triage_failed", "message": str(exc)}), 503

    action_required = decision.action_required
    action_required_str = "true" if action_required is True else ("false" if action_required is False else "optional")

    fb = Feedback(
        account_id=user.account_id,
        user_id=user.id,
        message=message,
        context=context,
        urgency=urgency,
        source="feedback",
        status="auto_handled" if action_required is False else "optional" if action_required == "optional" else "new",
        action_required=action_required_str,
        metadata_json=decision.entities or {},
        ai_decision_json=decision.to_dict(),
    )

    ticket_record = None
    if action_required is True:
        ticket_record = Ticket(
            account_id=user.account_id,
            user_id=user.id,
            subject=subject,
            from_email=user.email or "feedback@inboxiq.local",
            body_preview=body[:500],
            category=decision.category,
            priority=decision.priority,
            sentiment=decision.sentiment,
            entities=decision.entities,
            status="new",
            message_id=f"feedback-{fb.id}",
            provider="feedback",
            decision=decision.to_dict(),
            team=decision.team,
            assigned_to=decision.assigned_to,
            owner=decision.owner,
            due_at=compute_due_at(decision.priority, user.account_id),
        )
        db.session.add(ticket_record)

    db.session.add(fb)
    db.session.flush()
    if ticket_record:
        ticket_record.message_id = ticket_record.message_id or f"feedback-{fb.id}"
        fb.ticket_id = ticket_record.id

    db.session.commit()

    return jsonify({"success": True, "feedback": fb.to_dict(), "ticket": ticket_record.to_dict() if ticket_record else None, "decision": decision.to_dict()})
