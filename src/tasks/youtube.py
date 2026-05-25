"""
YouTube cadence Celery tasks.

Beat schedule (src/celery_inboxiq.py):
  youtube.generate_scripts   — 1st + 15th of month, 7:00am
  youtube.render_videos      — Daily 7:30am
  youtube.publish_videos     — Daily 8:00am
  youtube.send_digest        — Daily 8:30am
"""
from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional
from uuid import uuid4

from celery import shared_task
from sqlalchemy.sql import func

from src.extensions import db
from src.models.campaigns import YouTubeVideo, VideoRender
from src.models.leads import ICPPainPoint, LeadAttribution
from src.models.content import BlogPost
from src.mcp import heygen_mcp, youtube_mcp
from src.notifications.emails import send_youtube_digest_email

logger = logging.getLogger(__name__)

PRODUCT_NAME = "InboxIQ"
PRODUCT_VALUE_PROPOSITION = (
    "InboxIQ is AI-driven email triage and auto-reply for B2B SaaS support and sales teams. "
    "It clears inboxes 10x faster, drafts replies in your voice, recovers warm leads from missed "
    "replies, surfaces SLA breaches before customers complain publicly, and never sleeps. "
    "Concrete outcomes customers see: hours of agent time saved per week, inbox-zero by Monday, "
    "lead reply rates up, and churn signals caught before renewal."
)

SHORT_CTA = "Link in description. Free to start."


def _ensure_short_cta(script: str) -> str:
    """The cadence skill mandates shorts end with the canonical CTA exactly.
    DSPy frequently puts this in cta_line and omits it from short_script —
    HeyGen only renders the script, so without this enforcement the spoken
    short ends without a CTA and the gate (or the viewer) won't see it.
    """
    s = (script or "").strip()
    if SHORT_CTA.lower() in s.lower():
        return s
    sep = " " if s.endswith((".", "!", "?")) else ". "
    return s + sep + SHORT_CTA


# ── Helpers ─────────────────────────────────────────────────────────────────

def _get_latest_blog_post(account_id: int, offset: int = 0) -> Optional[BlogPost]:
    used_ids = (
        db.session.query(YouTubeVideo.blog_post_id)
        .filter(
            YouTubeVideo.account_id == account_id,
            YouTubeVideo.blog_post_id.isnot(None),
            YouTubeVideo.video_type == "long_form",
        )
        .subquery()
    )
    return (
        db.session.query(BlogPost)
        .filter(
            BlogPost.status == "published",
            ~BlogPost.id.in_(used_ids),
        )
        .order_by(BlogPost.created_at.desc())
        .offset(offset)
        .first()
    )


def _get_top_pain_point(account_id: int) -> Optional[ICPPainPoint]:
    return (
        db.session.query(ICPPainPoint)
        .filter(ICPPainPoint.account_id == account_id, ICPPainPoint.active.is_(True))
        .order_by(ICPPainPoint.priority.desc())
        .first()
    )


def _build_utm_slug(video_type: str, blog_post_title: str) -> str:
    month = datetime.now(timezone.utc).strftime("%b-%Y").lower()
    slug_base = re.sub(r"[^a-z0-9]+", "-", blog_post_title.lower())[:40].strip("-")
    prefix = "yt-long" if video_type == "long_form" else "yt-short"
    slug = f"{prefix}-{slug_base}-{month}"
    if db.session.query(YouTubeVideo).filter_by(utm_slug=slug).first():
        slug = f"{slug}-{str(uuid4())[:4]}"
    return slug


