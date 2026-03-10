import os
import re
from functools import lru_cache
from datetime import datetime, timezone, timedelta
from flask import Blueprint, jsonify, request, url_for, redirect, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
from celery import Celery
from sqlalchemy import func, or_, case, desc
from src.api.v1 import v1
from src.extensions import db
from src.models.ai import DspyTrainingMetric
from src.models.core import Account, InboxConnection, AccountLLMConfig, ALLOWED_LLM_PROVIDERS
from src.models.misc import Feedback
from src.models.tickets import Ticket, DraftReplyFeedback
from src.inbox.logic import normalize_email_payload, run_dspy_decision, sample_messages, compute_due_at
from src.inbox.poll import (
    fetch_messages_gmail, fetch_messages_outlook,
    fetch_gmail_labels, fetch_outlook_categories,
    bootstrap_inboxiq_labels_gmail, bootstrap_inboxiq_labels_outlook,
    bootstrap_gmail_filters,
)

BODY_PREVIEW_LIMIT = 240


def _redact_body_preview(text: str) -> str:
    """
    Strip obvious secrets from body previews (tokens, reset codes, signatures).
    Keeps surrounding context for triage while masking sensitive params.
    """
    if not text:
        return ""

    patterns = [
        (r"(?i)(token|access_token|auth_token|reset_token|code|signature|secret|key)=([A-Za-z0-9._-]+)", r"\1=[redacted]"),
        (r"(?i)(password|passcode|otp|pin)=([A-Za-z0-9]+)", r"\1=[redacted]"),
        (r"https?://\\S{80,}", "[redacted link]"),
    ]

    redacted = text
    for pattern, repl in patterns:
        redacted = re.sub(pattern, repl, redacted)
    return redacted


def _build_body_preview(text: str) -> str:
    return _redact_body_preview(text or "")[:BODY_PREVIEW_LIMIT]

def _get_account_id(user_id: int | None) -> int | None:
    from src.models import User, Account  # local import to avoid cycles
    if not user_id:
        return None
    user = User.query.get(user_id)
    acct = user.account if user else None
    return getattr(acct, "id", None)


@lru_cache(maxsize=1)
def _celery_client() -> Celery:
    broker_url = current_app.config.get("CELERY_BROKER_URL") or os.getenv("CELERY_BROKER_URL")
    backend_url = current_app.config.get("CELERY_RESULT_BACKEND") or os.getenv("CELERY_RESULT_BACKEND")
    return Celery("inboxiq", broker=broker_url, backend=backend_url)


@v1.route("/inboxiq/inbound-email", methods=["POST"])
@jwt_required(optional=True)
def inbound_email():
    """
    Webhook/ingress for new emails. Validates, dedupes, and enqueues processing.
    """
    user_id = get_jwt_identity()
    account_id = _get_account_id(user_id)
    payload = request.get_json(force=True, silent=True) or {}
    raw_email = payload.get("message") or payload

    try:
        normalized = normalize_email_payload(raw_email)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400

    existing = Ticket.query.filter_by(
        message_id=normalized.get("message_id"),
        provider=normalized.get("provider"),
    ).first()
    if existing:
        return jsonify({"status": "duplicate", "ticket": existing.to_dict()}), 200

    try:
        task = _celery_client().send_task(
            "inboxiq.process_incoming_email",
            args=[{"email": normalized, "user_id": user_id, "account_id": account_id}],
            queue="inbox",
        )
    except Exception as exc:
        current_app.logger.exception("failed to enqueue inbound email", exc_info=exc)
        return jsonify({"error": "enqueue_failed", "message": str(exc)}), 502

    return jsonify({"status": "queued", "task_id": task.id})


@v1.route("/inboxiq/triage", methods=["POST"])
@jwt_required(optional=True)
def triage():
    user_id = get_jwt_identity()
    payload = request.get_json() or {}
    dry_run = bool(payload.get("dry_run"))
    messages = []
    if payload.get("messages"):
        messages = payload["messages"]
    elif payload.get("message"):
        messages = [payload["message"]]
    elif payload.get("seed_demo") or payload.get("use_samples"):
        messages = sample_messages()
    else:
        return jsonify({"error": "Provide message/messages or set seed_demo=true"}), 400

    account_id = _get_account_id(user_id)
    results = []
    summary = {"created": 0, "duplicates": 0, "errors": 0}

    for raw_email in messages:
        try:
            normalized = normalize_email_payload(raw_email)
        except ValueError as exc:
            summary["errors"] += 1
            results.append({"error": str(exc), "payload": raw_email})
            continue

        existing = Ticket.query.filter_by(
            message_id=normalized["message_id"], provider=normalized.get("provider")
        ).first()
        if existing and not dry_run:
            summary["duplicates"] += 1
            results.append({"status": "duplicate", "ticket": existing.to_dict()})
            continue

        try:
            decision = run_dspy_decision(normalized, account_id=account_id)
        except Exception as exc:
            summary["errors"] += 1
            results.append({"error": "triage_failed", "message": str(exc), "payload": raw_email})
            continue
        # Apply feedback-based overrides for identical subjects that were manually corrected.
        try:
            lower_subject = normalized["subject"].strip().lower()
            feedback_match = (
                Ticket.query.filter(
                    Ticket.manual_override.is_(True),
                    func.lower(Ticket.subject) == lower_subject,
                )
                .order_by(Ticket.updated_at.desc())
                .first()
            )
            fb = (feedback_match.override_metadata or {}).get("feedback") if feedback_match else None
            if fb:
                if fb.get("category"):
                    decision.category = fb["category"]
                if fb.get("priority"):
                    decision.priority = fb["priority"]
                if fb.get("team"):
                    decision.team = fb["team"]
                if fb.get("assigned_to"):
                    decision.assigned_to = fb["assigned_to"]
                decision.decision_trace.append(f"feedback_override:{feedback_match.id}")
        except Exception as exc:  # keep triage running even if feedback lookup fails
            current_app.logger.warning("feedback override lookup failed: %s", exc)

        ticket_record = None
        if not dry_run:
            redacted_body = _build_body_preview(normalized.get("body") or "")
            status = "needs_review" if decision.needs_review else "new"
            if decision.action_required is False:
                status = "auto_handled"
            elif decision.action_required == "optional" and status != "needs_review":
                status = "optional"
            ticket_record = Ticket(
                account_id=account_id,
                user_id=user_id,
                subject=normalized["subject"],
                from_email=normalized["from_email"],
                body_preview=redacted_body,
                category=decision.category,
                priority=decision.priority,
                sentiment=decision.sentiment,
                entities=decision.entities,
                status=status,
                message_id=normalized["message_id"],
                provider=normalized.get("provider"),
                provider_thread_url=normalized.get("provider_thread_url"),
                decision=decision.to_dict(),
                team=decision.team,
                assigned_to=decision.assigned_to,
                owner=decision.owner,
                due_at=compute_due_at(decision.priority, account_id),
                llm_model=decision.llm_model,
                llm_tokens_in=decision.llm_tokens_in,
                llm_tokens_out=decision.llm_tokens_out,
                llm_cost_usd=decision.llm_cost_usd,
            )
            db.session.add(ticket_record)
            try:
                db.session.commit()
                summary["created"] += 1
            except Exception:
                db.session.rollback()
                summary["errors"] += 1
                results.append({"error": "failed to persist", "payload": raw_email})
                continue

        results.append(
            {
                "decision": decision.to_dict(),
                "ticket": ticket_record.to_dict() if ticket_record else None,
                "dry_run": dry_run,
            }
        )

    return jsonify({"summary": summary, "results": results})


@v1.route("/inboxiq/tickets", methods=["GET"])
@jwt_required()
def tickets():
    user_id = get_jwt_identity()
    account_id = _get_account_id(user_id)
    page = max(int(request.args.get("page", 1)), 1)
    page_size = min(max(int(request.args.get("page_size", 20)), 1), 100)
    query = Ticket.query.order_by(Ticket.created_at.desc())

    if account_id:
        query = query.filter(Ticket.account_id == account_id)

    if request.args.get("status"):
        query = query.filter(Ticket.status == request.args["status"])
    if request.args.get("category"):
        query = query.filter(Ticket.category == request.args["category"])
    if request.args.get("priority"):
        query = query.filter(Ticket.priority == request.args["priority"])
    if request.args.get("provider"):
        query = query.filter(Ticket.provider == request.args["provider"])
    if request.args.get("created_after"):
        try:
            after_dt = datetime.fromisoformat(request.args["created_after"])
            query = query.filter(Ticket.created_at >= after_dt)
        except ValueError:
            return jsonify({"error": "invalid created_after (use ISO8601)"}), 400
    if request.args.get("created_before"):
        try:
            before_dt = datetime.fromisoformat(request.args["created_before"])
            query = query.filter(Ticket.created_at <= before_dt)
        except ValueError:
            return jsonify({"error": "invalid created_before (use ISO8601)"}), 400
    if request.args.get("q"):
        q = request.args["q"].strip()
        if q:
            query = query.filter(Ticket.search_vec.op("@@")(func.plainto_tsquery("english", q)))
    if request.args.get("mine") == "true" and user_id:
        query = query.filter(Ticket.user_id == user_id)

    total = query.count()
    items = query.offset((page - 1) * page_size).limit(page_size).all()
    return jsonify(
        {
            "tickets": [t.to_dict() for t in items],
            "pagination": {"page": page, "page_size": page_size, "total": total},
        }
    )


