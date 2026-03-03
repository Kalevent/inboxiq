"""
Admin API endpoints for customer insights and feature requests.

Provides metrics and insights about:
- Feature requests from customers
- Pain points analysis
- Use case patterns
- Sentiment trends
- Roadmap recommendations
"""
from datetime import datetime, timedelta, timezone
from flask import jsonify, request, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity

from src.api.v1 import v1
from src.api.v1.admin import _require_admin
from src.extensions import db
from src.models.core import User
import logging

logger = logging.getLogger(__name__)




@v1.route("/admin/insights/dashboard", methods=["GET"])
@jwt_required()
def get_insights_dashboard():
    """
    Get customer insights dashboard.

    Returns comprehensive analysis of:
    - Top feature requests (30 and 90 days)
    - Pain points
    - Sentiment trends
    - Roadmap recommendations based on customer feedback

    Returns:
        {
            "last_30_days": {...},
            "last_90_days": {...},
            "roadmap_recommendations": {...}
        }
    """
    if not _require_admin():
        return jsonify({"error": "forbidden"}), 403

    try:
        from src.marketing.customer_insights import get_customer_insights_dashboard

        dashboard_data = get_customer_insights_dashboard()

        return jsonify(dashboard_data), 200

    except Exception as e:
        logger.exception(f"Failed to get insights dashboard: {e}")
        return jsonify({
            "error": str(e)
        }), 500


@v1.route("/admin/insights/feature-requests", methods=["GET"])
@jwt_required()
def get_feature_requests():
    """
    Get detailed feature request analysis.

    Query params:
        days_back: Number of days to analyze (default: 30)

    Returns:
        {
            "feature_requests": {
                "top_10": [{feature, mentions}, ...],
                "total_unique": 45
            },
            "pain_points": {...},
            "sentiment": {...}
        }
    """
    if not _require_admin():
        return jsonify({"error": "forbidden"}), 403

    days_back = int(request.args.get("days_back", 30))

    try:
        from src.marketing.customer_insights import analyze_recent_customer_feedback

        insights = analyze_recent_customer_feedback(days_back=days_back)

        return jsonify(insights), 200

    except Exception as e:
        logger.exception(f"Failed to analyze feature requests: {e}")
        return jsonify({
            "error": str(e)
        }), 500


@v1.route("/admin/insights/roadmap", methods=["GET"])
@jwt_required()
def get_roadmap_recommendations():
    """
    Get AI-generated roadmap recommendations based on customer feedback.

    Query params:
        current_features: Comma-separated list of planned features (optional)

    Returns:
        {
            "top_priorities": ["Feature A", "Feature B", ...],
            "quick_wins": ["Quick win 1", ...],
            "strategic_bets": ["Big bet 1", ...],
            "reasoning": "...",
            "based_on": {...}
        }
    """
    if not _require_admin():
        return jsonify({"error": "forbidden"}), 403

    current_features_str = request.args.get("current_features", "")
    current_roadmap = [f.strip() for f in current_features_str.split(",") if f.strip()]

    try:
        from src.marketing.customer_insights import generate_feature_roadmap_recommendations

        recommendations = generate_feature_roadmap_recommendations(
            current_roadmap=current_roadmap if current_roadmap else None
        )

        return jsonify(recommendations), 200

    except Exception as e:
        logger.exception(f"Failed to generate roadmap recommendations: {e}")
        return jsonify({
            "error": str(e)
        }), 500


@v1.route("/admin/insights/track-request", methods=["POST"])
@jwt_required()
def track_feature_request():
    """
    Manually track a feature request.

    Body:
        {
            "customer_email": "user@example.com",
            "feature_description": "Support for multi-language emails",
            "urgency": "high",
            "source": "support_ticket"
        }

    Returns:
        {
            "status": "tracked",
            "tracked_at": "..."
        }
    """
    if not _require_admin():
        return jsonify({"error": "forbidden"}), 403

    payload = request.get_json(silent=True) or {}

    customer_email = payload.get("customer_email")
    feature_description = payload.get("feature_description")

    if not customer_email or not feature_description:
        return jsonify({
            "error": "customer_email and feature_description are required"
        }), 400

    try:
        from src.marketing.customer_insights import track_feature_request

        result = track_feature_request(
            customer_email=customer_email,
            feature_description=feature_description,
            urgency=payload.get("urgency", "medium"),
            source=payload.get("source", "manual")
        )

        return jsonify(result), 200

    except Exception as e:
        logger.exception(f"Failed to track feature request: {e}")
        return jsonify({
            "error": str(e)
        }), 500
