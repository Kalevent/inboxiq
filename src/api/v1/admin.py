from datetime import datetime, timedelta

from flask import request, jsonify, url_for, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy import func, desc, or_, cast, text

from src.api.v1 import v1
from src.extensions import db
from src.models import User, Account, Ticket, InboxConnection, Lead, TriageLabelConfig
from src.api.v1.testimonials import generate_testimonial_token
from src.billing.emailing import _send_email


def _parse_dates(default_days: int = 7):
    """Return (start, end) datetimes based on optional ?start=&end= ISO params."""
    try:
        end_raw = request.args.get("end")
        end = datetime.fromisoformat(end_raw) if end_raw else datetime.utcnow()
    except Exception:
        end = datetime.utcnow()
    try:
        start_raw = request.args.get("start")
        start = datetime.fromisoformat(start_raw) if start_raw else end - timedelta(days=default_days)
    except Exception:
        start = end - timedelta(days=default_days)
    return start, end


def _require_admin():
    """Simple admin gate based on email allowlist."""
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


@v1.route("/admin/adoption", methods=["GET"])
@jwt_required()
def admin_adoption():
    if not _require_admin():
        return jsonify({"error": "forbidden"}), 403
    try:
        start, end = _parse_dates(14)
        daily_signups = (
            db.session.query(func.date(User.created_at).label("day"), func.count(User.id))
            .filter(User.created_at >= start, User.created_at <= end)
            .group_by("day")
            .order_by("day")
            .all()
        )
        active_users_24h = (
            db.session.query(func.count(func.distinct(Ticket.user_id)))
            .filter(Ticket.created_at >= datetime.utcnow() - timedelta(days=1))
            .scalar()
            or 0
        )
        active_users_7d = (
            db.session.query(func.count(func.distinct(Ticket.user_id)))
            .filter(Ticket.created_at >= datetime.utcnow() - timedelta(days=7))
            .scalar()
            or 0
        )
        active_accounts = db.session.query(func.count(Account.id)).scalar() or 0
        connected_accounts = (
            db.session.query(func.count(func.distinct(InboxConnection.account_id)))
            .filter(InboxConnection.account_id.isnot(None))
            .scalar()
            or 0
        )

        return jsonify(
            {
                "daily_signups": [{"day": str(d), "count": int(c)} for d, c in daily_signups],
                "active_users_24h": int(active_users_24h),
                "active_users_7d": int(active_users_7d),
                "active_accounts": int(active_accounts),
                "connected_accounts": int(connected_accounts),
                "activation_funnel": {
                    "invited": int(active_accounts),  # placeholder: accounts created
                    "activated": int(active_accounts),  # placeholder
                    "inbox_connected": int(connected_accounts),
                },
            }
        )
    except Exception as exc:
        current_app.logger.exception("admin_adoption_failed", exc_info=exc)
        return jsonify({"error": "admin_adoption_failed"}), 200


@v1.route("/admin/tickets", methods=["GET"])
@jwt_required()
def admin_tickets():
    if not _require_admin():
        return jsonify({"error": "forbidden"}), 403
    try:
        start, end = _parse_dates(14)
        tickets_daily = (
            db.session.query(func.date(Ticket.created_at).label("day"), func.count(Ticket.id))
            .filter(Ticket.created_at >= start, Ticket.created_at <= end)
            .group_by("day")
            .order_by("day")
            .all()
        )
        by_category = (
            db.session.query(Ticket.category, func.count(Ticket.id))
            .group_by(Ticket.category)
            .order_by(desc(func.count(Ticket.id)))
            .all()
        )
        by_priority = (
            db.session.query(Ticket.priority, func.count(Ticket.id))
            .group_by(Ticket.priority)
            .order_by(desc(func.count(Ticket.id)))
            .all()
        )
        by_status = (
            db.session.query(Ticket.status, func.count(Ticket.id))
            .group_by(Ticket.status)
            .order_by(desc(func.count(Ticket.id)))
            .all()
        )
        total = db.session.query(func.count(Ticket.id)).scalar() or 0
        triage_success = total  # placeholder until explicit triage outcome is stored
        triage_fail = 0

        return jsonify(
            {
                "tickets_daily": [{"day": str(d), "count": int(c)} for d, c in tickets_daily],
                "by_category": [{"category": k, "count": int(c)} for k, c in by_category],
                "by_priority": [{"priority": k, "count": int(c)} for k, c in by_priority],
                "backlog_by_status": [{"status": k, "count": int(c)} for k, c in by_status],
                "triage": {"success": int(triage_success), "fail": int(triage_fail)},
                "avg_latency_seconds": None,  # not tracked yet
            }
        )
    except Exception as exc:
        current_app.logger.exception("admin_tickets_failed", exc_info=exc)
        return jsonify({"error": "admin_tickets_failed"}), 200