def _run_dspy_script_generation(
    blog_post: BlogPost,
    pain_point: ICPPainPoint,
    video_style: str,
) -> Dict[str, Any]:
    from src.dspy.config import _configure_dspy
    import dspy
    from src.dspy.signatures import build_youtube_signatures

    _configure_dspy(max_tokens=4000, temperature=0.7)
    sigs = build_youtube_signatures(dspy)

    icp_persona = "Head of Support / Founder, B2B SaaS, 10-50 employees, UK/US/Nigeria"

    long_pred = dspy.Predict(sigs["YouTubeLongFormScript"])(
        blog_post_content=blog_post.content_html or "",
        icp_persona=icp_persona,
        pain_point=pain_point.pain_point,
        consequence=pain_point.consequence,
        video_style=video_style,
        product_name=PRODUCT_NAME,
        product_value_proposition=PRODUCT_VALUE_PROPOSITION,
    )

    seo_pred = dspy.Predict(sigs["YouTubeSEOMetadata"])(
        script=long_pred.script,
        pain_point=pain_point.pain_point,
        blog_post_primary_keyword=blog_post.primary_keyword or "",
        video_type="long_form",
        product_name=PRODUCT_NAME,
        product_value_proposition=PRODUCT_VALUE_PROPOSITION,
    )

    # Distinct focus per short so DSPy produces two different videos rather
    # than the same prompt twice. Each angle is a different beat from the
    # long form — the first leans into the pain/cost, the second into the
    # visible outcome after the product fixes it.
    short_focuses = [
        f"the emotional cost of '{pain_point.pain_point}' — make a viewer who feels this pain right now nod hard",
        f"the visible outcome after {PRODUCT_NAME} resolves '{pain_point.pain_point}' — focus on what changes for the viewer's day",
    ]

    short_scripts = []
    for short_focus in short_focuses:
        short_pred = dspy.Predict(sigs["YouTubeShortScript"])(
            long_form_script=long_pred.script,
            pain_point=pain_point.pain_point,
            parent_youtube_url="",
            product_name=PRODUCT_NAME,
            short_focus=short_focus,
        )
        short_seo_pred = dspy.Predict(sigs["YouTubeSEOMetadata"])(
            script=short_pred.short_script,
            pain_point=pain_point.pain_point,
            blog_post_primary_keyword=blog_post.primary_keyword or "",
            video_type="short",
            product_name=PRODUCT_NAME,
            product_value_proposition=PRODUCT_VALUE_PROPOSITION,
        )
        short_tags = short_seo_pred.tags
        if isinstance(short_tags, str):
            try:
                short_tags = json.loads(short_tags)
            except (ValueError, TypeError):
                short_tags = [short_tags]
        short_scripts.append({
            "script": _ensure_short_cta(short_pred.short_script),
            "pattern_interrupt_line": short_pred.pattern_interrupt_line,
            "cta_line": short_pred.cta_line,
            "title": short_seo_pred.title,
            "description": short_seo_pred.description,
            "tags": short_tags,
            "thumbnail_prompt": short_seo_pred.thumbnail_prompt,
        })

    illustration_prompts = None
    if video_style == "illustration":
        illus_pred = dspy.Predict(sigs["YouTubeIllustrationPrompts"])(
            script=long_pred.script,
            pain_point=pain_point.pain_point,
            chapter_markers=long_pred.chapter_markers,
        )
        illustration_prompts = illus_pred.scene_prompts

    return {
        "script": long_pred.script,
        "hook_line": long_pred.hook_line,
        "chapter_markers": long_pred.chapter_markers,
        "cta_line": long_pred.cta_line,
        "illustration_prompts": illustration_prompts,
        "short_scripts": short_scripts,
        "seo": {
            "title": seo_pred.title,
            "description": seo_pred.description,
            "tags": seo_pred.tags,
            "thumbnail_prompt": seo_pred.thumbnail_prompt,
        },
    }


# ── Task 1: Generate Scripts ─────────────────────────────────────────────────

