"""Onboarding API endpoints."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity

from src.extensions import db
from src.models.campaigns import OnboardingVideo

logger = logging.getLogger(__name__)
bp = Blueprint("onboarding_api", __name__, url_prefix="/api/v1/onboarding")


@bp.route("/dismiss-video-banner", methods=["POST"])
@jwt_required()
def dismiss_video_banner():
    account_id = get_jwt_identity()
    onboarding = OnboardingVideo.query.filter_by(account_id=account_id).first()
    if not onboarding:
        return jsonify({"ok": True}), 200

    onboarding.banner_dismissed_at = datetime.now(timezone.utc)
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise

    return jsonify({"ok": True}), 200
