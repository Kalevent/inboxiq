import os
from typing import Optional
from urllib.parse import urljoin

import requests
from flask import request, jsonify, g
from flask_jwt_extended import jwt_required
from sqlalchemy import func
from src.api.v1 import v1
from src.extensions import db
from src.models import Ticket
from src.api.v1.access_control import account_allows_api
from src.api.v1.app_auth import _require_registered_app, _NO_BASIC_AUTH

SEARXNG_URL = os.getenv("SEARXNG_URL", "").rstrip("/")
SEARXNG_ENGINES = [e.strip() for e in (os.getenv("SEARXNG_ENGINES") or "").split(",") if e.strip()]
SEARXNG_TIMEOUT = float(os.getenv("SEARXNG_TIMEOUT", "10"))


def _to_tsquery(term: str) -> str:
    cleaned = " & ".join(t for t in term.split() if t)
    return cleaned or ""


def _client_ip() -> str:
    xff = request.headers.get("X-Forwarded-For")
    if xff:
        return xff.split(",")[0].strip()
    return request.remote_addr or ""


def _verify_api_key() -> Optional[tuple]:
    """Authenticate via RegisteredApp Basic Auth (client_id:client_secret)."""
    result = _require_registered_app("tickets:read")
    if result is _NO_BASIC_AUTH:
        return jsonify({"error": "unauthorized", "message": "credentials required — use HTTP Basic Auth with your client_id and client_secret"}), 401
    return result  # None = success, tuple = error response


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
    Expects: HTTP Basic Auth with client_id and client_secret (tickets:read scope).
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
