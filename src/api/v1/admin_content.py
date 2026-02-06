"""
Admin API endpoints for Content Generation Agent

ADMIN-ONLY endpoints for testing and validating content generation.
Not exposed to end users until proven successful.

Endpoints:
- POST /api/v1/admin/content/generate-blog - Generate blog post
- POST /api/v1/admin/content/generate-weekly - Generate weekly posts batch
- POST /api/v1/admin/content/optimize-post - Re-optimize existing post
- GET  /api/v1/admin/content/generated - List generated content
- POST /api/v1/admin/content/approve - Approve and publish content
- POST /api/v1/admin/content/reject - Reject generated content
"""
from flask import jsonify, request, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
from datetime import datetime

from src.api.v1 import v1
from src.extensions import db
from src.models import GeneratedContent, BlogPost, User, PitchedBlogTopic
from src.content.tasks import (
    generate_blog_post,
    generate_weekly_posts,
    optimize_existing_post
)


def _safe_json():
    """Parse JSON request body safely."""
    if not request.is_json:
        return {}
    return request.get_json(silent=True) or {}


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


@v1.route("/admin/content/generate-blog", methods=["POST"])
@jwt_required()
def generate_blog():
    """
    Generate a blog post using Content Generation Agent.

    Body:
        niche: Blog niche (optional, default: "Revenue Operations")
        audience: Target audience (optional)
        topic_index: Which topic to use (optional, default: 0)
        auto_publish: Auto-publish flag (optional, default: false)

    Returns:
        Generation task details
    """
    if not _require_admin():
        return jsonify({"error": "forbidden"}), 403

    payload = _safe_json()

    niche = payload.get("niche", "Revenue Operations")
    audience = payload.get("audience", "VP Revenue Operations, B2B SaaS, 100-500 employees")
    topic_index = payload.get("topic_index", 0)
    auto_publish = payload.get("auto_publish", False)

    # Queue Celery task
    task = generate_blog_post.delay(
        niche=niche,
        audience=audience,
        topic_index=topic_index,
        auto_publish=auto_publish
    )

    return jsonify({
        "success": True,
        "task_id": task.id,
        "niche": niche,
        "audience": audience,
        "auto_publish": auto_publish,
        "message": "Blog post generation queued. This may take 2-3 minutes."
    }), 202


@v1.route("/admin/content/generate-weekly", methods=["POST"])
@jwt_required()
def generate_weekly():
    """
    Generate weekly batch of blog posts.

    Body:
        num_posts: Number of posts to generate (default: 3)

    Returns:
        Batch generation task details
    """
    if not _require_admin():
        return jsonify({"error": "forbidden"}), 403

    payload = _safe_json()
    num_posts = payload.get("num_posts", 3)

    if num_posts < 1 or num_posts > 10:
        return jsonify({"error": "num_posts must be between 1 and 10"}), 400

    task = generate_weekly_posts.delay(num_posts=num_posts)

    return jsonify({
        "success": True,
        "task_id": task.id,
        "num_posts": num_posts,
        "message": f"Generating {num_posts} blog posts. This may take 10-15 minutes."
    }), 202


@v1.route("/admin/content/optimize-post", methods=["POST"])
@jwt_required()
def optimize_post():
    """
    Re-optimize existing blog post for SEO.

    Body:
        blog_post_id: BlogPost UUID

    Returns:
        Optimization task details
    """
    if not _require_admin():
        return jsonify({"error": "forbidden"}), 403

    payload = _safe_json()
    blog_post_id = payload.get("blog_post_id")

    if not blog_post_id:
        return jsonify({"error": "blog_post_id required"}), 400

    blog_post = db.session.query(BlogPost).filter(BlogPost.id == blog_post_id).first()
    if not blog_post:
        return jsonify({"error": f"Blog post {blog_post_id} not found"}), 404

    task = optimize_existing_post.delay(blog_post_id)

    return jsonify({
        "success": True,
        "task_id": task.id,
        "blog_post_id": blog_post_id,
        "message": "SEO optimization queued"
    }), 202