@v1.route("/inboxiq/cost-summary", methods=["GET"])
@jwt_required()
def cost_summary():
    """
    Return LLM cost and token totals for this account.

    Query params:
      - since  (ISO8601 datetime, default: start of current month)
      - until  (ISO8601 datetime, default: now)
      - group_by  "day" | "model" (default: neither — single aggregate)
    """
    from sqlalchemy import func as sqlfunc, cast, Date as SQLDate
    user_id = get_jwt_identity()
    account_id = _get_account_id(user_id)

    now = datetime.now(timezone.utc)
    default_since = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    try:
        since = datetime.fromisoformat(request.args["since"]) if request.args.get("since") else default_since
    except ValueError:
        return jsonify({"error": "invalid since (use ISO8601)"}), 400
    try:
        until = datetime.fromisoformat(request.args["until"]) if request.args.get("until") else now
    except ValueError:
        return jsonify({"error": "invalid until (use ISO8601)"}), 400

    group_by = request.args.get("group_by", "").lower()

    base = Ticket.query.filter(
        Ticket.account_id == account_id,
        Ticket.created_at >= since,
        Ticket.created_at <= until,
        Ticket.llm_tokens_in > 0,
    )

    if group_by == "day":
        rows = (
            db.session.query(
                cast(Ticket.created_at, SQLDate).label("day"),
                sqlfunc.count(Ticket.id).label("emails"),
                sqlfunc.sum(Ticket.llm_tokens_in).label("tokens_in"),
                sqlfunc.sum(Ticket.llm_tokens_out).label("tokens_out"),
                sqlfunc.sum(Ticket.llm_cost_usd).label("cost_usd"),
            )
            .filter(
                Ticket.account_id == account_id,
                Ticket.created_at >= since,
                Ticket.created_at <= until,
                Ticket.llm_tokens_in > 0,
            )
            .group_by(cast(Ticket.created_at, SQLDate))
            .order_by(cast(Ticket.created_at, SQLDate))
            .all()
        )
        return jsonify({
            "since": since.isoformat(),
            "until": until.isoformat(),
            "group_by": "day",
            "rows": [
                {
                    "day": str(r.day),
                    "emails": r.emails,
                    "tokens_in": r.tokens_in or 0,
                    "tokens_out": r.tokens_out or 0,
                    "cost_usd": float(r.cost_usd or 0),
                }
                for r in rows
            ],
        })

    if group_by == "model":
        rows = (
            db.session.query(
                Ticket.llm_model,
                sqlfunc.count(Ticket.id).label("emails"),
                sqlfunc.sum(Ticket.llm_tokens_in).label("tokens_in"),
                sqlfunc.sum(Ticket.llm_tokens_out).label("tokens_out"),
                sqlfunc.sum(Ticket.llm_cost_usd).label("cost_usd"),
            )
            .filter(
                Ticket.account_id == account_id,
                Ticket.created_at >= since,
                Ticket.created_at <= until,
                Ticket.llm_tokens_in > 0,
            )
            .group_by(Ticket.llm_model)
            .all()
        )
        return jsonify({
            "since": since.isoformat(),
            "until": until.isoformat(),
            "group_by": "model",
            "rows": [
                {
                    "model": r.llm_model or "unknown",
                    "emails": r.emails,
                    "tokens_in": r.tokens_in or 0,
                    "tokens_out": r.tokens_out or 0,
                    "cost_usd": float(r.cost_usd or 0),
                }
                for r in rows
            ],
        })

    # Single aggregate
    totals = base.with_entities(
        sqlfunc.count(Ticket.id),
        sqlfunc.sum(Ticket.llm_tokens_in),
        sqlfunc.sum(Ticket.llm_tokens_out),
        sqlfunc.sum(Ticket.llm_cost_usd),
    ).one()
    emails, tokens_in, tokens_out, cost_usd = totals
    emails = emails or 0
    tokens_in = tokens_in or 0
    tokens_out = tokens_out or 0
    cost_usd = float(cost_usd or 0)

    return jsonify({
        "since": since.isoformat(),
        "until": until.isoformat(),
        "emails_processed": emails,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "total_tokens": tokens_in + tokens_out,
        "cost_usd": cost_usd,
        "cost_per_email_usd": round(cost_usd / emails, 8) if emails else 0,
    })


def _priority_order():
    return case(
        (Ticket.priority == "P0", 0),  # Legacy P0 sorts as highest
        (Ticket.priority == "P1", 0),  # P1 = Urgent
        (Ticket.priority == "P2", 1),  # P2 = High
        (Ticket.priority == "P3", 2),  # P3 = Normal
        (Ticket.priority == "P4", 3),  # P4 = Low
        else_=2,  # Unknown defaults to normal
    )


def _parse_scope(scope: str | None):
    scope = (scope or "today").lower()
    now = datetime.now(timezone.utc)
    if scope == "last_24_hours":
        return scope, now - timedelta(hours=24)
    if scope == "last_7_days":
        return scope, now - timedelta(days=7)
    if scope == "all_time":
        return scope, None
    return "today", now.replace(hour=0, minute=0, second=0, microsecond=0)


def _ticket_view(t: Ticket) -> dict:
    from src.dspy.triage_config import get_triage_config
    triage_cfg = get_triage_config(t.account_id)

    decision = t.decision or {}
    priority = (t.priority or decision.get("priority") or triage_cfg.default_priority).upper()
    sentiment = (t.sentiment or decision.get("sentiment") or "neutral").lower()
    action_required = t.action_required
    needs_review = bool(decision.get("needs_review") or (t.status == "needs_review"))
    auto_flag = bool(decision.get("auto_handled") or (t.status == "auto_handled"))
    risk_flag = bool(decision.get("risk_flag"))
    provider = (t.provider or decision.get("provider") or "email").lower()

    def _ai_reason(decision: dict, fallback: str) -> str:
        # Check top-level first, then merged dict (where auto-handled reasons are stored)
        return (
            decision.get("ai_reason")
            or decision.get("reason")
            or decision.get("merged", {}).get("ai_reason")
            or fallback
        )

    def _sla_display(priority_val: str | None) -> str:
        return triage_cfg.get_sla_display(priority_val)

    def _infer_use_case() -> str:
        hint = (decision.get("use_case") or "").lower()
        if hint:
            return hint
        category = (t.category or decision.get("category") or "").lower()
        intent = (decision.get("intent") or "").lower()
        subject = (t.subject or "").lower()
        tokens = f"{category} {intent} {subject}"
        if any(term in tokens for term in ("claim", "claims", "insurance")):
            return "claims"
        if any(term in tokens for term in ("hr", "people", "payroll", "benefits")):
            return "hr"
        if any(term in tokens for term in ("finance", "billing", "invoice", "refund", "payment")):
            return "finance"
        return "support"

    if action_required is None and auto_flag:
        action_required = False
    if action_required is None and triage_cfg.should_auto_handle_p2_neutral(priority, sentiment, risk_flag):
        action_required = False
    if action_required is None and needs_review:
        action_required = "optional"
    # Enforce status-driven override to avoid stale decision flags.
    if t.status == "auto_handled":
        action_required = False
    if t.status == "optional":
        action_required = "optional"

    def _channel_from_provider(provider_val: str) -> str:
        email_providers = {
            "gmail",
            "outlook",
            "imap",
            "email",
            "google",
            "gsuite",
            "google_oauth",
            "ms_graph",
            "microsoft",
            "office365",
            "exchange",
            "ews",
            "smtp",
        }
        if provider_val in email_providers:
            return "email"
        if provider_val in {"feedback"}:
            return "feedback"
        if provider_val in {"web", "form", "forms"}:
            return "form"
        if provider_val in {"chat", "intercom", "slack"}:
            return "chat"
        if provider_val in {"crm", "hubspot", "salesforce"}:
            return "crm"
        if provider_val in {"api", "webhook"}:
            return "api"
        return "other"

    if action_required is True:
        decision_outcome = "action_required"
    elif action_required == "optional":
        decision_outcome = "needs_review"
    elif action_required is False:
        decision_outcome = "auto_handled"
    else:
        decision_outcome = "action_required"

    view = {
        "id": t.id,
        "priority": priority,
        "subject": t.subject,
        "category": t.category or decision.get("category") or triage_cfg.default_category,
        "intent": decision.get("intent") or triage_cfg.default_category,
        "sentiment": sentiment or "neutral",
        "provider": provider,
        "channel": _channel_from_provider(provider),
        "ai_reason": _ai_reason(decision, triage_cfg.get_action_reason_text(action_required)),
        "owner": t.owner or decision.get("owner") or triage_cfg.default_owner,
        "team": t.team or decision.get("team"),
        "assigned_to": t.assigned_to or decision.get("assigned_to"),
        "due_at": t.due_at.isoformat() if t.due_at else None,
        "sla": _sla_display(priority),
        "url": url_for("ticket_detail", ticket_id=t.id),
        "provider_url": t.provider_thread_url or decision.get("url"),
        "action_required": action_required,
        "status": t.status,
        "use_case": _infer_use_case(),
        "decision_type": decision.get("decision_type") or "triage",
        "decision_outcome": decision_outcome,
        "confidence": decision.get("confidence"),
        "decision_trace": decision.get("decision_trace") or [],
        "entities_json": decision.get("entities_json"),
        "route_json": decision.get("route_json"),
        "workflow_json": decision.get("workflow_json"),
        "escalation_json": decision.get("escalation_json"),
        "risk_flag": risk_flag,
        "draft_reply": bool(decision.get("reply_text") or decision.get("draft_reply")),
    }
    return view


