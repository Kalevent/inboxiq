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
from src.agents.worker import process_email_with_agents
from src.inbox.logic import normalize_email_payload, run_dspy_decision, compute_due_at
from src.inbox.merger import merge_decisions, should_skip_triage
from src.extensions import db
from src.models.core import InboxConnection, Account
from src.models.tickets import Ticket
from src.dspy.triage_labels import get_triage_labels
from src.dspy.training.train import train_from_overrides
from src.dspy import _configure_dspy
import logging

# Default body preview limit (can be overridden per-account via TriageConfig)
DEFAULT_BODY_PREVIEW_LIMIT = 240

_log = logging.getLogger(__name__)


def _writeback_to_provider(
    provider: str | None,
    provider_message_id: str | None,
    provider_thread_id: str | None,
    account_id: int | None,
    category: str,
    priority: str,
    action_required,
    reply_text: str | None,
    from_email: str,
    subject: str,
    email_type: str | None = None,
    is_automated: bool = False,
) -> None:
    """
    Write triage results back into the user's inbox (Gmail label + optional draft reply).
    Delegates to poll.writeback_to_provider after resolving the connection and token.
    Best-effort — failures are logged and swallowed so they never block ticket creation.
    """
    if not provider or provider not in ("gmail", "outlook") or not provider_message_id:
        return

    from src.models.core import InboxConnection
    from src.inbox.poll import writeback_to_provider as _wb

    conn = InboxConnection.query.filter_by(
        account_id=account_id, provider=provider, status="connected"
    ).first()
    if not conn or not conn.access_token:
        return

    meta = conn.metadata_json or {}
    label_cache = meta.setdefault("label_ids", {})

    result = _wb(
        provider=provider,
        provider_message_id=provider_message_id,
        provider_thread_id=provider_thread_id,
        access_token=conn.access_token,
        label_cache=label_cache,
        category=category,
        priority=priority,
        reply_text=reply_text,
        from_email=from_email,
        subject=subject,
        email_type=email_type,
        is_automated=is_automated,
    )

    # Persist any newly-created label IDs back to the connection
    if result.get("label_applied"):
        try:
            conn.metadata_json = dict(meta)
            db.session.commit()
        except Exception as exc:
            db.session.rollback()
            _log.warning("writeback metadata save failed: account=%s error=%s", account_id, exc)


