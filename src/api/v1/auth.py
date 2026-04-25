from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
import urllib.parse
from datetime import datetime, timedelta, timezone

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
    verify_jwt_in_request,
)

from src.api.v1 import v1
from src.extensions import cache, db
from src.models.core import Account, InboxConnection, User
from src.security import log_audit


def _create_trial_lead(email: str, account_id: int) -> None:
    """
    Create a Lead record for a new signup so they enter the funnel at TRIAL stage.
    Called after both email activation and OAuth signup. Silently no-ops if the
    lead already exists or any error occurs — never blocks the auth flow.
    """
    import logging
    from uuid import uuid4
    try:
        from src.models.leads import Lead, LeadFunnelStage
        now = datetime.now(timezone.utc)
        existing = Lead.query.filter_by(email=email).first()
        if existing:
            # Already a lead — just advance to trial stage if they're still in visits/discovery
            if existing.current_funnel_stage in (None, "visits", "discovery"):
                existing.current_funnel_stage = "trial"
                existing.stage_entered_at = now
                stage = LeadFunnelStage(
                    lead_id=existing.id,
                    stage="trial",
                    entered_at=now,
                )
                db.session.add(stage)
                db.session.commit()
            return
        lead = Lead(
            id=str(uuid4()),
            email=email,
            name=email.split("@")[0].replace(".", " ").replace("_", " ").capitalize(),
            status="New Lead",
            source="signup",
            current_funnel_stage="trial",
            stage_entered_at=now,
            created_at=now,
            updated_at=now,
        )
        db.session.add(lead)
        db.session.flush()
        stage = LeadFunnelStage(
            lead_id=lead.id,
            stage="trial",
            entered_at=now,
        )
        db.session.add(stage)
        db.session.commit()
    except Exception:
        db.session.rollback()
        logging.getLogger(__name__).warning(
            "_create_trial_lead: failed for %s account=%s", email, account_id, exc_info=True
        )


GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"

_CONNECT_STATE_TTL = 600  # 10 minutes


def _make_connect_state(user_id: str | int, next_dest: str = "") -> str:
    """Embed a signed user_id (and optional next destination) in the OAuth state so
    the callback works even when the JWT cookie cannot be read."""
    secret = current_app.config.get("SECRET_KEY", "")
    ts = int(time.time())
    # Only include next_dest in payload when provided — keeps legacy 4-part format intact
    if next_dest:
        payload = f"connect_inbox:{user_id}:{ts}:{next_dest}"
    else:
        payload = f"connect_inbox:{user_id}:{ts}"
    sig = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()[:24]
    return f"{payload}:{sig}"


def _parse_connect_state(state: str) -> str | None:
    """Verify and return the user_id from a state made by _make_connect_state.
    Returns None if the state is invalid, tampered, or expired."""
    try:
        parts = state.split(":")
        if parts[0] != "connect_inbox":
            return None
        if len(parts) == 4:
            # Legacy format: connect_inbox:user_id:ts:sig
            _, user_id, ts_str, sig = parts
            payload = f"connect_inbox:{user_id}:{ts_str}"
        elif len(parts) == 5:
            # Extended format: connect_inbox:user_id:ts:next_dest:sig
            _, user_id, ts_str, next_dest, sig = parts
            payload = f"connect_inbox:{user_id}:{ts_str}:{next_dest}"
        else:
            return None
        if int(time.time()) - int(ts_str) > _CONNECT_STATE_TTL:
            return None
        secret = current_app.config.get("SECRET_KEY", "")
        expected = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()[:24]
        if not hmac.compare_digest(sig, expected):
            return None
        return user_id
    except Exception:
        return None


def _get_connect_next(state: str) -> str:
    """Extract the next destination from a connect state. Returns '' if not present."""
    try:
        parts = state.split(":")
        if len(parts) == 5 and parts[0] == "connect_inbox":
            return parts[3]
    except Exception:
        pass
    return ""

# Sign-in only — no restricted scopes, no Google verification required
GOOGLE_SIGNIN_SCOPES = ["openid", "email", "profile"]

# Gmail inbox connection — restricted scopes, requires Google verification for production
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

