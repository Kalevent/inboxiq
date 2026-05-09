"""
Social OAuth callback routes  (blueprint: social_auth, prefix: /social_auth)

LinkedIn flow:
  GET /social_auth/linkedin           → redirect to LinkedIn for authorisation
  GET /social_auth/linkedin/callback  → exchange code for token, save encrypted

Twitter (X) OAuth 2.0 + PKCE flow:
  GET /social_auth/twitter            → redirect to Twitter for authorisation
  GET /social_auth/twitter/callback   → exchange code for token, save encrypted

Facebook OAuth 2.0 flow:
  GET /social_auth/facebook           → redirect to Facebook for authorisation
  GET /social_auth/facebook/callback  → exchange code for token, save encrypted

Required env vars:
  LINKEDIN_CLIENT_ID, LINKEDIN_CLIENT_SECRET, LINKEDIN_REDIRECT_URI
  TWITTER_CLIENT_ID, TWITTER_CLIENT_SECRET, TWITTER_REDIRECT_URI
  FACEBOOK_CLIENT_ID, FACEBOOK_CLIENT_SECRET, FACEBOOK_REDIRECT_URI
"""
import base64
import hashlib
import hmac
import os
import secrets
import time
import urllib.parse
from typing import Optional
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
# NOTE: LinkedIn org-page posting requires the r_organization_admin scope.
# Before adding it here, request "Marketing Developer Platform" access in the
# LinkedIn Developer Portal for this app — without it, OAuth requests with
# r_organization_admin will fail. Once approved + added below, existing
# linkedin_social connections must disconnect/reconnect to populate
# metadata_json["org_id"] via _fetch_admin_organization_id.
_SCOPE = "openid profile email w_member_social w_organization_social"
_PROVIDER = "linkedin_social"

_TW_AUTH_URL = "https://twitter.com/i/oauth2/authorize"
_TW_TOKEN_URL = "https://api.twitter.com/2/oauth2/token"
_TW_USERINFO_URL = "https://api.twitter.com/2/users/me"
_TW_SCOPE = "tweet.read tweet.write users.read offline.access"
_TW_PROVIDER = "twitter_social"

_FB_AUTH_URL = "https://www.facebook.com/v19.0/dialog/oauth"
_FB_TOKEN_URL = "https://graph.facebook.com/v19.0/oauth/access_token"
_FB_ME_URL = "https://graph.facebook.com/v19.0/me"
_FB_SCOPE = "pages_manage_posts,pages_read_engagement,pages_show_list"
_FB_PROVIDER = "facebook_social"


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


def _fb_callback_uri():
    override = os.getenv("FACEBOOK_REDIRECT_URI")
    if override:
        return override
    return url_for("social_auth.facebook_callback", _external=True)


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


# ── LinkedIn helpers ──────────────────────────────────────────────────────────

def _resolve_org_id(account_id: int, fresh_org_id: Optional[str]) -> Optional[str]:
    """Return the org_id to persist, preferring fresh_org_id when present.

    If fresh_org_id is None (e.g. transient network error or missing scope),
    fall back to the previously-persisted org_id from an existing
    ``linkedin_social`` connection so that a re-OAuth cannot silently wipe
    a valid org_id.
    """
    if fresh_org_id:
        return fresh_org_id
    existing = InboxConnection.query.filter_by(
        account_id=account_id, provider=_PROVIDER
    ).first()
    if existing:
        return (existing.metadata_json or {}).get("org_id") or None
    return None


def _fetch_admin_organization_id(access_token: str) -> Optional[str]:
    """Return the numeric ID of the first LinkedIn org the user can administer, or None.

    Calls /v2/organizationAcls to discover which organisations the authenticated user
    has ADMINISTRATOR role on.  Requires the ``r_organization_admin`` scope — if the
    OAuth flow does not request that scope the endpoint returns an empty elements list
    and this function returns None.  In that case posting will skip with
    ``not_configured`` until the user reconnects with the full scope set.

    NOTE: Existing ``linkedin_social`` connections were created before ``org_id`` was
    captured.  Account holders must disconnect + reconnect once to populate
    ``metadata_json['org_id']``.  Until then, ``_post_to_linkedin`` returns
    ``{"status": "skipped", "reason": "not_configured"}``.
    """
    try:
        resp = requests.get(
            "https://api.linkedin.com/v2/organizationAcls",
            params={"q": "roleAssignee", "role": "ADMINISTRATOR", "state": "APPROVED"},
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=15,
        )
        resp.raise_for_status()
        elements = (resp.json() or {}).get("elements") or []
        if not elements:
            return None
        urn = elements[0].get("organizationalTarget", "")  # 'urn:li:organization:999'
        return urn.rsplit(":", 1)[-1] or None
    except Exception:
        return None


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

    # Fetch admin org_id (best-effort — requires r_organization_admin scope)
    fresh_org_id = _fetch_admin_organization_id(access_token)
    if not fresh_org_id:
        current_app.logger.warning(
            f"LinkedIn: could not fetch admin org_id for account={account_id} "
            "(missing r_organization_admin scope or no admin org found)"
        )

    # Resolve: use fresh value when available, otherwise preserve any existing
    # org_id so that a re-OAuth with a failing fetch cannot silently wipe it.
    org_id = _resolve_org_id(account_id, fresh_org_id)

    # Persist encrypted token + org_id
    metadata: dict = {
        "access_token_enc": encrypt_value(access_token),
        "expires_in": token_data.get("expires_in"),
        "scope": _SCOPE,
    }
    if org_id:
        metadata["org_id"] = org_id

    try:
        _save_connection(account_id, _PROVIDER, metadata)
    except Exception as exc:
        db.session.rollback()
        current_app.logger.exception(f"LinkedIn save failed for account={account_id}: {exc}")
        return _page(False, "Connection failed. Please try again.")

    current_app.logger.info(f"LinkedIn connected: account={account_id}, org_id={org_id!r}")
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


