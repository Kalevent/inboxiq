"""YouTube API endpoints — HeyGen webhook + pipeline UI."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from flask import Blueprint, g, request, jsonify

from src.extensions import db
from src.models.campaigns import YouTubeVideo
from src.settings import login_required_settings
from src.tasks.youtube import generate_scripts, render_videos, publish_videos

logger = logging.getLogger(__name__)
bp = Blueprint("youtube_api", __name__, url_prefix="/api/v1/youtube")

_ALLOWED_TASKS = {"generate_scripts", "render_videos", "publish_videos"}


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
    event_data = data.get("event_data") or {}
    if not isinstance(event_data, dict):
        return jsonify({"error": "invalid event_data"}), 400
    heygen_job_id = event_data.get("video_id") or event_data.get("id")

    if not heygen_job_id:
        return jsonify({"error": "missing video_id"}), 400

    video = db.session.query(YouTubeVideo).filter_by(heygen_job_id=heygen_job_id).first()

    if not video:
        logger.warning("heygen_webhook: unknown job_id %s", heygen_job_id)
        return jsonify({"ok": True}), 200

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


@bp.route("/videos", methods=["GET"])
@login_required_settings
def list_videos():
    """List YouTubeVideo rows for the account, with optional status/type filter."""
    account_id = g.current_account_id
    status_filter = request.args.get("status")
    type_filter = request.args.get("type")

    q = YouTubeVideo.query.filter_by(account_id=account_id)
    if status_filter:
        q = q.filter(YouTubeVideo.status == status_filter)
    if type_filter:
        q = q.filter(YouTubeVideo.video_type == type_filter)
    videos = q.order_by(YouTubeVideo.created_at.desc()).limit(100).all()

    # Resolve pain point text — one extra query, avoids N+1
    from src.models.leads import ICPPainPoint
    pain_point_ids = [v.icp_pain_point_id for v in videos if v.icp_pain_point_id]
    pp_map: dict[str, str] = {}
    if pain_point_ids:
        pp_map = {
            pp.id: pp.pain_point
            for pp in ICPPainPoint.query.filter(ICPPainPoint.id.in_(pain_point_ids)).all()
        }

    return jsonify([{
        "id": v.id,
        "title": v.title or "",
        "video_type": v.video_type,
        "video_style": v.video_style,
        "status": v.status,
        "pain_point": pp_map.get(v.icp_pain_point_id, ""),
        "view_count": v.view_count,
        "click_count": v.click_count,
        "youtube_url": v.youtube_url,
        "published_at": v.published_at.isoformat() if v.published_at else None,
        "created_at": v.created_at.isoformat() if v.created_at else None,
    } for v in videos])


@bp.route("/pain_points", methods=["GET"])
@login_required_settings
def list_pain_points():
    """List active ICPPainPoint rows for the account, ordered by priority."""
    account_id = g.current_account_id
    from src.models.leads import ICPPainPoint
    pain_points = (
        ICPPainPoint.query
        .filter_by(account_id=account_id, active=True)
        .order_by(ICPPainPoint.priority.desc())
        .all()
    )
    return jsonify([{
        "id": pp.id,
        "pain_point": pp.pain_point,
        "consequence": pp.consequence,
        "persona": pp.persona,
        "priority": pp.priority,
        "active": pp.active,
    } for pp in pain_points])


@bp.route("/pain_points", methods=["POST"])
@login_required_settings
def create_pain_point():
    """Create a new ICPPainPoint for the account."""
    account_id = g.current_account_id
    data = request.get_json(silent=True) or {}
    pain_point_text = (data.get("pain_point") or "").strip()
    consequence = (data.get("consequence") or "").strip()
    if not pain_point_text or not consequence:
        return jsonify({"status": "error", "error": "pain_point and consequence are required"}), 400

    from src.models.leads import ICPPainPoint
    from src.models.marketing import ICPConfig

    icp_config = ICPConfig.query.filter_by(account_id=account_id).first()
    if not icp_config:
        icp_config = ICPConfig(account_id=account_id)
        db.session.add(icp_config)
        try:
            db.session.flush()
        except Exception:
            db.session.rollback()
            return jsonify({"status": "error", "error": "Failed to create ICP config"}), 500

    try:
        priority = int(data.get("priority") or 5)
    except (ValueError, TypeError):
        priority = 5

    pp = ICPPainPoint(
        account_id=account_id,
        icp_config_id=icp_config.id,
        pain_point=pain_point_text,
        consequence=consequence,
        persona=(data.get("persona") or "").strip() or None,
        priority=priority,
        active=True,
    )
    db.session.add(pp)
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        return jsonify({"status": "error", "error": "Database error"}), 500

    return jsonify({"status": "ok", "id": pp.id})


@bp.route("/trigger/<task_name>", methods=["POST"])
@login_required_settings
def trigger_task(task_name: str):
    """Manually trigger a YouTube cadence Celery task."""
    if task_name not in _ALLOWED_TASKS:
        return jsonify({"status": "error", "error": f"Unknown task: {task_name}"}), 400

    account_id = g.current_account_id
    task_map = {
        "generate_scripts": generate_scripts,
        "render_videos": render_videos,
        "publish_videos": publish_videos,
    }
    task_map[task_name].delay(account_id=account_id)
    return jsonify({"status": "queued", "task": task_name})
