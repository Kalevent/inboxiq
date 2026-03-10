from __future__ import annotations

import base64
import json
import urllib.parse
from datetime import datetime, timezone

import requests
from flask import Blueprint, current_app, jsonify, redirect, request, url_for
from flask_jwt_extended import (
    create_access_token,
    create_refresh_token,
    decode_token,
    get_jwt_identity,
    jwt_required,
    set_access_cookies,
    set_refresh_cookies,
)

from src.api.v1 import v1
from src.extensions import cache, db
from src.models.core import Account, InboxConnection, User
from src.security import log_audit


GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"

# Sign-in only — no restricted scopes, no Google verification required
GOOGLE_SIGNIN_SCOPES = ["openid", "email", "profile"]

# Gmail inbox connection — restricted scopes, requires Google verification for production
# Only requested after the user has signed in and explicitly connects their inbox
GOOGLE_GMAIL_SCOPES = [
    "openid",
    "email",
    "profile",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
]

# Backward-compat alias (kept so nothing else breaks)
GOOGLE_SCOPES = GOOGLE_SIGNIN_SCOPES

MS_AUTH_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/authorize"
MS_TOKEN_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/token"

# Sign-in only — no mail scopes, no admin consent required
MS_SIGNIN_SCOPES = [
    "openid",
    "offline_access",
    "email",
    "profile",
    "https://graph.microsoft.com/User.Read",
]

# Inbox connection — mail scopes requested after sign-in
MS_MAIL_SCOPES = MS_SIGNIN_SCOPES + [
    "https://graph.microsoft.com/Mail.ReadWrite",
]

# Backward-compat alias
MS_SCOPES = MS_SIGNIN_SCOPES


def _derive_account_name(email: str) -> str:
    parts = email.split("@")
    if len(parts) == 2:
        domain = parts[1].split(".")[0]
        return f"{domain.title()} Support"
    return "My Account"


def _whitelist_refresh(jwt_token: str) -> None:
    try:
        claims = decode_token(jwt_token)
        jti = claims.get("jti")
        exp = claims.get("exp")
        if jti and exp:
            ttl = max(1, int(exp - datetime.now(timezone.utc).timestamp()))
            try:
                cache.set(f"jwt_refresh_whitelist:{jti}", True, timeout=ttl)
            except Exception:
                pass
    except Exception:
        pass


def _find_or_create_user(email: str, display_name: str | None) -> tuple[User, bool]:
    """Find existing user by email or create account+user. Returns (user, is_new)."""
    user = User.query.filter(User.email.ilike(email)).first()
    if user:
        return user, False
    now = datetime.now(timezone.utc)
    account_name = display_name or _derive_account_name(email)
    account = Account(name=account_name, seats_limit=3, seats_used=0, created_at=now, updated_at=now)
    db.session.add(account)
    db.session.flush()
    user = User(email=email, password_hash=None, account_id=account.id, created_at=now, updated_at=now)
    db.session.add(user)
    db.session.commit()
    return user, True


def _issue_social_session(user: User, is_new: bool):
    """Set JWT cookies and redirect to onboarding (new) or dashboard (returning)."""
    additional_claims = {"account_id": str(user.account_id)}
    token = create_access_token(identity=str(user.id), additional_claims=additional_claims)
    refresh = create_refresh_token(identity=str(user.id), additional_claims=additional_claims)
    _whitelist_refresh(refresh)
    log_audit("auth.social_login", resource_type="user", resource_id=str(user.id),
              account_id=user.account_id, user_id=user.id)
    dest = url_for("onboarding_page")
    response = redirect(dest)
    set_access_cookies(response, token)
    set_refresh_cookies(response, refresh)
    return response


def _decode_id_token_raw(id_token: str) -> dict:
    """
    Lightweight ID token decoding without signature verification (sufficient for metadata extraction).
    """
    try:
        parts = id_token.split(".")
        if len(parts) < 2:
            return {}
        padded = parts[1] + "=" * (-len(parts[1]) % 4)
        payload = base64.urlsafe_b64decode(padded.encode("utf-8"))
        return json.loads(payload.decode("utf-8"))
    except Exception:
        return {}


