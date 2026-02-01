"""
Lightweight Celery setup for InboxIQ billing jobs only.
Does not pull in legacy schedules or tasks.
"""
import os
import re
from datetime import datetime, timedelta, timezone
from celery import Celery
from celery.schedules import crontab
from src.app import create_app
from src.agent_worker import process_email_with_agents
from src.inboxiq_logic import normalize_email_payload, run_dspy_decision, compute_due_at
from src.decision_merger import merge_decisions, should_skip_triage
from src.extensions import db
from src.models import Ticket, InboxConnection, Account
from src.triage_labels import get_triage_labels
from src.dspy_train import train_from_overrides
from src.dspy import _configure_dspy
import logging

# Default body preview limit (can be overridden per-account via TriageConfig)
DEFAULT_BODY_PREVIEW_LIMIT = 240


def make_celery(app) -> Celery:
    broker_url = app.config.get("CELERY_BROKER_URL") or os.getenv("CELERY_BROKER_URL")
    backend_url = app.config.get("CELERY_RESULT_BACKEND") or os.getenv("CELERY_RESULT_BACKEND")
    celery_app = Celery("inboxiq", broker=broker_url, backend=backend_url)

    def _parse_bool(val: str | None, default: bool = False) -> bool:
        if val is None:
            return default
        return val.lower() in ("1", "true", "yes", "on")

    # Optional daily lead sourcing schedule (runs only if env/config is present)
    sourcing_agent = os.getenv("LEAD_SOURCING_AGENT_ID")
    sourcing_queries = [q.strip() for q in (os.getenv("LEAD_SOURCING_QUERIES") or "").split("|") if q.strip()]
    sourcing_max_results = int(os.getenv("LEAD_SOURCING_MAX_RESULTS", "5") or "5")
    sourcing_send_probe = _parse_bool(os.getenv("LEAD_SOURCING_SEND_PROBE"), False)
    dspy_train_enabled = _parse_bool(os.getenv("DSPY_TRAIN_AUTOMATION"), False)
    dspy_train_hour = int(os.getenv("DSPY_TRAIN_SCHEDULE_HOUR", "3"))
    dspy_train_minute = int(os.getenv("DSPY_TRAIN_SCHEDULE_MINUTE", "0"))

    celery_app.conf.update(
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        timezone="UTC",
        enable_utc=True,
        broker_connection_retry_on_startup=True,
        beat_schedule={
            "billing_trial_checker_daily": {
                "task": "billing.run_trial_checker",
                "schedule": crontab(hour=0, minute=15),
                "options": {"queue": "billing"},
            },
            "billing_retry_hourly": {
                "task": "billing.run_retry_processor",
                "schedule": crontab(minute=0),
                "options": {"queue": "billing"},
            },
            "billing_dunning_daily": {
                "task": "billing.run_dunning_sender",
                "schedule": crontab(hour=6, minute=0),
                "options": {"queue": "billing"},
            },
            "inboxiq_poll_connections": {
                "task": "inboxiq.poll_connections",
                "schedule": crontab(minute="*/15"),
                "options": {"queue": "inbox"},
            },
            **(
                {
                    "lead_sourcing_daily": {
                        "task": "leads.sourcing_job",
                        "schedule": crontab(hour=2, minute=0),
                        "args": [sourcing_agent, sourcing_queries, sourcing_max_results, sourcing_send_probe],
                        "options": {"queue": "leads"},
                    }
                }
                if sourcing_agent and sourcing_queries
                else {}
            ),
            **(
                {
                    "dspy_train_overrides_daily": {
                        "task": "inboxiq.train_dspy_overrides",
                        "schedule": crontab(hour=dspy_train_hour, minute=dspy_train_minute),
                        "options": {"queue": "inbox"},
                    }
                }
                if dspy_train_enabled
                else {}
            ),
        },
    )

    # Ensure tasks use Flask context
    class ContextTask(celery_app.Task):
        abstract = True

        def __call__(self, *args, **kwargs):
            with app.app_context():
                return super().__call__(*args, **kwargs)

    celery_app.Task = ContextTask
    return celery_app


app = create_app()
celery = make_celery(app)
celery.autodiscover_tasks(["src.billing", "src.publishing", "src.leads"])


def _redact_body_preview(text: str) -> str:
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


def _build_body_preview(text: str, account_id: int | None = None) -> str:
    from src.triage_config import get_triage_config
    limit = get_triage_config(account_id).body_preview_limit
    return _redact_body_preview(text or "")[:limit]