# ── Facebook start ────────────────────────────────────────────────────────────

@bp.route("/facebook")
@login_required_settings
def facebook_start():
    """Kick off Facebook OAuth for the logged-in account."""
    client_id = current_app.config.get("FACEBOOK_CLIENT_ID") or os.getenv("FACEBOOK_CLIENT_ID")
    if not client_id:
        current_app.logger.error("Facebook OAuth: FACEBOOK_CLIENT_ID not configured")
        return "Configuration error.", 500

    account_id = g.current_account_id
    if not account_id:
        return _page(False, "Could not determine your account. Please log in again.", "Facebook")

    state = _make_state(account_id)
    params = {
        "client_id": client_id,
        "redirect_uri": _fb_callback_uri(),
        "scope": _FB_SCOPE,
        "state": state,
        "response_type": "code",
    }
    return redirect(_FB_AUTH_URL + "?" + urllib.parse.urlencode(params))


# ── Facebook callback ──────────────────────────────────────────────────────────

@bp.route("/facebook/callback")
def facebook_callback():
    """Facebook sends the browser here with ?code=... after the user approves."""

    error = request.args.get("error")
    if error:
        desc = request.args.get("error_description") or request.args.get("error_reason") or error
        return _page(False, f"Facebook denied: {desc}", "Facebook")

    code = request.args.get("code")
    state = request.args.get("state")

    if not state:
        return _page(False, "Missing state parameter.", "Facebook")

    valid, account_id, _ = _verify_state(state)
    if not valid or not account_id:
        return _page(False, "Invalid state — possible CSRF. Please try again.", "Facebook")

    if not code:
        return _page(False, "No authorization code returned by Facebook.", "Facebook")

    client_id = current_app.config.get("FACEBOOK_CLIENT_ID") or os.getenv("FACEBOOK_CLIENT_ID")
    client_secret = current_app.config.get("FACEBOOK_CLIENT_SECRET") or os.getenv("FACEBOOK_CLIENT_SECRET")
    if not client_id or not client_secret:
        current_app.logger.error("Facebook OAuth: credentials not configured")
        return _page(False, "Server configuration error. Contact the administrator.", "Facebook")

    # Exchange code → access_token
    try:
        token_resp = requests.get(
            _FB_TOKEN_URL,
            params={
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": _fb_callback_uri(),
                "code": code,
            },
            timeout=10,
        )
        if not token_resp.ok:
            current_app.logger.error(
                f"Facebook token exchange HTTP {token_resp.status_code}: {token_resp.text}"
            )
        token_resp.raise_for_status()
        token_data = token_resp.json()
    except Exception as exc:
        current_app.logger.exception(f"Facebook token exchange failed: {exc}")
        return _page(False, "Connection failed. Please try again.", "Facebook")

    access_token = token_data.get("access_token")
    if not access_token:
        current_app.logger.error("Facebook: no access_token in response")
        return _page(False, "Connection failed. Please try again.", "Facebook")

    # Fetch user info and pages
    fb_user_id = None
    fb_name = None
    pages = []
    try:
        me = requests.get(
            _FB_ME_URL,
            params={"fields": "id,name", "access_token": access_token},
            timeout=10,
        ).json()
        fb_user_id = me.get("id")
        fb_name = me.get("name")

        # Fetch pages the user manages
        pages_resp = requests.get(
            f"https://graph.facebook.com/v19.0/{fb_user_id}/accounts",
            params={"access_token": access_token},
            timeout=10,
        ).json()
        pages = pages_resp.get("data", [])
    except Exception:
        pass

    # Persist encrypted token (user token + page tokens)
    try:
        metadata = {
            "access_token_enc": encrypt_value(access_token),
            "fb_user_id": fb_user_id,
            "fb_name": fb_name,
            "scope": _FB_SCOPE,
            "pages": [
                {
                    "id": p.get("id"),
                    "name": p.get("name"),
                    "access_token_enc": encrypt_value(p["access_token"]) if p.get("access_token") else None,
                }
                for p in pages
            ],
        }
        _save_connection(account_id, _FB_PROVIDER, metadata)
    except Exception as exc:
        db.session.rollback()
        current_app.logger.exception(f"Facebook save failed for account={account_id}: {exc}")
        return _page(False, "Connection failed. Please try again.", "Facebook")

    current_app.logger.info(f"Facebook connected: account={account_id} user={fb_name} pages={len(pages)}")
    page_info = f" with {len(pages)} page(s)" if pages else ""
    return _page(True, f"Facebook connected as {fb_name or 'your account'}{page_info}.", "Facebook")