@shared_task(name="youtube.generate_scripts")
def generate_scripts(account_id: int | None = None, video_style: str = "avatar") -> Dict[str, Any]:
    if not account_id:
        logger.error("youtube.generate_scripts called without account_id — set YOUTUBE_ACCOUNT_ID env var")
        return {"status": "error", "reason": "account_id required"}
    blog_post_offset = 0 if video_style == "avatar" else 1
    blog_post = _get_latest_blog_post(account_id, offset=blog_post_offset)
    if not blog_post:
        logger.warning("youtube.generate_scripts: no eligible blog post", extra={"account_id": account_id})
        return {"status": "skipped", "reason": "no eligible blog post"}

    pain_point = _get_top_pain_point(account_id)
    if not pain_point:
        logger.warning("youtube.generate_scripts: no active ICPPainPoint", extra={"account_id": account_id})
        return {"status": "skipped", "reason": "no active ICPPainPoint"}

    try:
        generated = _run_dspy_script_generation(blog_post, pain_point, video_style)
    except Exception:
        logger.exception("youtube.generate_scripts: DSPy generation failed")
        return {"status": "error", "reason": "dspy generation failed"}

    seo = generated["seo"]
    utm_slug = _build_utm_slug("long_form", blog_post.title)
    utm_campaign = utm_slug.replace("yt-long-", "")

    tags = seo["tags"]
    if isinstance(tags, str):
        try:
            tags = json.loads(tags)
        except (ValueError, TypeError):
            tags = [tags]

    raw_illus = generated.get("illustration_prompts")
    if isinstance(raw_illus, list):
        illus = raw_illus
    elif raw_illus:
        try:
            illus = json.loads(raw_illus)
        except (ValueError, TypeError):
            illus = None
    else:
        illus = None

    long_render = VideoRender(
        account_id=account_id,
        programme="youtube",
        video_style=video_style,
        aspect_ratio="16:9",
        script=generated["script"],
        illustration_prompts=illus,
    )
    try:
        db.session.add(long_render)
        db.session.flush()
    except Exception:
        db.session.rollback()
        raise

    long_form = YouTubeVideo(
        account_id=account_id,
        blog_post_id=blog_post.id,
        icp_pain_point_id=pain_point.id,
        video_type="long_form",
        video_style=video_style,
        video_render_id=long_render.id,
        script=generated["script"],
        title=seo["title"],
        description=seo["description"],
        tags=tags,
        thumbnail_prompt=seo["thumbnail_prompt"],
        utm_slug=utm_slug,
        utm_medium="long_form",
        utm_campaign=utm_campaign,
        status="script_ready",
        script_generated_at=datetime.now(timezone.utc),
    )

    try:
        db.session.add(long_form)
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise

    shorts_created = 0
    for i, short_data in enumerate(generated["short_scripts"]):
        short_slug = _build_utm_slug("short", f"{blog_post.title}-{i+1}")
        short_render = VideoRender(
            account_id=account_id,
            programme="youtube",
            video_style=video_style,
            aspect_ratio="9:16",
            script=short_data["script"],
        )
        try:
            db.session.add(short_render)
            db.session.flush()
        except Exception:
            db.session.rollback()
            logger.exception("youtube.generate_scripts: failed to flush short render %d", i)
            continue

        short = YouTubeVideo(
            account_id=account_id,
            blog_post_id=blog_post.id,
            icp_pain_point_id=pain_point.id,
            parent_video_id=long_form.id,
            video_type="short",
            video_style=video_style,
            video_render_id=short_render.id,
            script=short_data["script"],
            title=short_data.get("title"),
            description=short_data.get("description"),
            tags=short_data.get("tags"),
            thumbnail_prompt=short_data.get("thumbnail_prompt"),
            utm_slug=short_slug,
            utm_medium="short",
            utm_campaign=short_slug.replace("yt-short-", ""),
            status="script_ready",
            script_generated_at=datetime.now(timezone.utc),
        )
        try:
            db.session.add(short)
            db.session.commit()
            shorts_created += 1
        except Exception:
            db.session.rollback()
            logger.exception("youtube.generate_scripts: failed to save short %d", i)

    return {"status": "ok", "long_form_created": True, "shorts_created": shorts_created}


# ── Task 2: Render Videos ────────────────────────────────────────────────────

def _script_passes_quality_gate(script: str) -> tuple[bool, str]:
    """Pre-HeyGen validation. Each render costs money, so reject scripts that
    violate the cadence skill's hard rules before submission.

    Long form scripts speak the CTA inline ("Start free at kalevent.com").
    Shorts point at the description ("Link in description. Free to start.")
    per the cadence skill — the spoken short does NOT name the domain.

    Returns (ok, reason). reason is empty when ok=True.
    """
    text = (script or "").lower()
    has_cta = "kalevent.com" in text or "link in description" in text
    if not has_cta:
        return False, "script CTA must reference kalevent.com or 'link in description'"
    # Strip CTA URL before checking product mention so a script that ONLY
    # references the URL (without naming the product) still fails the gate.
    body = text.replace("kalevent.com", "")
    if PRODUCT_NAME.lower() not in body:
        return False, f"script does not name {PRODUCT_NAME} outside the CTA URL"
    return True, ""