@v1.route("/inboxiq/dashboard-data", methods=["GET"])
@jwt_required()
def dashboard_data():
    """
    Dashboard data API: filters/sorts by scope, priority, action_required, text search.
    """
    user_id = get_jwt_identity()
    account_id = _get_account_id(user_id)
    if not account_id:
        return jsonify({"error": "missing_account"}), 400

    scope, created_after = _parse_scope(request.args.get("scope"))
    priority = (request.args.get("priority") or "").upper()
    q = (request.args.get("q") or "").strip()
    action_only = request.args.get("action_only", "true").lower() != "false"
    draft_only = request.args.get("draft_only", "false").lower() == "true"
    use_case_filter = (request.args.get("use_case") or "").strip().lower()
    channel_filter = (request.args.get("channel") or "").strip().lower()

    query = Ticket.query.filter(Ticket.account_id == account_id)
    if created_after:
        query = query.filter(Ticket.created_at >= created_after)
    if priority in ("P0", "P1", "P2", "P3", "P4"):  # P0 kept for legacy
        query = query.filter(Ticket.priority == priority)
    if q:
        search_filter = Ticket.subject.ilike(f"%{q}%") | Ticket.body_preview.ilike(f"%{q}%")
        try:
            search_filter = or_(search_filter, Ticket.search_vec.op("@@")(func.plainto_tsquery("english", q)))
        except Exception:
            # fallback to plain ilike if search_vec is unavailable
            pass
        query = query.filter(search_filter)

    # Sort by priority first, then recency
    query = query.order_by(_priority_order(), Ticket.created_at.desc())

    all_tickets = query.limit(200).all()
    now = datetime.now(timezone.utc)

    decision_minutes = []
    sla_risk_count = 0
    for t in all_tickets:
        if t.created_at:
            end_time = t.updated_at or t.created_at
            delta = (end_time - t.created_at).total_seconds() / 60
            if delta >= 0:
                decision_minutes.append(delta)
        if t.due_at and t.due_at <= now + timedelta(hours=1) and t.status not in ("auto_handled",):
            sla_risk_count += 1

    from src.dspy.triage_config import get_triage_config
    triage_cfg = get_triage_config(account_id)

    action_required_items = []
    optional_items = []
    auto_items = []
    for t in all_tickets:
        view = _ticket_view(t)
        if use_case_filter and use_case_filter != "all":
            if (view.get("use_case") or "").lower() != use_case_filter:
                continue
        if channel_filter and channel_filter != "all":
            if (view.get("channel") or "").lower() != channel_filter:
                continue
        if draft_only and not view.get("draft_reply"):
            continue
        action_required = view.get("action_required")
        needs_review = bool((t.decision or {}).get("needs_review") or (t.status == "needs_review"))
        risk_flag = bool((t.decision or {}).get("risk_flag"))
        if action_required is True:
            action_required_items.append(view)
        elif action_required == "optional" or needs_review:
            view["ai_reason"] = view.get("ai_reason") or triage_cfg.get_fallback_message("optional")
            optional_items.append(view)
        elif action_required is False or t.status == "auto_handled" or triage_cfg.should_auto_handle_p2_neutral(view["priority"], view["sentiment"], risk_flag):
            view["ai_reason"] = view.get("ai_reason") or triage_cfg.get_fallback_message("auto_handled")
            auto_items.append(view)
        else:
            action_required_items.append(view)

    feedback_auto = (
        Feedback.query.filter(
            Feedback.account_id == account_id,
            Feedback.action_required.in_(["false", "optional"]),
        )
        .order_by(Feedback.created_at.desc())
        .limit(100)
        .all()
    )
    auto_feedback_items = []
    for fb in feedback_auto:
        decision = fb.ai_decision_json or {}
        auto_feedback_items.append(
            {
                "id": fb.id,
                "subject": (decision.get("summary") or fb.message or "Feedback")[:140],
                "category": decision.get("category") or "feedback",
                "intent": decision.get("intent") or "feedback",
                "sentiment": decision.get("sentiment") or "neutral",
                "priority": decision.get("priority") or triage_cfg.default_priority,
                "ai_reason": decision.get("ai_reason") or triage_cfg.get_fallback_message("auto_handled"),
                "owner": decision.get("owner") or triage_cfg.default_owner,
                "team": decision.get("team") or triage_cfg.default_team or "Product",
                "assigned_to": decision.get("assigned_to"),
                "provider": "feedback",
                "channel": "feedback",
                "action_required": False if fb.action_required == "false" else "optional",
                "decision_type": decision.get("decision_type") or "feedback",
                "decision_outcome": "auto_handled" if fb.action_required == "false" else "needs_review",
                "confidence": decision.get("confidence"),
                "decision_trace": decision.get("decision_trace") or [],
                "use_case": decision.get("use_case") or "feedback",
                "risk_flag": bool(decision.get("risk_flag")),
                "url": f"/feedback/{fb.id}",
                "source": "feedback",
            }
        )

    total = len(action_required_items) + len(optional_items) + len(auto_items)
    actionable = len(action_required_items)
    auto_count = len(auto_items)
    eliminated_pct = round((auto_count / total) * 100, 1) if total else 0.0

    if action_only:
        optional_items = []
        auto_items = []

    email_providers = {
        "gmail",
        "outlook",
        "imap",
        "email",
        "google",
        "gsuite",
        "google_oauth",
        "ms_graph",
        "microsoft",
        "office365",
        "exchange",
        "ews",
        "smtp",
    }
    auto_email_count = sum(
        1 for item in auto_items
        if (item.get("provider") or "").lower() in email_providers
    )
    auto_other_count = len(auto_items) - auto_email_count

    avg_decision_minutes = round(sum(decision_minutes) / len(decision_minutes), 1) if decision_minutes else 0

    return jsonify(
        {
            "scope": scope,
            "counts": {
                "action_required": actionable,
                "optional": len(optional_items),
                "auto_handled": len(auto_items),
                "auto_handled_email": auto_email_count,
                "auto_handled_other": auto_other_count,
                "auto_handled_feedback": len(auto_feedback_items),
                "actionable_surfaced": actionable,
                "auto_handled_metric": auto_count,
                "triage_eliminated_pct": eliminated_pct,
                "missed_emails": 0,
                "decision_time_avg_minutes": avg_decision_minutes,
                "sla_risk_count": sla_risk_count,
            },
            "action_required": action_required_items,
            "optional": optional_items,
            "auto_handled": auto_items,
            "auto_handled_feedback": auto_feedback_items,
        }
    )


@v1.route("/inboxiq/training-metrics", methods=["GET"])
@jwt_required()
def training_metrics():
    """
    Return recent DSPy training metrics for the current account.
    """
    user_id = get_jwt_identity()
    account_id = _get_account_id(user_id)
    if not account_id:
        return jsonify({"error": "missing_account"}), 400

    rows = (
        DspyTrainingMetric.query.filter(DspyTrainingMetric.account_id == account_id)
        .order_by(desc(DspyTrainingMetric.created_at))
        .limit(20)
        .all()
    )
    metrics = [row.to_dict() for row in rows]
    latest = metrics[0] if metrics else None
    return jsonify({"latest": latest, "metrics": metrics})


@v1.route("/inboxiq/tickets/<ticket_id>/override", methods=["POST"])
@jwt_required(optional=True)
def override(ticket_id: str):
    user_id = get_jwt_identity()
    ticket = Ticket.query.get(ticket_id)
    if not ticket:
        return jsonify({"error": "Ticket not found"}), 404

    data = request.get_json() or {}
    category = data.get("category")
    priority = data.get("priority")
    sentiment = data.get("sentiment")
    status = data.get("status")
    if not any([category, priority, sentiment, status]):
        return jsonify({"error": "Provide category, priority, sentiment, or status"}), 400

    previous = {
        "category": ticket.category,
        "priority": ticket.priority,
        "sentiment": ticket.sentiment,
        "status": ticket.status,
    }
    status_action_map = {
        "auto_handled": False,
        "optional": "optional",
        "needs_review": "optional",
        "new": True,
        "open": True,
    }
    if category:
        ticket.category = category
    if priority:
        ticket.priority = priority
    if sentiment:
        ticket.sentiment = sentiment
    if status:
        ticket.status = status
        mapped_action_required = status_action_map.get(status)
        if mapped_action_required is not None:
            ticket.action_required = mapped_action_required
    ticket.manual_override = True
    ticket.override_metadata = {
        "by_user": user_id,
        "at": datetime.utcnow().isoformat(),
        "previous": previous,
        "reason": data.get("reason"),
    }
    db.session.commit()
    return jsonify({"ticket": ticket.to_dict()})


@v1.route("/inboxiq/tickets/<ticket_id>/feedback", methods=["POST"])
@jwt_required()
def ticket_feedback(ticket_id: str):
    """
    Collect quick feedback on triage correctness; optionally override category/priority.
    """
    ticket = Ticket.query.get(ticket_id)
    if not ticket:
        return jsonify({"error": "Ticket not found"}), 404
    data = request.get_json() or {}
    correct = bool(data.get("correct", False))
    # Trim inputs to avoid persisting accidental whitespace
    category = (data.get("category") or "").strip() or None
    priority = (data.get("priority") or "").strip() or None
    team = (data.get("team") or "").strip() or None
    assigned_to = (data.get("assigned_to") or "").strip() or None
    note = (data.get("note") or "").strip() or None

    feedback = ticket.override_metadata or {}
    feedback["feedback"] = {
        "correct": correct,
        "category": category,
        "priority": priority,
        "note": note,
        "at": datetime.utcnow().isoformat(),
    }
    ticket.override_metadata = feedback
    if not correct:
        previous = {"category": ticket.category, "priority": ticket.priority}
        if category:
            ticket.category = category
        if priority:
            ticket.priority = priority
            ticket.due_at = compute_due_at(ticket.priority, ticket.account_id)
        if team:
            ticket.team = team
        if assigned_to:
            ticket.assigned_to = assigned_to
        ticket.manual_override = True
        ticket.override_metadata["previous"] = previous
    try:
        db.session.commit()
    except Exception as exc:
        current_app.logger.error(
            {"event": "ticket.feedback.error", "ticket_id": ticket_id, "error": str(exc)}, exc_info=True
        )
        db.session.rollback()
        return jsonify({"error": "Could not save feedback"}), 500
    return jsonify({"ticket": ticket.to_dict()})


