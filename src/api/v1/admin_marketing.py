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
- POST   /api/v1/enterprise/inquiry            — public enterprise inquiry form (rate-limited)
- GET    /api/v1/admin/enterprise/inquiries    — list enterprise inquiries (admin)
- PATCH  /api/v1/admin/enterprise/inquiries/<id> — update inquiry status / notes (admin)
- GET    /api/v1/admin/savings-report          — monthly savings report (admin, any account)
- GET    /api/v1/billing/savings-report        — monthly savings report (account-scoped, jwt)
"""
from datetime import datetime, timedelta, timezone

from flask import jsonify, request, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity

from src.api.v1 import v1
from src.billing.models import AccountUsageCounter
from src.extensions import db
from src.funnel_stages import CONVERSION_STAGES
from src.models import Account, EnterpriseInquiry, InAppMessage, InAppMessageDismissal, LandingPage, Lead, LeadAttribution, NurtureEmailSend, Referral, User
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
        conversion_stages = CONVERSION_STAGES

        # Leads created in period grouped by utm_source
        source_rows = db.session.query(
            db.func.coalesce(Lead.utm_source, Lead.source, "direct").label("src"),
            db.func.count().label("leads"),
            db.func.sum(
                db.cast(Lead.current_funnel_stage.in_(conversion_stages), db.Integer)
            ).label("conversions"),
        ).filter(
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


# ── Enterprise inquiry endpoints ──────────────────────────────────────────────

def _inquiry_to_dict(inq: EnterpriseInquiry) -> dict:
    return {
        "id": inq.id,
        "name": inq.name,
        "email": inq.email,
        "company": inq.company,
        "phone": inq.phone,
        "employee_count": inq.employee_count,
        "message": inq.message,
        "account_id": inq.account_id,
        "status": inq.status,
        "admin_notes": inq.admin_notes,
        "created_at": inq.created_at.isoformat() if inq.created_at else None,
        "updated_at": inq.updated_at.isoformat() if inq.updated_at else None,
    }


@v1.route("/enterprise/inquiry", methods=["POST"])
def submit_enterprise_inquiry():
    """
    Public endpoint — submit an Enterprise plan inquiry.

    Rate-limited to 5/hour per IP by Flask-Limiter (if configured in the app).
    No JWT required: prospective customers and existing users can both submit.

    Body (JSON):
        name        str  required
        email       str  required
        company     str  optional
        phone       str  optional
        employee_count  int  optional
        message     str  optional
        account_id  int  optional  — passed by frontend if user is logged in
    """
    body = request.get_json(silent=True) or {}

    name = sanitize_html((body.get("name") or "").strip())
    email = (body.get("email") or "").strip().lower()
    if not name or not email or "@" not in email:
        return jsonify({"error": "name and a valid email are required"}), 400

    company = sanitize_html((body.get("company") or "").strip()) or None
    phone = sanitize_html((body.get("phone") or "").strip()) or None
    employee_count = body.get("employee_count")
    if employee_count is not None:
        try:
            employee_count = int(employee_count)
        except (ValueError, TypeError):
            employee_count = None
    message = sanitize_html((body.get("message") or "").strip()) or None
    account_id = body.get("account_id")
    if account_id is not None:
        try:
            account_id = int(account_id)
        except (ValueError, TypeError):
            account_id = None

    inq = EnterpriseInquiry(
        name=name,
        email=email,
        company=company,
        phone=phone,
        employee_count=employee_count,
        message=message,
        account_id=account_id,
        status="new",
    )
    db.session.add(inq)
    db.session.commit()

    # Notify admins
    try:
        from src.billing.emailing import _send_email
        admin_emails_raw = current_app.config.get("ADMIN_EMAILS", "")
        admin_list = [e.strip() for e in admin_emails_raw.split(",") if e.strip()]
        subject = f"[Enterprise Inquiry] {name} — {company or email}"
        text_body = (
            f"New Enterprise plan inquiry received.\n\n"
            f"Name:           {name}\n"
            f"Email:          {email}\n"
            f"Company:        {company or '—'}\n"
            f"Phone:          {phone or '—'}\n"
            f"Employees:      {employee_count or '—'}\n"
            f"Account ID:     {account_id or '—'}\n\n"
            f"Message:\n{message or '(none)'}\n\n"
            f"Inquiry ID: {inq.id}\n"
            f"Review at: https://kalevent.com/admin"
        )
        html_body = (
            f"<h2>New Enterprise Plan Inquiry</h2>"
            f"<table style='border-collapse:collapse'>"
            f"<tr><td><strong>Name</strong></td><td>{name}</td></tr>"
            f"<tr><td><strong>Email</strong></td><td>{email}</td></tr>"
            f"<tr><td><strong>Company</strong></td><td>{company or '—'}</td></tr>"
            f"<tr><td><strong>Phone</strong></td><td>{phone or '—'}</td></tr>"
            f"<tr><td><strong>Employees</strong></td><td>{employee_count or '—'}</td></tr>"
            f"<tr><td><strong>Account ID</strong></td><td>{account_id or '—'}</td></tr>"
            f"</table>"
            f"<p><strong>Message:</strong><br/>{message or '(none)'}</p>"
            f"<p>Inquiry ID: <code>{inq.id}</code></p>"
        )
        for admin_email in admin_list:
            _send_email(admin_email, subject, text_body, html_body)
    except Exception as exc:
        logger.warning("Enterprise inquiry admin notification failed: %s", exc)

    return jsonify({"status": "received", "inquiry_id": inq.id}), 201


@v1.route("/admin/enterprise/inquiries", methods=["GET"])
@jwt_required()
def list_enterprise_inquiries():
    """List all enterprise inquiries, newest first. Admin only."""
    if not _require_admin():
        return jsonify({"error": "forbidden"}), 403

    try:
        status_filter = request.args.get("status")
        q = db.session.query(EnterpriseInquiry).order_by(EnterpriseInquiry.created_at.desc())
        if status_filter:
            q = q.filter(EnterpriseInquiry.status == status_filter)
        inquiries = q.limit(200).all()
        return jsonify({"inquiries": [_inquiry_to_dict(i) for i in inquiries]}), 200
    except Exception as exc:
        logger.error("list_enterprise_inquiries failed: %s", exc)
        return jsonify({"error": "database error", "detail": str(exc)}), 503


@v1.route("/admin/enterprise/inquiries/<inquiry_id>", methods=["PATCH"])
@jwt_required()
def update_enterprise_inquiry(inquiry_id: str):
    """
    Update status and/or admin_notes on an inquiry. Admin only.

    Body: { status: "new|contacted|closed", admin_notes: "..." }
    """
    if not _require_admin():
        return jsonify({"error": "forbidden"}), 403

    inq = db.session.get(EnterpriseInquiry, inquiry_id)
    if not inq:
        return jsonify({"error": "not found"}), 404

    body = request.get_json(silent=True) or {}
    if "status" in body and body["status"] in ("new", "contacted", "closed"):
        inq.status = body["status"]
    if "admin_notes" in body:
        inq.admin_notes = (body["admin_notes"] or "").strip() or None

    db.session.commit()
    return jsonify(_inquiry_to_dict(inq)), 200


@v1.route("/admin/enterprise/inquiries/<inquiry_id>/notify-engineering", methods=["POST"])
@jwt_required()
def notify_engineering_for_inquiry(inquiry_id: str):
    """
    Email the admin/engineering team the kubectl activation command for an
    Enterprise inquiry. Use after closing a deal — cheaper than Slack automation.

    Sends to ADMIN_EMAILS env var (comma-separated).
    Marks the inquiry as 'contacted' if it was 'new'.
    """
    if not _require_admin():
        return jsonify({"error": "forbidden"}), 403

    inq = db.session.get(EnterpriseInquiry, inquiry_id)
    if not inq:
        return jsonify({"error": "not found"}), 404

    from src.email_utils import send_enterprise_onboarding_notification

    admin_emails = [
        e.strip()
        for e in (current_app.config.get("ADMIN_EMAILS") or "").split(",")
        if e.strip()
    ]
    if not admin_emails:
        return jsonify({"error": "ADMIN_EMAILS not configured"}), 500

    sent = send_enterprise_onboarding_notification(
        to_emails=admin_emails,
        inquiry_name=inq.name,
        inquiry_email=inq.email,
        inquiry_company=inq.company or "",
        account_id=inq.account_id,
    )

    if not sent:
        return jsonify({"error": "Failed to send email. Check SMTP configuration."}), 502

    # Auto-advance status to 'contacted' so it's clear action was taken
    if inq.status == "new":
        inq.status = "contacted"
        db.session.commit()

    return jsonify({"sent": True, "to": admin_emails, "inquiry": _inquiry_to_dict(inq)}), 200


# ── Savings / ROI report ──────────────────────────────────────────────────────

# Default assumptions for ROI calculation.
# Each AI decision (email triage + draft) saves ~3 minutes of manual work.
# Adjust via query params if needed.
_DEFAULT_MINS_PER_DECISION = 3
_DEFAULT_HOURLY_RATE_GBP = 30


def _build_savings_report(account_id: int, months: int, mins_per_decision: int, hourly_rate: float, override_signals_per_month: int = 0) -> dict:
    """
    Build savings report for a given account over the last N billing months.

    Returns a dict with per-month breakdown and totals.
    """
    # Determine the last `months` billing_month strings ("YYYY-MM")
    now = datetime.now(timezone.utc)
    billing_months = []
    for i in range(months - 1, -1, -1):
        # Go back i months from current month
        year = now.year
        month = now.month - i
        while month <= 0:
            month += 12
            year -= 1
        billing_months.append(f"{year:04d}-{month:02d}")

    # Query usage counters for those months
    rows = (
        db.session.query(AccountUsageCounter)
        .filter(
            AccountUsageCounter.account_id == account_id,
            AccountUsageCounter.billing_month.in_(billing_months),
        )
        .all()
    )
    row_by_month = {r.billing_month: r for r in rows}

    monthly_breakdown = []
    total_ai_decisions = 0
    total_automation_runs = 0
    total_nurture_emails = 0
    total_incoming_signals = 0

    for bm in billing_months:
        row = row_by_month.get(bm)
        ai = row.ai_decisions if row else 0
        auto = row.automation_runs if row else 0
        nurture = row.nurture_emails if row else 0
        # Use override_signals_per_month for prospects with no tracked data yet
        signals = (row.incoming_signals if row else 0) or override_signals_per_month
        # Savings: AI decisions + automation runs each save ~mins_per_decision minutes
        units_saved = ai + auto
        hours_saved = round(units_saved * mins_per_decision / 60, 2)
        cost_saved = round(hours_saved * hourly_rate, 2)
        monthly_breakdown.append({
            "month": bm,
            "incoming_signals": signals,
            "ai_decisions": ai,
            "automation_runs": auto,
            "nurture_emails": nurture,
            "hours_saved": hours_saved,
            "cost_saved_gbp": cost_saved,
        })
        total_ai_decisions += ai
        total_automation_runs += auto
        total_nurture_emails += nurture
        total_incoming_signals += signals

    avg_signals = round(total_incoming_signals / max(months, 1))
    total_units = total_ai_decisions + total_automation_runs
    total_hours = round(total_units * mins_per_decision / 60, 2)
    total_cost = round(total_hours * hourly_rate, 2)
    # Enterprise value-based price estimate: 12% of annual savings
    annual_cost_est = round(total_cost / max(months, 1) * 12, 2)
    enterprise_price_est = round(annual_cost_est * 0.12 / 12, 2)  # monthly

    return {
        "account_id": account_id,
        "months": months,
        "assumptions": {
            "mins_per_decision": mins_per_decision,
            "hourly_rate_gbp": hourly_rate,
            "override_signals_per_month": override_signals_per_month,
        },
        "monthly_breakdown": monthly_breakdown,
        "totals": {
            "incoming_signals": total_incoming_signals,
            "avg_monthly_signals": avg_signals,
            "ai_decisions": total_ai_decisions,
            "automation_runs": total_automation_runs,
            "nurture_emails": total_nurture_emails,
            "hours_saved": total_hours,
            "cost_saved_gbp": total_cost,
        },
        "roi_summary": {
            "avg_monthly_saving_gbp": round(total_cost / max(months, 1), 2),
            "projected_annual_saving_gbp": annual_cost_est,
            "enterprise_price_estimate_monthly_gbp": enterprise_price_est,
        },
    }


@v1.route("/admin/savings-report", methods=["GET"])
@jwt_required()
def admin_savings_report():
    """
    Admin: view savings report for any account.

    Query params:
        account_id  int  required
        months      int  1-24, default 3
        mins_per_decision  int  default 3
        hourly_rate float  default 30
    """
    if not _require_admin():
        return jsonify({"error": "forbidden"}), 403

    try:
        account_id = int(request.args["account_id"])
    except (KeyError, ValueError, TypeError):
        return jsonify({"error": "account_id is required"}), 400

    account = db.session.get(Account, account_id)
    if not account:
        return jsonify({"error": "account not found"}), 404

    months = min(int(request.args.get("months", 3)), 24)
    mins_per_decision = int(request.args.get("mins_per_decision", _DEFAULT_MINS_PER_DECISION))
    hourly_rate = float(request.args.get("hourly_rate", _DEFAULT_HOURLY_RATE_GBP))
    override_signals = int(request.args.get("override_signals", 0))

    report = _build_savings_report(account_id, months, mins_per_decision, hourly_rate, override_signals)
    report["account_name"] = account.name
    return jsonify(report), 200


@v1.route("/billing/savings-report", methods=["GET"])
@jwt_required()
def my_savings_report():
    """
    Account-scoped savings report for the logged-in user's account.

    Query params:
        months      int  1-24, default 3
        mins_per_decision  int  default 3
        hourly_rate float  default 30
    """
    user_id = get_jwt_identity()
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"error": "unauthorized"}), 401

    account = db.session.get(Account, user.account_id)
    if not account:
        return jsonify({"error": "account not found"}), 404

    months = min(int(request.args.get("months", 3)), 24)
    mins_per_decision = int(request.args.get("mins_per_decision", _DEFAULT_MINS_PER_DECISION))
    hourly_rate = float(request.args.get("hourly_rate", _DEFAULT_HOURLY_RATE_GBP))

    report = _build_savings_report(user.account_id, months, mins_per_decision, hourly_rate)
    report["account_name"] = account.name
    return jsonify(report), 200
