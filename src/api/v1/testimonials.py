from datetime import datetime
from datetime import datetime, timedelta
from flask import jsonify, request, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
from itsdangerous import URLSafeSerializer, BadSignature

from src.api.v1 import v1
from src.extensions import db
from src.models import Testimonial, Ticket, User, Account


def _serializer() -> URLSafeSerializer:
    secret = current_app.config.get("SECRET_KEY", "change-me")
    return URLSafeSerializer(secret_key=secret, salt="testimonial-token")


def _load_token(token: str):
    try:
        return _serializer().loads(token)
    except BadSignature:
        return None


def _save_testimonial(account_id, user_id, rating, message, consent_public, source):
    t = Testimonial(
        account_id=account_id,
        user_id=user_id,
        rating=rating,
        message=message,
        consent_public=bool(consent_public),
        source=source,
        status="pending",
    )
    db.session.add(t)
    db.session.commit()
    return t


def _usage_ok(account_id):
    min_tickets = current_app.config.get("TESTIMONIAL_MIN_TICKETS", 3)
    min_days = current_app.config.get("TESTIMONIAL_MIN_ACCOUNT_AGE_DAYS", 7)
    # tickets gate
    ticket_count = Ticket.query.filter_by(account_id=account_id).count()
    if ticket_count < min_tickets:
        return False
    # account age gate
    acct = Account.query.get(account_id) if account_id else None
    if acct and acct.created_at:
        age = datetime.utcnow().date() - acct.created_at.date()
        if age < timedelta(days=min_days):
            return False
    return True


@v1.route("/testimonials", methods=["POST"])
@jwt_required()
def submit_testimonial():
    user_id = get_jwt_identity()
    user = User.query.get(user_id) if user_id else None
    if not user:
        return jsonify({"error": "not_authenticated"}), 401

    account_id = user.account_id
    payload = request.get_json(silent=True) or {}
    try:
        rating = int(payload.get("rating") or 0)
    except ValueError:
        rating = 0
    message = (payload.get("message") or "").strip()
    consent_public = bool(payload.get("consent_public"))

    if rating < 1 or rating > 5 or not message:
        return jsonify({"error": "validation_error"}), 400

    if not _usage_ok(account_id):
        return jsonify({"error": "insufficient_usage"}), 403

    t = _save_testimonial(account_id, user_id, rating, message, consent_public, "in_app")
    return jsonify({"success": True, "testimonial": t.to_dict()})


@v1.route("/testimonials/with-token", methods=["POST"])
def submit_testimonial_with_token():
    token = request.args.get("token") or (request.get_json(silent=True) or {}).get("token")
    payload = _load_token(token) if token else None
    if not payload:
        return jsonify({"error": "invalid_token"}), 400

    account_id = payload.get("account_id")
    user_id = payload.get("user_id")
    body = request.get_json(silent=True) or {}
    try:
        rating = int(body.get("rating") or 0)
    except ValueError:
        rating = 0
    message = (body.get("message") or "").strip()
    consent_public = bool(body.get("consent_public"))
    if rating < 1 or rating > 5 or not message:
        return jsonify({"error": "validation_error"}), 400

    if not _usage_ok(account_id):
        return jsonify({"error": "insufficient_usage"}), 403

    t = _save_testimonial(account_id, user_id, rating, message, consent_public, "email_token")
    return jsonify({"success": True, "testimonial": t.to_dict()})


def generate_testimonial_token(account_id, user_id):
    return _serializer().dumps({"account_id": account_id, "user_id": user_id, "ts": datetime.utcnow().isoformat()})
