# Import flask dependencies
from datetime import datetime, timedelta, timezone

import base64
import json
from flask import Blueprint, current_app, jsonify, request, url_for
from flask_jwt_extended import (
    create_access_token,
    create_refresh_token,
    decode_token,
    get_jwt,
    get_jwt_identity,
    jwt_required,
    set_access_cookies,
    set_refresh_cookies,
    unset_jwt_cookies,
)

from src.extensions import cache, db, jwt, limiter
from src.models import User, AuthEvent, Passkey, TOTPDevice
from src.security import hash_password, verify_password
from src.models import Account
from src.email_utils import send_activation_email, send_password_reset_email
import pyotp
from webauthn import (
    generate_registration_options,
    generate_authentication_options,
    options_to_json,
    verify_registration_response,
    verify_authentication_response,
)
from webauthn.helpers.bytes_to_base64url import bytes_to_base64url
from webauthn.helpers.structs import (
    PublicKeyCredentialCreationOptions,
    RegistrationCredential,
    AuthenticationCredential,
    UserVerificationRequirement,
    AuthenticatorSelectionCriteria,
)

bp = Blueprint("auth", __name__, url_prefix='/auth')


def _validate_password_strength(password: str) -> tuple[bool, str | None]:
    """Basic password rules: length >= 12, must include letters and numbers."""
    if not password or len(password) < 12:
        return False, "password must be at least 12 characters"
    has_letter = any(c.isalpha() for c in password)
    has_digit = any(c.isdigit() for c in password)
    if not (has_letter and has_digit):
        return False, "password must include letters and numbers"
    return True, None


def _current_user():
    """Return (user, account_id_int) from JWT, or (None, None)."""
    try:
        user_id_raw = get_jwt_identity()
        claims = get_jwt() or {}
        account_id_raw = claims.get("account_id")
        user_id = int(user_id_raw) if user_id_raw is not None else None
        account_id = int(account_id_raw) if account_id_raw is not None else None
        if not user_id:
            return None, None
        user = db.session.get(User, user_id)
        return user, account_id
    except Exception:
        return None, None


@bp.route("/login", methods=["POST"])
@limiter.limit("5 per minute", override_defaults=False)
def login():
    """Login with password check and return JWT (with account_id claim)."""
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    account_id_raw = data.get("account_id")
    account_id = None

    if account_id_raw not in (None, ""):
        try:
            account_id = int(account_id_raw)
        except (TypeError, ValueError):
            return jsonify({"error": "account_id must be an integer"}), 400
    if not email:
        return jsonify({"error": "email is required"}), 400

    user = User.query.filter_by(email=email).first()
    if not user:
        _log_login_attempt(outcome="fail", email=email, account_id=account_id, reason="user not found")
        return jsonify({"error": "invalid credentials"}), 401
    valid_password, algo = verify_password(user.password_hash, password)
    if not valid_password:
        _log_login_attempt(outcome="fail", email=email, account_id=account_id, user_id=user.id, reason="bad password")
        return jsonify({"error": "invalid credentials"}), 401
    if account_id is not None and user.account_id != account_id:
        _log_login_attempt(outcome="fail", email=email, account_id=account_id, user_id=user.id, reason="account mismatch")
        return jsonify({"error": "invalid credentials for workspace"}), 401

    # On successful PBKDF2 verification, upgrade hash to Argon2 for future logins.
    if algo == "pbkdf2":
        user.password_hash = hash_password(password)
        db.session.add(user)
        db.session.commit()

    additional_claims = {"account_id": str(user.account_id)}
    token = create_access_token(identity=str(user.id), additional_claims=additional_claims)
    refresh_token = create_refresh_token(identity=str(user.id), additional_claims=additional_claims)
    _whitelist_refresh(jwt_token=refresh_token)
    _log_login_attempt(outcome="success", email=email, account_id=user.account_id, user_id=user.id)
    response = jsonify(
        {
            "access_token": token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "user_id": user.id,
            "account_id": user.account_id,
        }
    )
    set_access_cookies(response, token)
    set_refresh_cookies(response, refresh_token)
    return response, 200


