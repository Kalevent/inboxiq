"""
Admin API endpoints for marketing visibility.

Provides:
- GET  /api/v1/admin/marketing/ab-results      — per-step A/B test evaluation
- GET  /api/v1/admin/marketing/nurture-stats   — aggregate send stats
- GET  /api/v1/admin/marketing/referral-stats  — referral programme totals
- GET  /api/v1/admin/marketing/attribution     — UTM source / campaign breakdown
- GET  /api/v1/admin/messages                  — list broadcast messages
- POST /api/v1/admin/messages                  — create broadcast message
- DELETE /api/v1/admin/messages/<id>           — delete broadcast message
- GET    /api/v1/admin/landing-pages           — list landing pages
- POST   /api/v1/admin/landing-pages           — create landing page
- PATCH  /api/v1/admin/landing-pages/<id>      — update landing page
- DELETE /api/v1/admin/landing-pages/<id>      — delete landing page
"""
from datetime import datetime, timedelta, timezone

from flask import jsonify, request, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity

from src.api.v1 import v1
from src.extensions import db
from src.models import InAppMessage, InAppMessageDismissal, LandingPage, Lead, LeadAttribution, NurtureEmailSend, Referral, User
from src.sanitize import sanitize_html
import logging

logger = logging.getLogger(__name__)


def _require_admin():
    """Check if user is admin based on email allowlist."""
    user_id = get_jwt_identity()
    user = db.session.get(User, user_id) if user_id else None
    default_admin = "support@kalevent.com"
    allowed = set(
        e.strip().lower()
        for e in (current_app.config.get("ADMIN_EMAILS", "") or default_admin).split(",")
        if e.strip()
    )
    if not user or (allowed and user.email.lower() not in allowed):
        return None
    return user


@v1.route("/admin/marketing/ab-results", methods=["GET"])
@jwt_required()
def get_ab_test_results():
    """
    Get live A/B test evaluation for all nurture campaign steps.

    Query params:
        lookback_days: Days to look back (default: 30)

    Returns:
        {
            "steps": [{
                "key": "discovery:day1",
                "campaign_type": "discovery",
                "sequence_day": 1,
                "winner": "A" | "B" | "inconclusive",
                "reason": "...",
                "variant_a": {"sends": N, "opens": N, "open_rate": N},
                "variant_b": {"sends": N, "opens": N, "open_rate": N},
                "z_score": N,
                "p_value": N,
                "lift_pct": N
            }],
            "lookback_days": int,
            "evaluated_at": ISO timestamp
        }
    """
    if not _require_admin():
        return jsonify({"error": "forbidden"}), 403

    try:
        lookback_days = int(request.args.get("lookback_days", 30))
    except (ValueError, TypeError):
        return jsonify({"error": "lookback_days must be an integer"}), 400

    try:
        from src.marketing.ab_testing import _evaluate_step

        steps = [
            ("discovery", 1),
            ("discovery", 3),
            ("discovery", 7),
            ("discovery", 14),
            ("discovery", 21),
            ("consideration", 1),
            ("consideration", 3),
            ("consideration", 7),
            ("consideration", 14),
        ]

        results = []
        for campaign_type, day in steps:
            result = _evaluate_step(campaign_type, day, lookback_days)
            result["key"] = f"{campaign_type}:day{day}"
            results.append(result)

        return jsonify({
            "steps": results,
            "lookback_days": lookback_days,
            "evaluated_at": datetime.now(timezone.utc).isoformat(),
        }), 200

    except Exception as exc:
        logger.exception("Failed to get A/B results: %s", exc)
        return jsonify({"error": str(exc)}), 500


