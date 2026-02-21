"""
Admin API endpoints for nurture campaign and A/B test visibility.

Provides:
- GET /api/v1/admin/marketing/ab-results   — per-step A/B test evaluation
- GET /api/v1/admin/marketing/nurture-stats — aggregate send stats by campaign/variant/vertical
"""
from datetime import datetime, timezone

from flask import jsonify, request, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity

from src.api.v1 import v1
from src.extensions import db
from src.models import NurtureEmailSend, User
import logging

logger = logging.getLogger(__name__)


def _require_admin():
    """Check if user is admin based on email allowlist."""
    user_id = get_jwt_identity()
    user = db.session.get(User, user_id) if user_id else None
    default_admin = "support@kalevent.com"
    allowed = set(
        e.strip().lower()
        for e in (current_app.config.get("ADMIN_EMAILS", "") or default_admin).split(",")
        if e.strip()
    )
    if not user or (allowed and user.email.lower() not in allowed):
        return None
    return user


@v1.route("/admin/marketing/ab-results", methods=["GET"])
@jwt_required()
def get_ab_test_results():
    """
    Get live A/B test evaluation for all nurture campaign steps.

    Query params:
        lookback_days: Days to look back (default: 30)

    Returns:
        {
            "steps": [{
                "key": "discovery:day1",
                "campaign_type": "discovery",
                "sequence_day": 1,
                "winner": "A" | "B" | "inconclusive",
                "reason": "...",
                "variant_a": {"sends": N, "opens": N, "open_rate": N},
                "variant_b": {"sends": N, "opens": N, "open_rate": N},
                "z_score": N,
                "p_value": N,
                "lift_pct": N
            }],
            "lookback_days": int,
            "evaluated_at": ISO timestamp
        }
    """
    if not _require_admin():
        return jsonify({"error": "forbidden"}), 403

    try:
        lookback_days = int(request.args.get("lookback_days", 30))
    except (ValueError, TypeError):
        return jsonify({"error": "lookback_days must be an integer"}), 400

    try:
        from src.marketing.ab_testing import _evaluate_step

        steps = [
            ("discovery", 1),
            ("discovery", 3),
            ("discovery", 7),
            ("discovery", 14),
            ("discovery", 21),
            ("consideration", 1),
            ("consideration", 3),
            ("consideration", 7),
            ("consideration", 14),
        ]

        results = []
        for campaign_type, day in steps:
            result = _evaluate_step(campaign_type, day, lookback_days)
            result["key"] = f"{campaign_type}:day{day}"
            results.append(result)

        return jsonify({
            "steps": results,
            "lookback_days": lookback_days,
            "evaluated_at": datetime.now(timezone.utc).isoformat(),
        }), 200

    except Exception as exc:
        logger.exception("Failed to get A/B results: %s", exc)
        return jsonify({"error": str(exc)}), 500


@v1.route("/admin/marketing/nurture-stats", methods=["GET"])
@jwt_required()
def get_nurture_stats():
    """
    Get aggregate nurture send statistics.

    Returns:
        {
            "total_sends": int,
            "total_opens": int,
            "overall_open_rate": float,
            "by_campaign": {
                "discovery": {"sends": N, "opens": N, "open_rate": N},
                "consideration": {...}
            },
            "by_vertical": {"b2b_saas": N, ...},
            "by_variant": {
                "A": {"sends": N, "opens": N, "open_rate": N},
                "B": {...}
            }
        }
    """
    if not _require_admin():
        return jsonify({"error": "forbidden"}), 403

    try:
        total = db.session.query(
            db.func.count().label("sends"),
            db.func.sum(db.cast(NurtureEmailSend.opened, db.Integer)).label("opens"),
        ).filter(
            NurtureEmailSend.ab_variant.in_(["A", "B"]),
        ).one()

        total_sends = total.sends or 0
        total_opens = int(total.opens or 0)

        by_campaign_rows = db.session.query(
            NurtureEmailSend.campaign_type,
            db.func.count().label("sends"),
            db.func.sum(db.cast(NurtureEmailSend.opened, db.Integer)).label("opens"),
        ).filter(
            NurtureEmailSend.ab_variant.in_(["A", "B"]),
        ).group_by(NurtureEmailSend.campaign_type).all()

        by_campaign = {}
        for row in by_campaign_rows:
            sends = row.sends or 0
            opens = int(row.opens or 0)
            by_campaign[row.campaign_type] = {
                "sends": sends,
                "opens": opens,
                "open_rate": round(opens / sends, 4) if sends else 0,
            }

        sends_col = db.func.count().label("sends")
        by_vertical_rows = db.session.query(
            NurtureEmailSend.vertical,
            sends_col,
        ).filter(
            NurtureEmailSend.ab_variant.in_(["A", "B"]),
            NurtureEmailSend.vertical.isnot(None),
        ).group_by(NurtureEmailSend.vertical).order_by(db.desc(sends_col)).limit(10).all()

        by_vertical = {row.vertical: row.sends for row in by_vertical_rows}

        by_variant_rows = db.session.query(
            NurtureEmailSend.ab_variant,
            db.func.count().label("sends"),
            db.func.sum(db.cast(NurtureEmailSend.opened, db.Integer)).label("opens"),
        ).filter(
            NurtureEmailSend.ab_variant.in_(["A", "B"]),
        ).group_by(NurtureEmailSend.ab_variant).all()

        by_variant = {}
        for row in by_variant_rows:
            sends = row.sends or 0
            opens = int(row.opens or 0)
            by_variant[row.ab_variant] = {
                "sends": sends,
                "opens": opens,
                "open_rate": round(opens / sends, 4) if sends else 0,
            }

        return jsonify({
            "total_sends": total_sends,
            "total_opens": total_opens,
            "overall_open_rate": round(total_opens / total_sends, 4) if total_sends else 0,
            "by_campaign": by_campaign,
            "by_vertical": by_vertical,
            "by_variant": by_variant,
        }), 200

    except Exception as exc:
        logger.exception("Failed to get nurture stats: %s", exc)
        return jsonify({"error": str(exc)}), 500