@bp.route("/signup", methods=["POST"])
@limiter.limit("20 per hour", override_defaults=False)
def signup():
    """Start signup: create account + user stub, send activation token (link returned for now)."""
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    if not email:
        return jsonify({"error": "email is required"}), 400

    existing = User.query.filter_by(email=email).first()
    if existing:
        return jsonify({"error": "email already exists"}), 409

    account_name_raw = (data.get("account_name") or "").strip()
    account_name = account_name_raw or _derive_account_name(email)

    seats_limit = 3
    try:
        seats_candidate = int(data.get("seats"))
        if seats_candidate > 0:
            seats_limit = seats_candidate
    except (TypeError, ValueError):
        pass

    now = datetime.now(timezone.utc)
    account = Account(name=account_name, seats_limit=seats_limit, seats_used=0, created_at=now, updated_at=now)
    db.session.add(account)
    db.session.flush()

    user = User(email=email, password_hash=None, account_id=account.id, created_at=now, updated_at=now)
    db.session.add(user)
    db.session.flush()

    activation_token = create_access_token(
        identity=str(user.id),
        additional_claims={"account_id": str(account.id), "purpose": "activation"},
        expires_delta=timedelta(minutes=10),
    )
    activation_link = url_for("activate_page", token=activation_token, _external=True)
    email_sent = send_activation_email(email, activation_link, account_name)
    if not email_sent:
        db.session.rollback()
        return jsonify({"error": "unable to send activation email; please try again"}), 502

    db.session.commit()

    return (
        jsonify(
            {
                "account_id": account.id,
                "activation_link": activation_link,
                "message": "Activation email sent. Use the link to set your password.",
            }
        ),
        201,
    )


@bp.route("/auth/resend-activation", methods=["POST"])
def resend_activation():
    """Resend activation token for an existing, not-yet-activated user."""
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    if not email:
        return jsonify({"error": "email is required"}), 400

    user = User.query.filter_by(email=email).first()
    if not user:
        return jsonify({"error": "user not found"}), 404
    if user.password_hash:
        return jsonify({"error": "account already activated"}), 400

    account = db.session.get(Account, user.account_id)
    if not account:
        return jsonify({"error": "account not found"}), 404

    activation_token = create_access_token(
        identity=str(user.id),
        additional_claims={"account_id": str(account.id), "purpose": "activation"},
        expires_delta=timedelta(minutes=10),
    )
    activation_link = url_for("activate_page", token=activation_token, _external=True)
    email_sent = send_activation_email(email, activation_link, account.name or "Your account")
    if not email_sent:
        return jsonify({"error": "unable to send activation email; please try again"}), 502

    return jsonify({"activation_link": activation_link, "message": "New activation link sent."}), 200


@bp.route("/me", methods=["GET"])
@jwt_required()
def me():
    """Return current user info using token."""
    user_id = get_jwt_identity()
    claims = get_jwt()
    account_id = claims.get("account_id")
    try:
        account_id_int = int(account_id) if account_id is not None else None
    except (TypeError, ValueError):
        account_id_int = None
    try:
        user_id_int = int(user_id)
    except (TypeError, ValueError):
        return jsonify({"error": "invalid token"}), 401
    user = db.session.get(User, user_id_int)
    if not user:
        return jsonify({"error": "invalid token"}), 401
    return jsonify({"id": user.id, "email": user.email, "account_id": account_id_int}), 200


@bp.route("/2fa/totp/start", methods=["POST"])
@jwt_required()
def totp_start():
    """Begin TOTP enrollment: issue secret and pending device."""
    user, account_id = _current_user()
    if not user:
        return jsonify({"error": "unauthorized"}), 401
    secret = pyotp.random_base32()
    device = TOTPDevice(user_id=user.id, secret=secret, verified_at=None)
    db.session.add(device)
    db.session.commit()
    issuer = current_app.config.get("APP_NAME") or "InboxIQ"
    otpauth_url = pyotp.totp.TOTP(secret).provisioning_uri(name=user.email or str(user.id), issuer_name=issuer)
    return jsonify({"device_id": device.id, "secret": secret, "otpauth_url": otpauth_url}), 200


