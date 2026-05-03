"""Generic HeyGen webhook — programme-agnostic render completion handler."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from flask import Blueprint, request, jsonify

from src.extensions import db
from src.models.campaigns import VideoRender

logger = logging.getLogger(__name__)
bp = Blueprint("heygen_api", __name__, url_prefix="/api/v1/heygen")


@bp.route("/webhook", methods=["POST"])
def heygen_webhook():
    data = request.get_json(silent=True) or {}
    event_data = data.get("event_data") or {}
    if not isinstance(event_data, dict):
        return jsonify({"error": "invalid event_data"}), 400

    heygen_job_id = event_data.get("video_id") or event_data.get("id")
    if not heygen_job_id:
        return jsonify({"error": "missing video_id"}), 400

    render = VideoRender.query.filter_by(heygen_job_id=heygen_job_id).first()
    if not render:
        logger.warning("heygen_webhook: unknown job_id %s", heygen_job_id)
        return jsonify({"ok": True}), 200

    event_type = data.get("event_type", "")
    if "success" in event_type or "complete" in event_type:
        render.heygen_render_url = event_data.get("video_url") or event_data.get("url")
        render.status = "render_complete"
        render.render_completed_at = datetime.now(timezone.utc)
    elif "fail" in event_type or "error" in event_type:
        render.status = "failed"

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise

    return jsonify({"ok": True}), 200
