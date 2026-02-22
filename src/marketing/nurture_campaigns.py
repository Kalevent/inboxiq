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

NurtureEmailSend records prevent duplicate sends of the same sequence step.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Any

from src.celery_inboxiq import celery
from src.extensions import db
from src.funnel_stages import DISCOVERY, CONSIDERATION
from src.models import Lead, NurtureEmailSend

logger = logging.getLogger(__name__)

# Minimum days between any two nurture emails to the same lead.
_MIN_SEND_INTERVAL_DAYS = 6


def _ab_variant(lead_id: str) -> str:
    """Deterministically assign A/B variant from lead_id hash."""
    return "B" if hash(lead_id) % 2 else "A"


def _variant_extra(variant: str, base_extra: str) -> str:
    """Append variant-specific instruction for the DSPy generator."""
    if variant == "B":
        return base_extra + " Emphasize concrete ROI metrics and a specific case study number in the subject line."
    return base_extra


def _already_sent(lead_id: str, campaign_type: str, sequence_day: int) -> bool:
    """Return True if this exact step was already sent to this lead."""
    return db.session.query(NurtureEmailSend).filter_by(
        lead_id=lead_id,
        campaign_type=campaign_type,
        sequence_day=sequence_day,
    ).first() is not None


def _log_send(lead_id: str, campaign_type: str, sequence_day: int,
              variant: str, subject_line: str, vertical: str) -> None:
    """Record a successful send in NurtureEmailSend."""
    try:
        send = NurtureEmailSend(
            lead_id=lead_id,
            campaign_type=campaign_type,
            sequence_day=sequence_day,
            ab_variant=variant,
            subject_line=subject_line[:500] if subject_line else None,
            vertical=vertical,
        )
        db.session.add(send)
        # Flush within the caller's transaction; the caller commits.
    except Exception as exc:
        logger.warning("Failed to log nurture send for lead %s: %s", lead_id, exc)