@v1.route("/admin/integrations", methods=["GET"])
@jwt_required()
def admin_integrations():
    if not _require_admin():
        return jsonify({"error": "forbidden"}), 403
    try:
        provider_counts = (
            db.session.query(InboxConnection.provider, func.count(InboxConnection.id))
            .group_by(InboxConnection.provider)
            .all()
        )
        last_polls = (
            db.session.query(InboxConnection.account_id, func.max(InboxConnection.updated_at).label("last_poll"))
            .group_by(InboxConnection.account_id)
            .all()
        )
        errors = (
            db.session.query(
                InboxConnection.account_id,
                InboxConnection.provider,
                cast(InboxConnection.metadata_json["last_poll_error"], db.Text).label("error"),
                InboxConnection.updated_at,
            )
            .filter(InboxConnection.metadata_json["last_poll_error"].isnot(None))
            .order_by(InboxConnection.updated_at.desc())
            .limit(50)
            .all()
        )
        return jsonify(
            {
                "providers": [{"provider": p, "count": int(c)} for p, c in provider_counts],
                "last_polls": [
                    {"account_id": aid, "last_poll_at": lp.isoformat() if hasattr(lp, "isoformat") and lp else None}
                    for aid, lp in last_polls
                ],
                "errors": [
                    {
                        "account_id": row.account_id,
                        "provider": row.provider,
                        "error": row.error,
                        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
                    }
                    for row in errors
                ],
            }
        )
    except Exception as exc:
        current_app.logger.exception("admin_integrations_failed", exc_info=exc)
        return jsonify({"error": "admin_integrations_failed"}), 200


@v1.route("/admin/agent-health", methods=["GET"])
@jwt_required()
def admin_agent_health():
    if not _require_admin():
        return jsonify({"error": "forbidden"}), 403
    try:
        from src.models import AgentEvent
        window_start = datetime.utcnow() - timedelta(days=30)
        total_invokes = db.session.query(func.count(AgentEvent.id)).filter(AgentEvent.event == "invoke").scalar() or 0
        successes = (
            db.session.query(func.count(AgentEvent.id))
            .filter(AgentEvent.status == "success", AgentEvent.created_at >= window_start)
            .scalar()
            or 0
        )
        errors = (
            db.session.query(func.count(AgentEvent.id))
            .filter(AgentEvent.status == "error", AgentEvent.created_at >= window_start)
            .scalar()
            or 0
        )
        timeouts = (
            db.session.query(func.count(AgentEvent.id))
            .filter(AgentEvent.status == "timeout", AgentEvent.created_at >= window_start)
            .scalar()
            or 0
        )
        retries = (
            db.session.query(func.count(AgentEvent.id))
            .filter(AgentEvent.event == "retry", AgentEvent.created_at >= window_start)
            .scalar()
            or 0
        )
        avg_latency = (
            db.session.query(func.avg(AgentEvent.latency_ms))
            .filter(AgentEvent.latency_ms.isnot(None), AgentEvent.created_at >= window_start)
            .scalar()
        )
        recent_errors = (
            AgentEvent.query.filter(AgentEvent.status == "error")
            .order_by(AgentEvent.created_at.desc())
            .limit(5)
            .all()
        )
        errors_list = [
            {
                "agent_name": e.agent_name,
                "error": e.error_message,
                "created_at": e.created_at.isoformat() if e.created_at else None,
            }
            for e in recent_errors
        ]
        return jsonify(
            {
                "invokes": int(total_invokes),
                "errors": int(errors),
                "retries": int(retries),
                "timeouts": int(timeouts),
                "successes": int(successes),
                "avg_latency_ms": float(avg_latency) if avg_latency else None,
                "recent_errors": errors_list,
            }
        )
    except Exception as exc:
        current_app.logger.exception("admin_agent_health_failed", exc_info=exc)
        return jsonify({"error": "admin_agent_health_failed"}), 200