@v1.route("/inboxiq/tickets/<ticket_id>/reply-feedback", methods=["POST"])
@jwt_required(optional=True)
def reply_feedback(ticket_id: str):
    """
    Collect feedback on AI-generated draft reply quality.
    Tracks acceptance, edits, helpfulness scores, and time saved.

    Expected payload:
    {
        "feedback_type": "accepted"|"edited"|"rejected",
        "final_text": "...",  # Required if feedback_type is "edited"
        "helpfulness_score": 1-5,  # Optional rating
        "time_saved_seconds": 120,  # Optional time tracking
        "metadata": {}  # Optional additional metadata
    }
    """
    ticket = Ticket.query.get(ticket_id)
    if not ticket:
        return jsonify({"error": "Ticket not found"}), 404

    # Check if ticket has a draft reply
    decision = ticket.decision or {}
    draft_text = decision.get("reply_text")
    if not draft_text:
        return jsonify({"error": "No draft reply found for this ticket"}), 400

    data = request.get_json() or {}
    feedback_type = (data.get("feedback_type") or "").strip().lower()
    if feedback_type not in ("accepted", "edited", "rejected"):
        return jsonify({"error": "feedback_type must be 'accepted', 'edited', or 'rejected'"}), 400

    final_text = (data.get("final_text") or "").strip() or None
    if feedback_type == "edited" and not final_text:
        return jsonify({"error": "final_text is required when feedback_type is 'edited'"}), 400

    helpfulness_score = data.get("helpfulness_score")
    if helpfulness_score is not None:
        try:
            helpfulness_score = int(helpfulness_score)
            if not (1 <= helpfulness_score <= 5):
                return jsonify({"error": "helpfulness_score must be between 1 and 5"}), 400
        except (ValueError, TypeError):
            return jsonify({"error": "helpfulness_score must be an integer"}), 400

    time_saved_seconds = data.get("time_saved_seconds")
    if time_saved_seconds is not None:
        try:
            time_saved_seconds = int(time_saved_seconds)
        except (ValueError, TypeError):
            time_saved_seconds = None

    # Calculate edit distance if final_text provided
    edit_distance = None
    if final_text and draft_text:
        # Simple Levenshtein distance calculation
        def levenshtein(s1: str, s2: str) -> int:
            if len(s1) < len(s2):
                return levenshtein(s2, s1)
            if len(s2) == 0:
                return len(s1)
            previous_row = range(len(s2) + 1)
            for i, c1 in enumerate(s1):
                current_row = [i + 1]
                for j, c2 in enumerate(s2):
                    insertions = previous_row[j + 1] + 1
                    deletions = current_row[j] + 1
                    substitutions = previous_row[j] + (c1 != c2)
                    current_row.append(min(insertions, deletions, substitutions))
                previous_row = current_row
            return previous_row[-1]

        edit_distance = levenshtein(draft_text, final_text)

    # Create feedback record
    feedback = DraftReplyFeedback(
        ticket_id=ticket_id,
        draft_text=draft_text,
        final_text=final_text,
        feedback_type=feedback_type,
        edit_distance=edit_distance,
        helpfulness_score=helpfulness_score,
        time_saved_seconds=time_saved_seconds,
        metadata_json=data.get("metadata") or {},
    )

    try:
        db.session.add(feedback)
        db.session.commit()
        current_app.logger.info(
            {"event": "reply_feedback.created", "ticket_id": ticket_id, "feedback_type": feedback_type}
        )
    except Exception as exc:
        current_app.logger.error(
            {"event": "reply_feedback.error", "ticket_id": ticket_id, "error": str(exc)}, exc_info=True
        )
        db.session.rollback()
        return jsonify({"error": "Could not save reply feedback"}), 500

    return jsonify({
        "feedback": feedback.to_dict(),
        "message": "Reply feedback saved successfully"
    })


@v1.route("/inboxiq/connect", methods=["POST"])
@jwt_required(optional=True)
def connect_inbox():
    """
    Store or update an inbox connection (placeholder OAuth drop-in).
    Expects: provider, email_address, access_token (optionally refresh_token, scopes).
    """
    user_id = get_jwt_identity()
    data = request.get_json() or {}
    provider = (data.get("provider") or "").lower()
    email_address = (data.get("email_address") or "").strip()
    access_token = data.get("access_token")
    if provider not in ("gmail", "outlook", "demo"):
        return jsonify({"error": "provider must be gmail, outlook, or demo"}), 400
    if not email_address or not access_token:
        return jsonify({"error": "email_address and access_token are required"}), 400

    account_id = _get_account_id(user_id)
    conn = InboxConnection.query.filter_by(account_id=account_id, email_address=email_address).first()
    if not conn:
        conn = InboxConnection(
            user_id=user_id or 0,
            account_id=account_id,
            provider=provider,
            email_address=email_address,
        )
        db.session.add(conn)

    conn.provider = provider
    conn.access_token = access_token
    conn.refresh_token = data.get("refresh_token")
    conn.scopes = data.get("scopes") or []
    conn.status = "connected"
    meta = conn.metadata_json or {}
    meta.update({"last_poll_status": "never", "last_poll_error": None})
    conn.metadata_json = meta
    db.session.commit()
    from src.security import log_audit
    log_audit("inbox.connected", resource_type="inbox_connection", resource_id=str(conn.id),
              metadata={"provider": provider, "email": email_address})

    return jsonify({"connection": conn.to_dict()})


@v1.route("/inboxiq/inbox/invite", methods=["POST"])
@jwt_required()
def send_inbox_invite():
    """
    Oliver enters a colleague's or family member's email address so they can
    connect their own inbox without ever logging into InboxIQ.

    Creates a placeholder InboxConnection (status="pending"), generates a
    signed 72-hour invite token, and emails the link to the recipient.

    Body: { email_address, provider ("gmail"|"outlook"), display_name (optional) }
    """
    from datetime import timedelta
    from src.api.v1.auth import make_inbox_invite_token
    from src.notifications.emails import send_inbox_invite_email
    from src.models.core import User

    user_id = get_jwt_identity()
    account_id = _get_account_id(user_id)
    if not account_id:
        return jsonify({"error": "Account not found"}), 404

    # Only owner/admin may invite
    user = User.query.get(user_id)
    if not user or getattr(user, "role", None) not in ("owner", "admin"):
        return jsonify({"error": "Only account owners and admins can invite inboxes"}), 403

    data = request.get_json() or {}
    email_address = (data.get("email_address") or "").strip().lower()
    provider = (data.get("provider") or "gmail").lower()
    display_name = (data.get("display_name") or "").strip() or None

    if not email_address:
        return jsonify({"error": "email_address is required"}), 400
    if provider not in ("gmail", "outlook"):
        return jsonify({"error": "provider must be gmail or outlook"}), 400

    # Check not already connected
    existing = InboxConnection.query.filter_by(account_id=account_id, email_address=email_address).first()
    if existing and existing.status == "connected":
        return jsonify({"error": f"{email_address} is already connected to this account"}), 409

    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(hours=72)
    token = make_inbox_invite_token(account_id, email_address)

    if existing:
        # Resend: refresh token on existing pending row
        existing.invite_token = token
        existing.invite_token_expires_at = expires_at
        existing.provider = provider
        if display_name:
            existing.display_name = display_name
        conn = existing
    else:
        conn = InboxConnection(
            user_id=int(user_id),
            account_id=account_id,
            provider=provider,
            email_address=email_address,
            display_name=display_name,
            status="pending",
            invite_token=token,
            invite_token_expires_at=expires_at,
        )
        db.session.add(conn)

    db.session.commit()

    # Build the accept link
    base_url = current_app.config.get("BASE_URL") or "https://inboxiq.kalevent.com"
    accept_link = f"{base_url}/api/v1/auth/inbox/accept-invite?token={token}"

    account = Account.query.get(account_id)
    inviter_name = account.name if account else "Your InboxIQ account"

    sent = send_inbox_invite_email(
        to_email=email_address,
        accept_link=accept_link,
        inviter_name=inviter_name,
        provider=provider,
    )

    current_app.logger.info({
        "event": "inbox.invite.sent",
        "account_id": account_id,
        "email": email_address,
        "provider": provider,
        "email_sent": sent,
    })

    return jsonify({
        "connection_id": conn.id,
        "email_address": email_address,
        "status": "pending",
        "invite_sent": sent,
        "message": f"Invite {'sent' if sent else 'created (email delivery disabled)'} for {email_address}",
    })


def _fetch_messages_stub(conn: InboxConnection, limit: int = 5):
    """
    Placeholder fetcher: uses sample messages until real provider pollers are wired.
    """
    msgs = sample_messages()[:limit]
    # stamp provider and unique ids to avoid collisions
    out = []
    for idx, m in enumerate(msgs):
        mcopy = dict(m)
        mcopy["provider"] = conn.provider or "demo"
        mcopy["message_id"] = f"{conn.provider}-stub-{mcopy.get('message_id') or idx}"
        out.append(mcopy)
    return out


def _detect_label_correction(ticket, raw_email: dict, account_id: int | None) -> None:
    """
    Phase 2 — passive feedback loop.

    When Oliver moves an email to a different Gmail label (e.g. from
    InboxIQ/Support to InboxIQ/Transactions), the next poll detects the
    mismatch and records a ClassificationCorrection.  This feeds SenderProfile
    confidence updates so future emails from the same domain are classified
    correctly without DSPy.

    Label format: InboxIQ/{Category} or InboxIQ/{Category}/{Sublabel}
    The canonical category is always parts[1] regardless of depth, which means:
      - InboxIQ/Billing/Urgent    (InboxIQ P1 sublabel) → "billing"
      - InboxIQ/Support/VIP       (user-created sublabel) → "support"
      - InboxIQ/Support/VIP/Gold  (deeply nested user sublabel) → "support"

    User-created sublabels are an emergent behaviour: users may create child
    labels under any InboxIQ/ label in their Gmail sidebar.  These label IDs
    are not stored in conn.metadata_json (we never created them), so we resolve
    unknown user-label IDs in one batched Gmail API call and cache the results.

    Only fires for Gmail (labelIds are included in the fetch payload).
    Outlook correction detection is a future enhancement.
    """
    if not account_id:
        return

    # We only have label IDs for Gmail
    provider_label_ids: list = raw_email.get("provider_label_ids") or []
    if not provider_label_ids:
        return

    # Reconstruct the InboxIQ label name we applied to this ticket
    inboxiq_applied_category = (ticket.category or "").strip().lower()
    if not inboxiq_applied_category:
        return

    from src.models.core import InboxConnection
    from src.extensions import db
    conn = InboxConnection.query.filter_by(
        account_id=account_id, provider="gmail", status="connected"
    ).first()
    if not conn:
        return

    # Build id→name from labels we created (stored in metadata_json)
    meta = conn.metadata_json or {}
    label_id_to_name: dict = {lid: name for name, lid in (meta.get("label_ids") or {}).items()}

    # User-created sublabels (e.g. InboxIQ/Support/VIP) have IDs starting with
    # "Label_" and won't be in our map.  Resolve them in a single API call and
    # cache so subsequent polls don't repeat the request.
    unknown_user_label_ids = [
        lid for lid in provider_label_ids
        if lid.startswith("Label_") and lid not in label_id_to_name
    ]
    if unknown_user_label_ids and conn.access_token:
        try:
            import requests as _req
            resp = _req.get(
                "https://gmail.googleapis.com/gmail/v1/users/me/labels",
                headers={"Authorization": f"Bearer {conn.access_token}"},
                timeout=8,
            )
            if resp.status_code == 200:
                cache_updated = False
                for lbl in resp.json().get("labels") or []:
                    lid, lname = lbl.get("id", ""), lbl.get("name", "")
                    if not lid or not lname:
                        continue
                    label_id_to_name[lid] = lname
                    # Cache any InboxIQ sublabels we didn't create ourselves
                    if lname.lower().startswith("inboxiq/") and lname not in meta.get("label_ids", {}):
                        meta.setdefault("label_ids", {})[lname] = lid
                        cache_updated = True
                if cache_updated:
                    conn.metadata_json = meta
                    db.session.commit()
        except Exception as _resolve_exc:
            current_app.logger.debug("label resolve failed (non-fatal): %s", _resolve_exc)

    # Extract canonical InboxIQ category from label name.
    # Always use parts[1] after splitting on "/" — this correctly handles:
    #   InboxIQ/Support           → "support"
    #   InboxIQ/Billing/Urgent    → "billing"  (our own P1 sublabel)
    #   InboxIQ/Support/VIP       → "support"  (user-created sublabel)
    current_inboxiq_categories: list[str] = []
    for lid in provider_label_ids:
        name = label_id_to_name.get(lid, "")
        if name.lower().startswith("inboxiq/"):
            parts = name.split("/")
            if len(parts) >= 2 and parts[1]:
                current_inboxiq_categories.append(parts[1].lower())

    if not current_inboxiq_categories:
        return  # No InboxIQ label on message — nothing to compare

    # If none of the current InboxIQ labels match the applied category, it's a correction
    if inboxiq_applied_category not in current_inboxiq_categories:
        corrected_category = current_inboxiq_categories[0]
        try:
            from src.models.tickets import ClassificationCorrection
            from src.inbox.sender_profile import upsert_sender_profile, _extract_domain

            correction = ClassificationCorrection(
                account_id=account_id,
                ticket_id=ticket.id,
                sender_domain=_extract_domain(ticket.from_email) or ticket.from_email,
                original_category=inboxiq_applied_category,
                corrected_category=corrected_category,
                signal_source="label_move",
            )
            db.session.add(correction)

            # Upsert SenderProfile with the corrected category (user_verified=True
            # because this is an explicit inbox action from Oliver)
            upsert_sender_profile(
                from_email=ticket.from_email,
                category=corrected_category,
                account_id=account_id,
                user_verified=True,
            )
            db.session.commit()

        except Exception as exc:
            db.session.rollback()
            current_app.logger.warning(
                "ClassificationCorrection failed: ticket=%s error=%s", ticket.id, exc
            )