@celery.task(
    name="inboxiq.process_incoming_email",
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    queue="inbox",
)
def process_incoming_email_task(self, payload: dict) -> dict:
    """
    Process a single inbound email:
      1) normalize payload
      2) dedupe on message_id+provider
      3) pre-filter check for obvious spam/marketing/auto-replies
      4) invoke agents (intake/enrich/triage) if not skipped
      5) run DSPy triage
      6) merge agent + DSPy decisions
      7) persist ticket with merged decision
    """
    email_payload = (payload or {}).get("email") or (payload or {})
    account_id = (payload or {}).get("account_id")
    user_id = (payload or {}).get("user_id")

    try:
        normalized = normalize_email_payload(email_payload)
    except Exception as exc:
        return {"status": "rejected", "error": str(exc)}

    existing = (
        Ticket.query.filter_by(
            message_id=normalized.get("message_id"),
            provider=normalized.get("provider"),
        ).first()
    )
    if existing:
        return {"status": "duplicate", "ticket_id": existing.id}

    # Pre-filter check: skip full triage for obvious spam/marketing/auto-replies
    skip_triage, pre_filter_type, pre_filter_reason = should_skip_triage(normalized)

    agent_result = None
    agent_decision = None

    # Only run agent pipeline if not skipping triage
    if not skip_triage:
        try:
            agent_result = process_email_with_agents(normalized)
            if agent_result:
                agent_decision = agent_result.get("decision") or agent_result.get("triage") or {}
        except Exception as exc:
            # Default to optional agents - don't fail intake if agents fail
            require_agents = os.getenv("AGENT_PIPELINE_REQUIRED", "0").lower() in ("1", "true", "yes", "on")
            if require_agents:
                logging.getLogger(__name__).error("agent pipeline failed; aborting intake: %s", exc)
                raise
            logging.getLogger(__name__).warning("agent pipeline failed; continuing without agents: %s", exc)
            agent_result = None

    # Run DSPy triage (will also apply heuristics internally)
    decision = run_dspy_decision(normalized, account_id=account_id)

    # Merge agent decision with DSPy decision
    dspy_dict = decision.to_dict()
    merged = merge_decisions(dspy_dict, agent_decision)

    # Apply pre-filter override if it detected non-actionable email
    if skip_triage and pre_filter_type:
        merged["action_required"] = False
        merged["email_type"] = pre_filter_type
        merged["is_automated"] = True
        merged["ai_reason"] = f"Auto-handled: {pre_filter_reason}"
        merged["decision_trace"] = merged.get("decision_trace", []) + [f"pre_filter:{pre_filter_type}"]
        merged["decision_outcome"] = "auto_handled"

    # Extract final values from merged decision
    category = merged.get("category") or decision.category
    priority = merged.get("priority") or decision.priority
    sentiment = merged.get("sentiment") or decision.sentiment
    action_required = merged.get("action_required")
    email_type = merged.get("email_type")
    is_automated = merged.get("is_automated", False)

    # Build comprehensive decision record
    decision_record = {
        "agent": agent_decision,
        "llm": dspy_dict,
        "merged": merged,
        "agent_pipeline": agent_result,
        "action_required": action_required,
        "email_type": email_type,
        "is_automated": is_automated,
        "pre_filter": {
            "skipped": skip_triage,
            "type": pre_filter_type,
            "reason": pre_filter_reason,
        } if skip_triage else None,
    }

    # Determine ticket status based on action_required
    if action_required is False:
        status = "auto_handled"
    elif action_required == "optional":
        status = "optional"
    elif decision.needs_review:
        status = "needs_review"
    else:
        status = "new"

    ticket = Ticket(
        account_id=account_id,
        user_id=user_id,
        subject=normalized.get("subject"),
        from_email=normalized.get("from_email"),
        body_preview=_build_body_preview(normalized.get("body"), account_id),
        category=category,
        priority=priority,
        sentiment=sentiment,
        entities=decision.entities,
        status=status,
        message_id=normalized.get("message_id"),
        provider=normalized.get("provider"),
        provider_thread_url=normalized.get("provider_thread_url"),
        decision=decision_record,
        team=merged.get("team") or decision.team,
        assigned_to=merged.get("assigned_to") or decision.assigned_to,
        owner=merged.get("owner") or decision.owner,
        due_at=compute_due_at(priority, account_id),
    )
    db.session.add(ticket)
    try:
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        logging.getLogger(__name__).exception("failed to persist inbound email ticket: %s", exc)
        raise self.retry(exc=exc)

    logging.getLogger(__name__).info(
        "ticket created: id=%s status=%s action_required=%s email_type=%s",
        ticket.id, status, action_required, email_type
    )

    return {
        "status": "created" if status != "auto_handled" else "auto_handled",
        "ticket_id": ticket.id,
        "category": category,
        "priority": priority,
        "action_required": action_required,
        "email_type": email_type,
    }


