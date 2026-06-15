from datetime import datetime, timedelta, timezone

from flask import request, jsonify, url_for, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy import func, desc, cast, text

from src.api.v1 import v1
from src.extensions import db
from src.models.core import User, Account, InboxConnection
from src.models.tickets import Ticket, TriageLabelConfig
from src.models.developer import AppProductAccess, RegisteredApp
from src.api.v1.testimonials import generate_testimonial_token
from src.billing.emailing import _send_email


def _parse_dates(default_days: int = 7):
    """Return (start, end) datetimes based on optional ?start=&end= ISO params."""
    try:
        end_raw = request.args.get("end")
        end = (
            datetime.fromisoformat(end_raw)
            if end_raw
            else datetime.now(timezone.utc)
        )
    except Exception:
        end = datetime.now(timezone.utc)
    try:
        start_raw = request.args.get("start")
        start = datetime.fromisoformat(start_raw) if start_raw else end - timedelta(days=default_days)
    except Exception:
        start = end - timedelta(days=default_days)
    return start, end


def _require_admin():
    """Admin gate: email allowlist + MFA verified in current session (ASVS V4.3.1)."""
    from flask_jwt_extended import get_jwt
    user_id = get_jwt_identity()
    user = db.session.get(User, user_id) if user_id else None
    default_admin = "kofi@kalevent.com"
    allowed = set(
        e.strip().lower()
        for e in (current_app.config.get("ADMIN_EMAILS", "") or default_admin).split(",")
        if e.strip()
    )
    if not user or (allowed and user.email.lower() not in allowed):
        return None
    claims = get_jwt()
    if not claims.get("mfa_verified"):
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
            .filter(
                Ticket.created_at
                >= datetime.now(timezone.utc) - timedelta(days=1)
            )
            .scalar()
            or 0
        )
        active_users_7d = (
            db.session.query(func.count(func.distinct(Ticket.user_id)))
            .filter(Ticket.created_at >= datetime.now(timezone.utc) - timedelta(days=7))
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
        window_start = datetime.now(timezone.utc) - timedelta(days=30)
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
    from src.models.billing import CustomerBillingProfile, Subscription, Plan, ChargeAttempt, table_exists
    try:
        now = datetime.now(timezone.utc)
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
        window_start = datetime.now(timezone.utc) - timedelta(days=30)
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
    Weekly blog metrics with real GSC data.
    """
    if not _require_admin():
        return jsonify({"error": "forbidden"}), 403

    try:
        from src.models import BlogPost
        from src.integrations.google_search_console import get_gsc_client

        # Get blog post counts from database
        total_posts = db.session.query(func.count(BlogPost.id)).scalar() or 0
        published = (
            db.session.query(func.count(BlogPost.id))
            .filter(BlogPost.status == "published")
            .scalar()
            or 0
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

        # Get GSC data if configured
        gsc_client = get_gsc_client()
        gsc_data = {}

        if gsc_client:
            try:
                gsc_data = gsc_client.get_blog_metrics(path_prefix='/blog/')
            except Exception as gsc_error:
                current_app.logger.warning(f"GSC fetch error: {gsc_error}")
                gsc_data = {
                    'impressions': None,
                    'clicks': None,
                    'ctr': None,
                    'indexed_pages': None
                }
        else:
            # GSC not configured - return None values
            gsc_data = {
                'impressions': None,
                'clicks': None,
                'ctr': None,
                'indexed_pages': None
            }

        return jsonify(
            {
                "impressions": gsc_data.get('impressions'),
                "clicks": gsc_data.get('clicks'),
                "ctr": gsc_data.get('ctr'),
                "indexed_pages": gsc_data.get('indexed_pages'),
                "total_posts": int(total_posts),
                "published_posts": int(published),
                "avg_word_count": float(avg_word_count) if avg_word_count else None,
                "avg_read_time_minutes": float(avg_read_time) if avg_read_time else None,
                "rankings": [],  # Could add top queries here
                "signups_from_blog": None,  # Would come from GA or your analytics
                "time_on_page_seconds": None,  # Would come from GA
            }
        )

    except Exception as exc:
        current_app.logger.exception("admin_blog_metrics_failed", exc_info=exc)
        return jsonify({"error": "admin_blog_metrics_failed"}), 500


@v1.route("/admin/dspy-eval", methods=["GET"])
@jwt_required()
def admin_dspy_eval():
    if not _require_admin():
        return jsonify({"error": "forbidden"}), 403
    try:
        from src.dspy.training.eval import evaluate

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
        from src.dspy.triage_labels import save_triage_labels

        return jsonify({"config": save_triage_labels(account_val, labels, name=name)})
    except ValueError as exc:
        # Validation error (e.g., labels with spaces)
        db.session.rollback()
        current_app.logger.warning("triage labels validation failed: %s", exc)
        return jsonify({"error": str(exc)}), 400
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


@v1.route("/admin/content/published-posts", methods=["GET"])
@jwt_required()
def admin_published_posts():
    """List recently published blog posts (auto-published by Content Generation Agent)."""
    if not _require_admin():
        return jsonify({"error": "forbidden"}), 403
    try:
        from src.models import BlogPost
        limit = min(max(int(request.args.get("limit", 20)), 1), 100)

        posts = (
            BlogPost.query
            .filter(BlogPost.status == "published")
            .order_by(BlogPost.published_at.desc())
            .limit(limit)
            .all()
        )

        return jsonify({
            "posts": [
                {
                    "id": str(post.id),
                    "title": post.title,
                    "slug": post.slug,
                    "published_at": post.published_at.isoformat() if post.published_at else None,
                    "word_count": post.word_count,
                    "funnel_stage": post.funnel_stage,
                    "primary_keyword": post.primary_keyword,
                    "auto_generated": post.auto_generated,
                    "dspy_quality_score": float(post.dspy_quality_score) if post.dspy_quality_score else None,
                }
                for post in posts
            ],
            "total": len(posts),
        })
    except Exception as exc:
        current_app.logger.exception("admin_published_posts_failed", exc_info=exc)
        return jsonify({"error": "admin_published_posts_failed"}), 500


@v1.route("/admin/content/published-posts/<post_id>", methods=["DELETE"])
@jwt_required()
def admin_delete_published_post(post_id):
    """Hard-delete a blog post by admin (including published posts)."""
    if not _require_admin():
        return jsonify({"error": "forbidden"}), 403
    from src.models.content import BlogPost
    from src.extensions import db
    post = BlogPost.query.filter_by(id=post_id).first()
    if not post:
        return jsonify({"error": "Post not found"}), 404
    try:
        db.session.delete(post)
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    current_app.logger.info("admin_deleted_blog_post slug=%s id=%s", post.slug, post_id)
    return jsonify({"deleted": True, "slug": post.slug})


@v1.route("/admin/content/generate-blog", methods=["POST"])
@jwt_required()
def admin_generate_blog():
    """Manually trigger content generation (on-demand)."""
    if not _require_admin():
        return jsonify({"error": "forbidden"}), 403
    try:
        from src.celery_inboxiq import celery

        payload = request.get_json(silent=True) or {}
        niche = payload.get("niche", "Revenue Operations")
        audience = payload.get("audience", "VP Revenue Operations, B2B SaaS, 100-500 employees")
        topic_index = int(payload.get("topic_index", 0))
        auto_publish = payload.get("auto_publish", True)

        # Queue the task to the inbox queue using the celery instance
        task = celery.send_task(
            'content.generate_blog_post',
            args=[niche, audience, topic_index, auto_publish],
            queue='inbox'
        )

        return jsonify({
            "success": True,
            "message": "Blog generation queued",
            "task_id": task.id,
            "niche": niche,
            "audience": audience,
        })
    except Exception as exc:
        current_app.logger.exception("admin_generate_blog_failed", exc_info=exc)
        return jsonify({"error": "admin_generate_blog_failed", "message": str(exc)}), 500


# ── Developer access admin endpoints ─────────────────────────────────────────

@v1.route("/admin/developer/enable", methods=["POST"])
@jwt_required()
def admin_developer_enable():
    """Enable developer_access for an account."""
    admin = _require_admin()
    if not admin:
        return jsonify({"error": "forbidden"}), 403

    from src.models import Account
    data = request.get_json() or {}
    account_id = data.get("account_id")
    if not account_id:
        return jsonify({"error": "account_id required"}), 400

    account = db.session.get(Account, account_id)
    if not account:
        return jsonify({"error": "account not found"}), 404

    account.developer_access = True
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    current_app.logger.info(f"admin: developer_access enabled for account={account_id} by {admin.email}")
    return jsonify({"ok": True, "account_id": account_id})


@v1.route("/admin/developer/requests", methods=["GET"])
@jwt_required()
def admin_developer_requests():
    """List all developer access requests."""
    admin = _require_admin()
    if not admin:
        return jsonify({"error": "forbidden"}), 403

    from src.models import DeveloperAccessRequest
    requests_all = DeveloperAccessRequest.query.order_by(
        DeveloperAccessRequest.created_at.desc()
    ).all()

    return jsonify({
        "requests": [
            {
                "id": r.id,
                "account_id": r.account_id,
                "full_name": r.full_name,
                "company": r.company,
                "use_case": r.use_case,
                "scopes": r.scopes,
                "callback_url": r.callback_url,
                "status": r.status,
                "created_at": r.created_at.strftime("%b %d, %Y") if r.created_at else None,
            }
            for r in requests_all
        ]
    })


@v1.route("/admin/developer/requests/<request_id>/review", methods=["POST"])
@jwt_required()
def admin_developer_review(request_id):
    """Approve or reject a developer access request."""
    admin = _require_admin()
    if not admin:
        return jsonify({"error": "forbidden"}), 403

    from src.models import DeveloperAccessRequest
    from datetime import datetime, timezone
    data = request.get_json() or {}
    status = data.get("status")
    if status not in ("approved", "rejected"):
        return jsonify({"error": "status must be approved or rejected"}), 400

    req = db.session.get(DeveloperAccessRequest, request_id)
    if not req:
        return jsonify({"error": "not found"}), 404

    req.status = status
    req.reviewed_by = admin.id
    req.reviewed_at = datetime.now(timezone.utc)
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    current_app.logger.info(
        f"admin: developer request {request_id} {status} by {admin.email}"
    )
    return jsonify({"ok": True, "status": status})


@v1.route("/admin/developer/product-requests", methods=["GET"])
@jwt_required()
def admin_developer_product_requests():
    """List all pending product access requests."""
    admin = _require_admin()
    if not admin:
        return jsonify({"error": "forbidden"}), 403

    requests_all = AppProductAccess.query.filter_by(status="pending").order_by(
        AppProductAccess.requested_at.desc()
    ).all()
    result = []
    for req in requests_all:
        app = db.session.get(RegisteredApp, req.app_id)
        account = db.session.get(Account, req.account_id)
        result.append({
            "id": req.id,
            "product_slug": req.product_slug,
            "status": req.status,
            "use_case": req.use_case,
            "requested_at": req.requested_at.isoformat() if req.requested_at else None,
            "app_name": app.name if app else None,
            "app_client_id": app.client_id if app else None,
            "account_email": account.email if account else None,
            "account_id": req.account_id,
        })
    return jsonify(result)


@v1.route("/admin/developer/product-requests/<request_id>/review", methods=["POST"])
@jwt_required()
def admin_developer_product_request_review(request_id):
    """Approve or reject a product access request."""
    admin = _require_admin()
    if not admin:
        return jsonify({"error": "forbidden"}), 403

    from datetime import datetime, timezone
    data = request.get_json(force=True) or {}
    status = data.get("status", "").strip()
    if status not in ("approved", "rejected"):
        return jsonify({"error": "status must be 'approved' or 'rejected'"}), 400

    req = db.session.get(AppProductAccess, request_id)
    if not req:
        return jsonify({"error": "not found"}), 404

    if req.status != "pending":
        return jsonify({"error": "request already reviewed"}), 409

    req.status = status
    req.reviewed_by = admin.id
    if status == "approved":
        req.approved_at = datetime.now(timezone.utc)
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    current_app.logger.info(
        f"admin: product access {request_id} {status} by {admin.email}"
    )
    return jsonify({"status": status})


# ── SaaS Metrics ──────────────────────────────────────────────────────────────

@v1.route("/admin/saas-metrics", methods=["GET"])
@jwt_required()
def admin_saas_metrics():
    """
    Core SaaS health metrics for the admin dashboard.

    Returns:
        mrr                 — Monthly Recurring Revenue (sum of active plan prices, GBP)
        new_mrr             — MRR added this calendar month (new active subscriptions)
        churned_mrr         — MRR lost this calendar month (canceled subscriptions)
        net_mrr             — new_mrr - churned_mrr
        active_customers    — count of active (non-trialing) paid subscriptions
        trialing_customers  — count of trialing subscriptions
        monthly_churn_rate  — canceled_this_month / (active_now + canceled_this_month)
        arpu                — average revenue per active paying user (GBP)
        ltv_estimate        — ARPU / monthly_churn_rate (null if churn_rate = 0)
        cac                 — total marketing spend this month / new_customers_this_month
                              (null if no spend data entered)
        ltv_cac_ratio       — ltv_estimate / cac (null if either is null)
        spend_this_month    — sum of MarketingSpend entries for current period
        new_customers_this_month — new active subscriptions started this calendar month
    """
    if not _require_admin():
        return jsonify({"error": "forbidden"}), 403

    from src.models.billing import Plan, Subscription, table_exists
    from src.models import MarketingSpend

    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    period_str = now.strftime("%Y-%m")

    # Defaults
    mrr = 0.0
    new_mrr = 0.0
    churned_mrr = 0.0
    active_customers = 0
    trialing_customers = 0
    monthly_churn_rate = 0.0
    arpu = 0.0
    ltv_estimate = None
    cac = None
    ltv_cac_ratio = None
    spend_this_month = 0.0
    new_customers_this_month = 0

    if table_exists(Subscription) and table_exists(Plan):
        try:
            # Active paid subscriptions (excludes trialing)
            active_rows = (
                db.session.query(Plan.price_cents)
                .join(Subscription, Subscription.plan_id == Plan.id)
                .filter(Subscription.status == "active")
                .all()
            )
            active_customers = len(active_rows)
            mrr = sum(r[0] for r in active_rows) / 100.0
            arpu = mrr / active_customers if active_customers else 0.0

            # Trialing
            trialing_customers = (
                db.session.query(func.count(Subscription.id))
                .filter(Subscription.status == "trialing")
                .scalar() or 0
            )

            # New active subscriptions this calendar month
            new_rows = (
                db.session.query(Plan.price_cents)
                .join(Subscription, Subscription.plan_id == Plan.id)
                .filter(Subscription.status == "active")
                .filter(Subscription.created_at >= month_start)
                .all()
            )
            new_customers_this_month = len(new_rows)
            new_mrr = sum(r[0] for r in new_rows) / 100.0

            # Canceled subscriptions this calendar month (churn)
            canceled_rows = (
                db.session.query(Plan.price_cents)
                .join(Subscription, Subscription.plan_id == Plan.id)
                .filter(Subscription.status == "canceled")
                .filter(Subscription.updated_at >= month_start)
                .all()
            )
            canceled_this_month = len(canceled_rows)
            churned_mrr = sum(r[0] for r in canceled_rows) / 100.0

            # Monthly churn rate: canceled / (active + canceled_this_month)
            denom = active_customers + canceled_this_month
            monthly_churn_rate = round(canceled_this_month / denom, 4) if denom else 0.0

            # LTV = ARPU / churn_rate (average customer lifetime × ARPU)
            if monthly_churn_rate > 0 and arpu > 0:
                ltv_estimate = round(arpu / monthly_churn_rate, 2)

        except Exception as exc:
            current_app.logger.warning("saas_metrics billing query failed: %s", exc)

    # CAC from manual spend entries
    try:
        spend_rows = (
            db.session.query(MarketingSpend.amount_gbp)
            .filter(MarketingSpend.period == period_str)
            .all()
        )
        spend_this_month = round(sum(r[0] for r in spend_rows), 2)
        if spend_this_month > 0 and new_customers_this_month > 0:
            cac = round(spend_this_month / new_customers_this_month, 2)
        elif spend_this_month > 0:
            cac = None  # spend exists but no new customers yet this month
    except Exception as exc:
        current_app.logger.warning("saas_metrics spend query failed: %s", exc)

    if ltv_estimate and cac and cac > 0:
        ltv_cac_ratio = round(ltv_estimate / cac, 2)

    return jsonify({
        "mrr": round(mrr, 2),
        "new_mrr": round(new_mrr, 2),
        "churned_mrr": round(churned_mrr, 2),
        "net_mrr": round(new_mrr - churned_mrr, 2),
        "active_customers": active_customers,
        "trialing_customers": trialing_customers,
        "monthly_churn_rate": monthly_churn_rate,
        "monthly_churn_pct": round(monthly_churn_rate * 100, 2),
        "arpu": round(arpu, 2),
        "ltv_estimate": ltv_estimate,
        "cac": cac,
        "ltv_cac_ratio": ltv_cac_ratio,
        "spend_this_month": spend_this_month,
        "new_customers_this_month": new_customers_this_month,
        "period": period_str,
    })


# ── Marketing Spend (manual CAC input) ────────────────────────────────────────

@v1.route("/admin/marketing-spend", methods=["GET"])
@jwt_required()
def list_marketing_spend():
    """List recent marketing spend entries (last 6 months)."""
    if not _require_admin():
        return jsonify({"error": "forbidden"}), 403

    from src.models import MarketingSpend
    rows = (
        db.session.query(MarketingSpend)
        .order_by(MarketingSpend.period.desc(), MarketingSpend.created_at.desc())
        .limit(50)
        .all()
    )
    return jsonify({
        "entries": [
            {
                "id": r.id,
                "period": r.period,
                "channel": r.channel,
                "amount_gbp": r.amount_gbp,
                "notes": r.notes,
                "created_at": r.created_at.isoformat(),
            }
            for r in rows
        ]
    })


@v1.route("/admin/marketing-spend", methods=["POST"])
@jwt_required()
def create_marketing_spend():
    """
    Record ad spend for a period.

    Body: {period: "2026-02", channel: "google", amount_gbp: 1500.00, notes: "..."}
    """
    if not _require_admin():
        return jsonify({"error": "forbidden"}), 403

    from src.models import MarketingSpend
    body = request.get_json(silent=True) or {}
    period = (body.get("period") or "").strip()
    channel = (body.get("channel") or "").strip()
    amount_gbp = body.get("amount_gbp")

    if not period or not channel or amount_gbp is None:
        return jsonify({"error": "period, channel, and amount_gbp are required"}), 400

    import re
    if not re.match(r'^\d{4}-\d{2}$', period):
        return jsonify({"error": "period must be YYYY-MM format"}), 400

    try:
        amount_gbp = float(amount_gbp)
        if amount_gbp < 0:
            return jsonify({"error": "amount_gbp must be non-negative"}), 400
    except (TypeError, ValueError):
        return jsonify({"error": "amount_gbp must be a number"}), 400

    entry = MarketingSpend(
        period=period,
        channel=channel[:100],
        amount_gbp=amount_gbp,
        notes=(body.get("notes") or "").strip()[:500] or None,
    )
    db.session.add(entry)
    db.session.commit()
    return jsonify({"id": entry.id, "status": "created"}), 201


@v1.route("/admin/marketing-spend/<entry_id>", methods=["DELETE"])
@jwt_required()
def delete_marketing_spend(entry_id: str):
    """Delete a marketing spend entry."""
    if not _require_admin():
        return jsonify({"error": "forbidden"}), 403

    from src.models import MarketingSpend
    entry = db.session.get(MarketingSpend, entry_id)
    if not entry:
        return jsonify({"error": "not found"}), 404
    db.session.delete(entry)
    db.session.commit()
    return jsonify({"status": "deleted"}), 200


@v1.route("/admin/accounts/pending-deletion", methods=["GET"])
@jwt_required()
def admin_accounts_pending_deletion():
    """List all soft-deleted accounts, ordered oldest deletion first."""
    from src.models.auth import AuditLog

    if not _require_admin():
        return jsonify({"error": "forbidden"}), 403

    accounts = (
        Account.query.filter(Account.deleted_at.isnot(None))
        .order_by(Account.deleted_at.asc())
        .all()
    )

    result = []
    for acct in accounts:
        log = (
            AuditLog.query
            .filter_by(account_id=acct.id, action="account.deleted")
            .order_by(AuditLog.created_at.desc())
            .first()
        )
        initiated_by = (log.metadata_json or {}).get("initiated_by_email") if log else None
        result.append({
            "id": acct.id,
            "name": acct.name,
            "deleted_at": acct.deleted_at.isoformat(),
            "initiated_by": initiated_by,
        })

    return jsonify({"accounts": result}), 200


@v1.route("/admin/accounts/<int:account_id>/purge", methods=["DELETE"])
@jwt_required()
def admin_account_purge(account_id: int):
    """
    Hard-delete an account that has been soft-deleted for at least 30 days.
    Removes all rows across every account-scoped table.
    Admin-only. Irreversible.
    """
    from src.models.auth import AuditLog

    admin = _require_admin()
    if not admin:
        return jsonify({"error": "forbidden"}), 403

    account = db.session.get(Account, account_id)
    if not account:
        return jsonify({"error": "Account not found"}), 404
    if not account.is_deleted:
        return jsonify({"error": "Account has not been soft-deleted. Use the account deletion endpoint first."}), 409

    grace_cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    if account.deleted_at > grace_cutoff:
        days_remaining = (account.deleted_at - grace_cutoff).days + 1
        return jsonify({"error": f"Grace period not yet elapsed. {days_remaining} day(s) remaining."}), 409

    # Write audit log before destroying data
    log = AuditLog(
        account_id=None,  # account is being removed; keep as NULL so FK doesn't break
        user_id=admin.id,
        action="account.purged",
        resource_type="account",
        resource_id=str(account_id),
        ip_address=request.remote_addr,
        user_agent=(request.user_agent.string or "")[:300],
        metadata_json={
            "account_name": account.name,
            "deleted_at": account.deleted_at.isoformat(),
            "purged_by_email": admin.email,
        },
    )
    db.session.add(log)
    db.session.flush()  # persist log before cascade deletes

    # Delete in FK-safe dependency order
    purge_tables = [
        ("ticket_embeddings", "account_id"),
        ("draft_reply_feedback", "ticket_fk"),
        ("automation_rule_executions", "account_id"),
        ("automation_rules", "account_id"),
        ("automation_suggestions", "account_id"),
        ("automation_studio_waitlist", "account_id"),
        ("kb_article_embeddings", "account_id"),
        ("kb_articles", "account_id"),
        ("kb_integrations", "account_id"),
        ("inboxiq_tickets", "account_id"),
        ("inbox_connections", "account_id"),
        ("triage_label_configs", "account_id"),
        ("triage_configs", "account_id"),
        ("dspy_training_metrics", "account_id"),
        ("agent_events", "account_id"),
        ("charge_attempts", "account_id"),
        ("invoices", "account_id"),
        ("subscriptions", "account_id"),
        ("customer_billing_profiles", "account_id"),
        ("account_usage_counters", "account_id"),
        ("account_feature_flags", "account_id"),
        ("account_llm_configs", "account_id"),
        ("registered_apps", "account_id"),
        ("webhook_providers", "account_id"),
        ("passkeys", "user_id"),   # via users
        ("totp_devices", "user_id"),
        ("auth_events", "user_id"),
        ("users", "account_id"),
        ("accounts", "id"),
    ]
    deleted_counts = {}
    for table, col in purge_tables:
        if col == "ticket_fk":
            # no account_id on this table — delete via ticket ownership
            result = db.session.execute(
                text(f"DELETE FROM {table} WHERE ticket_id IN (SELECT id FROM inboxiq_tickets WHERE account_id = :aid)"),  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                {"aid": account_id},
            )
            deleted_counts[table] = result.rowcount
        elif col == "user_id":
            # scope to this account's users
            user_ids = db.session.execute(
                text("SELECT id FROM users WHERE account_id = :aid"), {"aid": account_id}
            ).scalars().all()
            if user_ids:
                result = db.session.execute(
                    text(f"DELETE FROM {table} WHERE {col} = ANY(:ids)"),  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                    {"ids": list(user_ids)},
                )
                deleted_counts[table] = result.rowcount
        else:
            result = db.session.execute(
                text(f"DELETE FROM {table} WHERE {col} = :aid"), {"aid": account_id}  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
            )
            deleted_counts[table] = result.rowcount

    db.session.commit()
    current_app.logger.warning({
        "event": "account.purged",
        "account_id": account_id,
        "admin_user_id": admin.id,
        "rows_deleted": deleted_counts,
    })
    return jsonify({"ok": True, "purged_account_id": account_id, "rows_deleted": deleted_counts}), 200