def _store_connection(provider: str, email_address: str, access_token: str, refresh_token: str | None, user_id: int | None):
    resolved_user_id = user_id
    account_id = None
    if resolved_user_id:
        u = User.query.get(resolved_user_id)
        account_id = getattr(u, "account_id", None)
    else:
        # Fallback: match the OAuth email to an existing user.
        user = User.query.filter(User.email.ilike(email_address)).first()
        if user:
            resolved_user_id = user.id
            account_id = user.account_id

    if not resolved_user_id:
        raise RuntimeError("login_required")

    conn = InboxConnection.query.filter_by(account_id=account_id, email_address=email_address).first() if account_id else None
    if conn is None:
        conn = InboxConnection.query.filter_by(user_id=resolved_user_id, provider=provider).first()
    if not conn:
        conn = InboxConnection(
            user_id=resolved_user_id,
            account_id=account_id,
            provider=provider,
            email_address=email_address,
        )
        db.session.add(conn)
    else:
        if account_id and not conn.account_id:
            conn.account_id = account_id
        conn.provider = provider

    conn.access_token = access_token
    if refresh_token:
        conn.refresh_token = refresh_token
    conn.status = "connected"
    meta = conn.metadata_json or {}
    meta.update({"last_poll_status": "never", "last_poll_counts": {"created": 0, "duplicates": 0, "errors": 0, "fetched": 0}})
    conn.metadata_json = meta
    db.session.commit()
    return conn


@v1.route("/auth/google/start", methods=["GET"])
@jwt_required(optional=True)
def google_start():
    """Sign-in / sign-up with Google. Uses only openid/email/profile — no Gmail scopes."""
    client_id = current_app.config.get("GOOGLE_CLIENT_ID")
    redirect_uri = current_app.config.get("GOOGLE_REDIRECT_URI") or url_for(".google_callback", _external=True)
    if not client_id or not redirect_uri:
        return jsonify({"error": "Google OAuth not configured"}), 500

    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": " ".join(GOOGLE_SIGNIN_SCOPES),
        "access_type": "offline",
        "state": "signin",
    }
    return redirect(f"{GOOGLE_AUTH_URL}?{urllib.parse.urlencode(params)}")


@v1.route("/auth/google/inbox/start", methods=["GET"])
@jwt_required()
def google_inbox_start():
    """Connect Gmail inbox for an already-authenticated user. Requests Gmail scopes."""
    client_id = current_app.config.get("GOOGLE_CLIENT_ID")
    redirect_uri = current_app.config.get("GOOGLE_REDIRECT_URI") or url_for(".google_callback", _external=True)
    if not client_id or not redirect_uri:
        return jsonify({"error": "Google OAuth not configured"}), 500

    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": " ".join(GOOGLE_GMAIL_SCOPES),
        "access_type": "offline",
        "include_granted_scopes": "true",
        "prompt": "consent",
        "state": "connect_inbox",
    }
    return redirect(f"{GOOGLE_AUTH_URL}?{urllib.parse.urlencode(params)}")


@v1.route("/auth/google/callback", methods=["GET"])
@jwt_required(optional=True)
def google_callback():
    code = request.args.get("code")
    if not code:
        return jsonify({"error": "Missing code"}), 400
    client_id = current_app.config.get("GOOGLE_CLIENT_ID")
    client_secret = current_app.config.get("GOOGLE_CLIENT_SECRET")
    redirect_uri = current_app.config.get("GOOGLE_REDIRECT_URI") or url_for(".google_callback", _external=True)
    if not client_id or not client_secret:
        return jsonify({"error": "Google OAuth not configured"}), 500

    token_data = {
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    }
    resp = requests.post(GOOGLE_TOKEN_URL, data=token_data, timeout=15)
    if resp.status_code != 200:
        return jsonify({"error": "Failed to exchange code", "details": resp.text}), 502
    tok = resp.json()
    state = request.args.get("state", "signin")
    id_claims = _decode_id_token_raw(tok.get("id_token", ""))
    email = (id_claims.get("email") or "").strip().lower() or "unknown@gmail.com"
    access_token = tok.get("access_token")
    refresh_token = tok.get("refresh_token")
    user_id = get_jwt_identity()

    if state == "connect_inbox":
        # Authenticated user connecting their Gmail inbox — store connection and redirect
        if not user_id:
            return redirect(url_for("login_page") + "?error=login_required")
        try:
            _store_connection("gmail", email, access_token, refresh_token, user_id)
        except RuntimeError:
            pass
        return redirect("https://mail.google.com")

    # state == "signin" (default): sign-up or log-in flow — no Gmail scopes requested
    if not user_id:
        try:
            user, is_new = _find_or_create_user(email, id_claims.get("name"))
        except Exception as exc:
            current_app.logger.error("google_callback signup error: %s", exc)
            return redirect(url_for("login_page") + "?error=account_error")
        return _issue_social_session(user, is_new)

    # Already logged in and hit /auth/google/start again — send to onboarding
    return redirect(url_for("onboarding_page"))


