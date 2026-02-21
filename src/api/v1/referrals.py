"""
Referral program API.

Endpoints:
  POST /api/v1/referrals/generate   — generate a referral code for a lead (jwt_required)
  GET  /api/v1/referrals/track      — public; record click + set cookie, redirect to homepage
  GET  /api/v1/referrals/my-stats   — referral stats for the calling lead (jwt_required)

Referral codes are 12-char URL-safe random strings.
The `ref_code` cookie is read by the intake endpoint to mark conversions.
"""
from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import datetime, timezone

from flask import jsonify, redirect, request, make_response
from flask_jwt_extended import jwt_required, get_jwt_identity

from src.api.v1 import v1
from src.extensions import db
from src.models import Lead, Referral, User

logger = logging.getLogger(__name__)

_REF_COOKIE = "ref_code"
_COOKIE_MAX_AGE = 60 * 60 * 24 * 30  # 30 days


def _account_id_for_user(user_id: int) -> int | None:
    user = db.session.get(User, user_id)
    return user.account_id if user else None


@v1.route("/referrals/generate", methods=["POST"])
@jwt_required()
def generate_referral():
    """
    Generate (or return existing) referral code for the caller.

    Body (JSON, all optional):
        referrer_email: str   — if omitted, uses caller's email
        lead_id: str          — link to a specific lead record
        source_page: str      — e.g. "settings", "dashboard"

    Returns:
        {
            "referral_code": "abc123xyz",
            "referral_url": "https://kalevent.com/ref/abc123xyz",
            "status": "pending" | "existing"
        }
    """
    user_id = get_jwt_identity()
    account_id = _account_id_for_user(user_id)
    if not account_id:
        return jsonify({"error": "account not found"}), 404

    body = request.get_json(silent=True) or {}
    referrer_email = body.get("referrer_email") or ""
    lead_id = body.get("lead_id")
    source_page = body.get("source_page", "")

    if not referrer_email and lead_id:
        lead = db.session.get(Lead, lead_id)
        referrer_email = lead.email if lead else ""

    if not referrer_email:
        user = db.session.get(User, user_id)
        referrer_email = user.email if user else ""

    if not referrer_email:
        return jsonify({"error": "referrer_email is required"}), 400

    # Return existing code if one already exists for this email + account
    existing = db.session.query(Referral).filter_by(
        account_id=account_id,
        referrer_email=referrer_email,
        status="pending",
    ).first()
    if existing:
        return jsonify({
            "referral_code": existing.referral_code,
            "referral_url": _ref_url(existing.referral_code),
            "status": "existing",
        }), 200

    code = secrets.token_urlsafe(9)  # 12 URL-safe chars
    referral = Referral(
        account_id=account_id,
        referrer_lead_id=lead_id,
        referrer_email=referrer_email,
        referral_code=code,
        source_page=source_page[:255] if source_page else None,
    )
    db.session.add(referral)
    db.session.commit()

    logger.info("Referral code generated: %s for %s (account %s)", code, referrer_email, account_id)
    return jsonify({
        "referral_code": code,
        "referral_url": _ref_url(code),
        "status": "pending",
    }), 201


@v1.route("/referrals/track", methods=["GET"])
def track_referral():
    """
    Public endpoint — record a referral link click and redirect to homepage.

    Query params:
        code: str  — the referral code

    Sets a `ref_code` cookie (30 days) so the intake endpoint can attribute the signup.
    """
    code = request.args.get("code", "").strip()
    if not code:
        return redirect("/", code=302)

    referral = db.session.query(Referral).filter_by(referral_code=code).first()
    if referral and referral.status == "pending":
        referral.status = "clicked"
        referral.clicked_at = datetime.now(timezone.utc)
        referral.ip_hash = _hash_ip(request.remote_addr or "")
        db.session.commit()
        logger.info("Referral clicked: %s", code)

    resp = make_response(redirect("/", code=302))
    resp.set_cookie(
        _REF_COOKIE,
        code,
        max_age=_COOKIE_MAX_AGE,
        httponly=True,
        samesite="Lax",
        secure=True,
    )
    return resp


@v1.route("/referrals/my-stats", methods=["GET"])
@jwt_required()
def my_referral_stats():
    """
    Stats for the currently authenticated user's referrals.

    Returns:
        {
            "total": N,
            "clicked": N,
            "converted": N,
            "referrals": [{code, status, created_at, referred_email}]
        }
    """
    user_id = get_jwt_identity()
    account_id = _account_id_for_user(user_id)
    user = db.session.get(User, user_id)
    if not user or not account_id:
        return jsonify({"error": "not found"}), 404

    rows = db.session.query(Referral).filter_by(
        account_id=account_id,
        referrer_email=user.email,
    ).order_by(Referral.created_at.desc()).limit(50).all()

    return jsonify({
        "total": len(rows),
        "clicked": sum(1 for r in rows if r.status in ("clicked", "converted", "rewarded")),
        "converted": sum(1 for r in rows if r.status in ("converted", "rewarded")),
        "referrals": [
            {
                "code": r.referral_code,
                "status": r.status,
                "created_at": r.created_at.isoformat(),
                "referred_email": r.referred_email,
            }
            for r in rows
        ],
    }), 200


def convert_referral_from_request(referred_email: str) -> None:
    """
    Called by the intake endpoint after a successful lead/signup.
    Reads the ref_code cookie and marks the matching Referral as converted.
    Safe to call; silently no-ops if no cookie or no matching referral.
    """
    code = request.cookies.get(_REF_COOKIE, "").strip()
    if not code:
        return
    try:
        referral = db.session.query(Referral).filter_by(referral_code=code).first()
        if referral and referral.status in ("pending", "clicked"):
            referral.status = "converted"
            referral.referred_email = referred_email
            referral.converted_at = datetime.now(timezone.utc)
            # Don't commit here — let the caller's transaction commit it
            logger.info("Referral converted: %s → %s", code, referred_email)
    except Exception as exc:
        logger.warning("Failed to convert referral %s: %s", code, exc)


# ── helpers ───────────────────────────────────────────────────────────────────

def _ref_url(code: str) -> str:
    return f"https://kalevent.com/ref/{code}"


def _hash_ip(ip: str) -> str:
    return hashlib.sha256(ip.encode()).hexdigest()
