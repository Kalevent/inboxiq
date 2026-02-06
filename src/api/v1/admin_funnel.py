"""
Admin API endpoints for Funnel v2.0 management

ADMIN-ONLY endpoints for testing and validating funnel system.
Not exposed to end users until proven successful.

Endpoints:
- POST /api/v1/admin/funnel/qualify-lead - Manually trigger lead qualification
- POST /api/v1/admin/funnel/update-interest - Update lead interest score
- POST /api/v1/admin/funnel/move-stage - Move lead to different stage
- POST /api/v1/admin/funnel/analyze-churn - Run churn analysis for customer
- GET  /api/v1/admin/funnel/metrics - Get funnel metrics
- POST /api/v1/admin/funnel/orchestrate - Run full orchestration job
"""
from flask import jsonify, request, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity

from src.api.v1 import v1
from src.extensions import db
from src.models import Lead, LeadFunnelStage, FunnelMetricsDaily, User


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


@v1.route("/admin/funnel/qualify-lead", methods=["POST"])
@jwt_required()
def qualify_lead():
    """
    Manually trigger lead qualification for testing.

    Body:
        lead_id: Lead UUID

    Returns:
        Qualification results
    """
    if not _require_admin():
        return jsonify({"error": "forbidden"}), 403

    payload = _safe_json()
    lead_id = payload.get("lead_id")

    if not lead_id:
        return jsonify({"error": "lead_id required"}), 400

    # Verify lead exists
    lead = db.session.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        return jsonify({"error": f"Lead {lead_id} not found"}), 404

    # Queue Celery task by name to avoid circular import issues
    from src.celery_inboxiq import celery
    task = celery.send_task('funnel.qualify_visitor', args=[lead_id])

    return jsonify({
        "success": True,
        "task_id": task.id,
        "lead_id": lead_id,
        "message": "Lead qualification queued"
    }), 202


@v1.route("/admin/funnel/update-interest", methods=["POST"])
@jwt_required()
def update_interest():
    """
    Manually update lead interest score for testing.

    Body:
        lead_id: Lead UUID

    Returns:
        Interest scoring results
    """
    if not _require_admin():
        return jsonify({"error": "forbidden"}), 403

    payload = _safe_json()
    lead_id = payload.get("lead_id")

    if not lead_id:
        return jsonify({"error": "lead_id required"}), 400

    lead = db.session.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        return jsonify({"error": f"Lead {lead_id} not found"}), 404

    from src.celery_inboxiq import celery
    task = celery.send_task('funnel.update_interest_score', args=[lead_id])

    return jsonify({
        "success": True,
        "task_id": task.id,
        "lead_id": lead_id,
        "message": "Interest score update queued"
    }), 202


