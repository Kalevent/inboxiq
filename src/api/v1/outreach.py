"""
API endpoints for email outreach campaigns.
"""
from flask import jsonify, request, send_file
from flask_jwt_extended import jwt_required, get_jwt_identity
from src.api.v1 import v1
from src.api.v1.admin import _require_admin
from src.extensions import db
from src.models.campaigns import EmailCampaign, EmailOutreach
from src.models.leads import Lead
from src.outreach.tasks import send_campaign_emails, track_email_event
from io import BytesIO
from datetime import datetime



@v1.route("/outreach/campaigns", methods=["GET"])
@jwt_required()
def list_campaigns():
    """List all email campaigns."""
    if not _require_admin():
        return jsonify({"error": "forbidden"}), 403

    campaigns = db.session.query(EmailCampaign).order_by(EmailCampaign.created_at.desc()).all()

    return jsonify({
        "campaigns": [
            {
                "id": c.id,
                "name": c.name,
                "status": c.status,
                "from_email": c.from_email,
                "total_sent": c.total_sent,
                "total_opened": c.total_opened,
                "total_clicked": c.total_clicked,
                "total_replied": c.total_replied,
                "open_rate": round((c.total_opened / c.total_sent * 100) if c.total_sent > 0 else 0, 1),
                "reply_rate": round((c.total_replied / c.total_sent * 100) if c.total_sent > 0 else 0, 1),
                "max_recipients": c.max_recipients,
                "created_at": c.created_at.isoformat() if c.created_at else None,
                "started_at": c.started_at.isoformat() if c.started_at else None,
            }
            for c in campaigns
        ]
    }), 200


@v1.route("/outreach/campaigns", methods=["POST"])
@jwt_required()
def create_campaign():
    """
    Create a new email campaign.

    Body:
        name: Campaign name
        subject_template: Email subject with {{variables}}
        body_template: Email body with {{variables}}
        from_email: Sender email
        from_name: Sender name (optional)
        max_recipients: Max emails to send (optional, for beta)
        follow_up_delay_days: [3, 7] for Day 3 and Day 7 follow-ups
        target_source: Filter leads by source (optional)
    """
    if not _require_admin():
        return jsonify({"error": "forbidden"}), 403

    data = request.json

    # Get default sender from database or fallback to config
    from flask import current_app
    from src.models import CampaignSender

    from_email = data.get("from_email")
    from_name = data.get("from_name")

    if not from_email or not from_name:
        # Try to get default sender from database
        default_sender = CampaignSender.query.filter_by(
            account_id=2,
            is_default=True,
            enabled=True
        ).first()

        if default_sender:
            from_email = from_email or default_sender.email
            from_name = from_name or default_sender.name
        else:
            # Fallback to config if no DB senders
            from_email = from_email or current_app.config.get("CAMPAIGN_DEFAULT_EMAIL", "kofi@kalevent.com")
            from_name = from_name or current_app.config.get("CAMPAIGN_DEFAULT_NAME", "Kofi from Kalevent")

    campaign = EmailCampaign(
        account_id=2,
        name=data.get("name"),
        subject_template=data.get("subject_template"),
        body_template=data.get("body_template"),
        from_email=from_email,
        from_name=from_name,
        max_recipients=data.get("max_recipients"),
        follow_up_delay_days=data.get("follow_up_delay_days", [3, 7]),
        target_source=data.get("target_source"),
        status="draft"
    )

    db.session.add(campaign)
    db.session.commit()

    return jsonify({
        "success": True,
        "campaign_id": campaign.id,
        "message": "Campaign created. Use /activate to start sending."
    }), 201


@v1.route("/outreach/campaigns/<campaign_id>/activate", methods=["POST"])
@jwt_required()
def activate_campaign(campaign_id):
    """Activate a campaign and start sending emails."""
    if not _require_admin():
        return jsonify({"error": "forbidden"}), 403

    campaign = db.session.query(EmailCampaign).filter(EmailCampaign.id == campaign_id).first()
    if not campaign:
        return jsonify({"error": "Campaign not found"}), 404

    campaign.status = "active"
    campaign.started_at = datetime.now()
    db.session.commit()

    # Trigger email sending task
    task = send_campaign_emails.apply_async(args=[campaign_id, 10], queue='leads')

    return jsonify({
        "success": True,
        "message": "Campaign activated. Emails will be sent shortly.",
        "task_id": task.id
    }), 200


