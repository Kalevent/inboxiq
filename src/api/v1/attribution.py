"""
Attribution tracking API endpoints.

Provides REST API for recording attribution touchpoints via webhooks.
Complements the attribution-mcp server with HTTP endpoints.
"""
from datetime import datetime, timezone
from flask import jsonify, request
from uuid import uuid4

from src.api.v1 import v1
from src.extensions import db
from src.funnel.stages import VISITS
from src.models.leads import LeadAttribution, Lead
import logging

logger = logging.getLogger(__name__)


@v1.route("/attribution/track", methods=["POST"])
def track_attribution():
    """
    Track a marketing touchpoint via webhook.

    Body:
        {
            "lead_id": "uuid...",  # Optional - will create lead if not exists
            "lead_email": "user@example.com",  # Required if no lead_id
            "source": "linkedin",
            "medium": "social",
            "campaign": "q1-awareness",
            "content": "blog-post-cta",
            "term": "inbox-automation",
            "touched_at": "2026-02-15T14:30:00Z"  # Optional, defaults to now
        }

    Returns:
        {
            "status": "success",
            "touchpoint_id": "uuid...",
            "lead_id": "uuid...",
            "touchpoint_order": 3
        }
    """
    payload = request.get_json(silent=True) or {}

    # Validate required fields
    lead_id = payload.get("lead_id")
    lead_email = payload.get("lead_email")

    if not lead_id and not lead_email:
        return jsonify({
            "error": "Either 'lead_id' or 'lead_email' is required"
        }), 400

    source = payload.get("source")
    if not source:
        return jsonify({"error": "'source' is required"}), 400

    try:
        # Find or create lead
        if lead_id:
            lead = db.session.get(Lead, lead_id)
            if not lead:
                return jsonify({
                    "error": f"Lead {lead_id} not found"
                }), 404
        else:
            # Find by email or create new lead
            lead = db.session.query(Lead).filter(
                Lead.email == lead_email
            ).first()

            if not lead:
                # Create new lead from attribution tracking
                lead = Lead(
                    id=str(uuid4()),
                    email=lead_email,
                    name=payload.get("name", lead_email.split('@')[0]),
                    source=source,
                    utm_source=source,
                    utm_medium=payload.get("medium"),
                    utm_campaign=payload.get("campaign"),
                    utm_term=payload.get("term"),
                    current_funnel_stage=VISITS,
                    status="new",
                    stage_entered_at=datetime.now(timezone.utc)
                )
                db.session.add(lead)
                db.session.flush()  # Get lead ID

                logger.info(f"Created new lead from attribution tracking: {lead_email}")

        # Determine touchpoint order
        existing_count = db.session.query(LeadAttribution).filter(
            LeadAttribution.lead_id == lead.id
        ).count()

        touchpoint_order = existing_count + 1

        # Parse touched_at timestamp
        touched_at_str = payload.get("touched_at")
        if touched_at_str:
            touched_at = datetime.fromisoformat(touched_at_str.replace('Z', '+00:00'))
        else:
            touched_at = datetime.now(timezone.utc)

        # Create touchpoint
        touchpoint = LeadAttribution(
            id=str(uuid4()),
            lead_id=lead.id,
            touchpoint_order=touchpoint_order,
            source=source,
            medium=payload.get("medium"),
            campaign=payload.get("campaign"),
            content=payload.get("content"),
            term=payload.get("term"),
            touched_at=touched_at,
            attribution_model="linear",
            attribution_weight=1.0
        )

        db.session.add(touchpoint)

        # Update lead's last engagement
        lead.last_engagement_at = touched_at

        db.session.commit()

        logger.info(f"Tracked touchpoint #{touchpoint_order} for lead {lead.id}: {source}/{payload.get('campaign')}")

        return jsonify({
            "status": "success",
            "touchpoint_id": touchpoint.id,
            "lead_id": lead.id,
            "touchpoint_order": touchpoint_order,
            "source": source,
            "campaign": payload.get("campaign")
        }), 200

    except Exception as e:
        logger.exception(f"Failed to track attribution: {e}")
        db.session.rollback()
        return jsonify({
            "status": "error",
            "error": str(e)
        }), 500


@v1.route("/attribution/report", methods=["GET"])
def get_attribution_report():
    """
    Get attribution report.

    Query params:
        start_date: ISO 8601 date (default: 30 days ago)
        end_date: ISO 8601 date (default: today)
        model: Attribution model (first_touch, last_touch, linear, time_decay)
        group_by: Group by campaign, source, medium (default: campaign)

    Returns:
        {
            "period": {"start": "...", "end": "..."},
            "model": "linear",
            "attribution": {
                "q1-awareness": {
                    "touches": 150,
                    "unique_leads": 45,
                    "attributed_conversions": 5.2,
                    "conversion_rate": 11.6
                }
            }
        }
    """
    from datetime import timedelta

    # Parse query parameters
    end_date_str = request.args.get("end_date")
    start_date_str = request.args.get("start_date")

    if end_date_str:
        end_date = datetime.fromisoformat(end_date_str.replace('Z', '+00:00'))
    else:
        end_date = datetime.now(timezone.utc)

    if start_date_str:
        start_date = datetime.fromisoformat(start_date_str.replace('Z', '+00:00'))
    else:
        start_date = end_date - timedelta(days=30)

    model = request.args.get("model", "linear")
    group_by = request.args.get("group_by", "campaign")

    try:
        # Get touchpoints in date range
        touchpoints = db.session.query(LeadAttribution, Lead).join(
            Lead, LeadAttribution.lead_id == Lead.id
        ).filter(
            LeadAttribution.touched_at >= start_date,
            LeadAttribution.touched_at <= end_date
        ).all()

        # Recalculate attribution weights
        from src.mcp.attribution_mcp import calculate_attribution

        leads_processed = set()
        for tp, lead in touchpoints:
            if lead.id not in leads_processed:
                calculate_attribution(lead.id, model)
                leads_processed.add(lead.id)

        # Group and aggregate
        attribution_groups = {}

        for touchpoint, lead in touchpoints:
            # Determine group key
            if group_by == "campaign":
                key = touchpoint.campaign or "unknown"
            elif group_by == "source":
                key = touchpoint.source
            elif group_by == "medium":
                key = touchpoint.medium or "unknown"
            else:
                key = "all"

            if key not in attribution_groups:
                attribution_groups[key] = {
                    "touches": 0,
                    "attributed_conversions": 0.0,
                    "unique_leads": set()
                }

            attribution_groups[key]["touches"] += 1
            attribution_groups[key]["unique_leads"].add(lead.id)

            # Add attribution weight if lead converted
            if lead.status in ["customer", "converted"]:
                attribution_groups[key]["attributed_conversions"] += touchpoint.attribution_weight

        # Format results
        result = {}
        for key, data in attribution_groups.items():
            unique_count = len(data["unique_leads"])
            result[key] = {
                "touches": data["touches"],
                "unique_leads": unique_count,
                "attributed_conversions": round(data["attributed_conversions"], 2),
                "conversion_rate": round((data["attributed_conversions"] / unique_count * 100) if unique_count else 0, 1)
            }

        return jsonify({
            "period": {
                "start": start_date.isoformat(),
                "end": end_date.isoformat()
            },
            "model": model,
            "group_by": group_by,
            "attribution": result
        }), 200

    except Exception as e:
        logger.exception(f"Failed to generate attribution report: {e}")
        return jsonify({
            "error": str(e)
        }), 500