@v1.route("/admin/marketing/nurture-stats", methods=["GET"])
@jwt_required()
def get_nurture_stats():
    """
    Get aggregate nurture send statistics.

    Returns:
        {
            "total_sends": int,
            "total_opens": int,
            "overall_open_rate": float,
            "by_campaign": {
                "discovery": {"sends": N, "opens": N, "open_rate": N},
                "consideration": {...}
            },
            "by_vertical": {"b2b_saas": N, ...},
            "by_variant": {
                "A": {"sends": N, "opens": N, "open_rate": N},
                "B": {...}
            }
        }
    """
    if not _require_admin():
        return jsonify({"error": "forbidden"}), 403

    try:
        total = db.session.query(
            db.func.count().label("sends"),
            db.func.sum(db.cast(NurtureEmailSend.opened, db.Integer)).label("opens"),
        ).filter(
            NurtureEmailSend.ab_variant.in_(["A", "B"]),
        ).one()

        total_sends = total.sends or 0
        total_opens = int(total.opens or 0)

        by_campaign_rows = db.session.query(
            NurtureEmailSend.campaign_type,
            db.func.count().label("sends"),
            db.func.sum(db.cast(NurtureEmailSend.opened, db.Integer)).label("opens"),
        ).filter(
            NurtureEmailSend.ab_variant.in_(["A", "B"]),
        ).group_by(NurtureEmailSend.campaign_type).all()

        by_campaign = {}
        for row in by_campaign_rows:
            sends = row.sends or 0
            opens = int(row.opens or 0)
            by_campaign[row.campaign_type] = {
                "sends": sends,
                "opens": opens,
                "open_rate": round(opens / sends, 4) if sends else 0,
            }

        sends_col = db.func.count().label("sends")
        by_vertical_rows = db.session.query(
            NurtureEmailSend.vertical,
            sends_col,
        ).filter(
            NurtureEmailSend.ab_variant.in_(["A", "B"]),
            NurtureEmailSend.vertical.isnot(None),
        ).group_by(NurtureEmailSend.vertical).order_by(db.desc(sends_col)).limit(10).all()

        by_vertical = {row.vertical: row.sends for row in by_vertical_rows}

        by_variant_rows = db.session.query(
            NurtureEmailSend.ab_variant,
            db.func.count().label("sends"),
            db.func.sum(db.cast(NurtureEmailSend.opened, db.Integer)).label("opens"),
        ).filter(
            NurtureEmailSend.ab_variant.in_(["A", "B"]),
        ).group_by(NurtureEmailSend.ab_variant).all()

        by_variant = {}
        for row in by_variant_rows:
            sends = row.sends or 0
            opens = int(row.opens or 0)
            by_variant[row.ab_variant] = {
                "sends": sends,
                "opens": opens,
                "open_rate": round(opens / sends, 4) if sends else 0,
            }

        return jsonify({
            "total_sends": total_sends,
            "total_opens": total_opens,
            "overall_open_rate": round(total_opens / total_sends, 4) if total_sends else 0,
            "by_campaign": by_campaign,
            "by_vertical": by_vertical,
            "by_variant": by_variant,
        }), 200

    except Exception as exc:
        logger.exception("Failed to get nurture stats: %s", exc)
        return jsonify({"error": str(exc)}), 500


# ── Referral Stats ─────────────────────────────────────────────────────────────

@v1.route("/admin/marketing/referral-stats", methods=["GET"])
@jwt_required()
def get_referral_stats():
    """
    Aggregate referral programme statistics.

    Returns:
        {
            "total_codes": N,
            "clicked": N,
            "converted": N,
            "conversion_rate": float,
            "recent": [{code, referrer_email, status, created_at, referred_email}]
        }
    """
    if not _require_admin():
        return jsonify({"error": "forbidden"}), 403

    try:
        rows = db.session.query(Referral).order_by(Referral.created_at.desc()).limit(100).all()
        total = len(rows)
        clicked = sum(1 for r in rows if r.status in ("clicked", "converted", "rewarded"))
        converted = sum(1 for r in rows if r.status in ("converted", "rewarded"))

        return jsonify({
            "total_codes": total,
            "clicked": clicked,
            "converted": converted,
            "conversion_rate": round(converted / total, 4) if total else 0,
            "recent": [
                {
                    "code": r.referral_code,
                    "referrer_email": r.referrer_email,
                    "status": r.status,
                    "created_at": r.created_at.isoformat(),
                    "referred_email": r.referred_email,
                }
                for r in rows[:20]
            ],
        }), 200

    except Exception as exc:
        logger.exception("Failed to get referral stats: %s", exc)
        return jsonify({"error": str(exc)}), 500


# ── Attribution Report ─────────────────────────────────────────────────────────