@bp.route("/2fa/totp/verify", methods=["POST"])
@jwt_required()
def totp_verify():
    """Verify a TOTP code for a pending device."""
    user, account_id = _current_user()
    if not user:
        return jsonify({"error": "unauthorized"}), 401
    data = request.get_json(silent=True) or {}
    device_id = data.get("device_id")
    code = (data.get("code") or "").strip()
    if not device_id or not code:
        return jsonify({"error": "device_id and code are required"}), 400
    device = TOTPDevice.query.filter_by(id=device_id, user_id=user.id).first()
    if not device:
        return jsonify({"error": "device not found"}), 404
    totp = pyotp.TOTP(device.secret)
    if not totp.verify(code, valid_window=1):
        return jsonify({"error": "invalid code"}), 400
    device.verified_at = datetime.now(timezone.utc)
    db.session.add(device)
    db.session.commit()
    return jsonify({"status": "verified"}), 200


@bp.route("/2fa/totp/disable", methods=["POST"])
@jwt_required()
def totp_disable():
    """Disable all TOTP devices for the user."""
    user, account_id = _current_user()
    if not user:
        return jsonify({"error": "unauthorized"}), 401
    TOTPDevice.query.filter_by(user_id=user.id).delete()
    db.session.commit()
    return jsonify({"status": "disabled"}), 200


@bp.route("/2fa/totp/status", methods=["GET"])
@jwt_required()
def totp_status():
    """List TOTP devices for the user."""
    user, account_id = _current_user()
    if not user:
        return jsonify({"error": "unauthorized"}), 401
    devices = TOTPDevice.query.filter_by(user_id=user.id).all()
    return jsonify({"devices": [d.to_dict() for d in devices]}), 200


def _rp_id():
    return current_app.config.get("PASSKEY_RP_ID") or (request.host.split(":")[0] if request.host else "localhost")


def _rp_origin():
    scheme = request.headers.get("X-Forwarded-Proto", request.scheme or "https")
    host = request.headers.get("Host") or request.host or "localhost"
    return f"{scheme}://{host}"


@bp.route("/passkeys/registration/options", methods=["POST"])
@jwt_required()
def passkey_registration_options():
    user, account_id = _current_user()
    if not user:
        return jsonify({"error": "unauthorized"}), 401
    selection = AuthenticatorSelectionCriteria(user_verification=UserVerificationRequirement.PREFERRED)
    options: PublicKeyCredentialCreationOptions = generate_registration_options(
        rp_id=_rp_id(),
        rp_name=current_app.config.get("APP_NAME") or "InboxIQ",
        user_id=str(user.id),
        user_name=user.email or f"user-{user.id}",
        user_display_name=user.email or "InboxIQ user",
        authenticator_selection=selection,
    )
    cache.set(f"passkey:reg:{user.id}", options.challenge, timeout=600)
    return jsonify(json.loads(options_to_json(options)))


@bp.route("/passkeys/registration/verify", methods=["POST"])
@jwt_required()
def passkey_registration_verify():
    user, account_id = _current_user()
    if not user:
        return jsonify({"error": "unauthorized"}), 401
    data = request.get_json(silent=True) or {}
    expected_challenge = cache.get(f"passkey:reg:{user.id}")
    if not expected_challenge:
        return jsonify({"error": "registration challenge expired"}), 400
    try:
        credential = RegistrationCredential.parse_raw(json.dumps(data))
        verification = verify_registration_response(
            credential=credential,
            expected_challenge=expected_challenge,
            expected_rp_id=_rp_id(),
            expected_origin=_rp_origin(),
            require_user_verification=True,
        )
    except Exception as exc:
        current_app.logger.exception("passkey registration failed")
        return jsonify({"error": f"registration failed: {exc}"}), 400

    credential_id_b64 = bytes_to_base64url(verification.credential_id)
    existing = Passkey.query.filter_by(credential_id=credential_id_b64).first()
    if existing:
        return jsonify({"error": "passkey already registered"}), 409

    passkey = Passkey(
        user_id=user.id,
        label=data.get("label") or "Passkey",
        credential_id=credential_id_b64,
        public_key=bytes_to_base64url(verification.credential_public_key),
        sign_count=verification.sign_count or 0,
        transports=data.get("transports") or [],
        last_used_at=None,
    )
    db.session.add(passkey)
    db.session.commit()
    cache.delete(f"passkey:reg:{user.id}")
    return jsonify({"status": "registered", "passkey": passkey.to_dict()}), 200


