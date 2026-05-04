"""Outreach video Celery tasks."""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List

from celery import shared_task

from src.extensions import db
from src.models.campaigns import VideoRender, OutreachVideo, EmailCampaign, EmailOutreach
from src.models.leads import Lead
from src.mcp import heygen_mcp

logger = logging.getLogger(__name__)


def _get_eligible_leads(campaign_id: str, account_id: int, limit: int) -> List[Any]:
    """
    Return leads eligible for outreach video for a given campaign.

    Criteria:
    - sequence_step=2 EmailOutreach exists (second follow-up sent)
    - No replied_at on any EmailOutreach for this lead in the campaign
    - open_count >= 1 on at least one EmailOutreach row
    - Lead.fit_score >= OUTREACH_VIDEO_FIT_SCORE_MIN
    - No existing OutreachVideo for (account_id, lead_id)
    """
    fit_min = int(os.getenv("OUTREACH_VIDEO_FIT_SCORE_MIN", "7"))

    step2_subq = (
        db.session.query(EmailOutreach.lead_id)
        .filter(
            EmailOutreach.campaign_id == campaign_id,
            EmailOutreach.sequence_step == 2,
        )
        .subquery()
    )

    replied_subq = (
        db.session.query(EmailOutreach.lead_id)
        .filter(
            EmailOutreach.campaign_id == campaign_id,
            EmailOutreach.replied_at.isnot(None),
        )
        .subquery()
    )

    opened_subq = (
        db.session.query(EmailOutreach.lead_id)
        .filter(
            EmailOutreach.campaign_id == campaign_id,
            EmailOutreach.open_count >= 1,
        )
        .subquery()
    )

    if campaign_id is None:
        # No campaign configured — nothing to process
        return []

    has_video_subq = (
        db.session.query(OutreachVideo.lead_id)
        .filter(
            OutreachVideo.account_id == account_id,
            OutreachVideo.lead_id == Lead.id,
        )
        .correlate(Lead)
        .exists()
    )

    leads = (
        db.session.query(Lead)
        .filter(
            Lead.account_id == account_id,
            Lead.id.in_(step2_subq),
            Lead.id.notin_(replied_subq),
            Lead.id.in_(opened_subq),
            ~has_video_subq,
            Lead.fit_score >= fit_min,
        )
        .limit(limit)
        .all()
    )
    return leads


def _run_outreach_script_generation(lead: Any) -> Dict[str, Any]:
    """Fetch fresh intent signals and generate DSPy script for one lead."""
    from src.dspy.config import _configure_dspy
    import dspy
    from src.dspy.signatures import build_outreach_signatures

    company_domain = ""
    if lead.email and "@" in lead.email:
        company_domain = lead.email.split("@")[1]

    intent_signals = "no recent signals found"
    if company_domain:
        try:
            from src.mcp.enrichment_v2_mcp import detect_intent_signals
            result = detect_intent_signals(company_domain=company_domain)
            sigs = result.get("signals", [])
            if sigs:
                intent_signals = "; ".join(
                    s.get("description", "") for s in sigs[:3] if s.get("description")
                ) or "no recent signals found"
        except Exception:
            logger.warning(
                "outreach.queue_videos: intent signal fetch failed for domain %s", company_domain
            )

    recipient_name = (lead.name or "")[:200]
    recipient_company = (lead.company_name or "")[:200]
    industry = (lead.industry or "B2B SaaS")[:100]
    pain_point = f"{industry} companies dealing with inbox overload and missed follow-ups"[:300]

    _configure_dspy()
    sigs = build_outreach_signatures(dspy)
    pred = dspy.Predict(sigs["OutreachVideoScript"])(
        recipient_name=recipient_name,
        recipient_company=recipient_company or "your company",
        industry=industry,
        intent_signals=intent_signals[:500],
        pain_point=pain_point,
    )

    return {
        "script": pred.script,
        "hook_line": pred.hook_line,
        "cta_line": pred.cta_line,
        "subject_line": pred.subject_line,
    }