def make_celery(app) -> Celery:
    broker_url = app.config.get("CELERY_BROKER_URL") or os.getenv("CELERY_BROKER_URL")
    backend_url = app.config.get("CELERY_RESULT_BACKEND") or os.getenv("CELERY_RESULT_BACKEND")
    celery_app = Celery("inboxiq", broker=broker_url, backend=backend_url)

    def _parse_bool(val: str | None, default: bool = False) -> bool:
        if val is None:
            return default
        return val.lower() in ("1", "true", "yes", "on")

    dspy_train_enabled = _parse_bool(os.getenv("DSPY_TRAIN_AUTOMATION"), False)
    dspy_train_hour = int(os.getenv("DSPY_TRAIN_SCHEDULE_HOUR", "3"))
    dspy_train_minute = int(os.getenv("DSPY_TRAIN_SCHEDULE_MINUTE", "0"))

    content_gen_enabled = _parse_bool(os.getenv("CONTENT_GENERATION_ENABLED"), True)
    content_gen_day = int(os.getenv("CONTENT_GENERATION_DAY", "1"))  # Monday
    content_gen_hour = int(os.getenv("CONTENT_GENERATION_HOUR", "6"))
    content_gen_minute = int(os.getenv("CONTENT_GENERATION_MINUTE", "0"))

    funnel_orchestration_enabled = _parse_bool(os.getenv("FUNNEL_ORCHESTRATION_ENABLED"), True)
    daily_metrics_enabled = _parse_bool(os.getenv("DAILY_METRICS_ENABLED"), True)

    # Lead Discovery configuration
    lead_discovery_enabled = _parse_bool(os.getenv("LEAD_DISCOVERY_ENABLED"), False)
    lead_discovery_niche = os.getenv("LEAD_DISCOVERY_NICHE", "B2B SaaS revenue operations")
    lead_discovery_account_id = os.getenv("LEAD_DISCOVERY_ACCOUNT_ID", None)
    lead_discovery_max_leads = int(os.getenv("LEAD_DISCOVERY_MAX_LEADS", "50"))
    lead_discovery_hour = int(os.getenv("LEAD_DISCOVERY_HOUR", "2"))  # 2am daily

    # Trial onboarding configuration
    trial_onboarding_enabled = _parse_bool(os.getenv("TRIAL_ONBOARDING_ENABLED"), True)
    trial_onboarding_hour = int(os.getenv("TRIAL_ONBOARDING_HOUR", "8"))  # 8am daily
    trial_onboarding_max_emails = int(os.getenv("TRIAL_ONBOARDING_MAX_EMAILS", "100"))

    # Content distribution configuration
    content_distribution_enabled = _parse_bool(os.getenv("CONTENT_DISTRIBUTION_ENABLED"), True)
    content_distribution_hour = int(os.getenv("CONTENT_DISTRIBUTION_HOUR", "10"))  # 10am daily
    content_distribution_max_posts = int(os.getenv("CONTENT_DISTRIBUTION_MAX_POSTS", "5"))

    # Nurture campaigns configuration
    nurture_campaigns_enabled = _parse_bool(os.getenv("NURTURE_CAMPAIGNS_ENABLED"), True)
    nurture_discovery_hour = int(os.getenv("NURTURE_DISCOVERY_HOUR", "9"))  # 9am daily
    nurture_consideration_hour = int(os.getenv("NURTURE_CONSIDERATION_HOUR", "11"))  # 11am daily
    nurture_max_sends = int(os.getenv("NURTURE_MAX_SENDS", "50"))

    celery_app.conf.update(
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        timezone="UTC",
        enable_utc=True,
        broker_connection_retry_on_startup=True,
        beat_schedule={
            # NOTE: billing tasks (trial_checker, retry_processor, dunning_sender) are
            # handled exclusively by celery_billing.py / inboxiq-celery-billing-beat.
            # Do NOT add them here to avoid duplicate task execution.
            "inboxiq_poll_connections": {
                "task": "inboxiq.poll_connections",
                "schedule": crontab(minute="*/15"),
                "options": {"queue": "inbox"},
            },
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
            **(
                {
                    # B2B SaaS blog post — Monday
                    "content_weekly_blog_b2b_saas": {
                        "task": "content.generate_blog_post",
                        "schedule": crontab(day_of_week=content_gen_day, hour=content_gen_hour, minute=content_gen_minute),
                        "args": [
                            "B2B SaaS customer support automation",
                            "Head of Support / VP Customer Success, B2B SaaS, 50-500 employees",
                            0,  # topic_index
                            True,  # auto_publish → always goes through distribution pipeline
                        ],
                        "options": {"queue": "inbox"},
                    },
                    # E-commerce blog post — Thursday (stagger to avoid same-day publish)
                    "content_weekly_blog_ecommerce": {
                        "task": "content.generate_blog_post",
                        "schedule": crontab(day_of_week=4, hour=content_gen_hour, minute=content_gen_minute),
                        "args": [
                            "E-commerce post-purchase support",
                            "E-commerce operations manager, DTC brands, 10-200 employees",
                            0,
                            True,
                        ],
                        "options": {"queue": "inbox"},
                    },
                }
                if content_gen_enabled
                else {}
            ),
            **(
                {
                    "funnel_orchestration_job": {
                        "task": "funnel.orchestration_job",
                        "schedule": crontab(minute="*/15"),  # Every 15 minutes
                        "options": {"queue": "leads"},
                    }
                }
                if funnel_orchestration_enabled
                else {}
            ),
            **(
                {
                    "aggregate_funnel_metrics_daily": {
                        "task": "funnel.aggregate_daily_metrics",
                        "schedule": crontab(hour=1, minute=0),  # 1am daily
                        "options": {"queue": "leads"},
                    }
                }
                if daily_metrics_enabled
                else {}
            ),
            **(
                {
                    "discover_leads_daily": {
                        "task": "funnel.discover_leads_via_search",
                        "schedule": crontab(hour=lead_discovery_hour, minute=0),  # 2am daily
                        "kwargs": {
                            "niche": lead_discovery_niche,
                            "max_leads": lead_discovery_max_leads,
                            "account_id": lead_discovery_account_id,  # Optional, for future multi-tenancy
                        },
                        "options": {"queue": "leads"},
                    }
                }
                if lead_discovery_enabled
                else {}
            ),
            **(
                {
                    "discover_buying_signals_daily": {
                        "task": "funnel.discover_buying_signals",
                        "schedule": crontab(hour=lead_discovery_hour, minute=30),  # 2:30am daily
                        "kwargs": {
                            "niche": lead_discovery_niche,
                            "signal_type": "hiring",
                            "max_results": 20,
                        },
                        "options": {"queue": "leads"},
                    }
                }
                if lead_discovery_enabled
                else {}
            ),
            **(
                {
                    "process_trial_onboarding_daily": {
                        "task": "trial.process_onboarding_emails",
                        "schedule": crontab(hour=trial_onboarding_hour, minute=0),  # 8am daily
                        "args": [trial_onboarding_max_emails],
                        "options": {"queue": "leads"},
                    }
                }
                if trial_onboarding_enabled
                else {}
            ),
            **(
                {
                    "auto_publish_blog_posts_daily": {
                        "task": "marketing.auto_publish_ready_posts",
                        "schedule": crontab(hour=content_distribution_hour, minute=0),  # 10am daily
                        "args": [content_distribution_max_posts],
                        "options": {"queue": "leads"},
                    }
                }
                if content_distribution_enabled
                else {}
            ),
            **(
                {
                    "send_discovery_nurture_daily": {
                        "task": "marketing.send_discovery_nurture",
                        "schedule": crontab(hour=nurture_discovery_hour, minute=0),  # 9am daily
                        "args": [nurture_max_sends],
                        "options": {"queue": "leads"},
                    }
                }
                if nurture_campaigns_enabled
                else {}
            ),
            **(
                {
                    "send_consideration_nurture_daily": {
                        "task": "marketing.send_consideration_nurture",
                        "schedule": crontab(hour=nurture_consideration_hour, minute=0),  # 11am daily
                        "args": [nurture_max_sends],
                        "options": {"queue": "leads"},
                    }
                }
                if nurture_campaigns_enabled
                else {}
            ),
            # Behavior-triggered campaigns — every 4 hours
            **(
                {
                    "check_behavior_triggers_4h": {
                        "task": "marketing.check_behavior_triggers",
                        "schedule": crontab(minute=30, hour="*/4"),  # :30 past every 4 hours
                        "options": {"queue": "leads"},
                    }
                }
                if nurture_campaigns_enabled
                else {}
            ),
            # A/B test evaluation — weekly on Monday at 7am
            **(
                {
                    "evaluate_nurture_ab_tests_weekly": {
                        "task": "marketing.evaluate_nurture_ab_tests",
                        "schedule": crontab(day_of_week=1, hour=7, minute=0),
                        "options": {"queue": "leads"},
                    }
                }
                if nurture_campaigns_enabled
                else {}
            ),
            # CRM social sync — daily at 6am (LinkedIn + Twitter profile verification)
            **(
                {
                    "sync_social_crm_leads_daily": {
                        "task": "marketing.sync_social_crm_leads",
                        "schedule": crontab(hour=6, minute=0),
                        "options": {"queue": "leads"},
                    }
                }
                if nurture_campaigns_enabled
                else {}
            ),
            # Enterprise monthly value report — 1st of each month at 8am
            **(
                {
                    "enterprise_value_report_monthly": {
                        "task": "marketing.send_enterprise_value_reports",
                        "schedule": crontab(hour=8, minute=0, day_of_month=1),
                        "options": {"queue": "leads"},
                    }
                }
                if nurture_campaigns_enabled
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
celery.autodiscover_tasks(["src.billing", "src.publishing", "src.leads", "src.funnel", "src.content", "src.trial", "src.marketing"])

# Initialize OpenTelemetry for Celery workers
from src.monitoring.observability import init_otel, get_tracer
from src.monitoring.sanitizer import safe_span_attribute

init_otel(service_name="inboxiq-celery")
tracer = get_tracer(__name__)


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
    from src.dspy.triage_config import get_triage_config
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
    with tracer.start_as_current_span("celery.process_incoming_email") as span:
        email_payload = (payload or {}).get("email") or (payload or {})
        account_id = (payload or {}).get("account_id")
        user_id = (payload or {}).get("user_id")

        # Record task context
        safe_span_attribute(span, "account_id", account_id)
        safe_span_attribute(span, "user_id", user_id)
        safe_span_attribute(span, "task_id", self.request.id)

        try:
            normalized = normalize_email_payload(email_payload)
        except Exception as exc:
            span.set_attribute("error", True)
            span.set_attribute("error.type", "normalization_failed")
            span.record_exception(exc)
            return {"status": "rejected", "error": str(exc)}

        # Record email metadata (sanitized)
        safe_span_attribute(span, "email.provider", normalized.get("provider"))
        safe_span_attribute(span, "email.message_id", normalized.get("message_id"))
        safe_span_attribute(span, "email.subject_length", len(normalized.get("subject", "")))

        # Check for duplicates
        existing = (
            Ticket.query.filter_by(
                message_id=normalized.get("message_id"),
                provider=normalized.get("provider"),
            ).first()
        )
        if existing:
            span.set_attribute("email.duplicate", True)
            span.set_attribute("email.existing_ticket_id", str(existing.id))

            # Writeback healing — re-apply the InboxIQ label (and draft if available)
            # for any ticket whose writeback was interrupted (e.g. worker killed mid-task).
            #
            # Two paths:
            # 1. Native Gmail category signal → use that category (cheap, no DB lookup)
            # 2. Ticket has a category but email has no InboxIQ label yet → re-apply from ticket
            #    This covers support/billing emails where the worker was killed before writeback.
            #
            # Both paths are idempotent — applying a label that already exists is a no-op.
            _NATIVE_LABEL_MAP = {
                "CATEGORY_SOCIAL":     "social",
                "CATEGORY_FORUMS":     "forums",
                "CATEGORY_UPDATES":    "updates",
                "CATEGORY_PROMOTIONS": "promotions",
                "CATEGORY_PURCHASES":  "transactions",
            }
            _provider_label_ids = normalized.get("provider_label_ids") or []

            # Path 1: native signal
            _healed = False
            for _native, _cat in _NATIVE_LABEL_MAP.items():
                if _native in _provider_label_ids:
                    try:
                        _writeback_to_provider(
                            provider=normalized.get("provider"),
                            provider_message_id=normalized.get("provider_message_id"),
                            provider_thread_id=normalized.get("provider_thread_id"),
                            account_id=account_id,
                            category=_cat,
                            priority=existing.priority or "P3",
                            action_required=False,
                            reply_text=None,
                            from_email=normalized.get("from_email", ""),
                            subject=normalized.get("subject", ""),
                            email_type=_cat,
                            is_automated=True,
                        )
                    except Exception:
                        pass
                    _healed = True
                    break

            # Path 2: ticket has category but no InboxIQ label on the message yet
            if not _healed and existing.category:
                _has_inboxiq_label = any(
                    lid for lid in _provider_label_ids
                    if lid.startswith("Label_")  # user/InboxIQ-created labels have Label_ prefix
                )
                if not _has_inboxiq_label:
                    _decision = existing.decision or {}
                    _reply_text = _decision.get("reply_text")
                    try:
                        _writeback_to_provider(
                            provider=normalized.get("provider"),
                            provider_message_id=normalized.get("provider_message_id"),
                            provider_thread_id=normalized.get("provider_thread_id"),
                            account_id=account_id,
                            category=existing.category,
                            priority=existing.priority or "P3",
                            action_required=existing.status not in ("auto_handled",),
                            reply_text=_reply_text,
                            from_email=normalized.get("from_email", ""),
                            subject=normalized.get("subject", ""),
                            email_type=existing.category,
                            is_automated=(existing.status == "auto_handled"),
                        )
                    except Exception:
                        pass

            return {"status": "duplicate", "ticket_id": existing.id}

        span.set_attribute("email.duplicate", False)

        # Count one AI decision per unique email processed (after dedupe, before triage)
        if account_id:
            try:
                from src.billing.quota import check_and_increment, increment_signals
                check_and_increment("ai_decisions", int(account_id))
                increment_signals(int(account_id))
            except Exception as _quota_exc:
                logging.getLogger(__name__).warning("Quota increment failed for ai_decisions account=%s: %s", account_id, _quota_exc)

        # Pre-filter check: skip full triage for obvious spam/marketing/auto-replies
        skip_triage, pre_filter_type, pre_filter_reason = should_skip_triage(normalized)
        span.set_attribute("email.skip_triage", skip_triage)
        if skip_triage:
            safe_span_attribute(span, "email.pre_filter_type", pre_filter_type)
            safe_span_attribute(span, "email.pre_filter_reason", pre_filter_reason)

        # Layer 2 — SenderProfile lookup (confidence-gradient routing)
        # Inject sender_hint or bypass DSPy entirely if domain is well-known.
        from src.inbox.sender_profile import get_sender_hint
        _sender_hint, _sender_confidence, _bypass_dspy = get_sender_hint(
            normalized.get("from_email", ""), account_id
        )
        if _sender_hint:
            normalized["sender_hint"] = _sender_hint
        span.set_attribute("sender_profile.confidence", _sender_confidence)
        span.set_attribute("sender_profile.bypass", _bypass_dspy)

    agent_result = None
    agent_decision = None

    # Only run agent pipeline if not skipping triage and not bypassing via SenderProfile
    _ACTIONABLE_CATEGORIES = {"support", "billing"}
    _effective_bypass = _bypass_dspy and _sender_hint not in _ACTIONABLE_CATEGORIES
    if not skip_triage and not _effective_bypass:
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

    # Run DSPy triage (will also apply heuristics internally).
    # _effective_bypass is already computed above — bypass only for non-actionable categories.
    if _effective_bypass:
        # High-confidence non-actionable domain — synthesise a minimal decision
        # so the rest of the pipeline (ticket creation, writeback) works unchanged.
        from src.inbox.logic import TriageDecision
        decision = TriageDecision(
            category=_sender_hint,  # _sender_hint == category string on bypass
            priority="P3",
            sentiment="neutral",
            entities={},
            confidence={"category": _sender_confidence},
            action_required=False,
            decision_trace=[f"sender_profile:bypass:confidence={_sender_confidence:.2f}"],
        )
    else:
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
        # Map pre_filter_type → InboxIQ category so the writeback applies the right label
        _PRE_FILTER_CATEGORY_MAP = {
            "social":        "social",
            "forums":        "forums",
            "updates":       "updates",
            "promotions":    "promotions",
            "transactional": "transactions",
        }
        if pre_filter_type in _PRE_FILTER_CATEGORY_MAP:
            merged["category"] = _PRE_FILTER_CATEGORY_MAP[pre_filter_type]

    # Extract final values from merged decision
    category = merged.get("category") or decision.category
    priority = merged.get("priority") or decision.priority
    sentiment = merged.get("sentiment") or decision.sentiment
    action_required = merged.get("action_required")
    email_type = merged.get("email_type")
    is_automated = merged.get("is_automated", False)

    # Build comprehensive decision record.
    # reply_text and reply_confidence are surfaced at the top level so the API,
    # Ticket.to_dict(), and dashboard all find them with a simple dict.get().
    decision_record = {
        "agent": agent_decision,
        "llm": dspy_dict,
        "merged": merged,
        "agent_pipeline": agent_result,
        "action_required": action_required,
        "email_type": email_type,
        "is_automated": is_automated,
        "reply_text": decision.reply_text,
        "reply_confidence": decision.reply_confidence,
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
        provider_message_id=normalized.get("provider_message_id"),
        provider_thread_id=normalized.get("provider_thread_id"),
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

    # Layer 4 — upsert SenderProfile so the domain confidence grows with each email.
    # Best-effort: never block ticket creation if this fails.
    try:
        from src.inbox.sender_profile import upsert_sender_profile
        upsert_sender_profile(
            from_email=normalized.get("from_email", ""),
            category=category,
            account_id=account_id,
        )
    except Exception as _sp_exc:
        logging.getLogger(__name__).warning("SenderProfile upsert failed: %s", _sp_exc)

    # Write triage results back into the provider inbox (Gmail labels / Outlook categories + draft replies).
    # This is the core "InboxIQ on top of your inbox" experience — Oliver stays in Gmail/Outlook
    # and sees labels and draft replies there without opening a separate dashboard.
    _writeback_to_provider(
        provider=normalized.get("provider"),
        provider_message_id=normalized.get("provider_message_id"),
        provider_thread_id=normalized.get("provider_thread_id"),
        account_id=account_id,
        category=category,
        priority=priority,
        action_required=action_required,
        reply_text=decision.reply_text,
        from_email=normalized.get("from_email"),
        subject=normalized.get("subject", ""),
        email_type=email_type,
        is_automated=is_automated,
    )

    # Trigger automation rules using intelligent agent (tool-calling like Claude Code!)
    try:
        import os
        from src.models import AutomationRule
        from src.automation.template_engine import build_context

        # Choose agent type (tool_calling is default - it's more powerful!)
        agent_type = os.getenv("AUTOMATION_AGENT_TYPE", "tool_calling")

        if agent_type == "tool_calling":
            from src.automation.tool_calling_agent import execute_workflow_with_tool_calling_agent as execute_workflow
            agent_name = "🤖 Tool-Calling Agent"
        else:
            from src.automation.dspy_agent import execute_workflow_with_dspy_agent as execute_workflow
            agent_name = "🧠 DSPy Agent"

        # Find all enabled automation rules for this account
        rules = AutomationRule.query.filter_by(
            account_id=account_id,
            enabled=True
        ).all()

        # Build trigger context for automation
        trigger_context = build_context(
            email=normalized,
            ticket=ticket,
            account_id=account_id,
            extracted=merged.get("entities", {}),
            rule_name=None  # Will be set per-rule
        )

        logging.getLogger(__name__).info(
            "🤖 Built automation trigger context: ticket_id=%s extracted_keys=%s agent=%s",
            ticket.id, list(merged.get("entities", {}).keys()), agent_name
        )

        # Execute matching rules with intelligent agent
        for rule in rules:
            trigger_event = rule.trigger.get("event") if isinstance(rule.trigger, dict) else None
            # Match on ticket.created or email.received
            if trigger_event in ("ticket.created", "email.received"):
                logging.getLogger(__name__).info(
                    "🤖 Executing automation with %s: rule_id=%s rule_name=%s trigger=%s",
                    agent_name, rule.id, rule.name, trigger_event
                )
                try:
                    # Use intelligent agent - autonomous and adaptive!
                    result = execute_workflow(
                        workflow_id=str(rule.id),
                        trigger_context=trigger_context,
                        trigger_event=trigger_event
                    )
                    logging.getLogger(__name__).info(
                        "🤖 Agent execution completed: rule_id=%s success=%s tool_calls=%s log=%s",
                        rule.id, result.get("success"),
                        len(result.get("tool_calls", [])),
                        result.get("agent_log", [])[:3]  # First 3 log entries
                    )
                except Exception as rule_exc:
                    logging.getLogger(__name__).exception(
                        "❌ Agent execution failed: rule_id=%s error=%s",
                        rule.id, str(rule_exc)
                    )
                    # Continue with other rules even if one fails
    except Exception as automation_exc:
        # Don't fail ticket creation if automation fails
        logging.getLogger(__name__).exception(
            "❌ Automation trigger failed for ticket=%s: %s",
            ticket.id, str(automation_exc)
        )

    # Record final ticket details (sanitized)
    span.set_attribute("ticket.id", str(ticket.id))
    span.set_attribute("ticket.status", status)
    safe_span_attribute(span, "ticket.category", category)
    safe_span_attribute(span, "ticket.priority", priority)
    safe_span_attribute(span, "ticket.sentiment", sentiment)
    safe_span_attribute(span, "ticket.email_type", email_type)
    span.set_attribute("ticket.is_automated", is_automated)
    span.set_attribute("ticket.action_required", str(action_required))

    # Add completion event for audit trail
    span.add_event("ticket_created", {
        "ticket_id": str(ticket.id),
        "status": status,
        "category": category,
        "priority": priority,
        "action_required": str(action_required),
    })

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
    # Use poll_inbox_service — the service-layer call that works without a fake
    # HTTP request context. ContextTask already provides app_context().
    from src.api.v1.inboxiq import poll_inbox_service

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
                poll_inbox_service(conn.id)
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

                # Save training metrics to database
                if outcome.get("status") == "compiled":
                    try:
                        import json
                        from src.models import DspyTrainingMetric

                        # Build metadata with per-field accuracy
                        metadata = {
                            "train_field_accuracy": outcome.get("train_field_accuracy", {}),
                            "eval_field_accuracy": outcome.get("eval_field_accuracy", {}),
                        }

                        metric = DspyTrainingMetric(
                            account_id=account_val,
                            model_id=model_id,
                            provider=provider_key,
                            sample_count=outcome.get("count") or 0,
                            seed_count=outcome.get("seed_count") or 0,
                            train_accuracy=outcome.get("train_accuracy"),
                            eval_accuracy=outcome.get("eval_accuracy"),
                            train_weighted=outcome.get("train_weighted"),
                            eval_weighted=outcome.get("eval_weighted"),
                            metadata_json=json.dumps(metadata),
                        )
                        db.session.add(metric)
                        db.session.commit()
                        logging.getLogger(__name__).info(
                            "Saved DSPy training metric: account=%s provider=%s "
                            "train_acc=%s eval_acc=%s train_weighted=%s eval_weighted=%s",
                            account_val, provider_key,
                            outcome.get("train_accuracy"), outcome.get("eval_accuracy"),
                            outcome.get("train_weighted"), outcome.get("eval_weighted"),
                        )
                    except Exception as exc:
                        db.session.rollback()
                        logging.getLogger(__name__).warning("Failed to persist DSPy metrics: %s", exc)
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