@v1.route("/admin/billing", methods=["GET"])
@jwt_required()
def admin_billing():
    if not _require_admin():
        return jsonify({"error": "forbidden"}), 403
    from src.billing.models import CustomerBillingProfile, Subscription, Plan, ChargeAttempt, table_exists
    try:
        now = datetime.utcnow()
        plan_mix = []
        trials_expiring = []
        failed_payments = []
        arpu = None

        if table_exists(CustomerBillingProfile):
            mix = (
                db.session.query(CustomerBillingProfile.plan_choice, func.count(CustomerBillingProfile.id))
                .group_by(CustomerBillingProfile.plan_choice)
                .all()
            )
            plan_mix = [{"plan": p or "unknown", "count": int(c)} for p, c in mix]
            trials_expiring = (
                db.session.query(CustomerBillingProfile.account_id, CustomerBillingProfile.trial_end)
                .filter(CustomerBillingProfile.trial_end.isnot(None))
                .filter(CustomerBillingProfile.trial_end <= now + timedelta(days=14))
                .order_by(CustomerBillingProfile.trial_end.asc())
                .limit(20)
                .all()
            )
        if table_exists(ChargeAttempt):
            failed_payments = (
                db.session.query(ChargeAttempt.provider, func.count(ChargeAttempt.id))
                .filter(ChargeAttempt.status == "failed")
                .filter(ChargeAttempt.updated_at >= now - timedelta(days=30))
                .group_by(ChargeAttempt.provider)
                .all()
            )
            failed_payments = [{"provider": p, "count": int(c)} for p, c in failed_payments]

        if table_exists(Subscription) and table_exists(Plan):
            # Rough ARPU: average of active subscription plan prices
            active = (
                db.session.query(Plan.price_cents)
                .join(Subscription, Subscription.plan_id == Plan.id)
                .filter(Subscription.status.in_(["active", "trialing"]))
                .all()
            )
            if active:
                arpu = sum(p[0] for p in active) / (100.0 * len(active))

        return jsonify(
            {
                "plan_mix": plan_mix,
                "trials_expiring": [
                    {"account_id": aid, "trial_end": te.isoformat() if hasattr(te, "isoformat") and te else None}
                    for aid, te in trials_expiring
                ],
                "failed_payments": failed_payments,
                "arpu": arpu,
            }
        )
    except Exception as exc:
        current_app.logger.exception("admin_billing_failed", exc_info=exc)
        return jsonify({"error": "admin_billing_failed"}), 200


@v1.route("/admin/security", methods=["GET"])
@jwt_required()
def admin_security():
    if not _require_admin():
        return jsonify({"error": "forbidden"}), 403
    try:
        from src.models import AuthEvent
        users_total = db.session.query(func.count(User.id)).scalar() or 0
        window_start = datetime.utcnow() - timedelta(days=30)
        login_fails = (
            db.session.query(func.count(AuthEvent.id))
            .filter(AuthEvent.event == "login", AuthEvent.outcome == "fail", AuthEvent.created_at >= window_start)
            .scalar()
            or 0
        )
        login_success = (
            db.session.query(func.count(AuthEvent.id))
            .filter(AuthEvent.event == "login", AuthEvent.outcome == "success", AuthEvent.created_at >= window_start)
            .scalar()
            or 0
        )
        reset_requests = (
            db.session.query(func.count(AuthEvent.id))
            .filter(AuthEvent.event == "password_reset_request", AuthEvent.created_at >= window_start)
            .scalar()
            or 0
        )
        reset_complete = (
            db.session.query(func.count(AuthEvent.id))
            .filter(AuthEvent.event == "password_reset_complete", AuthEvent.created_at >= window_start)
            .scalar()
            or 0
        )
        return jsonify(
            {
                "failed_logins": int(login_fails),
                "successful_logins": int(login_success),
                "password_resets": int(reset_complete),
                "password_reset_requests": int(reset_requests),
                "jwt_refresh_failures": 0,  # still placeholder
                "users_total": int(users_total),
            }
        )
    except Exception as exc:
        current_app.logger.exception("admin_security_failed", exc_info=exc)
        return jsonify({"error": "admin_security_failed"}), 200