@v1.route("/auth/outlook/start", methods=["GET"])
def outlook_start():
    """Sign-in / sign-up with Microsoft. Uses only openid/profile/User.Read — no mail scopes."""
    client_id = current_app.config.get("MICROSOFT_CLIENT_ID")
    redirect_uri = current_app.config.get("MICROSOFT_REDIRECT_URI") or url_for(".outlook_callback", _external=True)
    if not client_id or not redirect_uri:
        return jsonify({"error": "Microsoft OAuth not configured"}), 500

    params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "scope": " ".join(MS_SIGNIN_SCOPES),
        "response_mode": "query",
        "state": "signin",
    }
    return redirect(f"{MS_AUTH_URL}?{urllib.parse.urlencode(params)}")


@v1.route("/auth/outlook/inbox/start", methods=["GET"])
@jwt_required()
def outlook_inbox_start():
    """Connect Outlook inbox for an already-authenticated user. Requests mail scopes."""
    client_id = current_app.config.get("MICROSOFT_CLIENT_ID")
    redirect_uri = current_app.config.get("MICROSOFT_REDIRECT_URI") or url_for(".outlook_callback", _external=True)
    if not client_id or not redirect_uri:
        return jsonify({"error": "Microsoft OAuth not configured"}), 500

    params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "scope": " ".join(MS_MAIL_SCOPES),
        "response_mode": "query",
        "state": "connect_inbox",
        "prompt": "consent",
    }
    return redirect(f"{MS_AUTH_URL}?{urllib.parse.urlencode(params)}")


@v1.route("/auth/outlook/callback", methods=["GET"])
@jwt_required(optional=True)
def outlook_callback():
    code = request.args.get("code")
    if not code:
        return jsonify({"error": "Missing code"}), 400
    client_id = current_app.config.get("MICROSOFT_CLIENT_ID")
    client_secret = current_app.config.get("MICROSOFT_CLIENT_SECRET")
    redirect_uri = current_app.config.get("MICROSOFT_REDIRECT_URI") or url_for(".outlook_callback", _external=True)
    if not client_id or not client_secret:
        return jsonify({"error": "Microsoft OAuth not configured"}), 500

    state = request.args.get("state", "signin")
    scopes = MS_MAIL_SCOPES if state == "connect_inbox" else MS_SIGNIN_SCOPES

    token_data = {
        "client_id": client_id,
        "client_secret": client_secret,
        "code": code,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
        "scope": " ".join(scopes),
    }
    resp = requests.post(MS_TOKEN_URL, data=token_data, timeout=15)
    if resp.status_code != 200:
        return jsonify({"error": "Failed to exchange code", "details": resp.text}), 502
    tok = resp.json()
    id_claims = _decode_id_token_raw(tok.get("id_token", ""))
    email = (id_claims.get("preferred_username") or id_claims.get("email") or "").strip().lower() or "unknown@outlook.com"
    access_token = tok.get("access_token")
    refresh_token = tok.get("refresh_token")
    user_id = get_jwt_identity()

    if state == "connect_inbox":
        # Authenticated user connecting their Outlook inbox
        if not user_id:
            return redirect(url_for("login_page") + "?error=login_required")
        try:
            _store_connection("outlook", email, access_token, refresh_token, user_id)
        except RuntimeError:
            pass
        return redirect("https://outlook.office.com/mail")

    # state == "signin": sign-up or log-in flow — no mail scopes requested
    if not user_id:
        try:
            user, is_new = _find_or_create_user(email, id_claims.get("name"))
        except Exception as exc:
            current_app.logger.error("outlook_callback signup error: %s", exc)
            return redirect(url_for("login_page") + "?error=account_error")
        return _issue_social_session(user, is_new)

    # Already logged in — send to onboarding
    return redirect(url_for("onboarding_page"))
