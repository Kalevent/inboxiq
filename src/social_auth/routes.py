"""
Social OAuth callback routes  (blueprint: social_auth, prefix: /social_auth)

LinkedIn flow:
  GET /social_auth/linkedin           → redirect to LinkedIn for authorisation
  GET /social_auth/linkedin/callback  → exchange code for token, save encrypted

Twitter (X) OAuth 2.0 + PKCE flow:
  GET /social_auth/twitter            → redirect to Twitter for authorisation
  GET /social_auth/twitter/callback   → exchange code for token, save encrypted

Multi-tenant: each account connects its own token. The logged-in user's
account_id is embedded in the HMAC-signed state token at OAuth start and
extracted at callback — no session or DEFAULT_ACCOUNT_ID needed.

State token format (pipe-separated, base64url-encoded):
  nonce | unix_timestamp | account_id | pkce_verifier
  (pkce_verifier is empty for LinkedIn)

Required env vars:
  LINKEDIN_CLIENT_ID
  LINKEDIN_CLIENT_SECRET
  LINKEDIN_REDIRECT_URI   (e.g. https://kalevent.com/social_auth/linkedin/callback)
  TWITTER_CLIENT_ID       (OAuth 2.0 client ID from Developer Portal)
  TWITTER_CLIENT_SECRET   (OAuth 2.0 client secret)
  TWITTER_REDIRECT_URI    (e.g. https://kalevent.com/social_auth/twitter/callback)
"""
import base64
import hashlib
import hmac
import os
import secrets
import time
import urllib.parse
from uuid import uuid4

import requests
from flask import current_app, g, redirect, render_template_string, request, url_for

from src.crypto import encrypt_value
from src.extensions import db
from src.models.core import InboxConnection, User
from src.settings import login_required_settings
from src.social_auth import bp

_AUTH_URL = "https://www.linkedin.com/oauth/v2/authorization"
_TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"
_SCOPE = "openid profile email w_member_social"
_PROVIDER = "linkedin_social"

_TW_AUTH_URL = "https://twitter.com/i/oauth2/authorize"
_TW_TOKEN_URL = "https://api.twitter.com/2/oauth2/token"
_TW_USERINFO_URL = "https://api.twitter.com/2/users/me"
_TW_SCOPE = "tweet.read tweet.write users.read offline.access"
_TW_PROVIDER = "twitter_social"


# ── HMAC state helpers (no session needed) ───────────────────────────────────

_STATE_TTL = 600  # 10 minutes


def _signing_key() -> bytes:
    key = current_app.config.get("SECRET_KEY") or os.getenv("SECRET_KEY") or "dev-secret"
    return key.encode()


def _make_state(account_id: int, pkce_verifier: str = "") -> str:
    """Return a self-verifying, time-limited state token.

    Payload format (pipe-separated, base64url-encoded):
      nonce | unix_timestamp | account_id | pkce_verifier
    account_id is the logged-in user's account — extracted at callback.
    pkce_verifier is only populated for Twitter PKCE flows.
    """
    nonce = secrets.token_urlsafe(16)
    ts = str(int(time.time()))
    payload = f"{nonce}|{ts}|{account_id}|{pkce_verifier}"
    sig = hmac.new(_signing_key(), payload.encode(), hashlib.sha256).hexdigest()[:24]
    encoded = base64.urlsafe_b64encode(payload.encode()).rstrip(b"=").decode()
    return f"{encoded}.{sig}"


def _verify_state(state: str):
    """Verify a state token. Returns (valid: bool, account_id: int | None, pkce_verifier: str).

    Rejects tokens older than _STATE_TTL seconds or with invalid signatures.
    """
    try:
        encoded, sig = state.rsplit(".", 1)
        padding = "=" * (4 - len(encoded) % 4)
        payload = base64.urlsafe_b64decode(encoded + padding).decode()
        expected = hmac.new(_signing_key(), payload.encode(), hashlib.sha256).hexdigest()[:24]
        if not hmac.compare_digest(sig, expected):
            return False, None, ""
        parts = payload.split("|", 3)
        if len(parts) < 4:
            return False, None, ""
        _, ts_str, account_id_str, pkce_verifier = parts
        if time.time() - int(ts_str) > _STATE_TTL:
            return False, None, ""
        account_id = int(account_id_str) if account_id_str else None
        if not account_id:
            return False, None, ""
        return True, account_id, pkce_verifier
    except Exception:
        return False, None, ""


# ── Redirect URI helpers ──────────────────────────────────────────────────────

def _callback_uri():
    override = os.getenv("LINKEDIN_REDIRECT_URI")
    if override:
        return override
    return url_for("social_auth.linkedin_callback", _external=True)


def _tw_callback_uri():
    override = os.getenv("TWITTER_REDIRECT_URI")
    if override:
        return override
    return url_for("social_auth.twitter_callback", _external=True)