def _generate_dalle_frames(prompts: list, account_id: int) -> list:
    """Generate DALL-E 3 illustration frames and upload to S3 via uploads.py."""
    import openai
    import requests as http_requests
    from src.uploads import upload_bytes, build_public_url

    client = openai.OpenAI()
    urls = []
    for i, prompt in enumerate(prompts):
        try:
            response = client.images.generate(
                model="dall-e-3",
                prompt=prompt,
                size="1792x1024",
                quality="standard",
                n=1,
            )
            image_url = response.data[0].url
            from src.mcp.enrichment_v2_mcp import _safe_external_url
            img_bytes = http_requests.get(_safe_external_url(image_url), timeout=30).content
            key = f"youtube/frames/{account_id}/{uuid4()}.png"
            upload_bytes(key, img_bytes, "image/png", "attachment")
            urls.append(build_public_url(key))
        except Exception:
            logger.exception("youtube.render_videos: DALL-E frame %d failed", i)
    return urls


@shared_task(name="youtube.render_videos")
def render_videos(account_id: int | None = None) -> Dict[str, Any]:
    if not account_id:
        logger.error("youtube.render_videos called without account_id — set YOUTUBE_ACCOUNT_ID env var")
        return {"status": "error", "reason": "account_id required"}
    avatar_id = os.getenv("HEYGEN_AVATAR_ID", "")
    voice_id = os.getenv("HEYGEN_VOICE_ID", "")
    submitted = 0
    failed = 0

    rows = (
        db.session.query(YouTubeVideo, VideoRender)
        .join(VideoRender, YouTubeVideo.video_render_id == VideoRender.id)
        .filter(
            YouTubeVideo.account_id == account_id,
            YouTubeVideo.status.in_(["script_ready", "illustration_ready"]),
        )
        .all()
    )

    for video, render in rows:
        try:
            ok, reason = _script_passes_quality_gate(render.script or "")
            if not ok:
                logger.warning(
                    "youtube.render_videos: quality gate rejected video %s: %s",
                    video.id, reason,
                )
                video.status = "failed"
                render.status = "failed"
                try:
                    db.session.commit()
                except Exception:
                    db.session.rollback()
                failed += 1
                continue

            if video.video_style == "illustration" and video.status == "script_ready":
                prompts = render.illustration_prompts or []
                if not prompts:
                    logger.warning("youtube.render_videos: no illustration_prompts for %s", video.id)
                    continue
                frame_urls = _generate_dalle_frames(prompts, account_id)
                if len(frame_urls) < 2:
                    logger.error("youtube.render_videos: DALL-E mostly failed for %s", video.id)
                    failed += 1
                    continue
                render.dalle_frame_urls = frame_urls
                video.status = "illustration_ready"
                try:
                    db.session.commit()
                except Exception:
                    db.session.rollback()
                    raise

            if video.video_style == "illustration" and render.dalle_frame_urls:
                result = heygen_mcp.render_illustration_video(
                    script=render.script or "",
                    voice_id=voice_id,
                    frame_urls=render.dalle_frame_urls,
                    aspect_ratio=render.aspect_ratio,
                )
            else:
                result = heygen_mcp.render_video(
                    script=render.script or "",
                    avatar_id=avatar_id,
                    voice_id=voice_id,
                    video_format="mp4",
                    aspect_ratio=render.aspect_ratio,
                )

            if result["status"] == "submitted":
                render.heygen_job_id = result["job_id"]
                render.status = "rendering"
                render.render_submitted_at = datetime.now(timezone.utc)
                video.status = "rendering"
                try:
                    db.session.commit()
                except Exception:
                    db.session.rollback()
                    raise
                submitted += 1
            else:
                logger.error("youtube.render_videos: HeyGen submit failed for %s: %s", video.id, result.get("error"))
                failed += 1
        except Exception:
            db.session.rollback()
            logger.exception("youtube.render_videos: error on video %s", video.id)
            failed += 1

    # Fallback poll for renders stuck >30 min (webhook is primary signal)
    stale_cutoff = datetime.now(timezone.utc) - timedelta(minutes=30)
    stale_rows = (
        db.session.query(YouTubeVideo, VideoRender)
        .join(VideoRender, YouTubeVideo.video_render_id == VideoRender.id)
        .filter(
            YouTubeVideo.account_id == account_id,
            VideoRender.status == "rendering",
            VideoRender.render_submitted_at < stale_cutoff,
        )
        .all()
    )
    for video, render in stale_rows:
        if not render.heygen_job_id:
            continue
        poll = heygen_mcp.get_render_status(render.heygen_job_id)
        if poll["status"] == "completed":
            render.heygen_render_url = poll["render_url"]
            render.status = "render_complete"
            render.render_completed_at = datetime.now(timezone.utc)
            video.status = "render_complete"
            try:
                db.session.commit()
            except Exception:
                db.session.rollback()
        elif poll["status"] == "failed":
            render.status = "failed"
            video.status = "failed"
            try:
                db.session.commit()
            except Exception:
                db.session.rollback()

    return {"status": "ok", "submitted": submitted, "failed": failed}