@v1.route("/admin/marketing/attribution", methods=["GET"])
@jwt_required()
def get_admin_attribution_report():
    """
    UTM-based attribution report from existing Lead and LeadAttribution data.

    Query params:
        days: Number of days to look back (default: 30)

    Returns:
        {
            "by_source": [{"source", "leads", "conversions", "conv_rate"}],
            "by_campaign": [{"campaign", "leads", "conversions", "conv_rate"}],
            "channel_mix": {"organic": %, "paid": %, "referral": %, "direct": %},
            "totals": {"leads": N, "conversions": N, "overall_conv_rate": float},
            "period_days": int
        }
    """
    if not _require_admin():
        return jsonify({"error": "forbidden"}), 403

    try:
        days = int(request.args.get("days", 30))
    except (ValueError, TypeError):
        return jsonify({"error": "days must be an integer"}), 400

    try:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        conversion_stages = ("conversion", "retention")

        # Leads created in period grouped by utm_source
        source_rows = db.session.query(
            db.func.coalesce(Lead.utm_source, Lead.source, "direct").label("src"),
            db.func.count().label("leads"),
            db.func.sum(
                db.cast(Lead.current_funnel_stage.in_(conversion_stages), db.Integer)
            ).label("conversions"),
        ).filter(
            Lead.deleted == False,  # noqa: E712
            Lead.created_at >= cutoff,
        ).group_by(db.text("src")).order_by(db.desc(db.func.count())).limit(15).all()

        by_source = []
        total_leads = 0
        total_conv = 0
        for row in source_rows:
            leads = row.leads or 0
            convs = int(row.conversions or 0)
            total_leads += leads
            total_conv += convs
            by_source.append({
                "source": row.src or "direct",
                "leads": leads,
                "conversions": convs,
                "conv_rate": round(convs / leads, 4) if leads else 0,
            })

        # By campaign
        campaign_rows = db.session.query(
            db.func.coalesce(Lead.utm_campaign, "none").label("campaign"),
            db.func.count().label("leads"),
            db.func.sum(
                db.cast(Lead.current_funnel_stage.in_(conversion_stages), db.Integer)
            ).label("conversions"),
        ).filter(
            Lead.deleted == False,  # noqa: E712
            Lead.created_at >= cutoff,
            Lead.utm_campaign.isnot(None),
        ).group_by(db.text("campaign")).order_by(db.desc(db.func.count())).limit(10).all()

        by_campaign = [
            {
                "campaign": row.campaign,
                "leads": row.leads or 0,
                "conversions": int(row.conversions or 0),
                "conv_rate": round(int(row.conversions or 0) / (row.leads or 1), 4),
            }
            for row in campaign_rows
        ]

        # Channel mix: classify sources into buckets
        organic_srcs = {"organic", "seo", "google_organic", "bing_organic"}
        paid_srcs = {"cpc", "ppc", "paid", "google", "bing", "facebook", "meta",
                     "linkedin_ads", "twitter_ads", "display"}
        referral_srcs = {"referral", "linkedin", "twitter", "partner", "affiliate"}

        channel_counts = {"organic": 0, "paid": 0, "referral": 0, "direct": 0}
        for row in source_rows:
            src = (row.src or "direct").lower()
            leads = row.leads or 0
            if src in organic_srcs or "organic" in src:
                channel_counts["organic"] += leads
            elif src in paid_srcs or "paid" in src or "cpc" in src or "ads" in src:
                channel_counts["paid"] += leads
            elif src in referral_srcs or "referral" in src:
                channel_counts["referral"] += leads
            else:
                channel_counts["direct"] += leads

        channel_total = sum(channel_counts.values()) or 1
        channel_mix = {ch: round(n / channel_total * 100, 1) for ch, n in channel_counts.items()}

        return jsonify({
            "by_source": by_source,
            "by_campaign": by_campaign,
            "channel_mix": channel_mix,
            "totals": {
                "leads": total_leads,
                "conversions": total_conv,
                "overall_conv_rate": round(total_conv / total_leads, 4) if total_leads else 0,
            },
            "period_days": days,
        }), 200

    except Exception as exc:
        logger.exception("Failed to get attribution report: %s", exc)
        return jsonify({"error": str(exc)}), 500


# ── Broadcast Messages (admin CRUD) ───────────────────────────────────────────

@v1.route("/admin/messages", methods=["GET"])
@jwt_required()
def list_messages():
    """List all broadcast messages (drafts + published)."""
    if not _require_admin():
        return jsonify({"error": "forbidden"}), 403

    msgs = db.session.query(InAppMessage).order_by(InAppMessage.created_at.desc()).all()
    now = datetime.now(timezone.utc)
    return jsonify({
        "messages": [
            {
                "id": m.id,
                "title": m.title,
                "body": m.body,
                "type": m.type,
                "target": m.target,
                "target_account_id": m.target_account_id,
                "cta_text": m.cta_text,
                "cta_url": m.cta_url,
                "published_at": m.published_at.isoformat() if m.published_at else None,
                "expires_at": m.expires_at.isoformat() if m.expires_at else None,
                "created_at": m.created_at.isoformat(),
                "is_active": bool(
                    m.published_at
                    and m.published_at <= now
                    and (m.expires_at is None or m.expires_at > now)
                ),
            }
            for m in msgs
        ]
    }), 200