@shared_task(name="outreach.queue_videos", queue="content")
def queue_outreach_videos() -> Dict[str, Any]:
    if os.getenv("OUTREACH_VIDEO_ENABLED", "false").lower() != "true":
        return {"status": "skipped", "reason": "OUTREACH_VIDEO_ENABLED not set"}

    daily_limit = int(os.getenv("OUTREACH_VIDEO_DAILY_LIMIT", "20"))

    # Resolve the campaign(s) with outreach video enabled.
    # account_id is always sourced from DB objects (campaign or lead) — never user input.
    campaigns = EmailCampaign.query.filter_by(outreach_video_enabled=True).all()

    queued = 0
    errors = 0
    remaining = daily_limit

    for campaign in campaigns:
        if remaining <= 0:
            break

        leads = _get_eligible_leads(campaign.id, campaign.account_id, remaining)

        for lead in leads:
            if remaining <= 0:
                break

            # account_id sourced from the DB lead object — never from user-controlled input
            account_id = lead.account_id

            existing = OutreachVideo.query.filter_by(
                account_id=account_id, lead_id=lead.id
            ).first()
            if existing:
                continue

            try:
                generated = _run_outreach_script_generation(lead)
            except Exception:
                logger.exception(
                    "outreach.queue_videos: DSPy generation failed for lead %s", lead.id
                )
                errors += 1
                continue

            render = VideoRender(
                account_id=account_id,
                programme="outreach",
                video_style="avatar",
                aspect_ratio="16:9",
                script=generated["script"],
                subject_line=generated["subject_line"],
            )
            try:
                db.session.add(render)
                db.session.flush()
                outreach_vid = OutreachVideo(
                    account_id=account_id,
                    video_render_id=render.id,
                    lead_id=lead.id,
                )
                db.session.add(outreach_vid)
                db.session.commit()
            except Exception:
                db.session.rollback()
                logger.exception(
                    "outreach.queue_videos: DB write failed for lead %s", lead.id
                )
                errors += 1
                continue

            avatar_id = os.getenv("HEYGEN_AVATAR_ID", "")
            voice_id = os.getenv("HEYGEN_VOICE_ID", "")

            try:
                heygen_result = heygen_mcp.render_video(
                    script=generated["script"],
                    avatar_id=avatar_id,
                    voice_id=voice_id,
                    video_format="mp4",
                    aspect_ratio="16:9",
                )
            except Exception:
                logger.exception(
                    "outreach.queue_videos: HeyGen submission failed for lead %s", lead.id
                )
                db.session.delete(outreach_vid)
                db.session.delete(render)
                try:
                    db.session.commit()
                except Exception:
                    db.session.rollback()
                errors += 1
                continue

            if heygen_result.get("status") == "submitted":
                job_id = str(heygen_result.get("job_id") or "")[:128]
                if not job_id:
                    logger.error(
                        "outreach.queue_videos: HeyGen returned empty job_id for lead %s", lead.id
                    )
                    db.session.delete(outreach_vid)
                    db.session.delete(render)
                    try:
                        db.session.commit()
                    except Exception:
                        db.session.rollback()
                    errors += 1
                    continue
                render.heygen_job_id = job_id
                render.status = "rendering"
                render.render_submitted_at = datetime.now(timezone.utc)
                try:
                    db.session.commit()
                except Exception:
                    db.session.rollback()
                    logger.exception(
                        "outreach.queue_videos: failed to save HeyGen job_id for lead %s", lead.id
                    )
                    errors += 1
                    continue
                queued += 1
                remaining -= 1
            else:
                logger.error(
                    "outreach.queue_videos: HeyGen non-submitted status for lead %s: %s",
                    lead.id, heygen_result,
                )
                db.session.delete(outreach_vid)
                db.session.delete(render)
                try:
                    db.session.commit()
                except Exception:
                    db.session.rollback()
                errors += 1

    return {"status": "ok", "queued": queued, "errors": errors}
