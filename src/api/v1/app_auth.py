"""
RegisteredApp authentication helper — HTTP Basic Auth.

Usage:
    err = _require_registered_app("intake:write")
    if err:
        return err
    # g.intake_account_id and g.intake_app are now set

Callers try this first, then fall back to their legacy token scheme so
existing integrations keep working without any changes.
"""
import hmac
from datetime import datetime, timezone

from flask import g, jsonify, request, current_app

from src.api.v1.access_control import account_allows_api
from src.crypto import decrypt_value
from src.extensions import db
from src.models.developer import RegisteredApp


def _require_registered_app(required_scope: str):
    """Authenticate via HTTP Basic Auth (client_id : client_secret).

    Returns None on success — sets g.intake_account_id and g.intake_app.
    Returns a Flask (response, status) tuple on failure.
    Returns the sentinel value ``_NO_BASIC_AUTH`` when no Authorization header
    is present so callers can fall back to their legacy scheme.
    """
    auth = request.authorization
    if not auth or not auth.username or not auth.password:
        return _NO_BASIC_AUTH  # not a Basic Auth request

    client_id = auth.username
    client_secret = auth.password

    app = RegisteredApp.query.filter_by(client_id=client_id, status="active").first()
    if not app:
        return jsonify({"error": "unauthorized", "message": "invalid credentials"}), 401

    # Decrypt stored secret and compare in constant time
    try:
        stored_secret = decrypt_value(app.client_secret_enc)
    except Exception:
        current_app.logger.error(f"app_auth: failed to decrypt secret client_id={client_id}")
        return jsonify({"error": "unauthorized"}), 401

    if not hmac.compare_digest(stored_secret, client_secret):
        return jsonify({"error": "unauthorized", "message": "invalid credentials"}), 401

    # Scope check
    if required_scope and required_scope not in (app.scopes or []):
        return jsonify({
            "error": "forbidden",
            "message": f"scope '{required_scope}' not granted for this app",
        }), 403

    # IP allowlist
    if app.allowed_ips:
        remote_ip = (
            request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
            or request.remote_addr
            or ""
        )
        if remote_ip not in app.allowed_ips:
            return jsonify({"error": "forbidden", "message": "ip_not_allowed"}), 403

    # Origin allowlist — enforced for browser-based requests (forms, widgets).
    # Server-to-server calls carry no Origin header and are not restricted here.
    origin = request.headers.get("Origin", "").rstrip("/")
    if origin and app.allowed_origins:
        allowed = [o.rstrip("/") for o in (app.allowed_origins or [])]
        if origin not in allowed:
            return jsonify({"error": "forbidden", "message": "origin_not_allowed"}), 403

    # Plan check
    if not account_allows_api(app.account_id):
        return jsonify({
            "error": "plan_required",
            "message": "API access requires Business plan or active trial.",
        }), 403

    # Update last_used_at (best-effort — don't fail the request if this errors)
    try:
        app.last_used_at = datetime.now(timezone.utc)
        db.session.commit()
    except Exception:
        db.session.rollback()

    g.intake_account_id = app.account_id
    g.intake_app = app
    return None


# Sentinel — distinct from None (success) and a response tuple (error)
class _NoBasicAuth:
    pass

_NO_BASIC_AUTH = _NoBasicAuth()
