"""
Public landing page routes for ad campaign pages.

GET  /lp/<slug>       — render a published landing page; pass UTM params to template
POST /lp/<slug>/lead  — public lead capture form submission (rate-limited)

Lead capture creates a Lead + LeadAttribution row and also attributes any referral
cookie set by the referral program.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import uuid4

from flask import Blueprint, abort, jsonify, render_template, request

from src.extensions import db, limiter
from src.funnel.stages import DISCOVERY
from src.models.leads import Lead, LeadAttribution
from src.models.marketing import LandingPage
from src.sanitize import sanitize_html

logger = logging.getLogger(__name__)

bp = Blueprint("landing_pages", __name__)


@bp.route("/<slug>", methods=["GET"])
def view_landing_page(slug: str):
    """Render a published landing page."""
    page = LandingPage.query.filter_by(slug=slug, status="published").first()
    if not page:
        abort(404)

    # Increment view counter (best-effort)
    try:
        page.view_count = (page.view_count or 0) + 1
        db.session.commit()
    except Exception:
        db.session.rollback()

    utm = {
        "utm_source": request.args.get("utm_source", ""),
        "utm_medium": request.args.get("utm_medium", ""),
        "utm_campaign": request.args.get("utm_campaign", ""),
        "utm_term": request.args.get("utm_term", ""),
        "utm_content": request.args.get("utm_content", ""),
    }

    return render_template("lp/page.html", page=page, utm=utm)


@bp.route("/<slug>/lead", methods=["POST"])  # nosemgrep: inboxiq.auth.unprotected-write-endpoint
@limiter.limit("10 per minute", override_defaults=False)
def capture_lead(slug: str):
    """
    Public lead capture endpoint for landing page forms.

    Accepts JSON or form-encoded body:
        name        — required
        email       — required
        company     — optional
        phone       — optional
        utm_source, utm_medium, utm_campaign, utm_term, utm_content — passed by form hidden fields

    Returns:
        {"status": "ok", "lead_id": "..."}
    """
    if request.is_json:
        data = request.get_json(silent=True) or {}
    else:
        data = request.form.to_dict()

    # Honeypot: bots fill hidden fields, humans don't
    if data.get("website"):
        return jsonify({"status": "ok"}), 201  # silent reject

    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip().lower()

    if not name or not email:
        return jsonify({"error": "name and email are required"}), 400

    page = LandingPage.query.filter_by(slug=slug, status="published").first()
    if not page:
        return jsonify({"error": "not found"}), 404

    company = (data.get("company") or "").strip() or None
    phone = (data.get("phone") or "").strip() or None

    utm_source = (data.get("utm_source") or "").strip() or None
    utm_medium = (data.get("utm_medium") or "").strip() or None
    utm_campaign = (data.get("utm_campaign") or "").strip() or None
    utm_term = (data.get("utm_term") or "").strip() or None

    try:
        lead_id = str(uuid4())
        now = datetime.now(timezone.utc)

        lead = Lead(
            id=lead_id,
            account_id=page.account_id,
            name=name,
            email=email,
            company_name=company,
            phone=phone,
            source=utm_source or "landing_page",
            utm_source=utm_source,
            utm_medium=utm_medium,
            utm_campaign=utm_campaign,
            utm_term=utm_term,
            current_funnel_stage=DISCOVERY,
            stage_entered_at=now,
        )
        db.session.add(lead)

        attribution = LeadAttribution(
            id=str(uuid4()),
            lead_id=lead_id,
            touchpoint_order=1,
            source=utm_source or "direct",
            medium=utm_medium,
            campaign=utm_campaign,
            term=utm_term,
            attribution_model="first_touch",
            attribution_weight=1.0,
            touched_at=now,
        )
        db.session.add(attribution)

        # Attribute referral if cookie is present
        try:
            from src.api.v1.referrals import convert_referral_from_request
            convert_referral_from_request(email)
        except Exception as exc:
            logger.debug("Referral attribution skipped: %s", exc)

        # Increment lead counter
        page.lead_count = (page.lead_count or 0) + 1

        db.session.commit()
        logger.info("Landing page lead captured: %s (page=%s, account=%s)", email, slug, page.account_id)

        return jsonify({"status": "ok", "lead_id": lead_id}), 201

    except Exception as exc:
        db.session.rollback()
        logger.error("Landing page lead capture failed (slug=%s): %s", slug, exc)
        return jsonify({"error": "An error occurred. Please try again."}), 500