@v1.route("/admin/messages", methods=["POST"])
@jwt_required()
def create_message():
    """
    Create a broadcast message.

    Body:
        title: str (required)
        body: str (required)
        type: "info" | "success" | "warning"  (default "info")
        target: "all" | "trial" | "paid"       (default "all")
        target_account_id: int (optional)
        cta_text: str (optional)
        cta_url: str (optional)
        published_at: ISO string (optional — omit to save as draft)
        expires_at: ISO string (optional)
    """
    if not _require_admin():
        return jsonify({"error": "forbidden"}), 403

    body = request.get_json(silent=True) or {}
    title = (body.get("title") or "").strip()
    text = (body.get("body") or "").strip()
    if not title or not text:
        return jsonify({"error": "title and body are required"}), 400

    def _parse_dt(val):
        if not val:
            return None
        try:
            return datetime.fromisoformat(val.replace("Z", "+00:00"))
        except Exception:
            return None

    msg = InAppMessage(
        title=title[:200],
        body=text,
        type=body.get("type", "info") if body.get("type") in ("info", "success", "warning") else "info",
        target=body.get("target", "all") if body.get("target") in ("all", "trial", "paid") else "all",
        target_account_id=body.get("target_account_id"),
        cta_text=(body.get("cta_text") or "")[:100] or None,
        cta_url=(body.get("cta_url") or "")[:500] or None,
        published_at=_parse_dt(body.get("published_at")),
        expires_at=_parse_dt(body.get("expires_at")),
    )
    db.session.add(msg)
    db.session.commit()

    logger.info("InAppMessage created: %s (type=%s target=%s)", msg.id, msg.type, msg.target)
    return jsonify({"id": msg.id, "status": "created"}), 201


@v1.route("/admin/messages/<message_id>", methods=["DELETE"])
@jwt_required()
def delete_message(message_id: str):
    """Delete a broadcast message and all its dismissals."""
    if not _require_admin():
        return jsonify({"error": "forbidden"}), 403

    msg = db.session.get(InAppMessage, message_id)
    if not msg:
        return jsonify({"error": "not found"}), 404

    # Dismissals cascade via FK ondelete=CASCADE
    db.session.delete(msg)
    db.session.commit()
    return jsonify({"status": "deleted"}), 200


# ── Landing Pages ──────────────────────────────────────────────────────────────

def _page_to_dict(page: LandingPage) -> dict:
    return {
        "id": page.id,
        "account_id": page.account_id,
        "title": page.title,
        "slug": page.slug,
        "headline": page.headline,
        "subheadline": page.subheadline,
        "cta_text": page.cta_text,
        "cta_color": page.cta_color,
        "status": page.status,
        "published_at": page.published_at.isoformat() if page.published_at else None,
        "view_count": page.view_count,
        "lead_count": page.lead_count,
        "utm_source": page.utm_source,
        "utm_campaign": page.utm_campaign,
        "created_at": page.created_at.isoformat() if page.created_at else None,
    }


@v1.route("/admin/landing-pages", methods=["GET"])
@jwt_required()
def list_landing_pages():
    """List all landing pages (admin)."""
    if not _require_admin():
        return jsonify({"error": "forbidden"}), 403

    pages = db.session.query(LandingPage).order_by(LandingPage.created_at.desc()).limit(100).all()
    return jsonify({"landing_pages": [_page_to_dict(p) for p in pages]}), 200