def _poll_inbox_internal(connection_id: str, user_id: int | None = None):
    """
    Core poll logic that can be called from a Flask route, Celery task,
    or a direct function call (no request context required).
    """
    conn = InboxConnection.query.get(connection_id)
    if not conn:
        return jsonify({"error": "Connection not found"}), 404
    if conn.status != "connected":
        return jsonify({"error": f"Connection status is {conn.status}"}), 400

    # Choose fetcher: Gmail API with refresh; IMAP for outlook; stub fallback
    fetch_status = "ok"
    fetch_error = None
    try:
        if conn.provider == "gmail" and conn.access_token:
            messages, new_token = fetch_messages_gmail(
                access_token=conn.access_token,
                refresh_token=conn.refresh_token,
                client_id=current_app.config.get("GOOGLE_CLIENT_ID"),
                client_secret=current_app.config.get("GOOGLE_CLIENT_SECRET"),
                limit=25,
            )
            if new_token:
                conn.access_token = new_token

            # Label bootstrap + sync — best-effort, never blocks the poll.
            # Bootstrap (canonical InboxIQ labels + colours) runs on EVERY poll until
            # labels_version == "v2" is confirmed — this ensures a version upgrade
            # fires immediately regardless of the hourly rate-limit on user-label sync.
            try:
                from src.dspy.triage_labels import sync_labels_from_gmail as _sync_labels
                meta = conn.metadata_json or {}
                _LABEL_VERSION = "v6"
                last_sync = meta.get("labels_synced_at")
                _one_hour_ago = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()

                # Always bootstrap until version is confirmed
                if meta.get("labels_version") != _LABEL_VERSION:
                    canonical_ids = bootstrap_inboxiq_labels_gmail(conn.access_token)
                    meta["label_ids"] = {**meta.get("label_ids", {}), **canonical_ids}
                    meta["labels_version"] = _LABEL_VERSION
                    meta["labels_synced_at"] = datetime.now(timezone.utc).isoformat()
                    conn.metadata_json = dict(meta)  # new dict forces SQLAlchemy dirty-tracking
                    db.session.commit()
                    # Note: Gmail Filters API (category:social etc.) returns 403 for OAuth apps
                    # without domain-wide delegation. InboxIQ's post-triage writeback is the
                    # reliable mechanism — do not call bootstrap_gmail_filters here.

                # Hourly: merge user-created Gmail labels into triage categories
                elif not last_sync or last_sync < _one_hour_ago:
                    gmail_labels = fetch_gmail_labels(conn.access_token)
                    if gmail_labels:
                        _sync_labels(conn.account_id, gmail_labels)
                        meta["label_ids"] = {
                            **meta.get("label_ids", {}),
                            **{lbl["name"]: lbl["id"] for lbl in gmail_labels},
                        }
                    meta["labels_synced_at"] = datetime.now(timezone.utc).isoformat()
                    conn.metadata_json = meta
                    db.session.commit()
            except Exception as _lbl_exc:
                current_app.logger.warning("gmail label sync failed: %s", _lbl_exc)
        elif conn.provider == "outlook" and conn.access_token:
            messages, new_token = fetch_messages_outlook(
                access_token=conn.access_token,
                refresh_token=conn.refresh_token,
                client_id=current_app.config.get("MICROSOFT_CLIENT_ID"),
                client_secret=current_app.config.get("MICROSOFT_CLIENT_SECRET"),
                tenant_id=current_app.config.get("MICROSOFT_TENANT_ID"),
                limit=25,
            )
            if new_token:
                conn.access_token = new_token

            # Label bootstrap + sync — same pattern as Gmail.
            try:
                from src.dspy.triage_labels import sync_labels_from_gmail as _sync_labels
                meta = conn.metadata_json or {}
                _LABEL_VERSION = "v6"
                last_sync = meta.get("labels_synced_at")
                _one_hour_ago = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()

                if meta.get("labels_version") != _LABEL_VERSION:
                    canonical_ids = bootstrap_inboxiq_labels_outlook(conn.access_token)
                    meta["label_ids"] = {**meta.get("label_ids", {}), **canonical_ids}
                    meta["labels_version"] = _LABEL_VERSION
                    meta["labels_synced_at"] = datetime.now(timezone.utc).isoformat()
                    conn.metadata_json = meta
                    db.session.commit()

                elif not last_sync or last_sync < _one_hour_ago:
                    outlook_cats = fetch_outlook_categories(conn.access_token)
                    if outlook_cats:
                        _sync_labels(conn.account_id, outlook_cats)
                        meta["label_ids"] = {
                            **meta.get("label_ids", {}),
                            **{cat["name"]: cat["id"] for cat in outlook_cats},
                        }
                    meta["labels_synced_at"] = datetime.now(timezone.utc).isoformat()
                    conn.metadata_json = meta
                    db.session.commit()
            except Exception as _lbl_exc:
                current_app.logger.warning("outlook category sync failed: %s", _lbl_exc)
        else:
            messages = _fetch_messages_stub(conn)
    except Exception as exc:
        msg = str(exc)
        # Detect auth failures and avoid silently falling back
        if "401" in msg or "403" in msg or "Invalid Credentials" in msg or "service has been disabled" in msg:
            fetch_status = "auth_error"
            fetch_error = msg
            current_app.logger.error(
                {"event": "inbox.poll.auth_error", "connection_id": conn.id, "provider": conn.provider, "error": msg}
            )
            messages = []
        else:
            # Log at error level so crash email/alerts fire when a poll fails.
            current_app.logger.exception("inbox poll failed; falling back to stub", exc_info=exc)
            messages = _fetch_messages_stub(conn)
            fetch_status = "fallback_stub"
            fetch_error = msg
    created = 0
    duplicates = 0
    errors = 0
    queued = 0

    # Auth errors: stop and surface to caller so they can reconnect.
    if fetch_status == "auth_error":
        meta = conn.metadata_json or {}
        meta.update(
            {
                "last_poll_status": fetch_status,
                "last_poll_error": fetch_error,
                "last_poll_at": datetime.now(timezone.utc).isoformat(),
                "last_poll_counts": {
                    "created": created,
                    "queued": queued,
                    "duplicates": duplicates,
                    "errors": errors,
                    "fetched": 0,
                },
            }
        )
        try:
            conn.metadata_json = meta
            db.session.commit()
        except Exception:
            current_app.logger.error(
                {"event": "inbox.poll.meta_error", "connection_id": conn.id, "status": fetch_status},
                exc_info=True,
            )
            db.session.rollback()
        return jsonify({"error": "Authentication error. Please reconnect your inbox.", "status": fetch_status}), 401
    current_app.logger.info(
        "poll fetched %d messages for connection=%s subjects=%s",
        len(messages), conn.id,
        [(m.get("subject") or "")[:50] for m in messages[:5]],
    )
    for raw_email in messages:
        try:
            normalized = normalize_email_payload(raw_email)
        except ValueError as exc:
            errors += 1
            continue
        existing = Ticket.query.filter_by(
            message_id=normalized["message_id"], provider=normalized.get("provider")
        ).first()
        if existing:
            duplicates += 1
            # Phase 2 — ClassificationCorrection: detect if Oliver moved the email
            # to a label that differs from what InboxIQ applied.
            _detect_label_correction(existing, raw_email, conn.account_id)

            # Writeback healing: if this ticket was created but the label/draft was never
            # written back (e.g. worker was OOMKilled mid-task), heal it now.
            # Check: ticket has a category AND message has no InboxIQ Label_* tag yet.
            _provider_label_ids = normalized.get("provider_label_ids") or []
            _has_inboxiq_label = any(lid for lid in _provider_label_ids if lid.startswith("Label_"))
            if not _has_inboxiq_label and existing.category:
                try:
                    from src.inbox.poll import writeback_to_provider as _wb
                    _decision = existing.decision or {}
                    _reply_text = _decision.get("reply_text")
                    _meta = conn.metadata_json or {}
                    _label_cache = _meta.setdefault("label_ids", {})
                    # Normalize old stored categories to canonical InboxIQ labels.
                    # Old tickets may have "general", "bug", "technical" etc. from before normalization.
                    _CANONICAL_CATS = {"support", "billing", "transactions", "updates", "promotions", "social", "forums"}
                    _HEAL_CAT_MAP = {
                        "general": "support", "bug": "support", "technical": "support",
                        "sales": "support", "feedback": "support", "other": "support",
                        "marketing": "promotions", "newsletter": "updates",
                        "spam": "updates", "auto_reply": "updates", "notification": "updates",
                    }
                    _raw_cat = (existing.category or "support").lower().strip()
                    _heal_category = _raw_cat if _raw_cat in _CANONICAL_CATS else _HEAL_CAT_MAP.get(_raw_cat, "support")
                    _heal_email_type = _decision.get("email_type") or _decision.get("entities", {}).get("email_type") or None
                    _result = _wb(
                        provider=normalized.get("provider"),
                        provider_message_id=normalized.get("provider_message_id"),
                        provider_thread_id=normalized.get("provider_thread_id"),
                        access_token=conn.access_token,
                        label_cache=_label_cache,
                        category=_heal_category,
                        priority=existing.priority or "P3",
                        reply_text=_reply_text,
                        from_email=normalized.get("from_email", ""),
                        subject=normalized.get("subject", ""),
                        email_type=_heal_email_type,
                        is_automated=(existing.status == "auto_handled"),
                    )
                    if _result.get("label_applied"):
                        conn.metadata_json = dict(_meta)
                        db.session.commit()
                    current_app.logger.info(
                        "writeback healed for orphaned ticket id=%s raw_category=%s healed_category=%s label=%s draft=%s",
                        existing.id, existing.category, _heal_category,
                        _result.get("label_applied"), _result.get("draft_created"),
                    )
                except Exception as _heal_exc:
                    current_app.logger.warning("writeback heal failed: ticket=%s error=%s", existing.id, _heal_exc)
            continue
        try:
            task = _celery_client().send_task(
                "inboxiq.process_incoming_email",
                args=[{"email": normalized, "user_id": conn.user_id, "account_id": conn.account_id}],
                queue="inbox",
            )
            queued += 1
            created += 1
        except Exception as exc:
            errors += 1
            current_app.logger.warning("enqueue failed during poll: %s", exc)
            continue

    # Normalize status based on outcome so the dashboard doesn't show stale failures
    # when we successfully processed messages (even from the stub).
    if created + duplicates > 0:
        fetch_status = "ok"
        fetch_error = None
    elif fetch_status == "fallback_stub" and messages:
        fetch_status = "ok_stub"
        fetch_error = None
    elif fetch_status == "ok" and not messages:
        fetch_status = "ok_no_new"
        fetch_error = None

    meta = conn.metadata_json or {}
    meta.update(
        {
            "last_poll_status": fetch_status,
            "last_poll_error": fetch_error,
            "last_poll_at": datetime.now(timezone.utc).isoformat(),
            "last_poll_counts": {
                "created": created,
                "queued": queued,
                "duplicates": duplicates,
                "errors": errors,
                "fetched": len(messages),
            },
        }
    )
    current_app.logger.info(
        {
            "event": "inbox.poll.meta_update",
            "connection_id": conn.id,
            "status": fetch_status,
            "provider": conn.provider,
            "used_stub": fetch_status in ("fallback_stub", "ok_stub"),
        }
    )
    try:
        conn.metadata_json = meta
        db.session.add(conn)
        db.session.commit()
    except Exception:
        current_app.logger.error(
            {"event": "inbox.poll.meta_error", "connection_id": conn.id, "status": fetch_status},
            exc_info=True,
        )
        db.session.rollback()
        raise

    current_app.logger.info(
        {
            "event": "inbox.poll",
            "connection_id": conn.id,
            "provider": conn.provider,
            "status": fetch_status,
            "error": fetch_error,
            "counts": {"created": created, "duplicates": duplicates, "errors": errors, "fetched": len(messages)},
        }
    )

    return jsonify(
        {
            "connection": conn.to_dict(),
            "summary": {"created": created, "queued": queued, "duplicates": duplicates, "errors": errors},
            "last_poll": meta,
        }
    )