@v1.route("/admin/funnel/move-stage", methods=["POST"])
@jwt_required()
def move_stage():
    """
    Manually move lead to a different stage (admin testing).

    Body:
        lead_id: Lead UUID
        new_stage: Target stage (visits, discovery, consideration, conversion, retention)
        notes: Optional notes

    Returns:
        Stage transition results
    """
    if not _require_admin():
        return jsonify({"error": "forbidden"}), 403

    payload = _safe_json()
    lead_id = payload.get("lead_id")
    new_stage = payload.get("new_stage")
    notes = payload.get("notes")

    if not lead_id or not new_stage:
        return jsonify({"error": "lead_id and new_stage required"}), 400

    valid_stages = ['visits', 'discovery', 'consideration', 'conversion', 'retention']
    if new_stage not in valid_stages:
        return jsonify({"error": f"Invalid stage. Must be one of: {valid_stages}"}), 400

    lead = db.session.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        return jsonify({"error": f"Lead {lead_id} not found"}), 404

    try:
        # Import stage orchestration MCP tools (would use MCP server in production)
        from datetime import datetime

        old_stage = lead.current_funnel_stage

        # Update lead
        lead.current_funnel_stage = new_stage
        lead.stage_entered_at = datetime.now()
        lead.updated_at = datetime.now()

        # Create stage history entry
        stage_entry = LeadFunnelStage(
            lead_id=lead_id,
            stage=new_stage,
            entered_at=datetime.now(),
            notes=notes or f"Manual admin override from {old_stage} to {new_stage}"
        )
        db.session.add(stage_entry)

        # Close previous stage
        prev_stage = db.session.query(LeadFunnelStage).filter(
            LeadFunnelStage.lead_id == lead_id,
            LeadFunnelStage.stage == old_stage,
            LeadFunnelStage.exited_at.is_(None)
        ).first()

        if prev_stage:
            prev_stage.exited_at = datetime.now()

        db.session.commit()

        return jsonify({
            "success": True,
            "lead_id": lead_id,
            "old_stage": old_stage,
            "new_stage": new_stage,
            "stage_history_id": stage_entry.id,
            "message": f"Lead moved from {old_stage} to {new_stage}"
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@v1.route("/admin/funnel/analyze-churn", methods=["POST"])
@jwt_required()
def analyze_churn():
    """
    Run churn analysis for a specific customer.

    Body:
        lead_id: Lead UUID (must be in retention stage)

    Returns:
        Churn analysis results
    """
    if not _require_admin():
        return jsonify({"error": "forbidden"}), 403

    payload = _safe_json()
    lead_id = payload.get("lead_id")

    if not lead_id:
        return jsonify({"error": "lead_id required"}), 400

    lead = db.session.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        return jsonify({"error": f"Lead {lead_id} not found"}), 404

    if lead.current_funnel_stage != "retention":
        return jsonify({"error": "Lead must be in retention stage"}), 400

    # Run churn analysis for this specific lead
    # (In production, would use MCP server)
    from src.celery_inboxiq import celery
    task = celery.send_task('funnel.churn_risk_analysis')

    return jsonify({
        "success": True,
        "task_id": task.id,
        "lead_id": lead_id,
        "message": "Churn analysis queued"
    }), 202


@v1.route("/admin/funnel/metrics", methods=["GET"])
@jwt_required()
def get_metrics():
    """
    Get funnel metrics for admin dashboard.

    Query params:
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)
        stage: Filter by stage (optional)

    Returns:
        Funnel metrics
    """
    if not _require_admin():
        return jsonify({"error": "forbidden"}), 403

    from datetime import date, timedelta

    start_date = request.args.get("start_date", (date.today() - timedelta(days=30)).isoformat())
    end_date = request.args.get("end_date", date.today().isoformat())
    stage = request.args.get("stage")

    # Get stage distribution
    stage_query = db.session.query(
        Lead.current_funnel_stage,
        db.func.count(Lead.id).label('count')
    ).group_by(Lead.current_funnel_stage).all()

    stage_distribution = {row.current_funnel_stage: row.count for row in stage_query}

    # Get daily metrics (if available)
    metrics_query = db.session.query(FunnelMetricsDaily).filter(
        FunnelMetricsDaily.metric_date >= start_date,
        FunnelMetricsDaily.metric_date <= end_date
    )

    if stage:
        metrics_query = metrics_query.filter(FunnelMetricsDaily.stage == stage)

    daily_metrics = [m.to_dict() for m in metrics_query.all()]

    # Calculate conversion rates
    total_visits = stage_distribution.get('visits', 0)
    total_discovery = stage_distribution.get('discovery', 0)
    total_consideration = stage_distribution.get('consideration', 0)
    total_conversion = stage_distribution.get('conversion', 0)
    total_retention = stage_distribution.get('retention', 0)

    conversion_rates = {
        "visits_to_discovery": (total_discovery / total_visits * 100) if total_visits > 0 else 0,
        "discovery_to_consideration": (total_consideration / total_discovery * 100) if total_discovery > 0 else 0,
        "consideration_to_conversion": (total_conversion / total_consideration * 100) if total_consideration > 0 else 0,
        "conversion_to_retention": (total_retention / total_conversion * 100) if total_conversion > 0 else 0
    }

    return jsonify({
        "start_date": start_date,
        "end_date": end_date,
        "stage_distribution": stage_distribution,
        "conversion_rates": conversion_rates,
        "daily_metrics": daily_metrics,
        "total_leads": sum(stage_distribution.values())
    }), 200


@v1.route("/admin/funnel/orchestrate", methods=["POST"])
@jwt_required()
def orchestrate():
    """
    Manually trigger full funnel orchestration job.

    This runs:
    - Stage progression checks
    - Churn analysis (if Monday)

    Returns:
        Orchestration job results
    """
    if not _require_admin():
        return jsonify({"error": "forbidden"}), 403

    from src.celery_inboxiq import celery
    task = celery.send_task('funnel.orchestration_job')

    return jsonify({
        "success": True,
        "task_id": task.id,
        "message": "Funnel orchestration job queued"
    }), 202


@v1.route("/admin/funnel/check-progression", methods=["POST"])
@jwt_required()
def check_progression():
    """
    Check all leads for stage progression opportunities.

    Returns:
        Progression check results
    """
    if not _require_admin():
        return jsonify({"error": "forbidden"}), 403

    from src.celery_inboxiq import celery
    task = celery.send_task('funnel.check_stage_progression')

    return jsonify({
        "success": True,
        "task_id": task.id,
        "message": "Stage progression check queued"
    }), 202