@bp.route("/passkeys/list", methods=["GET"])
@jwt_required()
def passkey_list():
    user, account_id = _current_user()
    if not user:
        return jsonify({"error": "unauthorized"}), 401
    passkeys = Passkey.query.filter_by(user_id=user.id).all()
    return jsonify({"passkeys": [p.to_dict() for p in passkeys]}), 200


@bp.route("/passkeys/delete", methods=["POST"])
@jwt_required()
def passkey_delete():
    user, account_id = _current_user()
    if not user:
        return jsonify({"error": "unauthorized"}), 401
    data = request.get_json(silent=True) or {}
    passkey_id = data.get("id")
    if not passkey_id:
        return jsonify({"error": "id is required"}), 400
    passkey = Passkey.query.filter_by(id=passkey_id, user_id=user.id).first()
    if not passkey:
        return jsonify({"error": "not found"}), 404
    db.session.delete(passkey)
    db.session.commit()
    return jsonify({"status": "deleted"}), 200


@bp.route("/refresh", methods=["POST"])
@jwt_required(refresh=True)
def refresh():
    """Rotate refresh tokens: revoke old, issue new access + refresh."""
    current_refresh = get_jwt()
    user_id = current_refresh.get("sub")
    account_id = current_refresh.get("account_id")

    _revoke_token(current_refresh, reason="refresh rotation")

    additional_claims = {"account_id": str(account_id)}
    access_token = create_access_token(identity=str(user_id), additional_claims=additional_claims)
    refresh_token = create_refresh_token(identity=str(user_id), additional_claims=additional_claims)
    _whitelist_refresh(jwt_token=refresh_token)

    # Log refresh success
    try:
        evt = AuthEvent(
            user_id=int(user_id) if user_id is not None else None,
            account_id=int(account_id) if account_id is not None else None,
            email=None,
            event="jwt_refresh",
            outcome="success",
            ip=request.remote_addr or "",
            user_agent=(request.headers.get("User-Agent") or "")[:300],
        )
        db.session.add(evt)
        db.session.commit()
    except Exception:
        db.session.rollback()

    response = jsonify(
        {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "user_id": user_id,
            "account_id": account_id,
        }
    )
    set_access_cookies(response, access_token)
    set_refresh_cookies(response, refresh_token)
    return response, 200


@bp.route("/logout", methods=["POST"])
@jwt_required(verify_type=False)
def logout():
    """Revoke the current token (access or refresh) and clear cookies."""
    jwt_payload = get_jwt()
    _revoke_token(jwt_payload, reason="logout")

    response = jsonify({"status": "logged out"})
    unset_jwt_cookies(response)
    return response, 200