@v1.route("/inboxiq/poll/<connection_id>", methods=["GET", "POST"])
@jwt_required(optional=True)
def poll_inbox(connection_id: str):
    """
    HTTP entrypoint for polling; requires a request context for JWT, then delegates
    to the shared internal poll logic.
    """
    return _poll_inbox_internal(connection_id, get_jwt_identity())


@v1.route("/inboxiq/poll/mine", methods=["GET", "POST"])
@jwt_required()
def poll_my_inbox():
    """
    Trigger a poll for the current user's most recent connected inbox.
    Intended for dashboard "Poll now" button.
    """
    user_id = get_jwt_identity()
    conn = (
        InboxConnection.query.filter_by(user_id=user_id, status="connected")
        .order_by(InboxConnection.updated_at.desc())
        .first()
    )
    if not conn:
        return jsonify({"error": "No connected inbox found"}), 404
    return _poll_inbox_internal(conn.id, user_id)


def poll_inbox_service(connection_id: str, user_id: int | None = None):
    """
    Convenience helper for calling the poller without a Flask request context
    (e.g., from scripts/tests). Returns the same JSON response as the route.
    """
    return _poll_inbox_internal(connection_id, user_id)


@v1.route("/inboxiq/connections/mine", methods=["GET"])
@jwt_required()
def get_my_connection():
    user_id = get_jwt_identity()
    account_id = _get_account_id(user_id)
    def _pick_connection(connections):
        if not connections:
            return None
        def _is_email(conn):
            return (conn.provider or "").lower() in {"gmail", "outlook", "imap"}
        def _poll_ts(conn):
            meta = conn.metadata_json or {}
            ts = meta.get("last_poll_at")
            if not ts:
                return None
            try:
                ts_raw = str(ts)
                if ts_raw.endswith("Z"):
                    ts_raw = ts_raw[:-1] + "+00:00"
                parsed = datetime.fromisoformat(ts_raw)
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                return parsed
            except Exception:
                return None
        email_connections = [c for c in connections if _is_email(c)]
        candidate_pool = email_connections or connections
        return max(
            candidate_pool,
            key=lambda c: (_poll_ts(c) or datetime.min.replace(tzinfo=timezone.utc), c.updated_at or datetime.min.replace(tzinfo=timezone.utc)),
        )

    conn = None
    if account_id:
        conn = _pick_connection(
            InboxConnection.query.filter_by(account_id=account_id, status="connected").all()
        )
    if not conn:
        conn = _pick_connection(
            InboxConnection.query.filter_by(user_id=user_id, status="connected").all()
        )
    if not conn:
        return jsonify({"error": "No connected inbox found"}), 404
    if account_id and not conn.account_id:
        conn.account_id = account_id
        db.session.commit()
    meta = conn.metadata_json or {}
    last_poll_at = meta.get("last_poll_at")
    last_poll_status = meta.get("last_poll_status")
    last_poll_error = meta.get("last_poll_error")
    if not last_poll_at and last_poll_status and last_poll_status != "never" and conn.updated_at:
        last_poll_at = conn.updated_at.isoformat()
    poll_health = {"status": "unknown"}
    try:
        stale_minutes = int(os.getenv("INBOXIQ_POLL_STALE_MINUTES", "30"))
    except Exception:
        stale_minutes = 30
    if not last_poll_at:
        if last_poll_status and last_poll_status != "never":
            poll_health = {"status": "ok", "stale_minutes": stale_minutes}
        else:
            poll_health = {"status": "never", "stale_minutes": stale_minutes}
    else:
        ts = None
        try:
            ts_raw = str(last_poll_at)
            if ts_raw.endswith("Z"):
                ts_raw = ts_raw[:-1] + "+00:00"
            ts = datetime.fromisoformat(ts_raw)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
        except Exception:
            ts = None
        if last_poll_status == "error" or last_poll_error:
            poll_health = {"status": "error", "stale_minutes": stale_minutes}
        elif ts:
            age_min = (datetime.now(timezone.utc) - ts).total_seconds() / 60.0
            poll_health = {
                "status": "stale" if age_min > stale_minutes else "ok",
                "age_minutes": round(age_min, 1),
                "stale_minutes": stale_minutes,
            }
        else:
            poll_health = {"status": "unknown", "stale_minutes": stale_minutes}
    return jsonify(
        {
            "connection": conn.to_dict(),
            "last_poll": {
                "last_poll_at": last_poll_at,
                "last_poll_status": last_poll_status,
                "last_poll_error": last_poll_error,
                "last_poll_counts": meta.get("last_poll_counts"),
            },
            "poll_health": poll_health,
        }
    )


@v1.route("/inboxiq/connect/start", methods=["GET"])
@jwt_required(optional=True)
def start_connect():
    """
    Begin inbox connect flow. For now, return a callback URL that will create a demo connection.
    """
    provider = request.args.get("provider", "").lower()
    email_address = request.args.get("email") or "demo@example.com"
    if provider not in ("gmail", "outlook", "demo"):
        return jsonify({"error": "provider must be gmail, outlook, or demo"}), 400
    # In a real flow, redirect to provider OAuth. Here we simulate success.
    callback_url = url_for(".finish_connect", provider=provider, email=email_address, token="stub", _external=True, _scheme="http")
    return jsonify({"auth_url": callback_url})


@v1.route("/inboxiq/connect/callback", methods=["GET"])
@jwt_required(optional=True)
def finish_connect():
    """
    Simulated OAuth callback: create/update connection and auto-poll.
    """
    provider = (request.args.get("provider") or "demo").lower()
    email_address = request.args.get("email") or "demo@example.com"
    token = request.args.get("token") or "stub"
    user_id = get_jwt_identity()
    account_id = _get_account_id(user_id)

    conn = InboxConnection.query.filter_by(account_id=account_id, email_address=email_address).first()
    if not conn:
        conn = InboxConnection(
            user_id=user_id or 0,
            account_id=account_id,
            provider=provider,
            email_address=email_address,
        )
        db.session.add(conn)

    conn.provider = provider
    conn.access_token = token
    conn.status = "connected"
    conn.metadata_json = {"last_poll_status": "never"}
    db.session.commit()
    from src.security import log_audit
    log_audit("inbox.connected", resource_type="inbox_connection", resource_id=str(conn.id),
              metadata={"provider": provider, "email": email_address})

    # Auto-poll to create first tickets
    try:
        with current_app.test_request_context():
            # reuse existing poll logic
            poll_inbox(conn.id)
    except Exception:
        current_app.logger.warning("Auto-poll after connect failed", exc_info=True)

    return redirect(url_for("dashboard_home"))


