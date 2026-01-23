"""
Lightweight Celery setup for InboxIQ billing jobs only.
Does not pull in legacy schedules or tasks.
"""
import os
import re
from celery import Celery
from celery.schedules import crontab
from src.app import create_app
from src.agent_worker import process_email_with_agents
from src.inboxiq_logic import normalize_email_payload, triage_email
from src.extensions import db
from src.models import Ticket, InboxConnection
import logging

BODY_PREVIEW_LIMIT = 240


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


def _build_body_preview(text: str) -> str:
    return _redact_body_preview(text or "")[:BODY_PREVIEW_LIMIT]


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
      3) invoke agents (intake/enrich/triage)
      4) persist ticket with agent or heuristic decision
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

    agent_result = None
    try:
        agent_result = process_email_with_agents(normalized)
    except Exception as exc:
        logging.getLogger(__name__).warning("agent pipeline failed, will retry once: %s", exc)
        try:
            return self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            logging.getLogger(__name__).exception("agent pipeline failed after retries")

    # Use agent decision if present; fall back to heuristics to ensure fields are populated.
    heuristics = triage_email(normalized, account_id=account_id)
    agent_decision = None
    if agent_result:
        agent_decision = agent_result.get("decision") or agent_result.get("triage") or {}

    def _pick(key: str, default: str) -> str:
        if isinstance(agent_decision, dict):
            val = agent_decision.get(key)
            if isinstance(val, str) and val:
                return val
        return default

    category = _pick("category", heuristics.category)
    priority = _pick("priority", heuristics.priority)
    sentiment = _pick("sentiment", heuristics.sentiment)
    needs_review = heuristics.needs_review or False
    action_required = None
    if isinstance(agent_decision, dict):
        action_required = agent_decision.get("action_required")
    if action_required is None:
        action_required = heuristics.action_required

    decision_record = {
        "agent": agent_decision,
        "heuristics": heuristics.to_dict(),
        "agent_pipeline": agent_result,
        "action_required": action_required,
    }

    status = "needs_review" if needs_review else "new"
    if action_required is False:
        status = "auto_handled"
    elif action_required == "optional" and status != "needs_review":
        status = "optional"

    ticket = Ticket(
        account_id=account_id,
        user_id=user_id,
        subject=normalized.get("subject"),
        from_email=normalized.get("from_email"),
        body_preview=_build_body_preview(normalized.get("body")),
        category=category,
        priority=priority,
        sentiment=sentiment,
        entities=heuristics.entities,
        status=status,
        message_id=normalized.get("message_id"),
        provider=normalized.get("provider"),
        provider_thread_url=normalized.get("provider_thread_url"),
        decision=decision_record,
    )
    db.session.add(ticket)
    try:
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        logging.getLogger(__name__).exception("failed to persist inbound email ticket: %s", exc)
        raise self.retry(exc=exc)

    return {"status": "created", "ticket_id": ticket.id, "category": category, "priority": priority}


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