@bp.route("/activate", methods=["POST"])
def activate():
    """Complete activation by setting a password using the activation token."""
    data = request.get_json(silent=True) or {}
    token = data.get("token") or ""
    password = data.get("password") or ""
    if not token or not password:
        return jsonify({"error": "token and password are required"}), 400
    ok, reason = _validate_password_strength(password)
    if not ok:
        return jsonify({"error": reason}), 400
    try:
        decoded = decode_token(token)
    except Exception:
        return jsonify({"error": "invalid or expired token"}), 400

    purpose = decoded.get("purpose")
    if purpose != "activation":
        return jsonify({"error": "invalid token purpose"}), 400
    user_id = decoded.get("sub")
    account_id = decoded.get("account_id")
    try:
        user_id_int = int(user_id)
        account_id_int = int(account_id)
    except (TypeError, ValueError):
        return jsonify({"error": "invalid token payload"}), 400

    user = db.session.get(User, user_id_int)
    account = db.session.get(Account, account_id_int)
    if not user or not account or user.account_id != account.id:
        return jsonify({"error": "user not found"}), 404

    user.password_hash = hash_password(password)
    user.updated_at = datetime.now(timezone.utc)
    account.seats_used = max(account.seats_used or 0, 1)
    account.updated_at = user.updated_at
    db.session.add(user)
    db.session.add(account)
    db.session.commit()

    # Enroll user in trial onboarding sequence (send Day 1 email)
    try:
        from src.trial.tasks import enroll_user_in_trial_task
        enroll_user_in_trial_task.apply_async(args=[user_id_int], queue='leads')
    except Exception as e:
        # Don't fail activation if trial email fails
        import logging
        logging.getLogger(__name__).warning(f"Failed to enroll user {user_id_int} in trial onboarding: {e}")

    additional_claims = {"account_id": str(user.account_id)}
    access_token = create_access_token(identity=str(user.id), additional_claims=additional_claims)
    refresh_token = create_refresh_token(identity=str(user.id), additional_claims=additional_claims)
    _whitelist_refresh(jwt_token=refresh_token)

    response = jsonify(
        {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "user_id": user.id,
            "account_id": user.account_id,
        }
    )
    set_access_cookies(response, access_token)
    set_refresh_cookies(response, refresh_token)
    return response, 200


@bp.route("/reset/request", methods=["POST"])
@limiter.limit("5 per hour", override_defaults=False)
def request_password_reset():
    """
    Request a password reset link. Always responds 200 to avoid user enumeration.
    """
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    account_id_raw = data.get("account_id")
    account_id = None

    if account_id_raw not in (None, ""):
        try:
            account_id = int(account_id_raw)
        except (TypeError, ValueError):
            return jsonify({"error": "account_id must be an integer"}), 400
    if not email:
        return jsonify({"error": "email is required"}), 400

    user = User.query.filter_by(email=email).first()
    if user and account_id is not None and user.account_id != account_id:
        user = None  # account mismatch is treated as non-existent for privacy

    if not user:
        current_app.logger.info({"event": "auth.reset.ignored", "email": email, "account_id": account_id})
        try:
            evt = AuthEvent(
                email=email,
                account_id=account_id,
                event="password_reset_request",
                outcome="ignored",
                reason="user not found or account mismatch",
                ip=request.remote_addr or "",
                user_agent=(request.headers.get("User-Agent") or "")[:300],
            )
            db.session.add(evt)
            db.session.commit()
        except Exception:
            db.session.rollback()
        return jsonify({"status": "ok"})

    reset_token = create_access_token(
        identity=str(user.id),
        additional_claims={"account_id": str(user.account_id), "purpose": "password_reset"},
        expires_delta=timedelta(minutes=30),
    )
    try:
        decoded = decode_token(reset_token)
        jti = decoded.get("jti")
        exp = decoded.get("exp")
        if jti and exp:
            ttl = max(1, int(exp - datetime.now(timezone.utc).timestamp()))
            _cache_set_safe(f"reset_allow:{jti}", {"user_id": user.id}, timeout=ttl)
    except Exception:
        pass
    base_url = current_app.config.get("INBOXIQ_API_BASE_URL") or request.url_root.rstrip("/")
    reset_link = f"{base_url.rstrip('/')}/reset?token={reset_token}"

    sent = send_password_reset_email(email, reset_link, user.account_id)
    if not sent:
        current_app.logger.warning(
            {"event": "auth.reset.email_failed", "email": email, "account_id": user.account_id}
        )

    current_app.logger.info({"event": "auth.reset.requested", "email": email, "account_id": user.account_id})
    try:
        evt = AuthEvent(
            user_id=user.id,
            account_id=user.account_id,
            email=email,
            event="password_reset_request",
            outcome="success",
            ip=request.remote_addr or "",
            user_agent=(request.headers.get("User-Agent") or "")[:300],
        )
        db.session.add(evt)
        db.session.commit()
    except Exception:
        db.session.rollback()
    return jsonify({"status": "ok"})