def _pkce_pair():
    """Return (code_verifier, code_challenge) for PKCE."""
    verifier = base64.urlsafe_b64encode(os.urandom(40)).rstrip(b"=").decode()
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return verifier, challenge


# ── Token save helper ─────────────────────────────────────────────────────────

def _save_connection(account_id: int, provider: str, metadata: dict):
    """Upsert an InboxConnection for the given account and provider."""
    user = User.query.filter_by(account_id=account_id).first()
    if not user:
        raise RuntimeError(f"No user found for account_id={account_id}")

    existing = InboxConnection.query.filter_by(
        account_id=account_id, provider=provider
    ).first()

    if existing:
        existing.metadata_json = metadata
        existing.status = "connected"
    else:
        db.session.add(InboxConnection(
            id=str(uuid4()),
            account_id=account_id,
            user_id=user.id,
            provider=provider,
            status="connected",
            metadata_json=metadata,
        ))
    db.session.commit()


# ── LinkedIn start ────────────────────────────────────────────────────────────

@bp.route("/linkedin")
@login_required_settings
def linkedin_start():
    """Kick off LinkedIn OAuth for the logged-in account."""
    client_id = current_app.config.get("LINKEDIN_CLIENT_ID") or os.getenv("LINKEDIN_CLIENT_ID")
    if not client_id:
        current_app.logger.error("LinkedIn OAuth: LINKEDIN_CLIENT_ID not configured")
        return "Configuration error.", 500

    account_id = g.current_account_id
    if not account_id:
        return _page(False, "Could not determine your account. Please log in again.")

    state = _make_state(account_id)
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": _callback_uri(),
        "scope": _SCOPE,
        "state": state,
    }
    return redirect(_AUTH_URL + "?" + urllib.parse.urlencode(params))


# ── LinkedIn callback ─────────────────────────────────────────────────────────

@bp.route("/linkedin/callback")
def linkedin_callback():
    """LinkedIn sends the browser here with ?code=... after the user approves."""

    error = request.args.get("error")
    if error:
        return _page(False, f"LinkedIn denied: {request.args.get('error_description', error)}")

    code = request.args.get("code")
    state = request.args.get("state")

    if not state:
        return _page(False, "Missing state parameter.")

    valid, account_id, _ = _verify_state(state)
    if not valid or not account_id:
        return _page(False, "Invalid state — possible CSRF. Please try again.")

    if not code:
        return _page(False, "No authorization code returned by LinkedIn.")

    client_id = current_app.config.get("LINKEDIN_CLIENT_ID") or os.getenv("LINKEDIN_CLIENT_ID")
    client_secret = current_app.config.get("LINKEDIN_CLIENT_SECRET") or os.getenv("LINKEDIN_CLIENT_SECRET")
    if not client_id or not client_secret:
        current_app.logger.error("LinkedIn OAuth: credentials not configured")
        return _page(False, "Server configuration error. Contact the administrator.")

    # Exchange code → access_token
    try:
        token_resp = requests.post(
            _TOKEN_URL,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={
                "grant_type": "authorization_code",
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": _callback_uri(),
            },
            timeout=10,
        )
        if not token_resp.ok:
            current_app.logger.error(
                f"LinkedIn token exchange HTTP {token_resp.status_code}: {token_resp.text}"
            )
        token_resp.raise_for_status()
        token_data = token_resp.json()
    except Exception as exc:
        current_app.logger.exception(f"LinkedIn token exchange failed: {exc}")
        return _page(False, "Connection failed. Please try again.")

    access_token = token_data.get("access_token")
    if not access_token:
        current_app.logger.error("LinkedIn: no access_token in response")
        return _page(False, "Connection failed. Please try again.")

    # Persist encrypted token
    try:
        _save_connection(account_id, _PROVIDER, {
            "access_token_enc": encrypt_value(access_token),
            "expires_in": token_data.get("expires_in"),
            "scope": _SCOPE,
        })
    except Exception as exc:
        db.session.rollback()
        current_app.logger.exception(f"LinkedIn save failed for account={account_id}: {exc}")
        return _page(False, "Connection failed. Please try again.")

    current_app.logger.info(f"LinkedIn connected: account={account_id}")
    return _page(True, "LinkedIn connected successfully.", "LinkedIn")


# ── Twitter start ─────────────────────────────────────────────────────────────

@bp.route("/twitter")
@login_required_settings
def twitter_start():
    """Kick off Twitter OAuth 2.0 + PKCE for the logged-in account."""
    client_id = current_app.config.get("TWITTER_CLIENT_ID") or os.getenv("TWITTER_CLIENT_ID")
    if not client_id:
        current_app.logger.error("Twitter OAuth: TWITTER_CLIENT_ID not configured")
        return "Configuration error.", 500

    account_id = g.current_account_id
    if not account_id:
        return _page(False, "Could not determine your account. Please log in again.", "Twitter")

    verifier, challenge = _pkce_pair()
    state = _make_state(account_id, pkce_verifier=verifier)

    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": _tw_callback_uri(),
        "scope": _TW_SCOPE,
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    return redirect(_TW_AUTH_URL + "?" + urllib.parse.urlencode(params))


