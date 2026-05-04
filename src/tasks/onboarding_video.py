"""Onboarding video Celery tasks."""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict

from celery import shared_task

from src.extensions import db
from src.models.campaigns import VideoRender, OnboardingVideo
from src.models.core import Account, User
from src.mcp import heygen_mcp

logger = logging.getLogger(__name__)


def _run_onboarding_script_generation(
    recipient_name: str,
    recipient_company: str,
    referral_source: str,
) -> Dict[str, Any]:
    from src.dspy.config import _configure_dspy
    import dspy
    from src.dspy.signatures import build_onboarding_signatures

    _configure_dspy()
    sigs = build_onboarding_signatures(dspy)

    pred = dspy.Predict(sigs["OnboardingVideoScript"])(
        recipient_name=recipient_name,
        recipient_company=recipient_company or "your company",
        referral_source=referral_source or "us",
    )

    return {
        "script": pred.script,
        "hook_line": pred.hook_line,
        "cta_line": pred.cta_line,
    }


@shared_task(name="onboarding.queue_video")
def queue_onboarding_video(account_id: int, user_id: int) -> Dict[str, Any]:
    existing = OnboardingVideo.query.filter_by(account_id=account_id).first()
    if existing:
        logger.info("onboarding.queue_video: already exists for account %s", account_id)
        return {"status": "skipped", "reason": "already exists"}

    account = Account.query.get(account_id)
    if not account:
        logger.warning(
            "onboarding.queue_video: account not found account=%s",
            account_id,
        )
        return {"status": "skipped", "reason": "account or user not found"}

    user = User.query.get(user_id)
    if not user:
        logger.warning(
            "onboarding.queue_video: user not found account=%s user=%s",
            account_id, user_id,
        )
        return {"status": "skipped", "reason": "account or user not found"}

    if user.account_id != account_id:
        logger.warning(
            "onboarding.queue_video: user %s does not belong to account %s",
            user_id, account_id,
        )
        return {"status": "skipped", "reason": "user does not belong to account"}

    recipient_name = (user.name or user.email.split("@")[0])[:200]
    recipient_company = (account.name or "")[:200]
    referral_source = (account.referral_source or "")[:128]

    try:
        generated = _run_onboarding_script_generation(recipient_name, recipient_company, referral_source)
    except Exception:
        logger.exception("onboarding.queue_video: DSPy generation failed for account %s", account_id)
        return {"status": "error", "reason": "dspy generation failed"}

    render = VideoRender(
        account_id=account_id,
        programme="onboarding",
        video_style="avatar",
        aspect_ratio="16:9",
        script=generated["script"],
    )
    try:
        db.session.add(render)
        db.session.flush()
        onboarding = OnboardingVideo(
            account_id=account_id,
            video_render_id=render.id,
            recipient_user_id=user_id,
            recipient_name=recipient_name,
            recipient_company=recipient_company or None,
        )
        db.session.add(onboarding)
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise

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
            "onboarding.queue_video: HeyGen submission failed for account %s", account_id
        )
        return {"status": "error", "reason": "heygen submission failed"}

    if heygen_result.get("status") == "submitted":
        job_id = str(heygen_result.get("job_id") or "")[:128]
        if not job_id:
            logger.error("onboarding.queue_video: HeyGen returned empty job_id for account %s", account_id)
            return {"status": "error", "reason": "heygen returned empty job_id"}
        render.heygen_job_id = job_id
        render.status = "rendering"
        render.render_submitted_at = datetime.now(timezone.utc)
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise
        return {"status": "ok", "render_id": render.id}

    logger.error(
        "onboarding.queue_video: HeyGen non-submitted status for account %s: %s",
        account_id, heygen_result,
    )
    return {"status": "error", "reason": "heygen did not accept submission"}
