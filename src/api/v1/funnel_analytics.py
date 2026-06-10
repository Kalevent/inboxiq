"""
Public Funnel Analytics API endpoints

User-facing endpoints for funnel metrics and analytics.
All endpoints require JWT authentication.
Note: Multi-tenancy (account scoping) not yet implemented.

Endpoints:
- GET /api/v1/funnel/metrics - Get funnel metrics by stage/date/source
- GET /api/v1/funnel/conversion-rates - Stage-to-stage conversion percentages
- GET /api/v1/funnel/attribution - Top channels by conversions
- GET /api/v1/funnel/velocity - Average time spent in each stage
- GET /api/v1/funnel/cohorts - Cohort retention analysis
"""
from datetime import date, timedelta
from flask import jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy import func

from src.api.v1 import v1
from src.extensions import db
from src.funnel.stages import VISITS
from src.models.leads import Lead, LeadFunnelStage, FunnelMetricsDaily


@v1.route("/funnel/metrics", methods=["GET"])
@jwt_required()
def get_funnel_metrics():
    """
    Get funnel metrics by stage/date/source.

    Query params:
        start_date: Start date (YYYY-MM-DD), defaults to 30 days ago
        end_date: End date (YYYY-MM-DD), defaults to today
        source: Filter by source (optional)
        campaign: Filter by campaign (optional)

    Returns:
        Funnel metrics with stage distribution, conversion rates, daily metrics
    """
    account_id = get_jwt_identity()
    if not account_id:
        return jsonify({"error": "unauthorized"}), 401

    # Parse query params
    start_date_str = request.args.get("start_date", (date.today() - timedelta(days=30)).isoformat())
    end_date_str = request.args.get("end_date", date.today().isoformat())
    source = request.args.get("source")
    campaign = request.args.get("campaign")

    try:
        start_date = date.fromisoformat(start_date_str)
        end_date = date.fromisoformat(end_date_str)
    except ValueError:
        return jsonify({"error": "Invalid date format. Use YYYY-MM-DD"}), 400

    # Build base query (no account filtering - multi-tenancy not implemented yet)
    base_query = db.session.query(Lead)

    # Apply filters if provided
    if source:
        base_query = base_query.filter(Lead.first_attribution_source == source)
    if campaign:
        base_query = base_query.filter(Lead.first_attribution_campaign == campaign)

    # Get stage distribution
    stage_query = base_query.with_entities(
        Lead.current_funnel_stage,
        func.count(Lead.id).label('count')
    ).group_by(Lead.current_funnel_stage).all()

    stage_distribution = {row.current_funnel_stage or 'visits': row.count for row in stage_query}

    # Ensure all stages present in response (even if 0)
    for stage in ['visits', 'discovery', 'consideration', 'conversion', 'retention']:
        if stage not in stage_distribution:
            stage_distribution[stage] = 0

    # Get daily metrics from aggregated table
    metrics_query = db.session.query(FunnelMetricsDaily).filter(
        FunnelMetricsDaily.metric_date >= start_date,
        FunnelMetricsDaily.metric_date <= end_date
    )

    if source:
        metrics_query = metrics_query.filter(FunnelMetricsDaily.source == source)
    if campaign:
        metrics_query = metrics_query.filter(FunnelMetricsDaily.campaign == campaign)

    daily_metrics = []
    for m in metrics_query.order_by(FunnelMetricsDaily.metric_date.asc()).all():
        daily_metrics.append({
            "date": m.metric_date.isoformat() if m.metric_date else None,
            "stage": m.stage,
            "entries": m.entries,
            "exits": m.exits,
            "conversions": m.conversions_to_next,
            "conversion_rate": m.conversion_rate,
            "avg_time_hours": m.avg_time_in_stage_hours
        })

    # Calculate conversion rates
    total_visits = stage_distribution.get('visits', 0)
    total_discovery = stage_distribution.get('discovery', 0)
    total_consideration = stage_distribution.get('consideration', 0)
    total_conversion = stage_distribution.get('conversion', 0)
    total_retention = stage_distribution.get('retention', 0)

    conversion_rates = {
        "visits_to_discovery": round((total_discovery / total_visits * 100) if total_visits > 0 else 0, 2),
        "discovery_to_consideration": round((total_consideration / total_discovery * 100) if total_discovery > 0 else 0, 2),
        "consideration_to_conversion": round((total_conversion / total_consideration * 100) if total_consideration > 0 else 0, 2),
        "conversion_to_retention": round((total_retention / total_conversion * 100) if total_conversion > 0 else 0, 2)
    }

    return jsonify({
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "stage_distribution": stage_distribution,
        "conversion_rates": conversion_rates,
        "daily_metrics": daily_metrics,
        "total_leads": sum(stage_distribution.values()),
        "filters": {
            "source": source,
            "campaign": campaign
        }
    }), 200