@celery.task(
    name="inboxiq.poll_connections",
    bind=True,
    max_retries=0,
    default_retry_delay=60,
    queue="inbox",
)
def poll_connections_task(self):
    """
    Periodically poll all connected inboxes (gmail/outlook).
    Uses the existing poll_inbox view logic inside a test request context.
    """
    from src.api.v1.inboxiq import poll_inbox  # local import to avoid circulars

    conns = (
        InboxConnection.query.filter(
            InboxConnection.status == "connected",
            InboxConnection.provider.in_(("gmail", "outlook")),
        ).all()
    )
    polled = 0
    errors = 0
    for conn in conns:
        try:
            with app.test_request_context(f"/api/v1/inboxiq/poll/{conn.id}", method="POST"):
                poll_inbox(conn.id)
            polled += 1
        except Exception as exc:
            errors += 1
            logging.getLogger(__name__).warning("poll failed for connection %s: %s", conn.id, exc)
    return {"polled": polled, "errors": errors}


def _env_list(name: str) -> list[str]:
    raw = os.getenv(name) or ""
    return [entry.strip() for entry in raw.split(",") if entry.strip()]


@celery.task(
    name="inboxiq.train_dspy_overrides",
    bind=True,
    max_retries=0,
    queue="inbox",
)
def train_dspy_overrides_task(self) -> dict:
    """
    Compile DSPy triage modules from manual overrides, per tenant.
    Uses env-configured providers/models and saves compiled artifacts to DSPY_COMPILED_DIR.
    """
    limit = int(os.getenv("DSPY_TRAIN_LIMIT", "200"))
    min_samples = int(os.getenv("DSPY_TRAIN_MIN_SAMPLES", "20"))
    max_accounts = int(os.getenv("DSPY_TRAIN_MAX_ACCOUNTS", "0") or "0")
    lookback_days = int(os.getenv("DSPY_TRAIN_LOOKBACK_DAYS", "30"))
    account_ids = _env_list("DSPY_TRAIN_ACCOUNT_IDS")
    include_global = os.getenv("DSPY_TRAIN_GLOBAL", "0").lower() in ("1", "true", "yes", "on")

    providers = _env_list("DSPY_TRAIN_PROVIDERS")
    if not providers:
        current = (os.getenv("DSPY_PROVIDER") or "").strip().lower() or "openai"
        providers = [current]

    results: dict[str, list[dict]] = {}
    original_provider = os.getenv("DSPY_PROVIDER")
    original_model = os.getenv("DSPY_MODEL")

    try:
        if not account_ids:
            cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)
            q = (
                db.session.query(Ticket.account_id)
                .filter(Ticket.manual_override.is_(True), Ticket.account_id.isnot(None))
                .filter(Ticket.updated_at >= cutoff)
                .distinct()
            )
            if max_accounts > 0:
                q = q.limit(max_accounts)
            account_ids = [str(row[0]) for row in q.all()]
        if include_global:
            account_ids.append("global")

        for provider in providers:
            provider_key = provider.strip().lower()
            model_override = os.getenv(f"DSPY_TRAIN_MODEL_{provider_key.upper()}")
            model_name = model_override or os.getenv("DSPY_TRAIN_MODEL") or original_model or "gpt-4o-mini"

            os.environ["DSPY_PROVIDER"] = provider_key
            os.environ["DSPY_MODEL"] = model_name

            _, model_id, dspy_instance = _configure_dspy()
            results[provider_key] = []

            for raw_id in account_ids:
                account_val = None if raw_id == "global" else int(raw_id)
                labels = get_triage_labels(account_val)
                outcome = train_from_overrides(
                    account_id=account_val,
                    labels=labels,
                    dspy_instance=dspy_instance,
                    model_id=model_id,
                    limit=limit,
                    min_samples=min_samples,
                )
                outcome["account_id"] = account_val
                results[provider_key].append(outcome)
    finally:
        if original_provider is not None:
            os.environ["DSPY_PROVIDER"] = original_provider
        elif "DSPY_PROVIDER" in os.environ:
            del os.environ["DSPY_PROVIDER"]
        if original_model is not None:
            os.environ["DSPY_MODEL"] = original_model
        elif "DSPY_MODEL" in os.environ:
            del os.environ["DSPY_MODEL"]

    return {"status": "ok", "providers": results}