@bp.route("/reset/complete", methods=["POST"])
def complete_password_reset():
    """Complete password reset using a reset token and new password."""
    data = request.get_json(silent=True) or {}
    token = data.get("token") or ""
    password = data.get("password") or ""
    if not token or not password:
        return jsonify({"error": "token and password are required"}), 400
    ok, reason = _validate_password_strength(password)
    if not ok:
        return jsonify({"error": reason}), 400
    try:
        decoded = decode_token(token)
    except Exception:
        return jsonify({"error": "invalid or expired token"}), 400

    if decoded.get("purpose") != "password_reset":
        return jsonify({"error": "invalid token purpose"}), 400
    user_id = decoded.get("sub")
    account_id = decoded.get("account_id")
    try:
        user_id_int = int(user_id)
        account_id_int = int(account_id)
    except (TypeError, ValueError):
        return jsonify({"error": "invalid token payload"}), 400

    jti = decoded.get("jti")
    allowed = False
    if jti:
        try:
            allowed = bool(cache.get(f"reset_allow:{jti}"))
        except Exception:
            allowed = False
    if not allowed:
        return jsonify({"error": "invalid or expired token"}), 400

    user = db.session.get(User, user_id_int)
    account = db.session.get(Account, account_id_int)
    if not user or not account or user.account_id != account.id:
        return jsonify({"error": "user not found"}), 404

    user.password_hash = hash_password(password)
    user.updated_at = datetime.now(timezone.utc)
    db.session.add(user)
    db.session.commit()
    try:
        evt = AuthEvent(
            user_id=user.id,
            account_id=user.account_id,
            email=user.email,
            event="password_reset_complete",
            outcome="success",
            ip=request.remote_addr or "",
            user_agent=(request.headers.get("User-Agent") or "")[:300],
        )
        db.session.add(evt)
        db.session.commit()
    except Exception:
        db.session.rollback()

    # Invalidate reset token and revoke existing sessions.
    if jti:
        try:
            cache.delete(f"reset_allow:{jti}")
        except Exception:
            pass
    _force_logout_user(user.id)

    additional_claims = {"account_id": str(user.account_id)}
    access_token = create_access_token(identity=str(user.id), additional_claims=additional_claims)
    refresh_token = create_refresh_token(identity=str(user.id), additional_claims=additional_claims)
    _whitelist_refresh(jwt_token=refresh_token)

    response = jsonify(
        {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "user_id": user.id,
            "account_id": user.account_id,
        }
    )
    set_access_cookies(response, access_token)
    set_refresh_cookies(response, refresh_token)
    return response, 200


def _log_login_attempt(*, outcome: str, email: str, account_id=None, user_id=None, reason: str | None = None):
    """Emit a structured audit log for login attempts (no secrets) and persist to auth_events."""
    forwarded_for = request.headers.get("X-Forwarded-For", "")
    remote_addr = forwarded_for.split(",")[0].strip() if forwarded_for else (request.remote_addr or "")
    ua = (request.headers.get("User-Agent") or "").strip()
    payload = {
        "event": "auth.login",
        "outcome": outcome,
        "email": email,
        "account_id": account_id,
        "user_id": user_id,
        "ip": remote_addr,
        "user_agent": ua[:300],
        "reason": reason,
    }
    try:
        evt = AuthEvent(
            user_id=user_id,
            account_id=account_id,
            email=email,
            event="login",
            outcome=outcome,
            reason=reason,
            ip=remote_addr,
            user_agent=ua[:300],
        )
        db.session.add(evt)
        db.session.commit()
    except Exception:
        db.session.rollback()
    log = current_app.logger
    if outcome == "success":
        log.info(payload)
    else:
        log.warning(payload)


