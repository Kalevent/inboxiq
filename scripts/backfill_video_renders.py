#!/usr/bin/env python
"""One-shot backfill: create VideoRender records for all existing YouTubeVideo rows."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.app import create_app
from src.extensions import db
from src.models.campaigns import YouTubeVideo, VideoRender

app = create_app()

with app.app_context():
    videos = (
        db.session.query(YouTubeVideo)
        .filter(YouTubeVideo.video_render_id.is_(None))
        .all()
    )
    print(f"Backfilling {len(videos)} YouTubeVideo rows...")

    created = 0
    for video in videos:
        if video.youtube_video_id:
            render_status = "delivered"
        elif video.heygen_render_url:
            render_status = "render_complete"
        elif video.heygen_job_id and video.status == "rendering":
            render_status = "rendering"
        else:
            render_status = "pending"

        aspect_ratio = "16:9" if video.video_type == "long_form" else "9:16"

        render = VideoRender(
            account_id=video.account_id,
            programme="youtube",
            video_style=video.video_style,
            aspect_ratio=aspect_ratio,
            script=video.script,
            illustration_prompts=video.illustration_prompts,
            dalle_frame_urls=video.dalle_frame_urls,
            heygen_job_id=video.heygen_job_id,
            heygen_render_url=video.heygen_render_url,
            status=render_status,
            render_submitted_at=video.render_submitted_at,
            render_completed_at=video.render_completed_at,
            created_at=video.created_at,
        )
        db.session.add(render)
        db.session.flush()
        video.video_render_id = render.id
        created += 1

    try:
        db.session.commit()
        print(f"Done. Created {created} VideoRender records.")
    except Exception as e:
        db.session.rollback()
        print(f"Error: {e}")
        sys.exit(1)