@v1.route("/admin/content/generated", methods=["GET"])
@jwt_required()
def list_generated():
    """
    List generated content for admin review.

    Query params:
        status: Filter by status (draft, published, archived)
        content_type: Filter by type (blog_post, email, case_study)
        limit: Max results (default: 50)
        offset: Pagination offset (default: 0)

    Returns:
        List of generated content
    """
    if not _require_admin():
        return jsonify({"error": "forbidden"}), 403

    status = request.args.get("status", "draft")
    content_type = request.args.get("content_type")
    limit = int(request.args.get("limit", 50))
    offset = int(request.args.get("offset", 0))

    query = db.session.query(GeneratedContent).filter(
        GeneratedContent.status == status
    )

    if content_type:
        query = query.filter(GeneratedContent.content_type == content_type)

    query = query.order_by(GeneratedContent.created_at.desc())
    query = query.limit(limit).offset(offset)

    total_count = query.count()
    items = [item.to_dict() for item in query.all()]

    return jsonify({
        "total": total_count,
        "limit": limit,
        "offset": offset,
        "items": items
    }), 200


@v1.route("/admin/content/approve", methods=["POST"])
@jwt_required()
def approve_content():
    """
    Approve generated content and publish.

    Body:
        generated_content_id: GeneratedContent UUID
        publish_now: Publish immediately (default: true)
        scheduled_at: Schedule for future publication (optional, ISO datetime)

    Returns:
        Approval confirmation
    """
    if not _require_admin():
        return jsonify({"error": "forbidden"}), 403

    payload = _safe_json()
    content_id = payload.get("generated_content_id")
    publish_now = payload.get("publish_now", True)
    scheduled_at = payload.get("scheduled_at")

    if not content_id:
        return jsonify({"error": "generated_content_id required"}), 400

    content = db.session.query(GeneratedContent).filter(
        GeneratedContent.id == content_id
    ).first()

    if not content:
        return jsonify({"error": f"Generated content {content_id} not found"}), 404

    try:
        # Update generated content status
        content.status = "published"
        content.published_at = datetime.now() if publish_now else None
        content.updated_at = datetime.now()

        # Update linked blog post
        blog_post = db.session.query(BlogPost).filter(
            BlogPost.generated_content_id == content_id
        ).first()

        if blog_post:
            blog_post.status = "published" if publish_now else "queued"
            blog_post.published_at = datetime.now() if publish_now else None
            blog_post.updated_at = datetime.now()

        db.session.commit()

        return jsonify({
            "success": True,
            "generated_content_id": content_id,
            "blog_post_id": blog_post.id if blog_post else None,
            "status": "published" if publish_now else "queued",
            "published_at": content.published_at.isoformat() if content.published_at else None,
            "message": "Content approved and published" if publish_now else "Content approved and queued"
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@v1.route("/admin/content/reject", methods=["POST"])
@jwt_required()
def reject_content():
    """
    Reject generated content.

    Body:
        generated_content_id: GeneratedContent UUID
        reason: Rejection reason (optional)

    Returns:
        Rejection confirmation
    """
    if not _require_admin():
        return jsonify({"error": "forbidden"}), 403

    payload = _safe_json()
    content_id = payload.get("generated_content_id")
    reason = payload.get("reason", "Quality did not meet standards")

    if not content_id:
        return jsonify({"error": "generated_content_id required"}), 400

    content = db.session.query(GeneratedContent).filter(
        GeneratedContent.id == content_id
    ).first()

    if not content:
        return jsonify({"error": f"Generated content {content_id} not found"}), 404

    try:
        # Archive content
        content.status = "archived"
        content.updated_at = datetime.now()

        # Update metadata with rejection reason
        import json
        meta = json.loads(content.meta_data) if content.meta_data else {}
        meta["rejection_reason"] = reason
        meta["rejected_at"] = datetime.now().isoformat()
        content.meta_data = json.dumps(meta)

        # Update linked blog post
        blog_post = db.session.query(BlogPost).filter(
            BlogPost.generated_content_id == content_id
        ).first()

        if blog_post:
            blog_post.status = "failed"
            blog_post.updated_at = datetime.now()

        db.session.commit()

        return jsonify({
            "success": True,
            "generated_content_id": content_id,
            "status": "archived",
            "reason": reason,
            "message": "Content rejected and archived"
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@v1.route("/admin/content/stats", methods=["GET"])
@jwt_required()
def content_stats():
    """
    Get content generation statistics for admin dashboard.

    Returns:
        Content statistics
    """
    if not _require_admin():
        return jsonify({"error": "forbidden"}), 403

    from sqlalchemy import func

    # Count by status
    status_counts = db.session.query(
        GeneratedContent.status,
        func.count(GeneratedContent.id).label('count')
    ).group_by(GeneratedContent.status).all()

    status_distribution = {row.status: row.count for row in status_counts}

    # Count by content type
    type_counts = db.session.query(
        GeneratedContent.content_type,
        func.count(GeneratedContent.id).label('count')
    ).group_by(GeneratedContent.content_type).all()

    type_distribution = {row.content_type: row.count for row in type_counts}

    # Average quality score
    avg_quality = db.session.query(
        func.avg(GeneratedContent.quality_score)
    ).filter(GeneratedContent.quality_score.isnot(None)).scalar()

    # Recent content (last 7 days)
    from datetime import timedelta
    week_ago = datetime.now() - timedelta(days=7)
    recent_count = db.session.query(func.count(GeneratedContent.id)).filter(
        GeneratedContent.created_at >= week_ago
    ).scalar()

    return jsonify({
        "status_distribution": status_distribution,
        "type_distribution": type_distribution,
        "average_quality_score": float(avg_quality) if avg_quality else None,
        "content_last_7_days": recent_count,
        "total_content": sum(status_distribution.values())
    }), 200


@v1.route("/admin/content/pitch-topic", methods=["POST"])
@jwt_required()
def pitch_topic():
    """
    Submit a manual blog topic pitch.

    Body:
        title: Topic title/idea (required)
        description: Topic description or angle (optional)
        target_keyword: Primary keyword (optional)
        secondary_keywords: Array of secondary keywords (optional)
        funnel_stage: discovery | consideration | decision (optional)
        target_audience: Target audience description (optional)
        niche: Blog niche (optional)
        pitch_notes: Additional notes (optional)

    Returns:
        Created pitched topic
    """
    if not _require_admin():
        return jsonify({"error": "forbidden"}), 403

    payload = _safe_json()
    title = payload.get("title", "").strip()

    if not title:
        return jsonify({"error": "title is required"}), 400

    user = _require_admin()

    try:
        pitched_topic = PitchedBlogTopic(
            title=title,
            description=payload.get("description"),
            target_keyword=payload.get("target_keyword"),
            secondary_keywords=payload.get("secondary_keywords", []),
            funnel_stage=payload.get("funnel_stage"),
            target_audience=payload.get("target_audience"),
            niche=payload.get("niche"),
            pitch_notes=payload.get("pitch_notes"),
            status="pending",
            priority=payload.get("priority", 3),
            submitted_by=user.email,
            created_at=datetime.now(),
            updated_at=datetime.now()
        )

        db.session.add(pitched_topic)
        db.session.commit()

        return jsonify({
            "success": True,
            "pitched_topic": pitched_topic.to_dict(),
            "message": "Topic pitched successfully"
        }), 201

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@v1.route("/admin/content/pitched-topics", methods=["GET"])
@jwt_required()
def list_pitched_topics():
    """
    List pitched blog topics.

    Query params:
        status: Filter by status (pending, approved, rejected, generated)
        priority: Filter by priority (1, 2, 3)
        limit: Max results (default: 50)
        offset: Pagination offset (default: 0)

    Returns:
        List of pitched topics
    """
    if not _require_admin():
        return jsonify({"error": "forbidden"}), 403

    status = request.args.get("status")
    priority = request.args.get("priority", type=int)
    limit = int(request.args.get("limit", 50))
    offset = int(request.args.get("offset", 0))

    query = db.session.query(PitchedBlogTopic)

    if status:
        query = query.filter(PitchedBlogTopic.status == status)

    if priority:
        query = query.filter(PitchedBlogTopic.priority == priority)

    query = query.order_by(PitchedBlogTopic.priority.asc(), PitchedBlogTopic.created_at.desc())

    total_count = query.count()
    items = [item.to_dict() for item in query.limit(limit).offset(offset).all()]

    return jsonify({
        "total": total_count,
        "limit": limit,
        "offset": offset,
        "items": items
    }), 200


@v1.route("/admin/content/pitched-topics/<topic_id>/approve", methods=["POST"])
@jwt_required()
def approve_pitched_topic(topic_id):
    """
    Approve a pitched topic and optionally generate content.

    Body:
        generate_now: Generate content immediately (default: false)
        priority: Update priority (optional)

    Returns:
        Approval confirmation
    """
    if not _require_admin():
        return jsonify({"error": "forbidden"}), 403

    user = _require_admin()
    payload = _safe_json()
    generate_now = payload.get("generate_now", False)

    topic = db.session.query(PitchedBlogTopic).filter(
        PitchedBlogTopic.id == topic_id
    ).first()

    if not topic:
        return jsonify({"error": f"Pitched topic {topic_id} not found"}), 404

    try:
        topic.status = "approved"
        topic.reviewed_by = user.id
        topic.reviewed_at = datetime.now()
        topic.updated_at = datetime.now()

        if payload.get("priority"):
            topic.priority = payload.get("priority")

        db.session.commit()

        response = {
            "success": True,
            "pitched_topic": topic.to_dict(),
            "message": "Topic approved"
        }

        # Optionally generate content immediately
        if generate_now:
            from src.content.tasks import generate_blog_from_pitched_topic
            task = generate_blog_from_pitched_topic.delay(topic_id=topic_id)
            response["task_id"] = task.id
            response["message"] = "Topic approved and content generation queued"

        return jsonify(response), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@v1.route("/admin/content/pitched-topics/<topic_id>/reject", methods=["POST"])
@jwt_required()
def reject_pitched_topic(topic_id):
    """
    Reject a pitched topic.

    Body:
        reason: Rejection reason (optional)

    Returns:
        Rejection confirmation
    """
    if not _require_admin():
        return jsonify({"error": "forbidden"}), 403

    user = _require_admin()
    payload = _safe_json()
    reason = payload.get("reason")

    topic = db.session.query(PitchedBlogTopic).filter(
        PitchedBlogTopic.id == topic_id
    ).first()

    if not topic:
        return jsonify({"error": f"Pitched topic {topic_id} not found"}), 404

    try:
        topic.status = "rejected"
        topic.reviewed_by = user.id
        topic.reviewed_at = datetime.now()
        topic.updated_at = datetime.now()

        if reason:
            topic.pitch_notes = f"{topic.pitch_notes or ''}\n\nRejection reason: {reason}".strip()

        db.session.commit()

        return jsonify({
            "success": True,
            "pitched_topic": topic.to_dict(),
            "message": "Topic rejected"
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@v1.route("/admin/content/pitched-topics/<topic_id>", methods=["DELETE"])
@jwt_required()
def delete_pitched_topic(topic_id):
    """
    Delete a pitched topic.

    Returns:
        Deletion confirmation
    """
    if not _require_admin():
        return jsonify({"error": "forbidden"}), 403

    topic = db.session.query(PitchedBlogTopic).filter(
        PitchedBlogTopic.id == topic_id
    ).first()

    if not topic:
        return jsonify({"error": f"Pitched topic {topic_id} not found"}), 404

    try:
        db.session.delete(topic)
        db.session.commit()

        return jsonify({
            "success": True,
            "message": "Topic deleted"
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500