@v1.route("/admin/web", methods=["GET"])
@jwt_required()
def admin_web():
    if not _require_admin():
        return jsonify({"error": "forbidden"}), 403
    # Web analytics not persisted yet; return empty to keep endpoint stable.
    return jsonify({"pageviews": [], "signups_by_referrer": [], "onboarding_bounce": None, "geo": []})


@v1.route("/admin/blog-metrics", methods=["GET"])
@jwt_required()
def admin_blog_metrics():
    """
    Weekly blog metrics placeholder.
    Replace with real Google Search Console / analytics data when available.
    """
    if not _require_admin():
        return jsonify({"error": "forbidden"}), 403
    try:
        from src.models import BlogPost
        total_posts = db.session.query(func.count(BlogPost.id)).scalar() or 0
        published = (
            db.session.query(func.count(BlogPost.id)).filter(BlogPost.status == "published").scalar() or 0
        )
        avg_word_count = (
            db.session.query(func.avg(BlogPost.word_count))
            .filter(BlogPost.word_count.isnot(None))
            .scalar()
        )
        avg_read_time = (
            db.session.query(func.avg(BlogPost.read_time_minutes))
            .filter(BlogPost.read_time_minutes.isnot(None))
            .scalar()
        )
        return jsonify(
            {
                "impressions": None,
                "indexed_pages": None,
                "clicks": None,
                "rankings": [],
                "signups_from_blog": None,
                "time_on_page_seconds": None,
                "total_posts": int(total_posts),
                "published_posts": int(published),
                "avg_word_count": float(avg_word_count) if avg_word_count else None,
                "avg_read_time_minutes": float(avg_read_time) if avg_read_time else None,
            }
        )
    except Exception as exc:
        current_app.logger.exception("admin_blog_metrics_failed", exc_info=exc)
        return jsonify({"error": "admin_blog_metrics_failed"}), 200


@v1.route("/admin/lead-sourcing", methods=["GET"])
@jwt_required()
def admin_lead_sourcing():
    """
    Lead sourcing snapshot for admin dashboard.
    """
    if not _require_admin():
        return jsonify({"error": "forbidden"}), 403

    total_leads = db.session.query(func.count(Lead.id)).scalar() or 0
    leads_24h = (
        db.session.query(func.count(Lead.id))
        .filter(Lead.created_at >= datetime.utcnow() - timedelta(hours=24))
        .scalar()
        or 0
    )
    leads_week = (
        db.session.query(func.count(Lead.id))
        .filter(Lead.created_at >= datetime.utcnow() - timedelta(days=7))
        .scalar()
        or 0
    )

    # Recipients may not have an ORM model; use raw counts if table exists.
    recipients_total = None
    recipients_24h = None
    try:
        recipients_total = db.session.execute(text("select count(*) from recipients")).scalar() or 0
        recipients_24h = (
            db.session.execute(
                text("select count(*) from recipients where created_at >= now() - interval '24 hours'")
            ).scalar()
            or 0
        )
    except Exception:
        pass

    return jsonify(
        {
            "leads_total": int(total_leads),
            "leads_last_24h": int(leads_24h),
            "leads_last_7d": int(leads_week),
            "recipients_total": int(recipients_total) if recipients_total is not None else None,
            "recipients_last_24h": int(recipients_24h) if recipients_24h is not None else None,
        }
    )
    avg_word_count = (
        db.session.query(func.avg(BlogPost.word_count))
        .filter(BlogPost.word_count.isnot(None))
        .scalar()
    )
    avg_read_time = (
        db.session.query(func.avg(BlogPost.read_time_minutes))
        .filter(BlogPost.read_time_minutes.isnot(None))
        .scalar()
    )
    return jsonify(
        {
            "impressions": None,
            "indexed_pages": None,
            "clicks": None,
            "rankings": [],
            "signups_from_blog": None,
            "time_on_page_seconds": None,
            "total_posts": int(total_posts),
            "published_posts": int(published),
            "avg_word_count": float(avg_word_count) if avg_word_count else None,
            "avg_read_time_minutes": float(avg_read_time) if avg_read_time else None,
        }
    )