@v1.route("/funnel/conversion-rates", methods=["GET"])
@jwt_required()
def get_conversion_rates():
    """
    Get detailed stage-to-stage conversion rates.

    Query params:
        start_date: Start date (YYYY-MM-DD), defaults to 30 days ago
        end_date: End date (YYYY-MM-DD), defaults to today

    Returns:
        Detailed conversion rates with counts for each stage transition
    """
    account_id = get_jwt_identity()
    if not account_id:
        return jsonify({"error": "unauthorized"}), 401

    start_date_str = request.args.get("start_date", (date.today() - timedelta(days=30)).isoformat())
    end_date_str = request.args.get("end_date", date.today().isoformat())

    try:
        start_date = date.fromisoformat(start_date_str)
        end_date = date.fromisoformat(end_date_str)
    except ValueError:
        return jsonify({"error": "Invalid date format. Use YYYY-MM-DD"}), 400

    # Get leads that moved through stages in date range
    stage_movements = db.session.query(
        LeadFunnelStage.stage,
        func.count(LeadFunnelStage.id).label('count')
    ).join(Lead, LeadFunnelStage.lead_id == Lead.id).filter(
        
        LeadFunnelStage.entered_at >= start_date,
        LeadFunnelStage.entered_at <= end_date
    ).group_by(LeadFunnelStage.stage).all()

    stage_counts = {row.stage: row.count for row in stage_movements}

    # Calculate conversion rates
    visits = stage_counts.get('visits', 0)
    discovery = stage_counts.get('discovery', 0)
    consideration = stage_counts.get('consideration', 0)
    conversion = stage_counts.get('conversion', 0)
    retention = stage_counts.get('retention', 0)

    conversions = [
        {
            "from_stage": "visits",
            "to_stage": "discovery",
            "from_count": visits,
            "to_count": discovery,
            "conversion_rate": round((discovery / visits * 100) if visits > 0 else 0, 2)
        },
        {
            "from_stage": "discovery",
            "to_stage": "consideration",
            "from_count": discovery,
            "to_count": consideration,
            "conversion_rate": round((consideration / discovery * 100) if discovery > 0 else 0, 2)
        },
        {
            "from_stage": "consideration",
            "to_stage": "conversion",
            "from_count": consideration,
            "to_count": conversion,
            "conversion_rate": round((conversion / consideration * 100) if consideration > 0 else 0, 2)
        },
        {
            "from_stage": "conversion",
            "to_stage": "retention",
            "from_count": conversion,
            "to_count": retention,
            "conversion_rate": round((retention / conversion * 100) if conversion > 0 else 0, 2)
        }
    ]

    return jsonify({
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "conversions": conversions,
        "overall_conversion_rate": round((retention / visits * 100) if visits > 0 else 0, 2)
    }), 200