# ── Task 3: Publish Videos ───────────────────────────────────────────────────

@shared_task(name="youtube.publish_videos")
def publish_videos(account_id: int | None = None) -> Dict[str, Any]:
    if not account_id:
        logger.error("youtube.publish_videos called without account_id — set YOUTUBE_ACCOUNT_ID env var")
        return {"status": "error", "reason": "account_id required"}
    base_url = "https://kalevent.com/signup"
    published = 0
    failed = 0

    rows = (
        db.session.query(YouTubeVideo, VideoRender)
        .join(VideoRender, YouTubeVideo.video_render_id == VideoRender.id)
        .filter(
            YouTubeVideo.account_id == account_id,
            VideoRender.status == "render_complete",
        )
        .all()
    )

    for video, render in rows:
        try:
            utm_url = (
                f"{base_url}?utm_source=youtube"
                f"&utm_medium={video.utm_medium}"
                f"&utm_campaign={video.utm_campaign}"
            )
            description = (video.description or "").replace("{{UTM_LINK}}", utm_url)

            # The webhook stores HeyGen's gif preview URL (event_data.video_url
            # is the gif, not the mp4). Re-fetch via /v1/video_status.get to
            # get the signed mp4 URL — also handles signed URL expiry by
            # always pulling a fresh one at upload time.
            if not render.heygen_job_id:
                logger.error("youtube.publish_videos: render %s missing heygen_job_id", render.id)
                video.status = "failed"
                try:
                    db.session.commit()
                except Exception:
                    db.session.rollback()
                failed += 1
                continue

            poll = heygen_mcp.get_render_status(render.heygen_job_id)
            if poll.get("status") != "completed" or not poll.get("render_url"):
                logger.error(
                    "youtube.publish_videos: HeyGen status %r for job %s, marking failed",
                    poll.get("status"), render.heygen_job_id,
                )
                video.status = "failed"
                try:
                    db.session.commit()
                except Exception:
                    db.session.rollback()
                failed += 1
                continue
            mp4_url = poll["render_url"]

            video.status = "publishing"
            try:
                db.session.commit()
            except Exception:
                db.session.rollback()
                raise

            result = youtube_mcp.upload_video(
                file_url=mp4_url,
                title=video.title or "",
                description=description,
                tags=video.tags or [],
                category_id="28",
            )

            if result["status"] != "published":
                video.status = "failed"
                try:
                    db.session.commit()
                except Exception:
                    db.session.rollback()
                failed += 1
                continue

            video.youtube_video_id = result["youtube_video_id"]
            video.youtube_url = result["youtube_url"]
            video.description = description

            if video.video_type == "long_form":
                youtube_mcp.add_end_screen(video.youtube_video_id, utm_url)
                youtube_mcp.add_card(video.youtube_video_id, utm_url, offset_ms=360000)
                pinned = f"Start free → {utm_url}"
            else:
                parent = db.session.get(YouTubeVideo, video.parent_video_id) if video.parent_video_id else None
                parent_url = parent.youtube_url if parent and parent.youtube_url else "https://www.youtube.com/@inboxiq"
                pinned = f"Full video → {parent_url}"

            youtube_mcp.post_pinned_comment(video.youtube_video_id, pinned)

            video.status = "published"
            video.published_at = datetime.now(timezone.utc)
            render.status = "delivered"
            try:
                db.session.commit()
            except Exception:
                db.session.rollback()
                raise
            published += 1

            # After successful YouTube upload, enqueue 1 row per social platform.
            try:
                from src.marketing.social_distribution import enqueue_youtube_video
                pain_point_text = ""
                if video.icp_pain_point_id:
                    pp = db.session.get(ICPPainPoint, video.icp_pain_point_id)
                    if pp:
                        pain_point_text = pp.pain_point or ""
                enqueue_youtube_video(video, pain_point_text=pain_point_text)
            except Exception:
                logger.exception(
                    "youtube.publish_videos: enqueue social distribution failed video=%s account=%s",
                    video.id, video.account_id,
                )

        except Exception:
            db.session.rollback()
            logger.exception("youtube.publish_videos: error on video %s", video.id)
            try:
                video.status = "failed"
                db.session.commit()
            except Exception:
                db.session.rollback()
            failed += 1

    return {"status": "ok", "published": published, "failed": failed}


