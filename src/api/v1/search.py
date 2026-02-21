import hashlib
import os
import time
from collections import defaultdict
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urljoin

import requests
from flask import request, jsonify, g
from flask_jwt_extended import jwt_required
from sqlalchemy import func
from src.api.v1 import v1
from src.extensions import db
from src.models import Ticket, IntakeToken
from src.api.v1.access_control import account_allows_api
from src.api.v1.app_auth import _require_registered_app, _NO_BASIC_AUTH

SEARXNG_URL = os.getenv("SEARXNG_URL", "").rstrip("/")
SEARXNG_ENGINES = [e.strip() for e in (os.getenv("SEARXNG_ENGINES") or "").split(",") if e.strip()]
SEARXNG_TIMEOUT = float(os.getenv("SEARXNG_TIMEOUT", "10"))

_RATE_LIMIT_WINDOW = 60  # seconds
_RATE_LIMIT_MAX = 120  # requests per token per window
_RATE_LIMITS = defaultdict(list)


def _to_tsquery(term: str) -> str:
    # Simple sanitizer: replace spaces with & for AND search, quote phrases as needed.
    cleaned = " & ".join(t for t in term.split() if t)
    return cleaned or ""


def _client_ip() -> str:
    xff = request.headers.get("X-Forwarded-For")
    if xff:
        return xff.split(",")[0].strip()
    return request.remote_addr or ""


def _verify_api_key() -> Optional[tuple]:
    # Try RegisteredApp Basic Auth first (new scheme)
    result = _require_registered_app("tickets:read")
    if result is not _NO_BASIC_AUTH:
        return result  # None = success, tuple = error

    # Fall back to legacy X-API-Key scheme
    api_key = request.headers.get("X-API-Key")
    if not api_key:
        return jsonify({"error": "unauthorized", "message": "missing api key or credentials"}), 401

    header_hash = hashlib.sha256(api_key.encode("utf-8")).hexdigest()
    token_row = IntakeToken.query.filter_by(token_hash=header_hash, revoked_at=None).first()
    if not token_row:
        return jsonify({"error": "unauthorized"}), 401
    g.intake_account_id = token_row.account_id

    now = datetime.now(timezone.utc)
    if token_row.expires_at and token_row.expires_at < now:
        return jsonify({"error": "unauthorized", "message": "token expired"}), 401

    client_ip = _client_ip()
    if token_row.allowed_ips:
        if not client_ip or client_ip not in token_row.allowed_ips:
            return jsonify({"error": "forbidden", "message": "ip_not_allowed"}), 403

    ts_now = int(time.time())
    window_start = ts_now - _RATE_LIMIT_WINDOW
    entries = _RATE_LIMITS[header_hash]
    entries[:] = [t for t in entries if t >= window_start]
    if len(entries) >= _RATE_LIMIT_MAX:
        return jsonify({"error": "rate_limited"}), 429
    entries.append(ts_now)

    return None


@v1.route("/search/tickets", methods=["GET"])
@jwt_required()
def search_tickets():
    q = (request.args.get("q") or "").strip()
    if not q:
        return jsonify({"results": [], "total": 0})
    ts_query = _to_tsquery(q)
    ts_vector = func.to_tsvector("english", func.coalesce(Ticket.subject, "") + " " + func.coalesce(Ticket.body_preview, ""))
    query = (
        db.session.query(
            Ticket.id,
            Ticket.subject,
            Ticket.body_preview,
            Ticket.priority,
            Ticket.category,
            Ticket.created_at,
            func.ts_rank(ts_vector, func.to_tsquery("english", ts_query)).label("rank"),
        )
        .filter(ts_vector.op("@@")(func.to_tsquery("english", ts_query)))
        .order_by(db.desc("rank"))
        .limit(20)
    )
    rows = query.all()
    results = [
        {
            "id": r.id,
            "subject": r.subject,
            "body_preview": r.body_preview,
            "priority": r.priority,
            "category": r.category,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "rank": float(r.rank or 0),
        }
        for r in rows
    ]
    return jsonify({"results": results, "total": len(results)})

# 
@v1.route("/search", methods=["GET"])
def searx_proxy():
    """
    Authenticated proxy to SearxNG for external agents.
    Expects: X-API-Key header containing a valid IntakeToken plaintext.
    """
    if not SEARXNG_URL:
        return jsonify({"error": "config_error", "message": "SEARXNG_URL not set"}), 500

    auth_err = _verify_api_key()
    if auth_err:
        return auth_err

    account_id = getattr(g, "intake_account_id", None)
    if not account_allows_api(account_id):
        return (
            jsonify(
                {
                    "error": "plan_required",
                    "message": "API/webhooks require Business plan or active trial. Contact sales to upgrade.",
                }
            ),
            403,
        )

    query = (request.args.get("q") or "").strip()
    if not query:
        return jsonify({"error": "validation_error", "message": "missing query"}), 400

    params = {"q": query, "format": "json"}
    if SEARXNG_ENGINES:
        params["engines"] = ",".join(SEARXNG_ENGINES)

    try:
        resp = requests.get(
            urljoin(SEARXNG_URL + "/", "search"),
            params=params,
            timeout=SEARXNG_TIMEOUT,
            headers={"User-Agent": "kalevent-searx-proxy"},
        )
        resp.raise_for_status()
        data = resp.json()
        return jsonify({"results": data.get("results", []), "source": "searxng"})
    except requests.exceptions.HTTPError as exc:
        return jsonify({"error": "upstream_http_error", "status": exc.response.status_code}), exc.response.status_code
    except Exception as exc:  # pragma: no cover - defensive
        return jsonify({"error": "upstream_error", "message": str(exc)}), 502
