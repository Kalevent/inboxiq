"""YouTube API endpoints — HeyGen webhook."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from flask import Blueprint, request, jsonify

from src.extensions import db
from src.models.campaigns import YouTubeVideo

logger = logging.getLogger(__name__)
bp = Blueprint("youtube_api", __name__, url_prefix="/api/v1/youtube")


@bp.route("/heygen/webhook", methods=["POST"])
def heygen_webhook():
    """
    HeyGen render-complete callback.
    Payload: {"event_type": "avatar_video.success"|"avatar_video.fail",
              "event_data": {"video_id": "...", "video_url": "..."}}
    No auth required from HeyGen. We validate by job_id lookup in DB.
    """
    data = request.get_json(silent=True) or {}
    event_type = data.get("event_type", "")
    event_data = data.get("event_data", {})
    heygen_job_id = event_data.get("video_id") or event_data.get("id")

    if not heygen_job_id:
        return jsonify({"error": "missing video_id"}), 400

    video = db.session.query(YouTubeVideo).filter_by(heygen_job_id=heygen_job_id).first()

    if not video:
        logger.warning("heygen_webhook: unknown job_id %s", heygen_job_id)
        return jsonify({"ok": True}), 200  # ACK without leaking DB info

    if "success" in event_type or "complete" in event_type:
        video.heygen_render_url = event_data.get("video_url") or event_data.get("url")
        video.status = "render_complete"
        video.render_completed_at = datetime.now(timezone.utc)
    elif "fail" in event_type or "error" in event_type:
        video.status = "failed"

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise

    return jsonify({"ok": True}), 200