# Inbox connection — mail + calendar scopes requested after sign-in
MS_MAIL_SCOPES = MS_SIGNIN_SCOPES + [
    "https://graph.microsoft.com/Mail.ReadWrite",
    "https://graph.microsoft.com/Calendars.ReadWrite",
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
    account = Account(name=account_name, seats_limit=2, seats_used=0, created_at=now, updated_at=now)
    db.session.add(account)
    db.session.flush()
    user = User(email=email, password_hash=None, account_id=account.id, role="owner", created_at=now, updated_at=now)
    db.session.add(user)
    db.session.flush()
    # Create billing profile with explicit 7-day trial so the fallback default is never relied on
    try:
        from src.models.billing import CustomerBillingProfile
        billing_profile = CustomerBillingProfile(
            account_id=account.id,
            email=email,
            trial_start=now,
            trial_end=now + timedelta(days=7),
            trial_status="active",
            subscription_status="trialing",
        )
        db.session.add(billing_profile)
    except Exception:
        pass  # Non-fatal — access_control falls back gracefully
    db.session.commit()
    _create_trial_lead(email, account.id)
    return user, True


def _issue_social_session(user: User, is_new: bool):
    """Set JWT cookies and redirect to dashboard (connected) or onboarding (not yet connected)."""
    additional_claims = {"account_id": str(user.account_id)}
    token = create_access_token(identity=str(user.id), additional_claims=additional_claims)
    refresh = create_refresh_token(identity=str(user.id), additional_claims=additional_claims)
    _whitelist_refresh(refresh)
    log_audit("auth.social_login", resource_type="user", resource_id=str(user.id),
              account_id=user.account_id, user_id=user.id)
    has_inbox = InboxConnection.query.filter(
        InboxConnection.account_id == user.account_id,
        InboxConnection.provider.in_(["gmail", "outlook"]),
        InboxConnection.access_token.isnot(None),
    ).first() is not None
    dest = url_for("dashboard_home") if has_inbox else url_for("onboarding_page")
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

    if not resolved_user_id or not account_id:
        raise RuntimeError("login_required")

    # Look up only by (account_id, email_address) — never by user_id alone.
    # A user_id-only fallback can match a connection from a different mailbox
    # and silently adopt/corrupt it.
    conn = InboxConnection.query.filter_by(account_id=account_id, email_address=email_address).first()

    is_new_connection = not conn
    if is_new_connection:
        conn = InboxConnection(
            user_id=resolved_user_id,
            account_id=account_id,
            provider=provider,
            email_address=email_address,
        )
        db.session.add(conn)
    else:
        conn.provider = provider

    conn.access_token = access_token
    if refresh_token:
        conn.refresh_token = refresh_token
    conn.status = "connected"
    meta = conn.metadata_json or {}
    meta.update({"last_poll_status": "never", "last_poll_counts": {"created": 0, "duplicates": 0, "errors": 0, "fetched": 0}})
    conn.metadata_json = meta
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise

    # Send demo emails on first-time inbox connection only.
    # inbox_email is sourced from the OAuth token — not user input.
    # The task itself is idempotent (checks demo_emails_sent flag).
    if is_new_connection and provider in ("gmail", "outlook") and conn.email_address:
        try:
            from src.inbox.tasks import send_demo_emails_task
            send_demo_emails_task.apply_async(
                args=[conn.id, conn.email_address],
                countdown=60,  # 60s delay — let the first poll cycle initialise first
            )
        except Exception:
            # Non-fatal: demo emails failing must never break the connection flow
            current_app.logger.warning(
                "send_demo_emails_task could not be queued for connection %s", conn.id
            )

    return conn


# ── Inbox invite token helpers ────────────────────────────────────────────────

_INVITE_TTL = 72 * 3600  # 72 hours


def _signing_key() -> bytes:
    key = current_app.config.get("SECRET_KEY") or "dev-secret"
    return key.encode()


def make_inbox_invite_token(account_id: int, expected_email: str) -> str:
    """Return a signed, time-limited token encoding account_id + expected_email."""
    nonce = secrets.token_urlsafe(16)
    ts = str(int(time.time()))
    payload = f"{nonce}|{ts}|{account_id}|{expected_email}"
    sig = hmac.new(_signing_key(), payload.encode(), hashlib.sha256).hexdigest()[:24]
    encoded = base64.urlsafe_b64encode(payload.encode()).rstrip(b"=").decode()
    return f"{encoded}.{sig}"


def verify_inbox_invite_token(token: str):
    """Verify a token. Returns (valid: bool, account_id: int | None, expected_email: str)."""
    try:
        encoded, sig = token.rsplit(".", 1)
        padding = "=" * (4 - len(encoded) % 4)
        payload = base64.urlsafe_b64decode(encoded + padding).decode()
        expected_sig = hmac.new(_signing_key(), payload.encode(), hashlib.sha256).hexdigest()[:24]
        if not hmac.compare_digest(sig, expected_sig):
            return False, None, ""
        parts = payload.split("|", 3)
        if len(parts) < 4:
            return False, None, ""
        _, ts_str, account_id_str, expected_email = parts
        if time.time() - int(ts_str) > _INVITE_TTL:
            return False, None, ""
        return True, int(account_id_str), expected_email
    except Exception:
        return False, None, ""


@v1.route("/auth/inbox/accept-invite", methods=["GET"])
def inbox_accept_invite():
    """
    Entry point for the inbox invite link sent to the inbox owner (e.g. Oliver's wife).
    Verifies the signed token then redirects to the appropriate provider OAuth consent screen.
    No InboxIQ login required — the token carries all the context needed.
    """
    token = request.args.get("token", "")
    if not token:
        return _invite_result_page(False, "Invalid or missing invite link.")

    valid, account_id, expected_email = verify_inbox_invite_token(token)
    if not valid:
        return _invite_result_page(False, "This invite link has expired or is invalid. Ask the account owner to send a new one.")

    # Look up the placeholder connection to determine provider
    conn = InboxConnection.query.filter_by(
        account_id=account_id, email_address=expected_email, status="pending"
    ).first()
    if not conn:
        # Already connected — show success
        existing = InboxConnection.query.filter_by(
            account_id=account_id, email_address=expected_email, status="connected"
        ).first()
        if existing:
            return _invite_result_page(True, f"{expected_email} is already connected.")
        return _invite_result_page(False, "Invite not found. It may have already been used or cancelled.")

    # Verify the stored token matches (replay protection)
    if conn.invite_token != token:
        return _invite_result_page(False, "This invite link has already been used.")

    provider = conn.provider or "gmail"

    client_id = current_app.config.get("GOOGLE_CLIENT_ID")
    redirect_uri = current_app.config.get("GOOGLE_REDIRECT_URI") or url_for(".google_callback", _external=True)

    if provider == "gmail":
        if not client_id or not redirect_uri:
            return _invite_result_page(False, "Google OAuth is not configured. Contact support.")
        params = {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "scope": " ".join(GOOGLE_GMAIL_SCOPES),
            "access_type": "offline",
            "prompt": "consent",
            "login_hint": expected_email,
            "state": f"inbox_invite_gcal:{token}",
        }
        return redirect(f"{GOOGLE_AUTH_URL}?{urllib.parse.urlencode(params)}")

    if provider == "outlook":
        ms_client_id = current_app.config.get("MICROSOFT_CLIENT_ID")
        ms_redirect_uri = current_app.config.get("MICROSOFT_REDIRECT_URI") or url_for(".outlook_callback", _external=True)
        if not ms_client_id or not ms_redirect_uri:
            return _invite_result_page(False, "Microsoft OAuth is not configured. Contact support.")
        params = {
            "client_id": ms_client_id,
            "response_type": "code",
            "redirect_uri": ms_redirect_uri,
            "scope": " ".join(MS_MAIL_SCOPES),
            "response_mode": "query",
            "prompt": "consent",
            "login_hint": expected_email,
            "state": f"inbox_invite:{token}",
        }
        return redirect(f"{MS_AUTH_URL}?{urllib.parse.urlencode(params)}")

    return _invite_result_page(False, f"Unsupported provider: {provider}.")


def _complete_invite_connection(provider: str, email: str, access_token: str, refresh_token: str | None, token: str):
    """
    Called from Google/Outlook callbacks when state starts with inbox_invite:.
    Verifies email match, updates the placeholder InboxConnection to connected.
    Returns (success: bool, message: str).
    """
    valid, account_id, expected_email = verify_inbox_invite_token(token)
    if not valid:
        return False, "Invite link expired. Ask the account owner to send a new one."

    if email.lower().strip() != expected_email.lower().strip():
        return False, (
            f"You signed in as {email} but the invite was sent to {expected_email}. "
            "Please sign in with the correct Google account."
        )

    conn = InboxConnection.query.filter_by(
        account_id=account_id, email_address=expected_email
    ).first()
    if not conn:
        return False, "Invite not found. It may have been cancelled."

    if conn.invite_token != token:
        return False, "This invite link has already been used."

    conn.access_token = access_token
    if refresh_token:
        conn.refresh_token = refresh_token
    conn.status = "connected"
    conn.provider = provider
    conn.invite_token = None
    conn.invite_token_expires_at = None
    meta = conn.metadata_json or {}
    meta.update({"last_poll_status": "never", "last_poll_counts": {"created": 0, "duplicates": 0, "errors": 0, "fetched": 0}})
    conn.metadata_json = meta
    db.session.commit()
    current_app.logger.info(
        {"event": "inbox.invite.connected", "account_id": account_id, "email": email, "provider": provider}
    )
    log_audit(
        "inbox.invite.accepted",
        resource_type="inbox_connection",
        resource_id=conn.id,
        details={"email": email, "provider": provider, "account_id": account_id},
    )
    return True, f"Your {provider.title()} inbox has been connected to InboxIQ. You can close this tab."


def _complete_invite_gcal_connection(account_id: int, email: str, access_token: str, refresh_token: str | None) -> None:
    """
    Create or update a gcal InboxConnection for the invited user using tokens
    obtained during the combined Gmail+Calendar invite OAuth flow. Best-effort —
    logs on failure but never raises so the inbox connection result is unaffected.
    """
    from src.crypto import encrypt_value
    try:
        conn = InboxConnection.query.filter_by(account_id=account_id, provider="gcal").first()
        meta = {
            "access_token_enc": encrypt_value(access_token),
            "refresh_token_enc": encrypt_value(refresh_token) if refresh_token else None,
            "scope": "https://www.googleapis.com/auth/calendar",
            "linked_email": email,
        }
        if conn:
            conn.metadata_json = meta
            conn.status = "connected"
        else:
            user = User.query.filter_by(account_id=account_id).first()
            conn = InboxConnection(
                user_id=user.id if user else None,
                account_id=account_id,
                provider="gcal",
                status="connected",
                metadata_json=meta,
            )
            db.session.add(conn)
        db.session.commit()
        current_app.logger.info(
            {"event": "gcal.invite.connected", "account_id": account_id, "email": email}
        )
    except Exception as exc:
        db.session.rollback()
        current_app.logger.warning("gcal invite connection failed account=%s: %s", account_id, exc)


def _save_outlook_cal_connection(account_id: int, email: str, access_token: str, refresh_token: str | None) -> None:
    """
    Create or update an outlook_cal InboxConnection using tokens obtained during
    the Outlook inbox OAuth flow (Calendars.ReadWrite is bundled). Best-effort.
    """
    from src.crypto import encrypt_value
    try:
        conn = InboxConnection.query.filter_by(account_id=account_id, provider="outlook_cal").first()
        meta = {
            "access_token_enc": encrypt_value(access_token),
            "refresh_token_enc": encrypt_value(refresh_token) if refresh_token else None,
            "scope": "https://graph.microsoft.com/Calendars.ReadWrite",
            "linked_email": email,
        }
        if conn:
            conn.metadata_json = meta
            conn.status = "connected"
        else:
            user = User.query.filter_by(account_id=account_id).first()
            conn = InboxConnection(
                user_id=user.id if user else None,
                account_id=account_id,
                provider="outlook_cal",
                status="connected",
                metadata_json=meta,
            )
            db.session.add(conn)
        db.session.commit()
        current_app.logger.info(
            {"event": "outlook_cal.connected", "account_id": account_id, "email": email}
        )
    except Exception as exc:
        db.session.rollback()
        current_app.logger.warning("outlook_cal connection failed account=%s: %s", account_id, exc)


def _invite_result_page(success: bool, message: str) -> str:
    from flask import render_template_string
    color = "#16a34a" if success else "#dc2626"
    icon = "✅" if success else "❌"
    return render_template_string(
        """<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>InboxIQ Inbox Connect</title>
<style>
  body{font-family:-apple-system,sans-serif;display:flex;justify-content:center;
       align-items:center;min-height:100vh;margin:0;background:#f9fafb}
  .card{background:#fff;border-radius:12px;padding:40px 48px;max-width:480px;
        box-shadow:0 4px 24px rgba(0,0,0,.08);text-align:center}
  h2{font-size:22px;margin-bottom:16px}
  p{color:#374151;line-height:1.6}
</style></head>
<body><div class="card">
  <h2 style="color:{{ color }}">{{ icon }} Inbox Connect</h2>
  <p>{{ message }}</p>
</div></body></html>""",
        color=color, icon=icon, message=message,
    )


@v1.route("/auth/google/start", methods=["GET"])
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

    next_dest = request.args.get("next", "")
    if next_dest not in ("dashboard",):
        next_dest = ""

    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": " ".join(GOOGLE_GMAIL_SCOPES),
        "access_type": "offline",
        "prompt": "select_account consent",
        "state": _make_connect_state(get_jwt_identity(), next_dest),
    }
    return redirect(f"{GOOGLE_AUTH_URL}?{urllib.parse.urlencode(params)}")