@v1.route("/admin/landing-pages", methods=["POST"])
@jwt_required()
def create_landing_page():
    """
    Create a landing page.

    Body (JSON):
        title        — required; internal admin label
        slug         — required; unique URL slug (alphanumeric + hyphens)
        headline     — required; hero headline
        subheadline  — optional
        body_html    — optional; sanitized before storage
        cta_text     — optional; default "Get Started"
        cta_color    — optional; indigo|emerald|amber|rose (default indigo)
        status       — optional; draft|published (default draft)
        utm_source   — optional; annotation only
        utm_campaign — optional; annotation only
        account_id   — required; which account owns this page
    """
    user = _require_admin()
    if not user:
        return jsonify({"error": "forbidden"}), 403

    body = request.get_json(silent=True) or {}
    title = (body.get("title") or "").strip()
    slug = (body.get("slug") or "").strip().lower()
    headline = (body.get("headline") or "").strip()
    account_id = body.get("account_id")

    if not title or not slug or not headline or not account_id:
        return jsonify({"error": "title, slug, headline, and account_id are required"}), 400

    # Validate slug format (alphanumeric + hyphens only)
    import re
    if not re.match(r'^[a-z0-9][a-z0-9\-]*[a-z0-9]$', slug) and len(slug) > 1:
        return jsonify({"error": "slug must contain only lowercase letters, numbers, and hyphens"}), 400

    # Check slug uniqueness
    if db.session.query(LandingPage).filter_by(slug=slug).first():
        return jsonify({"error": f"slug '{slug}' is already taken"}), 409

    raw_html = body.get("body_html") or ""
    safe_html = sanitize_html(raw_html) if raw_html.strip() else None

    status = body.get("status", "draft")
    if status not in ("draft", "published", "archived"):
        status = "draft"

    now = datetime.now(timezone.utc)
    page = LandingPage(
        account_id=int(account_id),
        title=title,
        slug=slug,
        headline=headline,
        subheadline=(body.get("subheadline") or "").strip() or None,
        body_html=safe_html,
        cta_text=(body.get("cta_text") or "Get Started").strip(),
        cta_color=body.get("cta_color", "indigo") if body.get("cta_color") in ("indigo", "emerald", "amber", "rose") else "indigo",
        status=status,
        published_at=now if status == "published" else None,
        utm_source=(body.get("utm_source") or "").strip() or None,
        utm_campaign=(body.get("utm_campaign") or "").strip() or None,
    )
    db.session.add(page)
    db.session.commit()

    logger.info("LandingPage created: %s (slug=%s account=%s)", page.id, slug, account_id)
    return jsonify(_page_to_dict(page)), 201


@v1.route("/admin/landing-pages/<page_id>", methods=["PATCH"])
@jwt_required()
def update_landing_page(page_id: str):
    """
    Update a landing page.

    Accepted fields (all optional):
        title, slug, headline, subheadline, body_html,
        cta_text, cta_color, status, utm_source, utm_campaign
    """
    if not _require_admin():
        return jsonify({"error": "forbidden"}), 403

    page = db.session.get(LandingPage, page_id)
    if not page:
        return jsonify({"error": "not found"}), 404

    body = request.get_json(silent=True) or {}

    if "title" in body:
        page.title = (body["title"] or "").strip() or page.title
    if "headline" in body:
        page.headline = (body["headline"] or "").strip() or page.headline
    if "subheadline" in body:
        page.subheadline = (body["subheadline"] or "").strip() or None
    if "body_html" in body:
        raw = body.get("body_html") or ""
        page.body_html = sanitize_html(raw) if raw.strip() else None
    if "cta_text" in body:
        page.cta_text = (body["cta_text"] or "Get Started").strip()
    if "cta_color" in body and body["cta_color"] in ("indigo", "emerald", "amber", "rose"):
        page.cta_color = body["cta_color"]
    if "utm_source" in body:
        page.utm_source = (body["utm_source"] or "").strip() or None
    if "utm_campaign" in body:
        page.utm_campaign = (body["utm_campaign"] or "").strip() or None

    if "slug" in body:
        import re
        new_slug = (body["slug"] or "").strip().lower()
        if new_slug and new_slug != page.slug:
            if not re.match(r'^[a-z0-9][a-z0-9\-]*[a-z0-9]$', new_slug) and len(new_slug) > 1:
                return jsonify({"error": "invalid slug format"}), 400
            if db.session.query(LandingPage).filter_by(slug=new_slug).first():
                return jsonify({"error": f"slug '{new_slug}' is already taken"}), 409
            page.slug = new_slug

    if "status" in body:
        new_status = body["status"]
        if new_status in ("draft", "published", "archived"):
            if new_status == "published" and page.status != "published":
                page.published_at = datetime.now(timezone.utc)
            page.status = new_status

    db.session.commit()
    return jsonify(_page_to_dict(page)), 200


@v1.route("/admin/landing-pages/<page_id>", methods=["DELETE"])
@jwt_required()
def delete_landing_page(page_id: str):
    """Delete a landing page."""
    if not _require_admin():
        return jsonify({"error": "forbidden"}), 403

    page = db.session.get(LandingPage, page_id)
    if not page:
        return jsonify({"error": "not found"}), 404

    db.session.delete(page)
    db.session.commit()
    return jsonify({"status": "deleted"}), 200
