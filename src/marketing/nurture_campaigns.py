"""
Intelligent nurture campaign automation using DSPy.

Creates personalized nurture sequences for:
- Discovery stage: Educational content, thought leadership
- Consideration stage: Demos, ROI calculators, case studies

Uses PersonalizedEmailModule (B2B SaaS / E-commerce playbooks) for vertical-specific
copy. A/B variants are assigned deterministically via lead_id hash so each lead always
gets the same variant across multiple runs.

  Variant A (hash % 2 == 0): pain-point focused (baseline)
  Variant B (hash % 2 == 1): ROI / case-study focused

NurtureEmailSend records prevent duplicate sends of the same sequence step. The
insert uses ON CONFLICT DO NOTHING so concurrent task runs cannot collide on the
uq_nurture_send unique constraint.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Tuple
from uuid import uuid4

from sqlalchemy.dialects.postgresql import insert as pg_insert

from src.celery_inboxiq import celery
from src.extensions import db
from src.funnel.stages import CONSIDERATION, DISCOVERY
from src.models.campaigns import NurtureEmailSend
from src.models.leads import Lead

logger = logging.getLogger(__name__)

# Minimum days between any two nurture emails to the same lead.
_MIN_SEND_INTERVAL_DAYS = 6

# Stage day-number tiers: (days_in_stage_upper_bound_exclusive, sequence_day).
# First match wins; leads beyond all thresholds fall through to the fallback day.
_DISCOVERY_DAY_TIERS: List[Tuple[int, int]] = [(3, 1), (7, 3), (14, 7), (21, 14)]
_DISCOVERY_FALLBACK_DAY = 21

_CONSIDERATION_DAY_TIERS: List[Tuple[int, int]] = [(3, 1), (7, 3), (14, 7)]
_CONSIDERATION_FALLBACK_DAY = 14


def _ab_variant(lead_id: str) -> str:
    """Deterministically assign A/B variant from lead_id hash."""
    return "B" if hash(lead_id) % 2 else "A"


def _variant_extra(variant: str, base_extra: str) -> str:
    """Append variant-specific instruction for the DSPy generator."""
    if variant == "B":
        return base_extra + " Emphasize concrete ROI metrics and a specific case study number in the subject line."
    return base_extra


def _pick_day_number(days_in_stage: int, tiers: List[Tuple[int, int]], fallback: int) -> int:
    for threshold, day in tiers:
        if days_in_stage < threshold:
            return day
    return fallback


def _already_sent(lead_id: str, campaign_type: str, sequence_day: int) -> bool:
    """Return True if this exact step was already sent to this lead."""
    return db.session.query(NurtureEmailSend).filter_by(
        lead_id=lead_id,
        campaign_type=campaign_type,
        sequence_day=sequence_day,
    ).first() is not None


def _record_send(
    *,
    lead_id: str,
    campaign_type: str,
    sequence_day: int,
    variant: str,
    subject_line: str,
    vertical: str,
) -> None:
    """
    Idempotent insert of a NurtureEmailSend row. Uses ON CONFLICT DO NOTHING on the
    uq_nurture_send unique constraint so a concurrent task run that already logged
    this same (lead_id, campaign_type, sequence_day) cannot raise a UniqueViolation
    here. Commits its own transaction so a later failure in the loop doesn't lose
    this record.
    """
    try:
        stmt = pg_insert(NurtureEmailSend).values(
            id=str(uuid4()),
            lead_id=lead_id,
            campaign_type=campaign_type,
            sequence_day=sequence_day,
            ab_variant=variant,
            subject_line=(subject_line or "")[:500] or None,
            vertical=vertical,
        ).on_conflict_do_nothing(constraint="uq_nurture_send")
        db.session.execute(stmt)
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        logger.warning(
            "Failed to record nurture send lead=%s type=%s day=%s: %s",
            lead_id, campaign_type, sequence_day, exc,
        )


def _run_nurture_stage(
    *,
    stage: str,
    campaign_type: str,
    day_tiers: List[Tuple[int, int]],
    fallback_day: int,
    max_sends: int,
) -> Dict[str, Any]:
    """
    Shared driver for Discovery and Consideration nurture sends.

    Eligibility:
      - lead in `stage` for 2+ days
      - no nurture send in the last _MIN_SEND_INTERVAL_DAYS days
      - this exact (lead, campaign_type, sequence_day) not yet sent

    Per-lead failures are isolated — each lead's send commits independently and
    the loop continues if one fails. Every except clause rolls back first so a
    failed flush can never poison the session for subsequent iterations.
    """
    from src.notifications.emails import send_email

    two_days_ago = datetime.now(timezone.utc) - timedelta(days=2)
    cooldown_cutoff = datetime.now(timezone.utc) - timedelta(days=_MIN_SEND_INTERVAL_DAYS)

    recently_emailed_ids = db.session.query(NurtureEmailSend.lead_id).filter(
        NurtureEmailSend.sent_at > cooldown_cutoff,
    ).subquery()

    eligible_leads = db.session.query(Lead).filter(
        Lead.current_funnel_stage == stage,
        Lead.stage_entered_at <= two_days_ago,
        Lead.deleted == False,  # noqa: E712
        Lead.email.isnot(None),
        ~Lead.id.in_(recently_emailed_ids),
    ).limit(max_sends).all()

    if not eligible_leads:
        return {"status": "no_eligible_leads", "sent": 0}

    from src.dspy import _configure_dspy
    from src.dspy.email_personalization import PersonalizedEmailModule
    _configure_dspy()
    personalized_module = PersonalizedEmailModule()

    sent_count = 0
    failed_count = 0
    vertical_counts: Dict[str, int] = {}

    for lead in eligible_leads:
        # Snapshot ORM attributes BEFORE any DB write. After a failed flush,
        # SQLAlchemy expires loaded attributes; accessing them re-issues a SELECT
        # which then fails with PendingRollbackError. Reading into locals up front
        # means our error handler can log without ever touching an expired attr.
        lead_id = lead.id
        lead_email = lead.email
        lead_account_id = lead.account_id
        stage_entered_at = lead.stage_entered_at
        lead_name = lead.name
        lead_company = lead.company_name
        lead_industry = lead.industry
        lead_size = lead.company_size_bucket
        lead_engagement = lead.engagement_count

        try:
            if lead_account_id:
                try:
                    from src.features import feature_enabled
                    if not feature_enabled("nurture", lead_account_id):
                        continue
                except Exception:
                    pass  # Don't block send on gate failure

            days_in_stage = (datetime.now(timezone.utc) - stage_entered_at).days
            day_number = _pick_day_number(days_in_stage, day_tiers, fallback_day)

            if _already_sent(lead_id, campaign_type, day_number):
                continue

            variant = _ab_variant(lead_id)
            first_name = (lead_name or "").split()[0] or "there"
            base_extra = (
                f"Company size: {lead_size or 'unknown'}. "
                f"Engagement events: {lead_engagement or 0}."
            )
            extra = _variant_extra(variant, base_extra)

            email_content = personalized_module.generate(
                lead_first_name=first_name,
                company_name=lead_company or "your company",
                industry=lead_industry,
                email=lead_email,
                funnel_stage=stage,
                sequence_day=day_number,
                extra_context=extra,
            )

            success = send_email(
                to_email=lead_email,
                subject=email_content["subject_line"],
                html_body=email_content["email_body_html"],
                from_email="growth@kalevent.com",
                preheader=email_content.get("preview_text"),
            )

            if not success:
                failed_count += 1
                continue

            sent_count += 1
            vert = email_content.get("vertical", "unknown")
            vertical_counts[vert] = vertical_counts.get(vert, 0) + 1

            _record_send(
                lead_id=lead_id,
                campaign_type=campaign_type,
                sequence_day=day_number,
                variant=variant,
                subject_line=email_content["subject_line"],
                vertical=vert,
            )

            logger.info(
                "Sent %s nurture Day %d variant=%s (%s) to %s",
                campaign_type, day_number, variant, vert, lead_email,
            )

            if lead_account_id:
                try:
                    from src.billing.quota import check_and_increment
                    check_and_increment("nurture_emails", lead_account_id)
                except Exception as quota_exc:
                    db.session.rollback()
                    logger.warning(
                        "Quota increment failed for nurture_emails account=%s: %s",
                        lead_account_id, quota_exc,
                    )

        except Exception as exc:
            db.session.rollback()
            failed_count += 1
            logger.error(
                "Failed to send %s nurture to %s: %s",
                campaign_type, lead_email or "?", exc,
            )

    return {
        "status": "completed",
        "sent": sent_count,
        "failed": failed_count,
        "eligible_leads": len(eligible_leads),
        "vertical_breakdown": vertical_counts,
    }


@celery.task(name="marketing.send_discovery_nurture")
def send_discovery_nurture(max_sends: int = 50) -> Dict[str, Any]:
    """Send Discovery stage nurture emails. See _run_nurture_stage for eligibility."""
    return _run_nurture_stage(
        stage=DISCOVERY,
        campaign_type="discovery",
        day_tiers=_DISCOVERY_DAY_TIERS,
        fallback_day=_DISCOVERY_FALLBACK_DAY,
        max_sends=max_sends,
    )


@celery.task(name="marketing.send_consideration_nurture")
def send_consideration_nurture(max_sends: int = 30) -> Dict[str, Any]:
    """Send Consideration stage nurture emails. See _run_nurture_stage for eligibility."""
    return _run_nurture_stage(
        stage=CONSIDERATION,
        campaign_type="consideration",
        day_tiers=_CONSIDERATION_DAY_TIERS,
        fallback_day=_CONSIDERATION_FALLBACK_DAY,
        max_sends=max_sends,
    )