@jwt.token_in_blocklist_loader
def _is_token_revoked(jwt_header, jwt_payload):
    """Check revocation for both access and refresh tokens, enforce refresh allowlist."""
    jti = jwt_payload.get("jti")
    token_type = jwt_payload.get("type")
    user_id = jwt_payload.get("sub")
    issued_at = jwt_payload.get("iat")
    if not jti:
        return True

    # Force-logout check: if a user reset password, revoke older tokens.
    if user_id and issued_at:
        try:
            forced_after = cache.get(f"user.logout_after:{user_id}")
            if forced_after:
                forced_after_ts = float(forced_after)
                if issued_at < forced_after_ts:
                    return True
        except Exception:
            pass

    if cache.get(f"jwt_blk:{jti}"):
        # Log revocation hit (refresh token invalid)
        if token_type == "refresh":
            try:
                evt = AuthEvent(
                    user_id=int(user_id) if user_id else None,
                    account_id=int(jwt_payload.get("account_id")) if jwt_payload.get("account_id") else None,
                    email=None,
                    event="jwt_refresh",
                    outcome="fail",
                    reason="revoked",
                    ip=request.remote_addr or "",
                    user_agent=(request.headers.get("User-Agent") or "")[:300],
                )
                db.session.add(evt)
                db.session.commit()
            except Exception:
                db.session.rollback()
        return True
    if token_type == "refresh" and not _is_refresh_whitelisted(jwt_payload):
        # Log non-whitelisted refresh rejection
        try:
            evt = AuthEvent(
                user_id=int(user_id) if user_id else None,
                account_id=int(jwt_payload.get("account_id")) if jwt_payload.get("account_id") else None,
                email=None,
                event="jwt_refresh",
                outcome="fail",
                reason="not_whitelisted",
                ip=request.remote_addr or "",
                user_agent=(request.headers.get("User-Agent") or "")[:300],
            )
            db.session.add(evt)
            db.session.commit()
        except Exception:
            db.session.rollback()
        return True
    return False


def _revoke_token(jwt_payload: dict, reason: str):
    """Mark a JWT as revoked in cache based on its jti/exp."""
    jti = jwt_payload.get("jti")
    exp = jwt_payload.get("exp")
    if not jti or not exp:
        return
    now_ts = datetime.now(timezone.utc).timestamp()
    ttl = max(1, int(exp - now_ts))
    _cache_set_safe(f"jwt_blk:{jti}", {"reason": reason}, timeout=ttl)


def _force_logout_user(user_id: int):
    """Force-logout a user by revoking tokens issued before now (coarse-grained)."""
    now_ts = datetime.now(timezone.utc).timestamp()
    # Allow tokens up to 30 days; adjust as needed for refresh token lifetime.
    ttl = 60 * 60 * 24 * 30
    _cache_set_safe(f"user.logout_after:{user_id}", now_ts, timeout=ttl)


def _whitelist_refresh(jwt_token: str):
    """Store refresh token jti to allow rotation-only validation."""
    try:
        claims = decode_token(jwt_token)
    except Exception:
        return
    jti = claims.get("jti")
    exp = claims.get("exp")
    if not jti or not exp:
        return
    ttl = max(1, int(exp - datetime.now(timezone.utc).timestamp()))
    _cache_set_safe(f"jwt_refresh_whitelist:{jti}", True, timeout=ttl)


def _is_refresh_whitelisted(jwt_payload: dict) -> bool:
    jti = jwt_payload.get("jti")
    if not jti:
        return False
    return bool(cache.get(f"jwt_refresh_whitelist:{jti}"))


def _cache_set_safe(key: str, value, timeout: int | None = None):
    """Set cache key but do not fail login if cache backend is unavailable."""
    try:
        cache.set(key, value, timeout=timeout)
    except Exception as exc:  # pragma: no cover - defensive
        current_app.logger.warning({"event": "cache.set_failed", "key": key, "error": str(exc)})


def _derive_account_name(email: str) -> str:
    """Create a friendly account name from email domain."""
    parts = email.split("@")
    if len(parts) == 2:
        domain = parts[1].split(".")[0]
        return f"{domain.title()} Support"
    return "InboxIQ Workspace"
