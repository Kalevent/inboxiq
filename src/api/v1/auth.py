from __future__ import annotations

import base64
import json
import urllib.parse

import requests
from flask import Blueprint, current_app, jsonify, redirect, request, url_for
from flask_jwt_extended import get_jwt_identity, jwt_required

from src.api.v1 import v1
from src.models import InboxConnection
from src.extensions import db


GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_SCOPES = [
    "openid",
    "email",
    "profile",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
]

MS_AUTH_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/authorize"
MS_TOKEN_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
MS_SCOPES = [
    "openid",
    "offline_access",
    "email",
    "profile",
    "https://graph.microsoft.com/User.Read",
    "https://graph.microsoft.com/Mail.ReadWrite",
]


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
    account_id = None
    try:
        from src.models import User

        if user_id:
            u = User.query.get(user_id)
            account_id = getattr(u, "account_id", None)
    except Exception:
        account_id = None

    conn = InboxConnection.query.filter_by(user_id=user_id, provider=provider).first()
    if not conn:
        conn = InboxConnection(
            user_id=user_id or 0,
            account_id=account_id,
            provider=provider,
            email_address=email_address,
        )
        db.session.add(conn)

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
    client_id = current_app.config.get("GOOGLE_CLIENT_ID")
    redirect_uri = current_app.config.get("GOOGLE_REDIRECT_URI") or url_for(".google_callback", _external=True)
    if not client_id or not redirect_uri:
        return jsonify({"error": "Google OAuth not configured"}), 500

    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": " ".join(GOOGLE_SCOPES),
        "access_type": "offline",
        "include_granted_scopes": "true",
        "prompt": "consent",
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
    id_token = tok.get("id_token", "")
    email = _decode_id_token_raw(id_token).get("email") or request.args.get("email") or "unknown@gmail.com"
    access_token = tok.get("access_token")
    refresh_token = tok.get("refresh_token")
    user_id = get_jwt_identity()
    _store_connection("gmail", email, access_token, refresh_token, user_id)
    return redirect(url_for("dashboard_home"))


@v1.route("/auth/outlook/start", methods=["GET"])
@jwt_required(optional=True)
def outlook_start():
    client_id = current_app.config.get("MICROSOFT_CLIENT_ID")
    redirect_uri = current_app.config.get("MICROSOFT_REDIRECT_URI") or url_for(".outlook_callback", _external=True)
    if not client_id or not redirect_uri:
        return jsonify({"error": "Microsoft OAuth not configured"}), 500

    params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "scope": " ".join(MS_SCOPES),
        "response_mode": "query",
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

    token_data = {
        "client_id": client_id,
        "client_secret": client_secret,
        "code": code,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
        "scope": " ".join(MS_SCOPES),
    }
    resp = requests.post(MS_TOKEN_URL, data=token_data, timeout=15)
    if resp.status_code != 200:
        return jsonify({"error": "Failed to exchange code", "details": resp.text}), 502
    tok = resp.json()
    id_token = tok.get("id_token", "")
    email = _decode_id_token_raw(id_token).get("preferred_username") or request.args.get("email") or "unknown@outlook.com"
    access_token = tok.get("access_token")
    refresh_token = tok.get("refresh_token")
    user_id = get_jwt_identity()
    _store_connection("outlook", email, access_token, refresh_token, user_id)
    return redirect(url_for("dashboard_home"))