# ── Task 4: Send Digest ──────────────────────────────────────────────────────

@shared_task(name="youtube.send_digest")
def send_digest(account_id: int | None = None) -> Dict[str, Any]:
    """Daily 8:30am. Email admin: published this week, pipeline status, funnel attribution."""
    if not account_id:
        logger.error("youtube.send_digest called without account_id — set YOUTUBE_ACCOUNT_ID env var")
        return {"status": "error", "reason": "account_id required"}
    admin_email = os.getenv("ADMIN_EMAILS", "").split(",")[0].strip()
    if not admin_email:
        return {"status": "skipped", "reason": "no ADMIN_EMAILS configured"}

    week_ago = datetime.now(timezone.utc) - timedelta(days=7)

    published = (
        db.session.query(YouTubeVideo)
        .filter(
            YouTubeVideo.account_id == account_id,
            YouTubeVideo.status == "published",
            YouTubeVideo.published_at >= week_ago,
        )
        .all()
    )

    # Refresh view + click counts
    for video in published:
        if video.youtube_video_id:
            stats = youtube_mcp.get_video_stats(video.youtube_video_id)
            if stats["status"] == "ok":
                video.view_count = stats["view_count"]
        attribution_count = (
            db.session.query(func.count(LeadAttribution.id))
            .filter(LeadAttribution.campaign == video.utm_campaign)
            .scalar()
        ) or 0
        video.click_count = attribution_count
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()

    published_data = [
        {"title": v.title or v.id, "type": v.video_type, "views": v.view_count,
         "clicks": v.click_count, "url": v.youtube_url or ""}
        for v in published
    ]

    pipeline_rows = (
        db.session.query(YouTubeVideo, VideoRender)
        .join(VideoRender, YouTubeVideo.video_render_id == VideoRender.id)
        .filter(
            YouTubeVideo.account_id == account_id,
            YouTubeVideo.status.notin_(["published", "failed"]),
        )
        .all()
    )

    # Flag stale renders (>24h)
    stale_cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    for video, render in pipeline_rows:
        submitted_at = render.render_submitted_at
        if submitted_at is not None and submitted_at.tzinfo is None:
            submitted_at = submitted_at.replace(tzinfo=timezone.utc)
        if render.status == "rendering" and submitted_at and submitted_at < stale_cutoff:
            render.status = "failed"
            video.status = "failed"
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()

    pipeline_data = [
        {"id": v.id, "title": v.title, "status": v.status, "type": v.video_type}
        for v, _ in pipeline_rows
    ]

    youtube_visitors = (
        db.session.query(func.count(LeadAttribution.id))
        .filter(
            LeadAttribution.source == "youtube",
            LeadAttribution.created_at >= week_ago,
        )
        .scalar()
    ) or 0

    # YouTube trial attribution via LeadAttribution source + Lead join
    from src.models.leads import Lead
    youtube_trials = (
        db.session.query(func.count(Lead.id))
        .filter(
            Lead.utm_source == "youtube",
            Lead.created_at >= week_ago,
        )
        .scalar()
    ) or 0

    send_youtube_digest_email(
        to_email=admin_email,
        published_this_week=published_data,
        pipeline_status=pipeline_data,
        youtube_visitors=youtube_visitors,
        youtube_trials=youtube_trials,
    )

    return {"status": "ok", "published": len(published_data), "pipeline": len(pipeline_data)}