def _get_jwt_identity_safe() -> str | None:
    """Return the current JWT identity without raising on missing or expired tokens."""
    try:
        verify_jwt_in_request(optional=True)
        return get_jwt_identity()
    except Exception:
        return None


@v1.route("/auth/google/callback", methods=["GET"])
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
    # Prefer user_id from signed state (works for password-auth users whose JWT cookie
    # is on a different subdomain than the callback URL). Fall back to JWT cookie identity.
    user_id = _parse_connect_state(state) or _get_jwt_identity_safe()

    if state.startswith("inbox_invite_gcal:"):
        invite_token = state[len("inbox_invite_gcal:"):]
        ok, message = _complete_invite_connection("gmail", email, access_token, refresh_token, invite_token)
        if ok:
            _, account_id_from_token, _ = verify_inbox_invite_token(invite_token)
            if account_id_from_token:
                _complete_invite_gcal_connection(account_id_from_token, email, access_token, refresh_token)
        return _invite_result_page(ok, message + (" Google Calendar also connected." if ok else ""))

    if state.startswith("inbox_invite:"):
        invite_token = state[len("inbox_invite:"):]
        ok, message = _complete_invite_connection("gmail", email, access_token, refresh_token, invite_token)
        return _invite_result_page(ok, message)

    if state.startswith("connect_inbox:") or state == "connect_inbox":
        # Authenticated user connecting their Gmail inbox — store connection and redirect
        if not user_id:
            return redirect(url_for("login_page") + "?error=login_required")
        try:
            _store_connection("gmail", email, access_token, refresh_token, user_id)
            current_app.logger.info("gmail inbox connected: user_id=%s email=%s", user_id, email)
        except RuntimeError:
            pass
        # Save calendar connection — calendar scope is bundled into the Gmail auth flow
        # so the same tokens cover Calendar access. Best-effort, never blocks the redirect.
        user_obj = User.query.get(user_id)
        if user_obj and user_obj.account_id:
            _complete_invite_gcal_connection(user_obj.account_id, email, access_token, refresh_token)
        # Bootstrap InboxIQ labels and category filters immediately on connect.
        # Demonstrates gmail.modify (label creation) and gmail.settings.basic (filter creation)
        # before the first poll runs. Best-effort — never block the redirect.
        try:
            from src.inbox.poll import bootstrap_inboxiq_labels_gmail, bootstrap_gmail_filters
            label_ids = bootstrap_inboxiq_labels_gmail(access_token)
            bootstrap_gmail_filters(access_token, label_ids)
            current_app.logger.info("gmail bootstrap complete: user_id=%s", user_id)
        except Exception as exc:
            current_app.logger.warning("gmail bootstrap at connect failed user_id=%s: %s", user_id, exc)
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

    next_dest = request.args.get("next", "")
    if next_dest not in ("dashboard",):
        next_dest = ""

    params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "scope": " ".join(MS_MAIL_SCOPES),
        "response_mode": "query",
        "state": _make_connect_state(get_jwt_identity(), next_dest),
        "prompt": "consent",
    }
    return redirect(f"{MS_AUTH_URL}?{urllib.parse.urlencode(params)}")