@v1.route("/admin/dspy-eval", methods=["GET"])
@jwt_required()
def admin_dspy_eval():
    if not _require_admin():
        return jsonify({"error": "forbidden"}), 403
    try:
        from src.dspy_eval import evaluate

        limit = min(max(int(request.args.get("limit", 200)), 1), 500)
        account_id = request.args.get("account_id")
        account_val = int(account_id) if account_id else None
        metrics = evaluate(limit=limit, account_id=account_val)
        return jsonify({"metrics": metrics, "limit": limit, "account_id": account_val})
    except Exception as exc:
        current_app.logger.exception("admin_dspy_eval_failed", exc_info=exc)
        return jsonify({"error": "admin_dspy_eval_failed"}), 200


@v1.route("/admin/triage-labels", methods=["GET", "POST"])
@jwt_required()
def admin_triage_labels():
    if not _require_admin():
        return jsonify({"error": "forbidden"}), 403

    if request.method == "GET":
        account_id = request.args.get("account_id")
        account_val = int(account_id) if account_id else None
        try:
            query = TriageLabelConfig.query
            if account_val is not None:
                cfg = (
                    query.filter(TriageLabelConfig.account_id == account_val)
                    .order_by(TriageLabelConfig.updated_at.desc())
                    .first()
                )
                if cfg:
                    return jsonify({"config": cfg.to_dict()})
            global_cfg = (
                query.filter(TriageLabelConfig.account_id.is_(None))
                .order_by(TriageLabelConfig.updated_at.desc())
                .first()
            )
            if global_cfg:
                return jsonify({"config": global_cfg.to_dict()})
        except Exception as exc:
            current_app.logger.warning("triage labels unavailable: %s", exc)
        return jsonify({"config": None})

    payload = request.get_json(silent=True) or {}
    labels = payload.get("labels")
    if not isinstance(labels, dict):
        return jsonify({"error": "labels_required"}), 400
    account_id = payload.get("account_id")
    account_val = int(account_id) if account_id is not None else None
    name = (payload.get("name") or "default").strip()[:128] or "default"

    try:
        from src.triage_labels import save_triage_labels

        return jsonify({"config": save_triage_labels(account_val, labels, name=name)})
    except Exception as exc:
        db.session.rollback()
        current_app.logger.warning("triage labels save failed: %s", exc)
        return jsonify({"error": "triage_labels_storage_unavailable"}), 503


@v1.route("/admin/actions/invite-testimonial", methods=["POST"])
@jwt_required()
def admin_invite_testimonial():
    admin_user = _require_admin()
    if not admin_user:
        return jsonify({"error": "forbidden"}), 403
    payload = request.get_json(silent=True) or {}
    account_id = payload.get("account_id")
    user_id = payload.get("user_id")
    send_email = bool(payload.get("send_email"))
    to_email = (payload.get("to_email") or "").strip()

    if not account_id:
        return jsonify({"error": "account_id_required"}), 400

    token = generate_testimonial_token(account_id, user_id)
    link = url_for("v1.submit_testimonial_with_token", token=token, _external=True)
    if send_email and to_email:
        subject = "We'd love your quick feedback on InboxIQ"
        text = (
            "Hi,\n\nThanks for using InboxIQ. Would you share a quick testimonial? "
            f"Click here: {link}\n\nWe appreciate your feedback!\n"
        )
        html = (
            "<p>Hi,</p>"
            "<p>Thanks for using InboxIQ. Would you share a quick testimonial?</p>"
            f'<p><a href="{link}">Click here to submit</a></p>'
            "<p>We appreciate your feedback!</p>"
        )
        _send_email(to_email, subject, text, html)

    return jsonify({"success": True, "link": link, "token": token, "emailed": bool(send_email and to_email)})


@v1.route("/admin/actions/refresh-embeddings", methods=["POST"])
@jwt_required()
def admin_refresh_embeddings():
    admin_user = _require_admin()
    if not admin_user:
        return jsonify({"error": "forbidden"}), 403
    limit = int(request.args.get("limit", 500))
    try:
        from scripts.refresh_feedback_embeddings import refresh

        refresh(limit=limit)
        return jsonify({"success": True, "message": f"Refreshed embeddings for up to {limit} tickets"})
    except Exception as exc:
        current_app.logger.exception("refresh embeddings failed", exc_info=exc)
        return jsonify({"error": "refresh_failed", "message": str(exc)}), 500
