"""Per-platform queue for paced social distribution of blogs and YouTube videos."""
from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone
from typing import List

from sqlalchemy.exc import IntegrityError

from src.celery_inboxiq import celery
from src.extensions import db
from src.models.campaigns import (
    SocialDistributionQueueItem, YouTubeVideo,
)
from src.models.content import BlogPost
from src.models.core import InboxConnection
from src.marketing.content_distribution import (
    generate_social_content,
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

    if not post.account_id:
        logger.warning(
            "enqueue_blog_post: post %s has no account_id, skipping (existing rows need backfill)",
            post.id,
        )
        return 0

    content = generate_social_content(post)
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
            db.session.rollback()  # already enqueued (idempotent)
        except Exception:
            db.session.rollback()
            logger.exception(
                "enqueue: per-platform commit failed for %s/%s/%s",
                item.content_type, item.content_id, item.platform,
            )
            # continue — don't kill the whole batch
    return inserted


@celery.task(name="marketing.enqueue_blog_post_async")
def enqueue_blog_post_async(blog_post_id: str) -> int:
    """Async Celery wrapper around enqueue_blog_post for HTTP-handler use."""
    post = db.session.get(BlogPost, blog_post_id)
    if not post:
        logger.warning("enqueue_blog_post_async: blog post %s not found", blog_post_id)
        return 0
    return enqueue_blog_post(post)


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


def enqueue_youtube_video(video: YouTubeVideo, pain_point_text: str = "") -> int:
    """Create one pending queue item per platform for a published YouTube video.

    Idempotent. Returns count of NEW rows inserted.
    """
    if not video.youtube_url:
        logger.warning("enqueue_youtube_video: video %s has no youtube_url", video.id)
        return 0

    if not video.account_id:
        logger.warning("enqueue_youtube_video: video %s has no account_id, skipping", video.id)
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
            caption = f"{video.title or ''}\n\n{video.youtube_url}"

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
            db.session.rollback()  # already enqueued (idempotent)
        except Exception:
            db.session.rollback()
            logger.exception(
                "enqueue: per-platform commit failed for %s/%s/%s",
                item.content_type, item.content_id, item.platform,
            )
            # continue — don't kill the whole batch
    return inserted


# ---------------------------------------------------------------------------
# Daily picker Celery task
# ---------------------------------------------------------------------------

_POSTER_NAMES = {
    "linkedin": "_post_to_linkedin",
    "twitter": "_post_to_twitter",
    "facebook": "_post_to_facebook",
}


def _get_poster(platform: str):
    """Look up the poster function by name at call time so patches take effect."""
    module = sys.modules[__name__]
    return getattr(module, _POSTER_NAMES[platform])

PROVIDER_FOR = {
    "linkedin": "linkedin_social",
    "twitter": "twitter_social",
    "facebook": "facebook_social",
}

MAX_ATTEMPTS = 3


def _accounts_with_social_connections() -> List[int]:
    rows = (
        db.session.query(InboxConnection.account_id)
        .filter(
            InboxConnection.provider.in_(tuple(PROVIDER_FOR.values())),
            InboxConnection.status == "connected",
        )
        .distinct()
        .all()
    )
    return [r[0] for r in rows]


def _account_has_provider(account_id: int, platform: str) -> bool:
    return InboxConnection.query.filter_by(
        account_id=account_id,
        provider=PROVIDER_FOR[platform],
        status="connected",
    ).first() is not None


@celery.task(name="marketing.run_social_distribution_queue")
def run_social_distribution_queue() -> dict:
    """Daily picker: post one pending item per (account, platform)."""
    accounts = _accounts_with_social_connections()
    posted = 0
    failed = 0
    for account_id in accounts:
        for platform in PLATFORMS:
            if not _account_has_provider(account_id, platform):
                continue
            item = (
                SocialDistributionQueueItem.query
                .filter_by(account_id=account_id, platform=platform, status="pending")
                .order_by(SocialDistributionQueueItem.created_at.asc())
                .first()
            )
            if not item:
                continue

            poster = _get_poster(platform)
            try:
                result = poster(item)
            except Exception as exc:
                logger.exception("social poster crashed for %s/%s", account_id, platform)
                result = {"status": "error", "error": str(exc)}

            if result.get("status") == "ok":
                item.attempts = (item.attempts or 0) + 1
                item.status = "posted"
                item.posted_url = result.get("post_url")
                item.posted_at = datetime.now(timezone.utc)
                posted += 1
            elif result.get("status") == "skipped":
                item.status = "skipped"
                item.error = (result.get("reason") or "")[:1024]
                # do NOT increment attempts — skip is a config-not-ready signal, not a failed try
            else:
                item.attempts = (item.attempts or 0) + 1
                err = (result.get("error") or "")[:1024]
                item.error = err
                if item.attempts >= MAX_ATTEMPTS:
                    item.status = "failed"
                    failed += 1

            try:
                db.session.commit()
            except Exception:
                db.session.rollback()
                raise

    return {"status": "ok", "posted": posted, "failed": failed, "accounts": len(accounts)}


# ---------------------------------------------------------------------------
# One-shot backfill Celery task
# ---------------------------------------------------------------------------

@celery.task(name="marketing.backfill_social_distribution")
def backfill_social_distribution() -> dict:
    """One-shot: enqueue every published blog post and YouTube video into the queue.

    Idempotent — relies on the unique (content_type, content_id, platform) constraint.
    """
    blogs_enqueued = 0
    videos_enqueued = 0

    blogs = (
        BlogPost.query
        .filter(BlogPost.status == "published")
        .order_by(BlogPost.published_at.asc())
        .all()
    )
    for post in blogs:
        if enqueue_blog_post(post) > 0:
            blogs_enqueued += 1

    videos = (
        db.session.query(YouTubeVideo)
        .filter(
            YouTubeVideo.status == "published",
            YouTubeVideo.youtube_url.isnot(None),
        )
        .order_by(YouTubeVideo.published_at.asc())
        .all()
    )
    for video in videos:
        if enqueue_youtube_video(video) > 0:
            videos_enqueued += 1

    return {
        "status": "ok",
        "blogs_enqueued": blogs_enqueued,
        "videos_enqueued": videos_enqueued,
    }
