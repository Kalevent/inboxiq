# Import flask dependencies
from datetime import datetime, timedelta, timezone

from flask import Blueprint, jsonify, request, current_app, url_for
from flask_jwt_extended import get_jwt, jwt_required, create_access_token

from src.extensions import db, limiter
from src.models import Account, User
from src.security import hash_password
from src.email_utils import send_activation_email

bp = Blueprint("users", __name__,  url_prefix='/users')


@bp.route("", methods=["POST"])
@limiter.limit("30 per minute", override_defaults=False)
def create_user():
    """Create a user tied to an account, enforcing seat limits."""
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password")
    account_id = data.get("account_id")

    if not email:
        return jsonify({"error": "email is required"}), 400
    if not account_id:
        return jsonify({"error": "account_id is required"}), 400

    # Optional auth: require token for accounts with existing users; allow unauthenticated bootstrap when seats_used==0
    claims = {}
    token_account_id_int = None
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        claims = get_jwt() or {}
        token_account_id = claims.get("account_id")
        try:
            token_account_id_int = int(token_account_id) if token_account_id is not None else None
        except (TypeError, ValueError):
            token_account_id_int = None

    account = db.session.get(Account, account_id)
    if not account:
        return jsonify({"error": "account not found"}), 404
    if account.seats_used > 0 and token_account_id_int != account.id:
        return jsonify({"error": "forbidden for this account"}), 403
    if account.seats_used >= account.seats_limit:
        return jsonify({"error": "seat limit reached"}), 403

    existing = User.query.filter_by(email=email).first()
    if existing:
        return jsonify({"error": "email already exists"}), 409

    now = datetime.now(timezone.utc)
    user = User(
        email=email,
        password_hash=hash_password(password or ""),
        account_id=account.id,
        created_at=now,
        updated_at=now,
    )
    account.seats_used = account.seats_used + 1
    db.session.add(user)
    db.session.add(account)
    db.session.commit()

    return (
        jsonify(
            {
                "id": user.id,
                "email": user.email,
                "account_id": user.account_id,
                "seats_used": account.seats_used,
                "seats_limit": account.seats_limit,
            }
        ),
        201,
    )


@bp.route("/invite", methods=["POST"])
@jwt_required()
@limiter.limit("30 per minute", override_defaults=False)
def invite_user():
    """
    Invite a user into an existing account and email them an activation link.
    Requires the caller's token to belong to the target account.
    """
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    account_id = data.get("account_id")

    if not email:
        return jsonify({"error": "email is required"}), 400

    claims = get_jwt() or {}
    token_account_id = claims.get("account_id")
    try:
        token_account_id_int = int(token_account_id) if token_account_id is not None else None
    except (TypeError, ValueError):
        token_account_id_int = None

    try:
        account_id_int = int(account_id) if account_id is not None else None
    except (TypeError, ValueError):
        return jsonify({"error": "account_id must be an integer"}), 400

    # Default to the caller's account if none provided.
    target_account_id = account_id_int or token_account_id_int
    if not target_account_id:
        return jsonify({"error": "account_id is required"}), 400
    if token_account_id_int != target_account_id:
        return jsonify({"error": "forbidden for this account"}), 403

    account = db.session.get(Account, target_account_id)
    if not account:
        return jsonify({"error": "account not found"}), 404
    if account.seats_used >= account.seats_limit:
        return jsonify({"error": "seat limit reached"}), 403

    existing = User.query.filter_by(email=email).first()
    if existing:
        return jsonify({"error": "email already exists"}), 409

    now = datetime.now(timezone.utc)
    user = User(email=email, password_hash=None, account_id=account.id, created_at=now, updated_at=now)
    account.seats_used = account.seats_used + 1
    db.session.add(user)
    db.session.add(account)
    db.session.flush()

    activation_token = create_access_token(
        identity=str(user.id),
        additional_claims={"account_id": str(account.id), "purpose": "activation"},
        expires_delta=timedelta(minutes=30),
    )
    base_url = current_app.config.get("INBOXIQ_API_BASE_URL") or request.url_root.rstrip("/")
    activation_link = f"{base_url.rstrip('/')}{url_for('activate_page')}?token={activation_token}"
    email_sent = send_activation_email(email, activation_link, account.name or "Your workspace")
    if not email_sent:
        db.session.rollback()
        return jsonify({"error": "unable to send activation email; please try again"}), 502

    db.session.commit()
    return (
        jsonify(
            {
                "id": user.id,
                "email": user.email,
                "account_id": user.account_id,
                "activation_link": activation_link,
                "seats_used": account.seats_used,
                "seats_limit": account.seats_limit,
            }
        ),
        201,
    )
