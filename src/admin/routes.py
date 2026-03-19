from flask import render_template, request, redirect, url_for, flash
from datetime import datetime
from sqlalchemy import func

from src.admin import bp
from src.extensions import db
from src.models.content import PitchedBlogTopic
from src.content.tasks import generate_blog_from_pitched_topic
from src.settings import login_required_settings


@bp.route("/pitched-topics", methods=["GET"])
@login_required_settings
def pitched_topics():
    """Display pitched blog topics management page."""

    # Get filter parameters
    status = request.args.get("status", "pending")
    priority = request.args.get("priority", "all")
    search_query = request.args.get("q", "").strip()

    # Build query
    query = db.session.query(PitchedBlogTopic)

    if status != "all":
        query = query.filter(PitchedBlogTopic.status == status)

    if priority != "all":
        query = query.filter(PitchedBlogTopic.priority == int(priority))

    if search_query:
        search_pattern = f"%{search_query}%"
        query = query.filter(
            db.or_(
                PitchedBlogTopic.title.ilike(search_pattern),
                PitchedBlogTopic.target_keyword.ilike(search_pattern)
            )
        )

    # Order by priority and creation date
    query = query.order_by(
        PitchedBlogTopic.priority.asc(),
        PitchedBlogTopic.created_at.desc()
    )

    topics = query.all()

    # Get status counts
    status_counts = db.session.query(
        PitchedBlogTopic.status,
        func.count(PitchedBlogTopic.id).label('count')
    ).group_by(PitchedBlogTopic.status).all()

    counts = {row.status: row.count for row in status_counts}

    return render_template(
        "admin/pitched_topics.html",
        topics=[t.to_dict() for t in topics],
        counts=counts
    )


@bp.route("/pitched-topics/submit", methods=["POST"])
@login_required_settings
def submit_pitched_topic():
    """Handle pitched topic submission."""

    title = request.form.get("title", "").strip()
    if not title:
        flash("Title is required", "error")
        return redirect(url_for("admin.pitched_topics"))

    try:
        pitched_topic = PitchedBlogTopic(
            title=title,
            description=request.form.get("description", "").strip() or None,
            target_keyword=request.form.get("target_keyword", "").strip() or None,
            funnel_stage=request.form.get("funnel_stage", "").strip() or None,
            target_audience=request.form.get("target_audience", "").strip() or None,
            niche=request.form.get("niche", "").strip() or None,
            pitch_notes=request.form.get("pitch_notes", "").strip() or None,
            priority=int(request.form.get("priority", 3)),
            status="pending",
            submitted_by="admin@kalevent.com",  # TODO: Get from session
            created_at=datetime.now(),
            updated_at=datetime.now()
        )

        db.session.add(pitched_topic)
        db.session.commit()

        flash(f"Topic '{title}' pitched successfully!", "success")

    except Exception as e:
        db.session.rollback()
        flash(f"Error submitting topic: {str(e)}", "error")

    return redirect(url_for("admin.pitched_topics"))


@bp.route("/pitched-topics/<topic_id>/approve", methods=["POST"])
@login_required_settings
def approve_pitched_topic(topic_id):

    topic = db.session.query(PitchedBlogTopic).filter(
        PitchedBlogTopic.id == topic_id
    ).first()

    if not topic:
        flash("Topic not found", "error")
        return redirect(url_for("admin.pitched_topics"))

    try:
        topic.status = "approved"
        topic.reviewed_at = datetime.now()
        topic.updated_at = datetime.now()
        db.session.commit()

        generate_blog_from_pitched_topic.delay(topic_id=str(topic.id))
        flash(f"Topic '{topic.title}' approved and content generation queued!", "success")

    except Exception as e:
        db.session.rollback()
        flash(f"Error approving topic: {str(e)}", "error")

    return redirect(url_for("admin.pitched_topics"))


@bp.route("/pitched-topics/<topic_id>/reject", methods=["POST"])
@login_required_settings
def reject_pitched_topic(topic_id):

    topic = db.session.query(PitchedBlogTopic).filter(
        PitchedBlogTopic.id == topic_id
    ).first()

    if not topic:
        flash("Topic not found", "error")
        return redirect(url_for("admin.pitched_topics"))

    try:
        topic.status = "rejected"
        topic.reviewed_at = datetime.now()
        topic.updated_at = datetime.now()
        db.session.commit()

        flash(f"Topic '{topic.title}' rejected.", "success")

    except Exception as e:
        db.session.rollback()
        flash(f"Error rejecting topic: {str(e)}", "error")

    return redirect(url_for("admin.pitched_topics"))


@bp.route("/pitched-topics/<topic_id>/generate", methods=["POST"])
@login_required_settings
def generate_from_pitched_topic(topic_id):
    """Queue content generation from pitched topic."""

    topic = db.session.query(PitchedBlogTopic).filter(
        PitchedBlogTopic.id == topic_id
    ).first()

    if not topic:
        flash("Topic not found", "error")
        return redirect(url_for("admin.pitched_topics"))

    if topic.status != "approved":
        flash("Only approved topics can be generated", "error")
        return redirect(url_for("admin.pitched_topics"))

    try:
        # Queue Celery task
        task = generate_blog_from_pitched_topic.delay(topic_id=topic_id)

        flash(f"Content generation queued for '{topic.title}'. Task ID: {task.id}", "success")

    except Exception as e:
        flash(f"Error queueing generation: {str(e)}", "error")

    return redirect(url_for("admin.pitched_topics"))


@bp.route("/pitched-topics/<topic_id>/delete", methods=["POST"])
@login_required_settings
def delete_pitched_topic(topic_id):
    """Delete a pitched topic."""

    topic = db.session.query(PitchedBlogTopic).filter(
        PitchedBlogTopic.id == topic_id
    ).first()

    if not topic:
        flash("Topic not found", "error")
        return redirect(url_for("admin.pitched_topics"))

    try:
        title = topic.title
        db.session.delete(topic)
        db.session.commit()

        flash(f"Topic '{title}' deleted.", "success")

    except Exception as e:
        db.session.rollback()
        flash(f"Error deleting topic: {str(e)}", "error")

    return redirect(url_for("admin.pitched_topics"))