@v1.route("/funnel/attribution", methods=["GET"])
@jwt_required()
def get_attribution():
    """
    Get top channels by conversions (attribution analysis).

    Query params:
        start_date: Start date (YYYY-MM-DD), defaults to 30 days ago
        end_date: End date (YYYY-MM-DD), defaults to today
        limit: Number of top channels to return (default: 10)

    Returns:
        Top channels with conversion counts and percentages
    """
    account_id = get_jwt_identity()
    if not account_id:
        return jsonify({"error": "unauthorized"}), 401

    start_date_str = request.args.get("start_date", (date.today() - timedelta(days=30)).isoformat())
    end_date_str = request.args.get("end_date", date.today().isoformat())
    limit = int(request.args.get("limit", 10))

    try:
        start_date = date.fromisoformat(start_date_str)
        end_date = date.fromisoformat(end_date_str)
    except ValueError:
        return jsonify({"error": "Invalid date format. Use YYYY-MM-DD"}), 400

    # Get top sources
    source_query = db.session.query(
        Lead.first_attribution_source,
        func.count(Lead.id).label('count')
    ).filter(
        
        Lead.created_at >= start_date,
        Lead.created_at <= end_date,
        Lead.first_attribution_source.isnot(None)
    ).group_by(Lead.first_attribution_source).order_by(func.count(Lead.id).desc()).limit(limit).all()

    total_leads = db.session.query(func.count(Lead.id)).filter(
        
        Lead.created_at >= start_date,
        Lead.created_at <= end_date
    ).scalar()

    top_sources = []
    for row in source_query:
        source_name = row.first_attribution_source
        count = row.count
        percentage = round((count / total_leads * 100) if total_leads > 0 else 0, 2)

        # Get conversion count for this source
        conversions = db.session.query(func.count(Lead.id)).filter(
            
            Lead.first_attribution_source == source_name,
            Lead.current_funnel_stage == 'conversion'
        ).scalar()

        top_sources.append({
            "source": source_name,
            "leads": count,
            "percentage": percentage,
            "conversions": conversions,
            "conversion_rate": round((conversions / count * 100) if count > 0 else 0, 2)
        })

    # Get top campaigns
    campaign_query = db.session.query(
        Lead.first_attribution_campaign,
        func.count(Lead.id).label('count')
    ).filter(
        
        Lead.created_at >= start_date,
        Lead.created_at <= end_date,
        Lead.first_attribution_campaign.isnot(None)
    ).group_by(Lead.first_attribution_campaign).order_by(func.count(Lead.id).desc()).limit(limit).all()

    top_campaigns = []
    for row in campaign_query:
        campaign_name = row.first_attribution_campaign
        count = row.count
        percentage = round((count / total_leads * 100) if total_leads > 0 else 0, 2)

        conversions = db.session.query(func.count(Lead.id)).filter(
            
            Lead.first_attribution_campaign == campaign_name,
            Lead.current_funnel_stage == 'conversion'
        ).scalar()

        top_campaigns.append({
            "campaign": campaign_name,
            "leads": count,
            "percentage": percentage,
            "conversions": conversions,
            "conversion_rate": round((conversions / count * 100) if count > 0 else 0, 2)
        })

    return jsonify({
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "total_leads": total_leads,
        "top_sources": top_sources,
        "top_campaigns": top_campaigns
    }), 200


@v1.route("/funnel/velocity", methods=["GET"])
@jwt_required()
def get_velocity():
    """
    Get average time spent in each funnel stage (velocity metrics).

    Query params:
        start_date: Start date (YYYY-MM-DD), defaults to 30 days ago
        end_date: End date (YYYY-MM-DD), defaults to today

    Returns:
        Average time in hours/days for each stage
    """
    account_id = get_jwt_identity()
    if not account_id:
        return jsonify({"error": "unauthorized"}), 401

    start_date_str = request.args.get("start_date", (date.today() - timedelta(days=30)).isoformat())
    end_date_str = request.args.get("end_date", date.today().isoformat())

    try:
        start_date = date.fromisoformat(start_date_str)
        end_date = date.fromisoformat(end_date_str)
    except ValueError:
        return jsonify({"error": "Invalid date format. Use YYYY-MM-DD"}), 400

    # Calculate average time in each stage
    # For completed stages (those that exited), calculate time from entered_at to exited_at
    velocity_query = db.session.query(
        LeadFunnelStage.stage,
        func.avg(
            func.extract('epoch', LeadFunnelStage.exited_at - LeadFunnelStage.entered_at) / 3600
        ).label('avg_hours')
    ).join(Lead, LeadFunnelStage.lead_id == Lead.id).filter(
        
        LeadFunnelStage.entered_at >= start_date,
        LeadFunnelStage.entered_at <= end_date,
        LeadFunnelStage.exited_at.isnot(None)  # Only completed stages
    ).group_by(LeadFunnelStage.stage).all()

    velocity_metrics = []
    total_avg_hours = 0
    stage_count = 0

    for row in velocity_query:
        stage_name = row.stage
        avg_hours = float(row.avg_hours) if row.avg_hours else 0
        avg_days = round(avg_hours / 24, 2)

        velocity_metrics.append({
            "stage": stage_name,
            "avg_hours": round(avg_hours, 2),
            "avg_days": avg_days
        })

        total_avg_hours += avg_hours
        stage_count += 1

    # Calculate overall average time from visits to retention
    overall_avg_hours = round(total_avg_hours, 2)
    overall_avg_days = round(overall_avg_hours / 24, 2)

    return jsonify({
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "velocity_by_stage": velocity_metrics,
        "overall_avg_hours": overall_avg_hours,
        "overall_avg_days": overall_avg_days
    }), 200