@v1.route("/features/draft-reply", methods=["POST"])
@jwt_required()
def update_draft_reply_feature():
    """
    Enable or disable draft reply feature for an account.

    Request JSON:
        {
            "enabled": true/false
        }

    Returns:
        200: Feature updated successfully
        400: Invalid request
        403: Account not eligible for draft reply feature
    """
    user_id = get_jwt_identity()
    account_id = _get_account_id(user_id)

    if not account_id:
        return jsonify({"error": "account_not_found"}), 404

    data = request.get_json() or {}
    enabled = data.get("enabled", False)

    if not isinstance(enabled, bool):
        return jsonify({"error": "invalid_enabled_value"}), 400

    # Check if account is eligible for draft reply feature
    from src.features import check_draft_reply_access
    has_access = check_draft_reply_access(account_id)

    if enabled and not has_access:
        return jsonify({
            "error": "not_eligible",
            "message": "Draft reply feature requires Business plan or active trial"
        }), 403

    # Get or create feature flags
    from src.models import AccountFeatureFlags
    feature_flags = AccountFeatureFlags.query.filter_by(account_id=account_id).first()

    if not feature_flags:
        feature_flags = AccountFeatureFlags(
            account_id=account_id,
            draft_reply_enabled=enabled
        )
        db.session.add(feature_flags)
    else:
        feature_flags.draft_reply_enabled = enabled

    db.session.commit()

    return jsonify({
        "success": True,
        "draft_reply_enabled": enabled,
        "message": f"Draft reply feature {'enabled' if enabled else 'disabled'}"
    }), 200


@v1.route("/features/draft-reply", methods=["GET"])
@jwt_required()
def get_draft_reply_feature():
    """Get current draft reply feature status for account."""
    user_id = get_jwt_identity()
    account_id = _get_account_id(user_id)

    if not account_id:
        return jsonify({"error": "account_not_found"}), 404

    from src.models import AccountFeatureFlags
    from src.features import check_draft_reply_access

    feature_flags = AccountFeatureFlags.query.filter_by(account_id=account_id).first()
    has_access = check_draft_reply_access(account_id)

    return jsonify({
        "draft_reply_enabled": feature_flags.draft_reply_enabled if feature_flags else False,
        "has_access": has_access,
        "can_enable": has_access
    }), 200


@v1.route("/inboxiq/training/trigger", methods=["POST"])
@jwt_required()
def trigger_training():
    """
    Manually trigger DSPy training for the current account.

    Returns:
        200: Training queued or result returned
        400: Not enough samples for training
        403: Training not enabled for account
    """
    user_id = get_jwt_identity()
    account_id = _get_account_id(user_id)

    if not account_id:
        return jsonify({"error": "account_not_found"}), 404

    # Check if account has enough manual overrides
    override_count = Ticket.query.filter(
        Ticket.account_id == account_id,
        Ticket.manual_override.is_(True)
    ).count()

    min_samples = int(os.getenv("DSPY_TRAIN_MIN_SAMPLES", "20"))

    # Seed examples can supplement when override count is low
    include_seeds = os.getenv("DSPY_TRAIN_INCLUDE_SEEDS", "1").lower() in ("1", "true", "yes", "on")
    seed_count = 12 if include_seeds else 0  # Number of seed examples in dspy_train.py

    total_samples = override_count + seed_count
    can_train = total_samples >= min_samples

    if not can_train:
        return jsonify({
            "error": "insufficient_samples",
            "message": f"Need at least {min_samples} samples for training. You have {override_count} manual overrides + {seed_count} seed examples = {total_samples} total.",
            "override_count": override_count,
            "seed_count": seed_count,
            "total_samples": total_samples,
            "min_samples": min_samples,
        }), 400

    # Queue the training task via Celery
    try:
        task = _celery_client().send_task(
            "inboxiq.train_dspy_overrides",
            queue="inbox",
        )
        current_app.logger.info({
            "event": "training.triggered",
            "account_id": account_id,
            "task_id": task.id,
            "override_count": override_count,
        })
        return jsonify({
            "status": "queued",
            "task_id": task.id,
            "message": f"Training queued with {override_count} overrides + {seed_count} seeds",
            "override_count": override_count,
            "seed_count": seed_count,
        }), 200
    except Exception as exc:
        current_app.logger.error({
            "event": "training.trigger_failed",
            "account_id": account_id,
            "error": str(exc),
        })
        return jsonify({
            "error": "queue_failed",
            "message": "Failed to queue training task. Check Celery worker status.",
        }), 503


@v1.route("/inboxiq/training/status", methods=["GET"])
@jwt_required()
def training_status():
    """
    Get training readiness status for the current account.
    """
    user_id = get_jwt_identity()
    account_id = _get_account_id(user_id)

    if not account_id:
        return jsonify({"error": "account_not_found"}), 404

    # Check manual override count
    override_count = Ticket.query.filter(
        Ticket.account_id == account_id,
        Ticket.manual_override.is_(True)
    ).count()

    total_tickets = Ticket.query.filter(Ticket.account_id == account_id).count()
    min_samples = int(os.getenv("DSPY_TRAIN_MIN_SAMPLES", "20"))

    include_seeds = os.getenv("DSPY_TRAIN_INCLUDE_SEEDS", "1").lower() in ("1", "true", "yes", "on")
    seed_count = 12 if include_seeds else 0

    total_samples = override_count + seed_count
    can_train = total_samples >= min_samples

    # Get latest training run
    latest_metric = (
        DspyTrainingMetric.query
        .filter(DspyTrainingMetric.account_id == account_id)
        .order_by(desc(DspyTrainingMetric.created_at))
        .first()
    )

    return jsonify({
        "can_train": can_train,
        "override_count": override_count,
        "total_tickets": total_tickets,
        "seed_count": seed_count,
        "total_samples": total_samples,
        "min_samples": min_samples,
        "samples_needed": max(0, min_samples - total_samples),
        "latest_training": latest_metric.to_dict() if latest_metric else None,
    }), 200


# ---------------------------------------------------------------------------
# BYOL (Bring Your Own LLM) — per-account LLM provider config
# ---------------------------------------------------------------------------

@v1.route("/llm-config", methods=["GET"])
@jwt_required()
def get_llm_config():
    """Return the current BYOL config for the account (no api_key in response)."""
    from src.models.tickets import Ticket as _  # ensure app context
    user_id = get_jwt_identity()
    from src.models.core import User
    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "Not found"}), 404
    config = AccountLLMConfig.query.filter_by(account_id=user.account_id).first()
    return jsonify({
        "config": config.to_dict() if config else None,
        "allowed_providers": ALLOWED_LLM_PROVIDERS,
    }), 200


@v1.route("/llm-config", methods=["POST"])
@jwt_required()
def save_llm_config():
    """Save or update the BYOL LLM config for the account."""
    from src.crypto import encrypt_value
    from src.models.core import User

    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "Not found"}), 404
    if user.role not in ("owner", "admin"):
        return jsonify({"message": "Owner or Admin role required"}), 403

    data = request.get_json(silent=True) or {}
    provider = (data.get("provider") or "").strip()
    base_url = (data.get("base_url") or "").strip() or None
    model = (data.get("model") or "").strip()
    raw_key = (data.get("api_key") or "").strip() or None

    if not provider:
        return jsonify({"message": "provider is required"}), 400
    if provider not in ALLOWED_LLM_PROVIDERS:
        return jsonify({"message": f"Unsupported provider: {provider}"}), 400
    if not model:
        return jsonify({"message": "model is required"}), 400

    provider_meta = ALLOWED_LLM_PROVIDERS[provider]
    if provider_meta.get("base_url_editable") and not base_url:
        return jsonify({"message": f"{provider} requires an endpoint URL"}), 400

    # Validate model is in the allowlist (if provider has a fixed list)
    allowed_models = provider_meta.get("models", [])
    if allowed_models and model not in allowed_models:
        return jsonify({"message": f"Model '{model}' is not in the permitted list for {provider}"}), 400

    config = AccountLLMConfig.query.filter_by(account_id=user.account_id).first()
    if config is None:
        config = AccountLLMConfig(account_id=user.account_id)
        db.session.add(config)

    config.provider = provider
    config.base_url = base_url or provider_meta.get("base_url")
    config.model = model
    config.enabled = True
    if raw_key:
        config.api_key_enc = encrypt_value(raw_key)

    db.session.commit()
    from src.security import log_audit
    log_audit("ai_provider.configured", resource_type="llm_config",
              metadata={"provider": provider, "model": model})
    return jsonify({"message": "AI provider saved", "config": config.to_dict()}), 200


@v1.route("/llm-config", methods=["DELETE"])
@jwt_required()
def delete_llm_config():
    """Remove the BYOL config — account reverts to InboxIQ default."""
    from src.models.core import User

    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "Not found"}), 404
    if user.role not in ("owner", "admin"):
        return jsonify({"message": "Owner or Admin role required"}), 403

    config = AccountLLMConfig.query.filter_by(account_id=user.account_id).first()
    if config:
        from src.security import log_audit
        log_audit("ai_provider.removed", resource_type="llm_config",
                  metadata={"provider": config.provider})
        db.session.delete(config)
        db.session.commit()
    return jsonify({"message": "Custom AI provider removed"}), 200


@v1.route("/llm-config/test", methods=["POST"])
@jwt_required()
def test_llm_config():
    """
    Fire a minimal test prompt against the supplied LLM config.
    Does NOT require a saved config — tests the posted credentials directly.
    """
    from src.crypto import encrypt_value, decrypt_value
    from src.models.core import User
    from src.ai.client import call_byol

    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "Not found"}), 404
    if user.role not in ("owner", "admin"):
        return jsonify({"message": "Owner or Admin role required"}), 403

    data = request.get_json(silent=True) or {}
    provider = (data.get("provider") or "").strip()
    base_url = (data.get("base_url") or "").strip() or None
    model = (data.get("model") or "").strip()
    raw_key = (data.get("api_key") or "").strip() or None

    if not provider or not model:
        return jsonify({"message": "provider and model are required"}), 400
    if provider not in ALLOWED_LLM_PROVIDERS:
        return jsonify({"message": f"Unsupported provider: {provider}"}), 400

    # If no key supplied in request, try to use the saved encrypted key
    if not raw_key:
        saved = AccountLLMConfig.query.filter_by(account_id=user.account_id).first()
        if saved and saved.api_key_enc:
            raw_key = decrypt_value(saved.api_key_enc)

    provider_meta = ALLOWED_LLM_PROVIDERS[provider]
    resolved_base_url = base_url or provider_meta.get("base_url")

    try:
        result = call_byol(
            messages=[{"role": "user", "content": "Reply with one word: OK"}],
            config={
                "provider": provider,
                "base_url": resolved_base_url,
                "model": model,
                "api_key": raw_key,
            },
            max_tokens=10,
        )
        return jsonify({"message": f"Connection OK — model replied: {result['content'][:80]}"}), 200
    except Exception as exc:
        return jsonify({"message": f"Connection failed: {exc}"}), 400