# ── Twitter callback ──────────────────────────────────────────────────────────

@bp.route("/twitter/callback")
def twitter_callback():
    """Twitter sends the browser here with ?code=... after the user approves."""

    error = request.args.get("error")
    if error:
        return _page(False, f"Twitter denied: {request.args.get('error_description', error)}", "Twitter")

    code = request.args.get("code")
    state = request.args.get("state")

    if not state:
        return _page(False, "Missing state parameter.", "Twitter")

    valid, account_id, verifier = _verify_state(state)
    if not valid or not account_id:
        return _page(False, "Invalid state — possible CSRF. Please try again.", "Twitter")

    if not code or not verifier:
        return _page(False, "Missing authorization code or PKCE verifier.", "Twitter")

    client_id = current_app.config.get("TWITTER_CLIENT_ID") or os.getenv("TWITTER_CLIENT_ID")
    client_secret = current_app.config.get("TWITTER_CLIENT_SECRET") or os.getenv("TWITTER_CLIENT_SECRET")
    if not client_id:
        current_app.logger.error("Twitter OAuth: TWITTER_CLIENT_ID not configured")
        return _page(False, "Server configuration error. Contact the administrator.", "Twitter")

    # Exchange code → access_token
    try:
        auth = (client_id, client_secret) if client_secret else None
        token_resp = requests.post(
            _TW_TOKEN_URL,
            auth=auth,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": _tw_callback_uri(),
                "code_verifier": verifier,
                "client_id": client_id,
            },
            timeout=10,
        )
        if not token_resp.ok:
            current_app.logger.error(
                f"Twitter token exchange HTTP {token_resp.status_code}: {token_resp.text}"
            )
        token_resp.raise_for_status()
        token_data = token_resp.json()
    except Exception as exc:
        current_app.logger.exception(f"Twitter token exchange failed: {exc}")
        return _page(False, "Connection failed. Please try again.", "Twitter")

    access_token = token_data.get("access_token")
    if not access_token:
        current_app.logger.error("Twitter: no access_token in response")
        return _page(False, "Connection failed. Please try again.", "Twitter")

    refresh_token = token_data.get("refresh_token")

    # Fetch Twitter username
    twitter_username = None
    twitter_id = None
    try:
        me = requests.get(
            _TW_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10,
        ).json()
        data = me.get("data", {})
        twitter_username = data.get("username") or data.get("name")
        twitter_id = data.get("id")
    except Exception:
        pass

    # Persist encrypted token
    try:
        _save_connection(account_id, _TW_PROVIDER, {
            "access_token_enc": encrypt_value(access_token),
            "refresh_token_enc": encrypt_value(refresh_token) if refresh_token else None,
            "twitter_username": twitter_username,
            "twitter_id": twitter_id,
            "expires_in": token_data.get("expires_in"),
            "scope": _TW_SCOPE,
        })
    except Exception as exc:
        db.session.rollback()
        current_app.logger.exception(f"Twitter save failed for account={account_id}: {exc}")
        return _page(False, "Connection failed. Please try again.", "Twitter")

    current_app.logger.info(f"Twitter connected: account={account_id} username=@{twitter_username}")
    display = f"@{twitter_username}" if twitter_username else "your account"
    return _page(True, f"X (Twitter) connected as {display}.", "Twitter")


# ── Minimal result page ───────────────────────────────────────────────────────

def _page(success: bool, message: str, platform: str = "LinkedIn") -> str:
    return render_template_string(
        """<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>{{ platform }} OAuth</title>
<style>
  body{font-family:-apple-system,sans-serif;display:flex;justify-content:center;
       align-items:center;min-height:100vh;margin:0;background:#f9fafb}
  .card{background:#fff;border-radius:12px;padding:40px 48px;max-width:480px;
        box-shadow:0 4px 24px rgba(0,0,0,.08);text-align:center}
  h2{color:{{ color }};font-size:22px;margin-bottom:16px}
  p{color:#374151;line-height:1.6}
  a.back{display:inline-block;margin-top:24px;padding:10px 20px;background:#2563eb;
         color:#fff;border-radius:6px;text-decoration:none;font-weight:600}
</style></head>
<body><div class="card">
  <h2>{{ icon }} {{ platform }} OAuth</h2><p>{{ message }}</p>
  <a class="back" href="/settings?tab=integrations">Back to Integrations</a>
</div></body></html>""",
        color="#16a34a" if success else "#dc2626",
        icon="✅" if success else "❌",
        platform=platform,
        message=message,
    )