@v1.route("/funnel/cohorts", methods=["GET"])
@jwt_required()
def get_cohorts():
    """
    Get cohort retention analysis.

    Query params:
        entry_date_start: Cohort entry start date (YYYY-MM-DD), defaults to 90 days ago
        entry_date_end: Cohort entry end date (YYYY-MM-DD), defaults to 60 days ago
        cohort_size_days: Days to group cohorts (default: 7 for weekly cohorts)

    Returns:
        Cohort retention metrics showing how cohorts progress through stages
    """
    account_id = get_jwt_identity()
    if not account_id:
        return jsonify({"error": "unauthorized"}), 401

    # Default to 90-60 days ago to allow time for cohorts to progress
    entry_date_start_str = request.args.get("entry_date_start", (date.today() - timedelta(days=90)).isoformat())
    entry_date_end_str = request.args.get("entry_date_end", (date.today() - timedelta(days=60)).isoformat())
    cohort_size_days = int(request.args.get("cohort_size_days", 7))

    try:
        entry_date_start = date.fromisoformat(entry_date_start_str)
        entry_date_end = date.fromisoformat(entry_date_end_str)
    except ValueError:
        return jsonify({"error": "Invalid date format. Use YYYY-MM-DD"}), 400

    # Get leads that entered in the cohort period
    cohort_leads = db.session.query(Lead).filter(
        
        Lead.created_at >= entry_date_start,
        Lead.created_at <= entry_date_end
    ).all()

    # Group by cohort week/period
    cohorts = {}
    for lead in cohort_leads:
        if not lead.created_at:
            continue

        # Calculate cohort key (week number)
        days_since_start = (lead.created_at.date() - entry_date_start).days
        cohort_number = days_since_start // cohort_size_days
        cohort_key = f"cohort_{cohort_number}"

        if cohort_key not in cohorts:
            cohorts[cohort_key] = {
                "cohort_name": cohort_key,
                "entry_date": (entry_date_start + timedelta(days=cohort_number * cohort_size_days)).isoformat(),
                "total_leads": 0,
                "stage_counts": {
                    "visits": 0,
                    "discovery": 0,
                    "consideration": 0,
                    "conversion": 0,
                    "retention": 0
                }
            }

        cohorts[cohort_key]["total_leads"] += 1
        current_stage = lead.current_funnel_stage or VISITS
        cohorts[cohort_key]["stage_counts"][current_stage] += 1

    # Calculate retention percentages for each cohort
    cohort_list = []
    for cohort_key, cohort_data in sorted(cohorts.items()):
        total = cohort_data["total_leads"]
        stage_counts = cohort_data["stage_counts"]

        retention_rates = {
            "discovery_retention": round((stage_counts["discovery"] / total * 100) if total > 0 else 0, 2),
            "consideration_retention": round((stage_counts["consideration"] / total * 100) if total > 0 else 0, 2),
            "conversion_retention": round((stage_counts["conversion"] / total * 100) if total > 0 else 0, 2),
            "retention_rate": round((stage_counts["retention"] / total * 100) if total > 0 else 0, 2)
        }

        cohort_list.append({
            **cohort_data,
            "retention_rates": retention_rates
        })

    return jsonify({
        "entry_date_start": entry_date_start.isoformat(),
        "entry_date_end": entry_date_end.isoformat(),
        "cohort_size_days": cohort_size_days,
        "total_cohorts": len(cohort_list),
        "cohorts": cohort_list
    }), 200
