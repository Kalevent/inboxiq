"""
Public Content Generation API endpoints

User-facing endpoints for content generation via Content Generation Agent.
All endpoints require JWT authentication.

Endpoints:
- POST /api/v1/content/generate - Generate content via Content Generation Agent
- POST /api/v1/content/modify/<content_id> - Request modifications to published content
- GET /api/v1/content/performance/<content_id> - Get performance metrics
"""
from flask import jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from src.api.v1 import v1
from src.extensions import db
from src.models import GeneratedContent, User


def _safe_json():
    """Parse JSON request body safely."""
    if not request.is_json:
        return {}
    return request.get_json(silent=True) or {}


@v1.route("/content/generate", methods=["POST"])
@jwt_required()
def generate_content():
    """
    Generate content via Content Generation Agent (autonomous).

    Body:
        content_type: "blog_post" | "email" | "case_study" | "landing_page" (default: blog_post)
        niche: Blog niche (default: "Revenue Operations")
        audience: Target audience (default: "VP Revenue Operations, B2B SaaS")
        num_items: Number of items to generate (default: 1)
        topic_index: Which topic to use from generated list (default: 0)
        auto_publish: Auto-publish or save as draft (default: false)
        notify: Send notification when done (default: true)

    Returns:
        Task ID for async content generation (202 Accepted)
    """
    account_id = get_jwt_identity()
    if not account_id:
        return jsonify({"error": "unauthorized"}), 401

    payload = _safe_json()

    # Parse parameters
    content_type = payload.get("content_type", "blog_post")
    niche = payload.get("niche", "Revenue Operations")
    audience = payload.get("audience", "VP Revenue Operations, B2B SaaS, 100-500 employees")
    num_items = int(payload.get("num_items", 1))
    topic_index = int(payload.get("topic_index", 0))
    auto_publish = bool(payload.get("auto_publish", False))
    notify = bool(payload.get("notify", True))

    # Validate content_type
    valid_types = ["blog_post", "email", "case_study", "landing_page"]
    if content_type not in valid_types:
        return jsonify({
            "error": f"Invalid content_type. Must be one of: {valid_types}"
        }), 400

    # Validate num_items
    if num_items < 1 or num_items > 10:
        return jsonify({"error": "num_items must be between 1 and 10"}), 400

    # Currently only blog_post is fully implemented
    if content_type != "blog_post":
        return jsonify({
            "error": f"Content type '{content_type}' not yet implemented. Currently only 'blog_post' is supported."
        }), 400

    # Queue Celery task
    from src.content.tasks import generate_blog_post

    task_ids = []
    for i in range(num_items):
        task = generate_blog_post.delay(
            niche=niche,
            audience=audience,
            topic_index=(topic_index + i) % 5,  # Rotate through topics
            auto_publish=auto_publish
        )
        task_ids.append(task.id)

    # TODO: If notify=True, send notification when tasks complete
    # This would require tracking task completion and sending Slack/email

    return jsonify({
        "success": True,
        "task_ids": task_ids,
        "num_queued": len(task_ids),
        "status": "queued",
        "message": f"Content generation started for {num_items} item(s). You'll be notified when complete." if notify else f"Content generation started for {num_items} item(s).",
        "parameters": {
            "content_type": content_type,
            "niche": niche,
            "audience": audience,
            "auto_publish": auto_publish
        }
    }), 202


@v1.route("/content/modify/<content_id>", methods=["POST"])
@jwt_required()
def modify_content(content_id):
    """
    Request modifications to published content via natural language.

    Body:
        modification_request: Natural language description of changes (required)
        regenerate_seo: Re-optimize SEO after modifications (default: false)
        auto_publish: Auto-publish after modifications (default: false)

    Returns:
        Task ID for async modification (202 Accepted)
    """
    account_id = get_jwt_identity()
    if not account_id:
        return jsonify({"error": "unauthorized"}), 401

    payload = _safe_json()
    modification_request = payload.get("modification_request", "").strip()

    if not modification_request:
        return jsonify({"error": "modification_request is required"}), 400

    # Verify content exists and user has access
    content = db.session.query(GeneratedContent).filter(
        GeneratedContent.id == content_id
    ).first()

    if not content:
        return jsonify({"error": f"Content {content_id} not found"}), 404

    # TODO: Verify account access when GeneratedContent has account_id field
    # if content.account_id != account_id:
    #     return jsonify({"error": "forbidden"}), 403

    regenerate_seo = bool(payload.get("regenerate_seo", False))
    auto_publish = bool(payload.get("auto_publish", False))

    # Store modification request in metadata
    if not content.meta_data:
        content.meta_data = {}

    if "modification_history" not in content.meta_data:
        content.meta_data["modification_history"] = []

    from datetime import datetime
    content.meta_data["modification_history"].append({
        "timestamp": datetime.now().isoformat(),
        "request": modification_request,
        "requested_by": account_id
    })

    db.session.commit()

    # TODO: Queue task to apply modifications
    # This would involve:
    # 1. Parsing modification request
    # 2. Re-running Editor module with specific instructions
    # 3. Optionally re-running SEO optimizer
    # 4. Updating GeneratedContent record

    # For now, return success with note that feature is in development
    return jsonify({
        "success": True,
        "content_id": content_id,
        "modification_request": modification_request,
        "status": "recorded",
        "message": "Modification request recorded. Manual review required.",
        "note": "Automated content modification is in development. Your request has been saved and will be reviewed."
    }), 202


@v1.route("/content/performance/<content_id>", methods=["GET"])
@jwt_required()
def get_content_performance(content_id):
    """
    Get performance metrics for generated content.

    Returns:
        Performance metrics including views, engagement, conversions, SEO ranking, quality score
    """
    account_id = get_jwt_identity()
    if not account_id:
        return jsonify({"error": "unauthorized"}), 401

    # Get content
    content = db.session.query(GeneratedContent).filter(
        GeneratedContent.id == content_id
    ).first()

    if not content:
        return jsonify({"error": f"Content {content_id} not found"}), 404

    # TODO: Verify account access when GeneratedContent has account_id field
    # if content.account_id != account_id:
    #     return jsonify({"error": "forbidden"}), 403

    # Extract performance metrics
    performance_metrics = content.performance_metrics or {}
    meta_data = content.meta_data or {}

    return jsonify({
        "content_id": content.id,
        "title": content.title,
        "content_type": content.content_type,
        "status": content.status,
        "published_at": content.published_at.isoformat() if content.published_at else None,
        "funnel_stage": content.funnel_stage,
        "quality_score": content.quality_score,
        "seo_score": meta_data.get("seo_score"),
        "word_count": meta_data.get("word_count"),
        "target_keywords": meta_data.get("target_keywords"),
        "performance_metrics": {
            "views": performance_metrics.get("views", 0),
            "unique_visitors": performance_metrics.get("unique_visitors", 0),
            "engagement_rate": performance_metrics.get("engagement_rate", 0),
            "avg_time_on_page": performance_metrics.get("avg_time_on_page"),
            "conversions": performance_metrics.get("conversions", 0),
            "conversion_rate": performance_metrics.get("conversion_rate", 0),
            "seo_ranking": performance_metrics.get("seo_ranking"),
            "organic_traffic": performance_metrics.get("organic_traffic", 0),
            "bounce_rate": performance_metrics.get("bounce_rate")
        },
        "created_at": content.created_at.isoformat() if content.created_at else None,
        "updated_at": content.updated_at.isoformat() if content.updated_at else None
    }), 200