# ── Google Calendar ───────────────────────────────────────────────────────────

_GCAL_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
_GCAL_TOKEN_URL = "https://oauth2.googleapis.com/token"
_GCAL_SCOPE = "https://www.googleapis.com/auth/calendar"
_GCAL_PROVIDER = "gcal"


def _gcal_callback_uri():
    override = os.getenv("GCAL_REDIRECT_URI")
    if override:
        return override
    return url_for("social_auth.gcal_callback", _external=True)


@bp.route("/gcal")
@login_required_settings
def gcal_start():
    """Kick off Google Calendar OAuth for the logged-in account."""
    client_id = current_app.config.get("GOOGLE_CLIENT_ID") or os.getenv("GOOGLE_CLIENT_ID")
    if not client_id:
        current_app.logger.error("Google Calendar OAuth: GOOGLE_CLIENT_ID not configured")
        return "Configuration error.", 500

    account_id = g.current_account_id
    if not account_id:
        return _page(False, "Could not determine your account. Please log in again.", "Google Calendar")

    state = _make_state(account_id)
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": _gcal_callback_uri(),
        "scope": _GCAL_SCOPE,
        "state": state,
        "access_type": "offline",
        "prompt": "consent",
    }
    return redirect(_GCAL_AUTH_URL + "?" + urllib.parse.urlencode(params))


@bp.route("/gcal/callback")
def gcal_callback():
    """Google sends the browser here with ?code=... after the user approves."""

    error = request.args.get("error")
    if error:
        return _page(False, f"Google denied: {error}", "Google Calendar")

    code = request.args.get("code")
    state = request.args.get("state")

    if not state:
        return _page(False, "Missing state parameter.", "Google Calendar")

    valid, account_id, _ = _verify_state(state)
    if not valid or not account_id:
        return _page(False, "Invalid state — possible CSRF. Please try again.", "Google Calendar")

    if not code:
        return _page(False, "No authorization code returned by Google.", "Google Calendar")

    client_id = current_app.config.get("GOOGLE_CLIENT_ID") or os.getenv("GOOGLE_CLIENT_ID")
    client_secret = current_app.config.get("GOOGLE_CLIENT_SECRET") or os.getenv("GOOGLE_CLIENT_SECRET")
    if not client_id or not client_secret:
        current_app.logger.error("Google Calendar OAuth: credentials not configured")
        return _page(False, "Server configuration error. Contact the administrator.", "Google Calendar")

    # Exchange code → tokens
    try:
        token_resp = requests.post(
            _GCAL_TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": _gcal_callback_uri(),
            },
            timeout=10,
        )
        if not token_resp.ok:
            current_app.logger.error(
                f"Google Calendar token exchange HTTP {token_resp.status_code}: {token_resp.text}"
            )
        token_resp.raise_for_status()
        token_data = token_resp.json()
    except Exception as exc:
        current_app.logger.exception(f"Google Calendar token exchange failed: {exc}")
        return _page(False, "Connection failed. Please try again.", "Google Calendar")

    access_token = token_data.get("access_token")
    if not access_token:
        current_app.logger.error("Google Calendar: no access_token in response")
        return _page(False, "Connection failed. Please try again.", "Google Calendar")

    refresh_token = token_data.get("refresh_token")

    try:
        _save_connection(account_id, _GCAL_PROVIDER, {
            "access_token_enc": encrypt_value(access_token),
            "refresh_token_enc": encrypt_value(refresh_token) if refresh_token else None,
            "expires_in": token_data.get("expires_in"),
            "scope": _GCAL_SCOPE,
        })
    except Exception as exc:
        db.session.rollback()
        current_app.logger.exception(f"Google Calendar save failed for account={account_id}: {exc}")
        return _page(False, "Connection failed. Please try again.", "Google Calendar")

    current_app.logger.info(f"Google Calendar connected: account={account_id}")
    return _page(True, "Google Calendar connected successfully.", "Google Calendar")


