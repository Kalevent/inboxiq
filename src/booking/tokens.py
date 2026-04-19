import base64
import hashlib
import hmac
import json
import time as time_module

from flask import current_app

_TTL_SECONDS = 7 * 24 * 3600  # 7 days


def _secret() -> bytes:
    return current_app.config["SECRET_KEY"].encode()


def make_booking_token(payload: dict) -> str:
    """
    Sign a booking payload and return a URL-safe token string.

    payload must contain: account_id, ticket_id, subject,
    requester_email, requester_name, duration_minutes.
    """
    data = {**payload, "exp": int(time_module.time()) + _TTL_SECONDS}
    body = json.dumps(data, separators=(",", ":"), sort_keys=True)
    sig = hmac.new(_secret(), body.encode(), hashlib.sha256).hexdigest()
    encoded = base64.urlsafe_b64encode(body.encode()).decode().rstrip("=")
    return f"{encoded}.{sig}"


def verify_booking_token(token: str) -> dict | None:
    """
    Verify HMAC signature and expiry. Returns decoded payload or None.
    """
    try:
        encoded, sig = token.rsplit(".", 1)
        padding = "=" * (-len(encoded) % 4)
        body = base64.urlsafe_b64decode(encoded + padding).decode()
        expected = hmac.new(_secret(), body.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected):
            return None
        data = json.loads(body)
        if time_module.time() > data.get("exp", 0):
            return None
        return data
    except Exception:
        return None


def token_to_hash(token: str) -> str:
    """SHA-256 hash of the token string for DB storage (64 hex chars)."""
    return hashlib.sha256(token.encode()).hexdigest()