@v1.route("/auth/outlook/callback", methods=["GET"])
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
    _is_connect = state.startswith("connect_inbox:") or state == "connect_inbox"
    scopes = MS_MAIL_SCOPES if (_is_connect or state.startswith("inbox_invite:")) else MS_SIGNIN_SCOPES

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
    user_id = _parse_connect_state(state) or _get_jwt_identity_safe()

    if state.startswith("inbox_invite:"):
        invite_token = state[len("inbox_invite:"):]
        ok, message = _complete_invite_connection("outlook", email, access_token, refresh_token, invite_token)
        if ok:
            _, account_id_from_token, _ = verify_inbox_invite_token(invite_token)
            if account_id_from_token:
                _save_outlook_cal_connection(account_id_from_token, email, access_token, refresh_token)
        return _invite_result_page(ok, message)

    if _is_connect:
        # Authenticated user connecting their Outlook inbox
        if not user_id:
            return redirect(url_for("login_page") + "?error=login_required")
        try:
            _store_connection("outlook", email, access_token, refresh_token, user_id)
            current_app.logger.info("outlook inbox connected: user_id=%s email=%s", user_id, email)
        except RuntimeError:
            pass
        # Save calendar connection — Calendars.ReadWrite is bundled into the Outlook auth flow
        user_obj = User.query.get(user_id)
        if user_obj and user_obj.account_id:
            _save_outlook_cal_connection(user_obj.account_id, email, access_token, refresh_token)
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