@v1.route("/outreach/campaigns/<campaign_id>/pause", methods=["POST"])
@jwt_required()
def pause_campaign(campaign_id):
    """Pause an active campaign."""
    if not _require_admin():
        return jsonify({"error": "forbidden"}), 403

    campaign = db.session.query(EmailCampaign).filter(EmailCampaign.id == campaign_id).first()
    if not campaign:
        return jsonify({"error": "Campaign not found"}), 404

    campaign.status = "paused"
    db.session.commit()

    return jsonify({"success": True, "message": "Campaign paused"}), 200


@v1.route("/outreach/campaigns/<campaign_id>/outreaches", methods=["GET"])
@jwt_required()
def list_outreaches(campaign_id):
    """List all outreach emails for a campaign."""
    if not _require_admin():
        return jsonify({"error": "forbidden"}), 403

    limit = request.args.get("limit", 50, type=int)

    outreaches = db.session.query(EmailOutreach).filter(
        EmailOutreach.campaign_id == campaign_id
    ).order_by(EmailOutreach.created_at.desc()).limit(limit).all()

    return jsonify({
        "outreaches": [
            {
                "id": o.id,
                "recipient_email": o.recipient_email,
                "recipient_name": o.recipient_name,
                "subject": o.subject,
                "status": o.status,
                "sequence_step": o.sequence_step,
                "sent_at": o.sent_at.isoformat() if o.sent_at else None,
                "first_opened_at": o.first_opened_at.isoformat() if o.first_opened_at else None,
                "replied_at": o.replied_at.isoformat() if o.replied_at else None,
                "open_count": o.open_count,
                "click_count": o.click_count,
            }
            for o in outreaches
        ]
    }), 200


@v1.route("/outreach/track/<outreach_id>/open", methods=["GET"])
def track_open(outreach_id):
    """
    Track email open via transparent 1x1 pixel.
    Called when recipient opens email.
    """
    # Queue tracking event
    track_email_event.apply_async(
        args=[outreach_id, 'open'],
        kwargs={"timestamp": datetime.now().isoformat()},
        queue='leads'
    )

    # Return 1x1 transparent pixel
    pixel = BytesIO(b'\x47\x49\x46\x38\x39\x61\x01\x00\x01\x00\x80\x00\x00\xff\xff\xff\x00\x00\x00\x21\xf9\x04\x01\x00\x00\x00\x00\x2c\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02\x44\x01\x00\x3b')
    return send_file(pixel, mimetype='image/gif')


@v1.route("/outreach/track/<outreach_id>/click", methods=["GET"])
def track_click(outreach_id):
    """
    Track link click and redirect to target URL.
    """
    target_url = request.args.get("url", "https://kalevent.com")

    # Queue tracking event
    track_email_event.apply_async(
        args=[outreach_id, 'click'],
        kwargs={"timestamp": datetime.now().isoformat()},
        queue='leads'
    )

    # Redirect to target
    from flask import redirect
    return redirect(target_url, code=302)


@v1.route("/outreach/campaigns/<campaign_id>/stats", methods=["GET"])
@jwt_required()
def campaign_stats(campaign_id):
    """Get detailed stats for a campaign."""
    if not _require_admin():
        return jsonify({"error": "forbidden"}), 403

    campaign = db.session.query(EmailCampaign).filter(EmailCampaign.id == campaign_id).first()
    if not campaign:
        return jsonify({"error": "Campaign not found"}), 404

    # Get status breakdown
    from sqlalchemy import func
    status_counts = db.session.query(
        EmailOutreach.status,
        func.count(EmailOutreach.id)
    ).filter(
        EmailOutreach.campaign_id == campaign_id
    ).group_by(EmailOutreach.status).all()

    return jsonify({
        "campaign": {
            "id": campaign.id,
            "name": campaign.name,
            "status": campaign.status,
            "total_sent": campaign.total_sent,
            "total_opened": campaign.total_opened,
            "total_clicked": campaign.total_clicked,
            "total_replied": campaign.total_replied,
            "open_rate": round((campaign.total_opened / campaign.total_sent * 100) if campaign.total_sent > 0 else 0, 1),
            "click_rate": round((campaign.total_clicked / campaign.total_sent * 100) if campaign.total_sent > 0 else 0, 1),
            "reply_rate": round((campaign.total_replied / campaign.total_sent * 100) if campaign.total_sent > 0 else 0, 1),
            "max_recipients": campaign.max_recipients,
            "started_at": campaign.started_at.isoformat() if campaign.started_at else None,
        },
        "status_breakdown": dict(status_counts)
    }), 200