# ---------------------------------------------------------------------------
# GDPR Article 17 — Right to Erasure
# ---------------------------------------------------------------------------

@v1.route("/account", methods=["DELETE"])
@jwt_required()
def delete_account():
    """
    Hard-delete all account data (GDPR Article 17).

    Billing records are anonymised rather than deleted (7-year legal hold).
    Requires owner role and confirmation phrase "DELETE MY ACCOUNT" in body.
    """
    from src.models.core import User, Account, AccountFeatureFlags
    from src.models.auth import AuthEvent, Passkey, TOTPDevice
    from src.models.tickets import Ticket, TicketEmbedding, TriageLabelConfig, TriageConfig, DraftReplyFeedback
    from src.models.ai import DspyTrainingMetric
    from src.models.leads import Lead, LeadFunnelStage, LeadEngagementEvent, LeadAttribution, FunnelMetricsDaily
    from src.models.content import BlogPost, KBIntegration, KBArticle, KBArticleEmbedding, GeneratedContent, PitchedBlogTopic
    from src.models.campaigns import CampaignSender, EmailCampaign, EmailOutreach, NurtureEmailSend
    from src.models.automation import AutomationStudioWaitlist, AutomationRule, AutomationRuleExecution, WebhookProvider, AutomationSuggestion
    from src.models.marketing import Referral, InAppMessage, InAppMessageDismissal, LandingPage, EnterpriseInquiry
    from src.models.developer import DeveloperAccessRequest, RegisteredApp
    from src.models.billing import CustomerBillingProfile, PaymentMethod, AccountUsageCounter
    from src.models.misc import Testimonial, Feedback

    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "not_found"}), 404

    account_id = user.account_id

    if user.role != "owner":
        return jsonify({"error": "owner_required", "message": "Only the account owner can delete the account"}), 403

    body = request.get_json(silent=True) or {}
    if body.get("confirm") != "DELETE MY ACCOUNT":
        return jsonify({"error": "confirmation_required", "message": 'Send {"confirm": "DELETE MY ACCOUNT"}'}), 422

    current_app.logger.info({"event": "account.delete.initiated", "account_id": account_id, "user_id": user_id})
    from src.security import log_audit
    log_audit("account.deleted", resource_type="account", resource_id=str(account_id),
              account_id=account_id, user_id=user_id)

    try:
        # 1. Ticket leaf tables
        ticket_ids = [r[0] for r in Ticket.query.filter_by(account_id=account_id).with_entities(Ticket.id).all()]
        if ticket_ids:
            TicketEmbedding.query.filter(TicketEmbedding.ticket_id.in_(ticket_ids)).delete(synchronize_session=False)
            DraftReplyFeedback.query.filter(DraftReplyFeedback.ticket_id.in_(ticket_ids)).delete(synchronize_session=False)

        # 2. Lead leaf tables
        lead_ids = [r[0] for r in Lead.query.filter_by(account_id=account_id).with_entities(Lead.id).all()]
        if lead_ids:
            LeadFunnelStage.query.filter(LeadFunnelStage.lead_id.in_(lead_ids)).delete(synchronize_session=False)
            LeadEngagementEvent.query.filter(LeadEngagementEvent.lead_id.in_(lead_ids)).delete(synchronize_session=False)
            LeadAttribution.query.filter(LeadAttribution.lead_id.in_(lead_ids)).delete(synchronize_session=False)
            NurtureEmailSend.query.filter(NurtureEmailSend.lead_id.in_(lead_ids)).delete(synchronize_session=False)

        # 3. Campaign leaf tables
        campaign_ids = [r[0] for r in EmailCampaign.query.filter_by(account_id=account_id).with_entities(EmailCampaign.id).all()]
        if campaign_ids:
            EmailOutreach.query.filter(EmailOutreach.campaign_id.in_(campaign_ids)).delete(synchronize_session=False)

        # 4. KB leaf tables
        kb_ids = [r[0] for r in KBArticle.query.filter_by(account_id=account_id).with_entities(KBArticle.id).all()]
        if kb_ids:
            KBArticleEmbedding.query.filter(KBArticleEmbedding.article_id.in_(kb_ids)).delete(synchronize_session=False)

        # 5. Break automation circular FK: AutomationRule.suggestion_id → AutomationSuggestion
        AutomationRule.query.filter_by(account_id=account_id).update({"suggestion_id": None}, synchronize_session=False)

        # 6. Automation leaf tables then parents (AutomationRuleExecution has account_id directly)
        AutomationRuleExecution.query.filter_by(account_id=account_id).delete(synchronize_session=False)
        AutomationSuggestion.query.filter_by(account_id=account_id).delete(synchronize_session=False)
        AutomationRule.query.filter_by(account_id=account_id).delete(synchronize_session=False)
        AutomationStudioWaitlist.query.filter_by(account_id=account_id).delete(synchronize_session=False)
        WebhookProvider.query.filter_by(account_id=account_id).delete(synchronize_session=False)

        # 7. Core data tables
        Ticket.query.filter_by(account_id=account_id).delete(synchronize_session=False)
        Lead.query.filter_by(account_id=account_id).delete(synchronize_session=False)
        EmailCampaign.query.filter_by(account_id=account_id).delete(synchronize_session=False)
        CampaignSender.query.filter_by(account_id=account_id).delete(synchronize_session=False)
        KBArticle.query.filter_by(account_id=account_id).delete(synchronize_session=False)
        KBIntegration.query.filter_by(account_id=account_id).delete(synchronize_session=False)
        DspyTrainingMetric.query.filter_by(account_id=account_id).delete(synchronize_session=False)
        TriageLabelConfig.query.filter_by(account_id=account_id).delete(synchronize_session=False)
        TriageConfig.query.filter_by(account_id=account_id).delete(synchronize_session=False)
        FunnelMetricsDaily.query.filter_by(account_id=account_id).delete(synchronize_session=False)
        GeneratedContent.query.filter_by(account_id=account_id).delete(synchronize_session=False)
        BlogPost.query.filter_by(account_id=account_id).delete(synchronize_session=False)
        # PitchedBlogTopic: nullify reviewed_by (FK → User) before delete
        PitchedBlogTopic.query.filter_by(account_id=account_id).update({"reviewed_by": None}, synchronize_session=False)
        PitchedBlogTopic.query.filter_by(account_id=account_id).delete(synchronize_session=False)
        Testimonial.query.filter_by(account_id=account_id).delete(synchronize_session=False)
        Feedback.query.filter_by(account_id=account_id).delete(synchronize_session=False)

        # 8. Marketing (EnterpriseInquiry has ondelete=SET NULL — anonymise, keep for sales records)
        Referral.query.filter_by(account_id=account_id).delete(synchronize_session=False)
        LandingPage.query.filter_by(account_id=account_id).delete(synchronize_session=False)
        EnterpriseInquiry.query.filter_by(account_id=account_id).update({"account_id": None}, synchronize_session=False)

        # 9. Developer
        DeveloperAccessRequest.query.filter_by(account_id=account_id).delete(synchronize_session=False)
        RegisteredApp.query.filter_by(account_id=account_id).delete(synchronize_session=False)

        # 10. Billing: anonymise only (7-year legal hold — HMRC / GDPR recital 65)
        billing_profile = CustomerBillingProfile.query.filter_by(account_id=account_id).first()
        if billing_profile:
            PaymentMethod.query.filter_by(profile_id=billing_profile.id).update(
                {"brand": "DELETED", "last4": "0000", "provider_payment_method_id": "DELETED"},
                synchronize_session=False,
            )
            billing_profile.email = f"deleted-{account_id}@deleted.invalid"
            billing_profile.billing_name = "DELETED"
            billing_profile.address = {}
            billing_profile.tax_id = None
            db.session.add(billing_profile)
        AccountUsageCounter.query.filter_by(account_id=account_id).delete(synchronize_session=False)

        # 11. Auth/user children
        AuthEvent.query.filter_by(account_id=account_id).delete(synchronize_session=False)
        user_ids = [r[0] for r in User.query.filter_by(account_id=account_id).with_entities(User.id).all()]
        if user_ids:
            InAppMessageDismissal.query.filter(InAppMessageDismissal.user_id.in_(user_ids)).delete(synchronize_session=False)
            Passkey.query.filter(Passkey.user_id.in_(user_ids)).delete(synchronize_session=False)
            TOTPDevice.query.filter(TOTPDevice.user_id.in_(user_ids)).delete(synchronize_session=False)
        InAppMessage.query.filter_by(target_account_id=account_id).delete(synchronize_session=False)

        # 12. Account-level config
        InboxConnection.query.filter_by(account_id=account_id).delete(synchronize_session=False)
        AccountFeatureFlags.query.filter_by(account_id=account_id).delete(synchronize_session=False)
        AccountLLMConfig.query.filter_by(account_id=account_id).delete(synchronize_session=False)

        # 13. Users then Account (last)
        User.query.filter_by(account_id=account_id).delete(synchronize_session=False)
        Account.query.filter_by(id=account_id).delete(synchronize_session=False)

        db.session.commit()

        current_app.logger.info({"event": "account.delete.completed", "account_id": account_id})
        return jsonify({"status": "deleted", "account_id": account_id}), 200

    except Exception as exc:
        db.session.rollback()
        current_app.logger.exception({"event": "account.delete.failed", "account_id": account_id, "error": str(exc)})
        return jsonify({"error": "delete_failed", "message": "Account deletion failed. Contact support@kalevent.com"}), 500