# ── Microsoft Outlook Calendar ───────────────────────────────────────────────

_OUTLOOK_CAL_AUTH_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/authorize"
_OUTLOOK_CAL_TOKEN_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
_OUTLOOK_CAL_SCOPE = "openid offline_access https://graph.microsoft.com/Calendars.ReadWrite"
_OUTLOOK_CAL_PROVIDER = "outlook_cal"


def _outlook_cal_callback_uri():
    override = os.getenv("OUTLOOK_CAL_REDIRECT_URI")
    if override:
        return override
    return url_for("social_auth.outlook_cal_callback", _external=True)


@bp.route("/outlook_cal")
@login_required_settings
def outlook_cal_start():
    """Kick off Microsoft Calendar OAuth for the logged-in account."""
    client_id = current_app.config.get("MICROSOFT_CLIENT_ID") or os.getenv("MICROSOFT_CLIENT_ID")
    if not client_id:
        current_app.logger.error("Outlook Calendar OAuth: MICROSOFT_CLIENT_ID not configured")
        return "Configuration error.", 500

    account_id = g.current_account_id
    if not account_id:
        return _page(False, "Could not determine your account. Please log in again.", "Outlook Calendar")

    state = _make_state(account_id)
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": _outlook_cal_callback_uri(),
        "scope": _OUTLOOK_CAL_SCOPE,
        "state": state,
        "response_mode": "query",
    }
    return redirect(_OUTLOOK_CAL_AUTH_URL + "?" + urllib.parse.urlencode(params))


@bp.route("/outlook_cal/callback")
def outlook_cal_callback():
    """Microsoft sends the browser here with ?code=... after the user approves."""

    error = request.args.get("error")
    if error:
        desc = request.args.get("error_description") or error
        return _page(False, f"Microsoft denied: {desc}", "Outlook Calendar")

    code = request.args.get("code")
    state = request.args.get("state")

    if not state:
        return _page(False, "Missing state parameter.", "Outlook Calendar")

    valid, account_id, _ = _verify_state(state)
    if not valid or not account_id:
        return _page(False, "Invalid state — possible CSRF. Please try again.", "Outlook Calendar")

    if not code:
        return _page(False, "No authorization code returned by Microsoft.", "Outlook Calendar")

    client_id = current_app.config.get("MICROSOFT_CLIENT_ID") or os.getenv("MICROSOFT_CLIENT_ID")
    client_secret = current_app.config.get("MICROSOFT_CLIENT_SECRET") or os.getenv("MICROSOFT_CLIENT_SECRET")
    if not client_id or not client_secret:
        current_app.logger.error("Outlook Calendar OAuth: credentials not configured")
        return _page(False, "Server configuration error. Contact the administrator.", "Outlook Calendar")

    # Exchange code → tokens
    try:
        token_resp = requests.post(
            _OUTLOOK_CAL_TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": _outlook_cal_callback_uri(),
                "scope": _OUTLOOK_CAL_SCOPE,
            },
            timeout=10,
        )
        if not token_resp.ok:
            current_app.logger.error(
                f"Outlook Calendar token exchange HTTP {token_resp.status_code}: {token_resp.text}"
            )
        token_resp.raise_for_status()
        token_data = token_resp.json()
    except Exception as exc:
        current_app.logger.exception(f"Outlook Calendar token exchange failed: {exc}")
        return _page(False, "Connection failed. Please try again.", "Outlook Calendar")

    access_token = token_data.get("access_token")
    if not access_token:
        current_app.logger.error("Outlook Calendar: no access_token in response")
        return _page(False, "Connection failed. Please try again.", "Outlook Calendar")

    refresh_token = token_data.get("refresh_token")

    try:
        _save_connection(account_id, _OUTLOOK_CAL_PROVIDER, {
            "access_token_enc": encrypt_value(access_token),
            "refresh_token_enc": encrypt_value(refresh_token) if refresh_token else None,
            "expires_in": token_data.get("expires_in"),
            "scope": _OUTLOOK_CAL_SCOPE,
        })
    except Exception as exc:
        db.session.rollback()
        current_app.logger.exception(f"Outlook Calendar save failed for account={account_id}: {exc}")
        return _page(False, "Connection failed. Please try again.", "Outlook Calendar")

    current_app.logger.info(f"Outlook Calendar connected: account={account_id}")
    return _page(True, "Outlook Calendar connected successfully.", "Outlook Calendar")


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
