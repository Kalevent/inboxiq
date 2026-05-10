"""
Lightweight Celery setup for InboxIQ billing jobs only.
Does not pull in legacy schedules or tasks.
"""
import os
import re
from datetime import datetime, timedelta, timezone
from celery import Celery
from flask import current_app
from celery.schedules import crontab
from src.app import create_app
from src.inbox.logic import normalize_email_payload, run_dspy_decision, compute_due_at
from src.inbox.merger import merge_decisions, should_skip_triage
from src.extensions import db
from src.models.core import InboxConnection, Account
from src.models.tickets import Ticket
from src.dspy.triage_labels import get_triage_labels
from src.dspy.training.train import train_from_overrides
from src.dspy import _configure_dspy
import logging
from celery.signals import task_prerun, task_postrun
from src.monitoring.metrics import record_task_cost

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
    sentiment: str | None = None,
    reply_confidence: float | None = None,
) -> None:
    """
    Write triage results back into the user's inbox (Gmail label + optional draft reply).
    Delegates to poll.writeback_to_provider after resolving the connection and token.
    Best-effort — failures are logged and swallowed so they never block ticket creation.
    """
    if not provider or provider not in ("gmail", "outlook") or not provider_message_id:
        _log.info("writeback skipped: provider=%s msg_id=%s", provider, bool(provider_message_id))
        return

    from src.models.core import InboxConnection
    from src.inbox.poll import writeback_to_provider as _wb

    conn = InboxConnection.query.filter_by(
        account_id=account_id, provider=provider, status="connected"
    ).first()
    if not conn or not conn.access_token:
        _log.warning("writeback skipped: no connected %s for account=%s", provider, account_id)
        return
    _log.info("writeback starting: provider=%s account=%s reply_text=%s", provider, account_id, bool(reply_text))

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
        # Pass refresh creds so writeback can recover from a stale access token.
        refresh_token=conn.refresh_token,
        client_id=current_app.config.get("GOOGLE_CLIENT_ID") if provider == "gmail" else current_app.config.get("MICROSOFT_CLIENT_ID"),
        client_secret=current_app.config.get("GOOGLE_CLIENT_SECRET") if provider == "gmail" else current_app.config.get("MICROSOFT_CLIENT_SECRET"),
        # Prior auth — needed to evaluate ApprovalPolicy conditions
        account_id=account_id,
        sentiment=sentiment,
        reply_confidence=reply_confidence,
    )

    # Persist label cache updates and any refreshed access token.
    if result.get("label_applied") or result.get("new_token"):
        try:
            if result.get("new_token"):
                conn.access_token = result["new_token"]
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

    # YouTube cadence configuration
    youtube_cadence_enabled = _parse_bool(os.getenv("YOUTUBE_CADENCE_ENABLED"), False)
    youtube_account_id = int(os.getenv("YOUTUBE_ACCOUNT_ID", "0")) or None

    # Outreach follow-ups and reply detection
    outreach_enabled = _parse_bool(os.getenv("OUTREACH_ENABLED"), True)

    # Trial onboarding configuration
    trial_onboarding_enabled = _parse_bool(os.getenv("TRIAL_ONBOARDING_ENABLED"), True)
    trial_onboarding_hour = int(os.getenv("TRIAL_ONBOARDING_HOUR", "8"))  # 8am daily
    trial_onboarding_max_emails = int(os.getenv("TRIAL_ONBOARDING_MAX_EMAILS", "100"))

    # Nurture campaigns configuration
    nurture_campaigns_enabled = _parse_bool(os.getenv("NURTURE_CAMPAIGNS_ENABLED"), True)
    nurture_discovery_hour = int(os.getenv("NURTURE_DISCOVERY_HOUR", "9"))  # 9am daily
    nurture_consideration_hour = int(os.getenv("NURTURE_CONSIDERATION_HOUR", "11"))  # 11am daily
    nurture_max_sends = int(os.getenv("NURTURE_MAX_SENDS", "50"))

    # Social distribution queue — daily picker
    social_distribution_hour = int(os.getenv("SOCIAL_DISTRIBUTION_HOUR", "11"))  # 11am UTC daily

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
            "inboxiq_nightly_link_check": {
                "task": "inboxiq.nightly_link_check",
                "schedule": crontab(hour=3, minute=0),  # 3am daily
                "options": {"queue": "inbox"},
            },
            "monitoring_smoke_test": {
                "task": "monitoring.run_smoke_test",
                "schedule": crontab(minute="*/15"),  # every 15 min between deploys
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
                        "options": {"queue": "content"},
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
                        "options": {"queue": "content"},
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
                    "billing_backfill_missing_profiles": {
                        "task": "billing.backfill_missing_profiles",
                        "schedule": crontab(hour=(trial_onboarding_hour - 1) % 24, minute=45),  # 15 min before trial emails
                        "options": {"queue": "billing"},
                    },
                    "process_trial_onboarding_daily": {
                        "task": "trial.process_onboarding_emails",
                        "schedule": crontab(hour=trial_onboarding_hour, minute=0),  # 8am daily
                        "args": [trial_onboarding_max_emails],
                        "options": {"queue": "leads"},
                    },
                }
                if trial_onboarding_enabled
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
            # Social distribution queue — daily picker, 11am UTC default
            "social_distribution_daily": {
                "task": "marketing.run_social_distribution_queue",
                "schedule": crontab(hour=social_distribution_hour, minute=0),
            },
            # Outreach: initial sends daily, follow-ups every 4 hours, reply scan every 4 hours
            **(
                {
                    "outreach_process_all_campaigns": {
                        "task": "outreach.process_all_campaigns",
                        "schedule": crontab(hour=7, minute=0),
                        "options": {"queue": "leads"},
                    },
                    "outreach_process_followups": {
                        "task": "outreach.process_followups",
                        "schedule": crontab(minute=0, hour="*/4"),
                        "options": {"queue": "leads"},
                    },
                    "outreach_scan_for_replies": {
                        "task": "outreach.scan_for_replies",
                        "schedule": crontab(minute=0, hour="2,6,10,14,18,22"),
                        "options": {"queue": "leads"},
                    },
                }
                if outreach_enabled
                else {}
            ),
            # LinkedIn outreach cadence — enrich urls → discover → draft → digest
            "linkedin_enrich_urls": {
                "task": "linkedin.enrich_linkedin_urls",
                "schedule": crontab(hour=5, minute=0),
                "options": {"queue": "inbox"},
            },
            "linkedin_discover_prospects": {
                "task": "linkedin.discover_prospects",
                "schedule": crontab(hour=7, minute=0),
                "options": {"queue": "inbox"},
            },
            "linkedin_draft_messages": {
                "task": "linkedin.draft_messages",
                "schedule": crontab(hour=7, minute=30),
                "options": {"queue": "inbox"},
            },
            "linkedin_send_digest": {
                "task": "linkedin.send_digest",
                "schedule": crontab(hour=8, minute=0),
                "options": {"queue": "inbox"},
            },
            "linkedin_expire_pending_connections": {
                "task": "linkedin.expire_pending_connections",
                "schedule": crontab(hour=6, minute=0),
                "options": {"queue": "inbox"},
            },
            "linkedin_update_acceptance_ratio_gauge": {
                "task": "linkedin.update_acceptance_ratio_gauge",
                "schedule": crontab(minute="*/30"),
                "options": {"queue": "inbox"},
            },
            # YouTube cadence — script generation, render polling, publish, digest
            **(
                {
                    "youtube_generate_scripts_1st": {
                        "task": "youtube.generate_scripts",
                        "schedule": crontab(day_of_month=1, hour=7, minute=0),
                        "kwargs": {"account_id": youtube_account_id, "video_style": "avatar"},
                        "options": {"queue": "content"},
                    },
                    "youtube_generate_scripts_15th": {
                        "task": "youtube.generate_scripts",
                        "schedule": crontab(day_of_month=15, hour=7, minute=0),
                        "kwargs": {"account_id": youtube_account_id, "video_style": "illustration"},
                        "options": {"queue": "content"},
                    },
                    "youtube_render_videos_daily": {
                        "task": "youtube.render_videos",
                        "schedule": crontab(hour=7, minute=30),
                        "kwargs": {"account_id": youtube_account_id},
                        "options": {"queue": "content"},
                    },
                    "youtube_publish_videos_daily": {
                        "task": "youtube.publish_videos",
                        "schedule": crontab(hour=8, minute=0),
                        "kwargs": {"account_id": youtube_account_id},
                        "options": {"queue": "content"},
                    },
                    "youtube_send_digest_daily": {
                        "task": "youtube.send_digest",
                        "schedule": crontab(hour=8, minute=30),
                        "kwargs": {"account_id": youtube_account_id},
                        "options": {"queue": "content"},
                    },
                }
                if youtube_cadence_enabled
                else {}
            ),
            **(
                {
                    "onboarding_deliver_videos_daily": {
                        "task": "onboarding.deliver_videos",
                        "schedule": crontab(hour=9, minute=0),
                        "options": {"queue": "content"},
                    },
                }
                if os.getenv("ONBOARDING_VIDEO_ENABLED", "false").lower() == "true"
                else {}
            ),
            **(
                {
                    "outreach.queue_videos": {
                        "task": "outreach.queue_videos",
                        "schedule": crontab(hour=8, minute=0),
                        "options": {"queue": "content"},
                    },
                    "outreach.deliver_videos": {
                        "task": "outreach.deliver_videos",
                        "schedule": crontab(hour=9, minute=30),
                        "options": {"queue": "content"},
                    },
                }
                if os.getenv("OUTREACH_VIDEO_ENABLED", "false").lower() == "true"
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
celery.autodiscover_tasks(["src.billing", "src.publishing", "src.leads", "src.funnel", "src.content", "src.trial", "src.marketing", "src.outreach", "src.inbox", "src.booking", "src.tasks.linkedin", "src.tasks.onboarding_video", "src.tasks.youtube", "src.tasks.outreach_video", "src.tasks.smoke"])

# autodiscover_tasks is lazy: workers occasionally start without finalizing
# the discovery, leaving @shared_task-decorated tasks unregistered. Explicit
# imports guarantee the registry is populated at module-load time. Verified
# via several tasks not being in `celery.tasks` on inbox-worker until manual
# import (2026-05-10 incident — qualify_visitor stuck 1237 leads unscored,
# linkedin.discover_prospects / enrich_linkedin_urls / draft_messages also
# silently unregistered).
from src.funnel import tasks as _funnel_tasks  # noqa: F401
from src.tasks import linkedin as _linkedin_tasks  # noqa: F401

# Wire Celery task_failure into app.logger so the SMTPHandler attached by
# configure_crash_email also pages on failed background tasks (otherwise
# only Flask request-handler exceptions would email).
from src.monitoring.crash_report import configure_celery_crash_email
configure_celery_crash_email(app)

# Initialize OpenTelemetry for Celery workers
from src.monitoring.observability import init_otel, get_tracer
from src.monitoring.sanitizer import safe_span_attribute

init_otel(service_name="inboxiq-celery")
tracer = get_tracer(__name__)

# --- Prometheus task instrumentation (auto-applies to all tasks) ---
import threading as _threading
import time as _time

_task_start: dict[str, float] = {}
_task_start_lock = _threading.Lock()


def _extract_account_id(args, kwargs):
    if "account_id" in kwargs:
        return kwargs["account_id"]
    if args and isinstance(args[0], dict):
        return args[0].get("account_id")
    return None


@task_prerun.connect
def _on_task_prerun(task_id, **_kw):
    with _task_start_lock:
        _task_start[task_id] = _time.perf_counter()


@task_postrun.connect
def _on_task_postrun(task_id, task, args, kwargs, state, **_kw):
    with _task_start_lock:
        start = _task_start.pop(task_id, None)
    if start is None:
        return
    elapsed = _time.perf_counter() - start
    account_id = _extract_account_id(args, kwargs)
    status = "success" if state == "SUCCESS" else "failure"
    record_task_cost(task.name, account_id=account_id, duration_seconds=elapsed, status=status)


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
    email_payload = (payload or {}).get("email") or (payload or {})
    account_id = (payload or {}).get("account_id")
    user_id = (payload or {}).get("user_id")
    with tracer.start_as_current_span("celery.process_incoming_email") as span:

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

            # Path 2: ticket has category but no InboxIQ label on the message yet.
            # Use the connection's known InboxIQ label IDs for the check — a plain
            # "Label_" prefix is too broad and matches any user-created Gmail label.
            if not _healed and existing.category:
                from src.models.core import InboxConnection as _IC
                _conn = _IC.query.filter_by(
                    account_id=account_id,
                    provider=normalized.get("provider"),
                    status="connected",
                ).first()
                _inboxiq_ids = set((_conn.metadata_json or {}).get("label_ids", {}).values()) if _conn else set()
                _has_inboxiq_label = bool(_inboxiq_ids & set(_provider_label_ids))
                if not _has_inboxiq_label:
                    _decision = existing.decision or {}
                    _reply_text = None  # Never re-create drafts during label healing — only fix the label
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

    _NON_ACTIONABLE_BYPASS_CATEGORIES = {
        "updates", "promotions", "social", "forums", "transactions",
        "spam", "marketing", "newsletter", "auto_reply", "notification",
    }
    _effective_bypass = _bypass_dspy and _sender_hint in _NON_ACTIONABLE_BYPASS_CATEGORIES
    # Legacy HTTP agent pipeline removed — DSPy triage handles classification directly.

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

    # Extract final values from merged decision.
    # Normalize to canonical InboxIQ categories — "general", "bug", "sales" etc.
    # can come from the agent pipeline and must be mapped before ticket creation.
    _CANONICAL_CATS = {"support", "billing", "transactions", "updates", "promotions", "social", "forums"}
    _CAT_NORM_MAP = {
        "general": "support", "other": "support", "bug": "support", "bug_report": "support",
        "technical": "support", "sales": "support", "feedback": "support",
        "marketing": "promotions", "newsletter": "updates",
        "spam": "updates", "auto_reply": "updates", "notification": "updates",
        "informational": "updates",
    }
    _raw_category = (merged.get("category") or decision.category or "support").lower().strip()
    category = _raw_category if _raw_category in _CANONICAL_CATS else _CAT_NORM_MAP.get(_raw_category, "support")
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

    # Best-effort: if this email is a meeting request and a draft was generated,
    # append a booking link so the visitor can self-schedule.
    if decision.reply_text and normalized.get("from_email"):
        try:
            from src.integrations.gcal import is_meeting_request as _is_meeting_req
            _subj = normalized.get("subject", "")
            _body = normalized.get("body") or normalized.get("text") or ""
            if _is_meeting_req(_subj, _body):
                from src.booking.service import generate_booking as _gen_booking
                _booking_url = _gen_booking(
                    account_id=account_id,
                    ticket_id=ticket.id,
                    subject=_subj,
                    requester_email=normalized.get("from_email", ""),
                    requester_name="",
                )
                decision.reply_text = (
                    decision.reply_text.rstrip()
                    + f"\n\nSchedule a time that works for you: {_booking_url}"
                )
        except Exception as _bk_exc:
            logging.getLogger(__name__).warning("Booking link injection failed: %s", _bk_exc)

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
        sentiment=sentiment,
        reply_confidence=decision.reply_confidence,
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
    name="inboxiq.nightly_link_check",
    bind=True,
    max_retries=0,
    queue="inbox",
)
def nightly_link_check_task(self) -> dict:
    """
    Crawl all public pages nightly, report any broken links to ADMIN_EMAILS.
    Skips destructive URLs; never reads or stores response bodies.
    """
    base_url = os.getenv("APP_BASE_URL") or "https://kalevent.com"

    from src.monitoring.link_checker import run_link_check, send_link_check_report
    report = run_link_check(base_url)
    send_link_check_report(report)

    logging.getLogger(__name__).info(
        "Link check complete: %d checked, %d broken, %d errors",
        report["checked"], len(report["broken"]), len(report["errors"]),
    )
    return {
        "checked": report["checked"],
        "broken": len(report["broken"]),
        "errors": len(report["errors"]),
    }


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


@celery.task(
    name="inboxiq.crawl_kb_source",
    bind=True,
    max_retries=0,
    queue="inbox",
)
def crawl_kb_source_task(self, account_id: int, base_url: str) -> dict:
    """
    Background task: crawl base_url and index all same-domain pages (one level deep).
    Called from the KB settings route when a user submits a crawl request.
    """
    from src.integrations.kb import crawl_kb_source
    result = crawl_kb_source(account_id, base_url)
    logger.info(
        "crawl_kb_source_task done account=%s base=%s indexed=%d skipped=%d errors=%d",
        account_id, base_url,
        result.get("indexed", 0), result.get("skipped", 0), len(result.get("errors", [])),
    )
    return result
