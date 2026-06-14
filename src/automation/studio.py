"""
Automation Studio waitlist and pre-launch endpoints.
"""
from flask import Blueprint, jsonify, request, redirect, render_template, flash
from src.extensions import db, limiter
from src.models.automation import AutomationStudioWaitlist
import logging

logger = logging.getLogger(__name__)

bp = Blueprint("automation_studio", __name__, url_prefix="/automation-studio")


@bp.route("/waitlist", methods=["POST"])  # nosemgrep: inboxiq.auth.unprotected-write-endpoint
@limiter.limit("10 per hour", override_defaults=False)
def join_waitlist():
    """Add email to Automation Studio waitlist."""
    # Get email from form or JSON
    email = request.form.get("email") or (request.get_json() or {}).get("email")

    # Get source tracking
    source = request.args.get("source", "homepage")
    utm_source = request.args.get("utm_source") or request.form.get("utm_source")
    utm_campaign = request.args.get("utm_campaign") or request.form.get("utm_campaign")
    utm_medium = request.args.get("utm_medium") or request.form.get("utm_medium")

    if not email:
        if request.is_json:
            return jsonify({"error": "Email required"}), 400
        flash("Email address is required", "error")
        return redirect("/#automation-studio-teaser")

    # Normalize email
    email = email.strip().lower()

    try:
        # Check if already on waitlist
        existing = AutomationStudioWaitlist.query.filter_by(email=email).first()
        if existing:
            logger.info(f"Duplicate waitlist signup: {email}")
            if request.is_json:
                return jsonify({"status": "already_subscribed", "message": "You're already on the waitlist!"}), 200
            return redirect("/#automation-studio-teaser?status=already")

        # Add to waitlist
        signup = AutomationStudioWaitlist(
            email=email,
            source=source,
            utm_source=utm_source,
            utm_campaign=utm_campaign,
            utm_medium=utm_medium
        )
        db.session.add(signup)
        db.session.commit()

        logger.info(f"New waitlist signup: {email} from {source}")

        # TODO: Send welcome email (async via Celery)
        # from src.automation_studio_emails import send_waitlist_welcome_email
        # send_waitlist_welcome_email.delay(email)

        if request.is_json:
            return jsonify({
                "status": "success",
                "message": "You're on the waitlist!",
                "waitlist_position": AutomationStudioWaitlist.query.count()
            }), 201

        return redirect("/#automation-studio-teaser?status=success")

    except Exception as e:
        logger.exception(f"Waitlist signup error: {e}")
        db.session.rollback()
        if request.is_json:
            return jsonify({"error": "Something went wrong. Please try again."}), 500
        flash("Something went wrong. Please try again.", "error")
        return redirect("/#automation-studio-teaser")


@bp.route("/waitlist/count", methods=["GET"])
def waitlist_count():
    """Get current waitlist count (for social proof)."""
    try:
        count = AutomationStudioWaitlist.query.count()
        return jsonify({"count": count})
    except Exception as e:
        logger.exception(f"Waitlist count error: {e}")
        return jsonify({"count": 0})


@bp.route("/landing", methods=["GET"])
def landing_page():
    """Dedicated Automation Studio landing page."""
    try:
        waitlist_count = AutomationStudioWaitlist.query.count()
    except Exception:
        waitlist_count = 0

    return render_template(
        "automation_studio_landing.html",
        waitlist_count=waitlist_count
    )


@bp.route("/admin/waitlist", methods=["GET"])
def admin_waitlist():
    """Admin view of waitlist signups (add @login_required in production)."""
    try:
        signups = AutomationStudioWaitlist.query.order_by(
            AutomationStudioWaitlist.created_at.desc()
        ).all()

        return jsonify({
            "total": len(signups),
            "qualified": sum(1 for s in signups if s.beta_qualified),
            "committed": sum(1 for s in signups if s.beta_committed),
            "signups": [s.to_dict() for s in signups]
        })
    except Exception as e:
        logger.exception(f"Admin waitlist error: {e}")
        return jsonify({"error": str(e)}), 500
