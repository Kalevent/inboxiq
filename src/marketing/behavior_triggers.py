"""
Behavior-triggered nurture campaigns.

Runs every 4 hours via Celery Beat. Detects high-value behavioral signals and
either accelerates the lead through the funnel or triggers a targeted email.

Triggers implemented:
  1. HIGH-INTENT PRICING VISITOR
     Lead has 3+ page_visit events where event_data contains '/pricing' or 'pricing'
     AND is still in DISCOVERY → bump to CONSIDERATION + queue consideration Day 1
  2. ENGAGEMENT SPIKE
     Lead has engagement_count >= 7 AND is in DISCOVERY → fast-track consideration
  3. DARK LEAD RE-ENGAGEMENT
     Lead has been in DISCOVERY/CONSIDERATION for 21+ days with no engagement
     in the last 14 days → send a re-engagement email (subject: "Still there?")

Each trigger checks NurtureEmailSend to prevent duplicate triggered sends.
The campaign_type for triggered emails uses the prefix "trigger_" so A/B test
evaluation treats them separately.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Any

from src.celery_inboxiq import celery
from src.extensions import db
from src.funnel.stages import DISCOVERY, CONSIDERATION
from src.models import Lead, LeadEngagementEvent, NurtureEmailSend

logger = logging.getLogger(__name__)

# ── Thresholds ────────────────────────────────────────────────────────────────
_PRICING_VISIT_THRESHOLD = 3          # pricing page visits to fast-track
_ENGAGEMENT_SPIKE_THRESHOLD = 7       # total events to fast-track
_DARK_LEAD_STAGE_DAYS = 21            # days in stage before "dark" check
_DARK_LEAD_SILENCE_DAYS = 14          # days without engagement to trigger re-eng
_LOOKBACK_DAYS = 7                    # window for counting recent pricing visits


def _already_triggered(lead_id: str, trigger_type: str) -> bool:
    """Return True if this trigger was already fired for this lead."""
    return db.session.query(NurtureEmailSend).filter_by(
        lead_id=lead_id,
        campaign_type=f"trigger_{trigger_type}",
        sequence_day=1,
    ).first() is not None


def _log_trigger_send(lead_id: str, trigger_type: str, subject_line: str, vertical: str) -> None:
    try:
        send = NurtureEmailSend(
            lead_id=lead_id,
            campaign_type=f"trigger_{trigger_type}",
            sequence_day=1,
            ab_variant=None,
            subject_line=subject_line[:500] if subject_line else None,
            vertical=vertical,
        )
        db.session.add(send)
    except Exception as exc:
        logger.warning("Failed to log trigger send for lead %s trigger %s: %s", lead_id, trigger_type, exc)


def _send_triggered_email(lead: Lead, trigger_type: str, subject: str, body_html: str) -> bool:
    """Send a triggered email and log it. Returns True on success."""
    from src.notifications.emails import send_email
    from src.dspy.email_personalization import infer_vertical

    try:
        success = send_email(
            to_email=lead.email,
            subject=subject,
            html_body=body_html,
            from_email="growth@kalevent.com",
        )
        if success:
            vertical = infer_vertical(lead.industry, lead.company_name, lead.email)
            _log_trigger_send(lead.id, trigger_type, subject, vertical)
        return success
    except Exception as exc:
        logger.error("Triggered email send failed for lead %s (%s): %s", lead.id, trigger_type, exc)
        return False


def _advance_to_consideration(lead: Lead) -> None:
    """Move a discovery lead to consideration stage."""
    if lead.current_funnel_stage != DISCOVERY:
        return
    lead.current_funnel_stage = CONSIDERATION
    lead.stage_entered_at = datetime.now(timezone.utc)
    logger.info("Behavior trigger advanced lead %s to consideration", lead.id)


@celery.task(name="marketing.check_behavior_triggers")
def check_behavior_triggers(max_per_trigger: int = 20) -> Dict[str, Any]:
    """
    Scan for behavioral signals and fire targeted campaign actions.

    Args:
        max_per_trigger: Max leads to process per trigger type per run.

    Returns:
        Summary of actions taken per trigger.
    """
    results: Dict[str, Any] = {
        "pricing_intent": {"advanced": 0, "emailed": 0, "errors": 0},
        "engagement_spike": {"advanced": 0, "errors": 0},
        "dark_lead": {"emailed": 0, "errors": 0},
    }

    now = datetime.now(timezone.utc)
    lookback = now - timedelta(days=_LOOKBACK_DAYS)
    silence_cutoff = now - timedelta(days=_DARK_LEAD_SILENCE_DAYS)
    old_stage_cutoff = now - timedelta(days=_DARK_LEAD_STAGE_DAYS)

    # ── Trigger 1: High-intent pricing visitor ──────────────────────────────
    try:
        # Leads in DISCOVERY with 3+ pricing page visits in the last 7 days.
        # event_data is JSON; we check if the JSON text contains 'pricing'.
        from sqlalchemy import func as sqlfunc, cast, String

        pricing_lead_ids = (
            db.session.query(LeadEngagementEvent.lead_id)
            .filter(
                LeadEngagementEvent.event_type == "page_visit",
                LeadEngagementEvent.created_at >= lookback,
                cast(LeadEngagementEvent.event_data, String).ilike("%pricing%"),
            )
            .group_by(LeadEngagementEvent.lead_id)
            .having(sqlfunc.count() >= _PRICING_VISIT_THRESHOLD)
            .subquery()
        )

        pricing_leads = db.session.query(Lead).filter(
            Lead.id.in_(pricing_lead_ids),
            Lead.current_funnel_stage == DISCOVERY,
            Lead.deleted == False,  # noqa: E712
            Lead.email.isnot(None),
        ).limit(max_per_trigger).all()

        for lead in pricing_leads:
            try:
                if not _already_triggered(lead.id, "pricing_intent"):
                    first_name = (lead.name or "").split()[0] or "there"
                    subject = f"{first_name}, ready to see InboxIQ in action?"
                    body_html = (
                        f"<p>Hi {first_name},</p>"
                        f"<p>I noticed you've been checking out our pricing page. "
                        f"Most teams that visit pricing 3+ times have specific questions about ROI.</p>"
                        f"<p>Let me take 15 minutes to show you exactly what InboxIQ would cost and "
                        f"save for <strong>{lead.company_name or 'your team'}</strong>.</p>"
                        f"<p><a href='https://kalevent.com/demo'>Book a 15-min ROI session →</a></p>"
                        f"<p>Best,<br>Team InboxIQ</p>"
                    )
                    _advance_to_consideration(lead)
                    if _send_triggered_email(lead, "pricing_intent", subject, body_html):
                        results["pricing_intent"]["advanced"] += 1
                        results["pricing_intent"]["emailed"] += 1
            except Exception as exc:
                logger.error("Pricing intent trigger error for lead %s: %s", lead.id, exc)
                results["pricing_intent"]["errors"] += 1

    except Exception as exc:
        logger.error("Pricing intent trigger query failed: %s", exc)

    # ── Trigger 2: Engagement spike (active lead stuck in DISCOVERY) ─────────
    try:
        spike_leads = db.session.query(Lead).filter(
            Lead.current_funnel_stage == DISCOVERY,
            Lead.engagement_count >= _ENGAGEMENT_SPIKE_THRESHOLD,
            Lead.deleted == False,  # noqa: E712
        ).limit(max_per_trigger).all()

        for lead in spike_leads:
            try:
                if not _already_triggered(lead.id, "engagement_spike"):
                    _advance_to_consideration(lead)
                    # Log the advance (no separate email — consideration nurture picks them up next run)
                    _log_trigger_send(lead.id, "engagement_spike", "stage_advance", "unknown")
                    results["engagement_spike"]["advanced"] += 1
            except Exception as exc:
                logger.error("Engagement spike trigger error for lead %s: %s", lead.id, exc)
                results["engagement_spike"]["errors"] += 1

    except Exception as exc:
        logger.error("Engagement spike trigger query failed: %s", exc)

    # ── Trigger 3: Dark lead re-engagement ───────────────────────────────────
    try:
        dark_leads = db.session.query(Lead).filter(
            Lead.current_funnel_stage.in_([DISCOVERY, CONSIDERATION]),
            Lead.stage_entered_at <= old_stage_cutoff,
            db.or_(
                Lead.last_engagement_at.is_(None),
                Lead.last_engagement_at <= silence_cutoff,
            ),
            Lead.deleted == False,  # noqa: E712
            Lead.email.isnot(None),
        ).limit(max_per_trigger).all()

        for lead in dark_leads:
            try:
                if not _already_triggered(lead.id, "re_engagement"):
                    first_name = (lead.name or "").split()[0] or "there"
                    subject = f"{first_name}, still interested in cutting support time?"
                    body_html = (
                        f"<p>Hi {first_name},</p>"
                        f"<p>It's been a while since we last connected. "
                        f"Support teams at {lead.company_name or 'companies like yours'} "
                        f"are still spending 30%+ of their week on repetitive tickets.</p>"
                        f"<p>If the timing isn't right, just reply and I'll stop. "
                        f"But if you'd like to see how InboxIQ handles that — "
                        f"<a href='https://kalevent.com/demo'>15 minutes is all it takes</a>.</p>"
                        f"<p>Best,<br>Team InboxIQ</p>"
                    )
                    if _send_triggered_email(lead, "re_engagement", subject, body_html):
                        results["dark_lead"]["emailed"] += 1
            except Exception as exc:
                logger.error("Dark lead trigger error for lead %s: %s", lead.id, exc)
                results["dark_lead"]["errors"] += 1

    except Exception as exc:
        logger.error("Dark lead trigger query failed: %s", exc)

    db.session.commit()

    logger.info(
        "Behavior triggers complete — pricing_intent: +%d advanced / +%d emailed | "
        "engagement_spike: +%d advanced | dark_lead: +%d emailed",
        results["pricing_intent"]["advanced"],
        results["pricing_intent"]["emailed"],
        results["engagement_spike"]["advanced"],
        results["dark_lead"]["emailed"],
    )

    return results
