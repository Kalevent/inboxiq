"""Per-platform queue for paced social distribution of blogs and YouTube videos."""
from __future__ import annotations

import logging
from typing import Optional, List

from sqlalchemy.exc import IntegrityError

from src.celery_inboxiq import celery
from src.extensions import db
from src.models.campaigns import (
    SocialDistributionQueueItem, YouTubeVideo, VideoRender,
)
from src.models.content import BlogPost
from src.models.core import InboxConnection
from src.marketing.content_distribution import (
    _generate_social_content,
    _post_to_linkedin,
    _post_to_twitter,
    _post_to_facebook,
)

logger = logging.getLogger(__name__)

PLATFORMS = ("linkedin", "twitter", "facebook")


def _compose_caption(text: str, hashtags: str) -> str:
    text = (text or "").strip()
    hashtags = (hashtags or "").strip()
    return f"{text}\n\n{hashtags}".strip() if hashtags else text


def enqueue_blog_post(post: BlogPost) -> int:
    """Create one pending queue item per platform for a published blog post.

    Idempotent — existing rows for (content_type='blog', content_id=post.id, platform) are skipped.
    Returns the number of NEW rows inserted.
    """
    if not post.canonical_url:
        logger.warning("enqueue_blog_post: post %s has no canonical_url, skipping", post.id)
        return 0

    content = _generate_social_content(post)
    inserted = 0
    for platform in PLATFORMS:
        per = content.get(platform) or {}
        caption = _compose_caption(per.get("text", ""), per.get("hashtags", ""))
        if not caption:
            continue
        item = SocialDistributionQueueItem(
            account_id=post.account_id,
            content_type="blog",
            content_id=post.id,
            platform=platform,
            caption=caption,
            target_url=post.canonical_url,
        )
        db.session.add(item)
        try:
            db.session.commit()
            inserted += 1
        except IntegrityError:
            db.session.rollback()  # already enqueued
    return inserted


def _generate_video_caption(*, title: str, video_type: str, pain_point_text: str,
                             youtube_url: str, platform: str):
    """DSPy-backed video caption generator. Returns a Prediction with caption_text + hashtags."""
    import dspy
    from src.dspy.signatures import build_youtube_video_social_caption
    from src.dspy.triage_config import _configure_dspy

    _configure_dspy()
    sigs = build_youtube_video_social_caption(dspy)
    predictor = dspy.Predict(sigs["YouTubeVideoSocialCaption"])
    return predictor(
        title=title,
        video_type=video_type,
        pain_point_text=pain_point_text,
        youtube_url=youtube_url,
        platform=platform,
    )


def enqueue_youtube_video(video: YouTubeVideo, render: VideoRender,
                          pain_point_text: str = "") -> int:
    """Create one pending queue item per platform for a published YouTube video.

    Idempotent. Returns count of NEW rows inserted.
    """
    if not video.youtube_url:
        logger.warning("enqueue_youtube_video: video %s has no youtube_url", video.id)
        return 0

    inserted = 0
    for platform in PLATFORMS:
        try:
            pred = _generate_video_caption(
                title=video.title or "",
                video_type=video.video_type or "short",
                pain_point_text=pain_point_text,
                youtube_url=video.youtube_url,
                platform=platform,
            )
            caption = _compose_caption(pred.caption_text, pred.hashtags)
        except Exception:
            logger.exception("video caption generation failed for %s/%s", video.id, platform)
            caption = f"{video.title}\n\n{video.youtube_url}"

        if not caption:
            continue
        item = SocialDistributionQueueItem(
            account_id=video.account_id,
            content_type="video",
            content_id=video.id,
            platform=platform,
            caption=caption,
            target_url=video.youtube_url,
        )
        db.session.add(item)
        try:
            db.session.commit()
            inserted += 1
        except IntegrityError:
            db.session.rollback()
    return inserted