@celery.task(name="marketing.send_discovery_nurture")
def send_discovery_nurture(max_sends: int = 50) -> Dict[str, Any]:
    """
    Send Discovery stage nurture emails.

    Targets leads that:
    - Are in DISCOVERY stage for 2+ days
    - Have not received a nurture email in the last 6 days
    - Have not already received this exact sequence day email

    Returns:
        Summary dict: status, sent, failed, eligible_leads, vertical_breakdown
    """
    from src.email_utils import send_email

    two_days_ago = datetime.now(timezone.utc) - timedelta(days=2)
    cooldown_cutoff = datetime.now(timezone.utc) - timedelta(days=_MIN_SEND_INTERVAL_DAYS)

    # Exclude leads that received any nurture email too recently.
    # We join NurtureEmailSend and exclude lead IDs with a recent send.
    recently_emailed_ids = db.session.query(NurtureEmailSend.lead_id).filter(
        NurtureEmailSend.sent_at > cooldown_cutoff,
    ).subquery()

    eligible_leads = db.session.query(Lead).filter(
        Lead.current_funnel_stage == DISCOVERY,
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
        try:
            # Feature gate per account
            if lead.account_id:
                try:
                    from src.features import feature_enabled
                    if not feature_enabled("nurture", lead.account_id):
                        continue
                except Exception:
                    pass  # Don't block send on gate failure

            days_in_stage = (datetime.now(timezone.utc) - lead.stage_entered_at).days

            if days_in_stage < 3:
                day_number = 1
            elif days_in_stage < 7:
                day_number = 3
            elif days_in_stage < 14:
                day_number = 7
            elif days_in_stage < 21:
                day_number = 14
            else:
                day_number = 21

            if _already_sent(lead.id, "discovery", day_number):
                continue

            variant = _ab_variant(lead.id)
            first_name = (lead.name or "").split()[0] or "there"
            base_extra = (
                f"Company size: {lead.company_size_bucket or 'unknown'}. "
                f"Engagement events: {lead.engagement_count or 0}."
            )
            extra = _variant_extra(variant, base_extra)

            email_content = personalized_module.generate(
                lead_first_name=first_name,
                company_name=lead.company_name or "your company",
                industry=lead.industry,
                email=lead.email,
                funnel_stage=DISCOVERY,
                sequence_day=day_number,
                extra_context=extra,
            )

            success = send_email(
                to_email=lead.email,
                subject=email_content["subject_line"],
                html_body=email_content["email_body_html"],
                from_email="growth@kalevent.com",
                preheader=email_content.get("preview_text"),
            )

            if success:
                sent_count += 1
                vert = email_content.get("vertical", "unknown")
                vertical_counts[vert] = vertical_counts.get(vert, 0) + 1
                _log_send(lead.id, "discovery", day_number, variant,
                          email_content["subject_line"], vert)
                logger.info(
                    "Sent Discovery nurture Day %d variant=%s (%s) to %s",
                    day_number, variant, vert, lead.email,
                )
                if lead.account_id:
                    try:
                        from src.quota import check_and_increment
                        check_and_increment("nurture_emails", lead.account_id)
                    except Exception as _qe:
                        logger.warning("Quota increment failed for nurture_emails account=%s: %s", lead.account_id, _qe)
            else:
                failed_count += 1

        except Exception as exc:
            logger.error("Failed to send Discovery nurture to %s: %s", getattr(lead, "email", "?"), exc)
            failed_count += 1

    db.session.commit()

    return {
        "status": "completed",
        "sent": sent_count,
        "failed": failed_count,
        "eligible_leads": len(eligible_leads),
        "vertical_breakdown": vertical_counts,
    }


@celery.task(name="marketing.send_consideration_nurture")
def send_consideration_nurture(max_sends: int = 30) -> Dict[str, Any]:
    """
    Send Consideration stage nurture emails.

    Targets leads that:
    - Are in CONSIDERATION stage for 2+ days
    - Have not received a nurture email in the last 6 days
    - Have not already received this exact sequence day email

    Returns:
        Summary dict: status, sent, failed, eligible_leads, vertical_breakdown
    """
    from src.email_utils import send_email

    two_days_ago = datetime.now(timezone.utc) - timedelta(days=2)
    cooldown_cutoff = datetime.now(timezone.utc) - timedelta(days=_MIN_SEND_INTERVAL_DAYS)

    recently_emailed_ids = db.session.query(NurtureEmailSend.lead_id).filter(
        NurtureEmailSend.sent_at > cooldown_cutoff,
    ).subquery()

    eligible_leads = db.session.query(Lead).filter(
        Lead.current_funnel_stage == CONSIDERATION,
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
        try:
            # Feature gate per account
            if lead.account_id:
                try:
                    from src.features import feature_enabled
                    if not feature_enabled("nurture", lead.account_id):
                        continue
                except Exception:
                    pass  # Don't block send on gate failure

            days_in_stage = (datetime.now(timezone.utc) - lead.stage_entered_at).days

            if days_in_stage < 3:
                day_number = 1
            elif days_in_stage < 7:
                day_number = 3
            elif days_in_stage < 14:
                day_number = 7
            else:
                day_number = 14

            if _already_sent(lead.id, "consideration", day_number):
                continue

            variant = _ab_variant(lead.id)
            base_extra = (
                f"Company size: {lead.company_size_bucket or 'unknown'}. "
                f"Engagement events: {lead.engagement_count or 0}."
            )
            extra = _variant_extra(variant, base_extra)

            first_name = (lead.name or "").split()[0] or "there"

            email_content = personalized_module.generate(
                lead_first_name=first_name,
                company_name=lead.company_name or "your company",
                industry=lead.industry,
                email=lead.email,
                funnel_stage=CONSIDERATION,
                sequence_day=day_number,
                extra_context=extra,
            )

            success = send_email(
                to_email=lead.email,
                subject=email_content["subject_line"],
                html_body=email_content["email_body_html"],
                from_email="growth@kalevent.com",
                preheader=email_content.get("preview_text"),
            )

            if success:
                sent_count += 1
                vert = email_content.get("vertical", "unknown")
                vertical_counts[vert] = vertical_counts.get(vert, 0) + 1
                _log_send(lead.id, "consideration", day_number, variant,
                          email_content["subject_line"], vert)
                logger.info(
                    "Sent Consideration nurture Day %d variant=%s (%s) to %s",
                    day_number, variant, vert, lead.email,
                )
                if lead.account_id:
                    try:
                        from src.quota import check_and_increment
                        check_and_increment("nurture_emails", lead.account_id)
                    except Exception as _qe:
                        logger.warning("Quota increment failed for nurture_emails account=%s: %s", lead.account_id, _qe)
            else:
                failed_count += 1

        except Exception as exc:
            logger.error("Failed to send Consideration nurture to %s: %s", getattr(lead, "email", "?"), exc)
            failed_count += 1

    db.session.commit()

    return {
        "status": "completed",
        "sent": sent_count,
        "failed": failed_count,
        "eligible_leads": len(eligible_leads),
        "vertical_breakdown": vertical_counts,
    }