# ============================================================================
# Campaign Senders Management
# ============================================================================

@v1.route("/outreach/senders", methods=["GET"])
@jwt_required()
def get_campaign_senders():
    """Get all campaign senders for the account."""
    if not _require_admin():
        return jsonify({"error": "forbidden"}), 403

    from src.models import CampaignSender

    senders = CampaignSender.query.filter_by(account_id=2).order_by(
        CampaignSender.is_default.desc(),
        CampaignSender.created_at.desc()
    ).all()

    return jsonify({
        "success": True,
        "senders": [s.to_dict() for s in senders]
    }), 200


@v1.route("/outreach/senders", methods=["POST"])
@jwt_required()
def add_campaign_sender():
    """
    Add a new campaign sender.

    Body:
        email: Sender email (e.g., kofi@kalevent.com)
        name: Display name (e.g., "Kofi from Kalevent")
        is_default: Set as default sender (optional, default: false)
    """
    if not _require_admin():
        return jsonify({"error": "forbidden"}), 403

    from src.models import CampaignSender
    from uuid import uuid4

    data = request.json

    # Validate required fields
    if not data.get("email") or not data.get("name"):
        return jsonify({"error": "email and name are required"}), 400

    # If setting as default, unset other defaults
    if data.get("is_default"):
        CampaignSender.query.filter_by(account_id=2, is_default=True).update({"is_default": False})

    sender = CampaignSender(
        id=str(uuid4()),
        account_id=2,
        email=data.get("email"),
        name=data.get("name"),
        is_default=data.get("is_default", False),
        enabled=True
    )

    db.session.add(sender)
    db.session.commit()

    return jsonify({
        "success": True,
        "sender": sender.to_dict(),
        "message": f"Campaign sender '{sender.name}' added successfully"
    }), 201


@v1.route("/outreach/senders/<sender_id>", methods=["PUT"])
@jwt_required()
def update_campaign_sender(sender_id):
    """Update a campaign sender (set as default, enable/disable, etc.)."""
    if not _require_admin():
        return jsonify({"error": "forbidden"}), 403

    from src.models import CampaignSender

    sender = CampaignSender.query.filter_by(id=sender_id, account_id=2).first()
    if not sender:
        return jsonify({"error": "Sender not found"}), 404

    data = request.json

    # If setting as default, unset other defaults
    if data.get("is_default"):
        CampaignSender.query.filter_by(account_id=2, is_default=True).update({"is_default": False})
        sender.is_default = True

    if "enabled" in data:
        sender.enabled = data["enabled"]

    if data.get("name"):
        sender.name = data["name"]

    db.session.commit()

    return jsonify({
        "success": True,
        "sender": sender.to_dict()
    }), 200


@v1.route("/outreach/senders/<sender_id>", methods=["DELETE"])
@jwt_required()
def delete_campaign_sender(sender_id):
    """Delete a campaign sender."""
    if not _require_admin():
        return jsonify({"error": "forbidden"}), 403

    from src.models import CampaignSender

    sender = CampaignSender.query.filter_by(id=sender_id, account_id=2).first()
    if not sender:
        return jsonify({"error": "Sender not found"}), 404

    # Don't allow deleting the last sender
    total_senders = CampaignSender.query.filter_by(account_id=2, enabled=True).count()
    if total_senders <= 1:
        return jsonify({"error": "Cannot delete the last campaign sender"}), 400

    db.session.delete(sender)
    db.session.commit()

    return jsonify({
        "success": True,
        "message": "Campaign sender deleted"
    }), 200
