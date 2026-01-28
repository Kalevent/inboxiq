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
from src.models import Ticket, InboxConnection, Feedback, DspyTrainingMetric
from src.inboxiq_logic import normalize_email_payload, run_dspy_decision, sample_messages, compute_due_at
from src.email_poll import fetch_messages_gmail, fetch_messages_outlook

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
                due_at=compute_due_at(decision.priority),
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


def _priority_order():
    return case(
        (Ticket.priority == "P0", 0),
        (Ticket.priority == "P1", 1),
        (Ticket.priority == "P2", 2),
        else_=3,
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
    decision = t.decision or {}
    priority = (t.priority or decision.get("priority") or "P2").upper()
    sentiment = (t.sentiment or decision.get("sentiment") or "neutral").lower()
    action_required = t.action_required
    needs_review = bool(decision.get("needs_review") or (t.status == "needs_review"))
    auto_flag = bool(decision.get("auto_handled") or (t.status == "auto_handled"))
    risk_flag = bool(decision.get("risk_flag"))
    provider = (t.provider or decision.get("provider") or "email").lower()

    def _ai_reason(decision: dict, fallback: str) -> str:
        return decision.get("ai_reason") or decision.get("reason") or fallback

    def _sla_display(priority_val: str | None) -> str:
        mapping = {"P0": "2h", "P1": "4h", "P2": "24h"}
        return mapping.get((priority_val or "").upper(), "24h")

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
    if action_required is None and priority == "P2" and sentiment == "neutral" and not risk_flag:
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
        "category": t.category or decision.get("category") or "general",
        "intent": decision.get("intent") or "general",
        "sentiment": sentiment or "neutral",
        "provider": provider,
        "channel": _channel_from_provider(provider),
        "ai_reason": _ai_reason(decision, "Action required — customer needs help."),
        "owner": t.owner or decision.get("owner") or "Support",
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
    if priority in ("P0", "P1", "P2"):
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
            view["ai_reason"] = view.get("ai_reason") or "Optional — not blocking, follow up if capacity."
            optional_items.append(view)
        elif action_required is False or t.status == "auto_handled" or (view["priority"] == "P2" and view["sentiment"] == "neutral" and not risk_flag):
            view["ai_reason"] = view.get("ai_reason") or "Informational / auto-handled."
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
                "priority": decision.get("priority") or "P2",
                "ai_reason": decision.get("ai_reason") or "Feedback auto-handled.",
                "owner": decision.get("owner") or "Product",
                "team": decision.get("team") or "Product",
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
            ticket.due_at = compute_due_at(ticket.priority)
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
    conn = InboxConnection.query.filter_by(user_id=user_id, provider=provider).first()
    if not conn:
        conn = InboxConnection(
            user_id=user_id or 0,
            account_id=account_id,
            provider=provider,
            email_address=email_address,
        )
        db.session.add(conn)

    conn.access_token = access_token
    conn.refresh_token = data.get("refresh_token")
    conn.scopes = data.get("scopes") or []
    conn.status = "connected"
    meta = conn.metadata_json or {}
    meta.update({"last_poll_status": "never", "last_poll_error": None})
    conn.metadata_json = meta
    db.session.commit()

    return jsonify({"connection": conn.to_dict()})


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
                limit=10,
            )
            if new_token:
                conn.access_token = new_token
        elif conn.provider == "outlook" and conn.access_token:
            messages, new_token = fetch_messages_outlook(
                access_token=conn.access_token,
                refresh_token=conn.refresh_token,
                client_id=current_app.config.get("MICROSOFT_CLIENT_ID"),
                client_secret=current_app.config.get("MICROSOFT_CLIENT_SECRET"),
                tenant_id=current_app.config.get("MICROSOFT_TENANT_ID"),
                limit=10,
            )
            if new_token:
                conn.access_token = new_token
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


@v1.route("/inboxiq/poll/<connection_id>", methods=["POST"])
@jwt_required(optional=True)
def poll_inbox(connection_id: str):
    """
    HTTP entrypoint for polling; requires a request context for JWT, then delegates
    to the shared internal poll logic.
    """
    return _poll_inbox_internal(connection_id, get_jwt_identity())


@v1.route("/inboxiq/poll/mine", methods=["POST"])
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

    conn = InboxConnection.query.filter_by(user_id=user_id, provider=provider).first()
    if not conn:
        conn = InboxConnection(
            user_id=user_id or 0,
            account_id=account_id,
            provider=provider,
            email_address=email_address,
        )
        db.session.add(conn)

    conn.access_token = token
    conn.status = "connected"
    conn.metadata_json = {"last_poll_status": "never"}
    db.session.commit()

    # Auto-poll to create first tickets
    try:
        with current_app.test_request_context():
            # reuse existing poll logic
            poll_inbox(conn.id)
    except Exception:
        current_app.logger.warning("Auto-poll after connect failed", exc_info=True)

    return redirect(url_for("dashboard_home"))
