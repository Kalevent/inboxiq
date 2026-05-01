"""
Celery tasks for Funnel Orchestration Agent

Automated tasks for:
- Lead discovery via web search
- Lead qualification
- Interest scoring
- Stage progression checks
- Churn risk analysis
"""
import logging
import os
import json
from datetime import datetime, timedelta
from celery import shared_task

log = logging.getLogger(__name__)

from src.extensions import db
from src.funnel.stages import VISITS, DISCOVERY, CONSIDERATION, RETENTION
from src.models.leads import Lead, LeadFunnelStage, LeadEngagementEvent, FunnelMetricsDaily

# Import DSPy modules
try:
    import dspy
    from src.dspy.funnel import (
        VisitorQualificationModule,
        InterestScoringModule,
        BuyingIntentModule,
        DealPredictorModule,
        ChurnPredictorModule
    )
    DSPY_AVAILABLE = True
except ImportError:
    DSPY_AVAILABLE = False


def initialize_dspy():
    """Initialize DSPy with LLM configuration."""
    if not DSPY_AVAILABLE:
        raise RuntimeError("DSPy not available")

    from src.dspy import _configure_dspy
    _configure_dspy()


@shared_task(name="funnel.qualify_visitor")
def qualify_visitor(lead_id: str):
    """
    Qualify a new visitor using VisitorQualificationModule.

    Args:
        lead_id: Lead UUID

    Returns:
        Dict with qualification results
    """
    initialize_dspy()

    lead = db.session.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        return {"error": f"Lead {lead_id} not found"}

    try:
        module = VisitorQualificationModule()

        result = module(
            company_name=lead.company_name or "Unknown",
            company_domain=lead.email.split('@')[1] if lead.email else "unknown.com",
            industry=lead.industry,
            employee_count=str(lead.num_employees) if lead.num_employees else None,
            source=lead.source
        )

        # Update lead with qualification results
        lead.fit_score = int(result.fit_score)
        lead.qualification_status = result.qualification_status

        # Auto-progress to discovery if qualified
        if result.qualification_status == "qualified" and int(result.fit_score) >= 6:
            lead.current_funnel_stage = DISCOVERY
            lead.stage_entered_at = datetime.now()

            # Create stage history entry
            stage_entry = LeadFunnelStage(
                lead_id=lead_id,
                stage=DISCOVERY,
                entered_at=datetime.now(),
                conversion_probability=None,
                notes=f"Auto-qualified with fit score {result.fit_score}"
            )
            db.session.add(stage_entry)

        db.session.commit()

        return {
            "lead_id": lead_id,
            "fit_score": result.fit_score,
            "qualification_status": result.qualification_status,
            "reasoning": result.reasoning,
            "recommended_action": result.recommended_action
        }

    except Exception as e:
        db.session.rollback()
        return {"error": str(e)}


@shared_task(name="funnel.update_interest_score")
def update_interest_score(lead_id: str):
    """
    Update lead interest score based on recent engagement.

    Args:
        lead_id: Lead UUID

    Returns:
        Dict with scoring results
    """
    initialize_dspy()

    lead = db.session.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        return {"error": f"Lead {lead_id} not found"}

    try:
        # Get recent engagement events
        events = db.session.query(LeadEngagementEvent).filter(
            LeadEngagementEvent.lead_id == lead_id
        ).order_by(LeadEngagementEvent.created_at.desc()).limit(50).all()

        engagement_json = json.dumps([{
            "type": e.event_type,
            "timestamp": e.created_at.isoformat()
        } for e in events])

        days_since_first = (datetime.now() - lead.created_at).days if lead.created_at else 0

        module = InterestScoringModule()

        result = module(
            lead_name=lead.name,
            company_name=lead.company_name or "Unknown",
            fit_score=lead.fit_score or 5,
            engagement_events=engagement_json,
            days_since_first_touch=days_since_first,
            total_engagement_count=lead.engagement_count or 0
        )

        # Update lead with interest scoring results
        lead.intent_score = int(result.intent_score)

        # Auto-progress to consideration if intent is high
        if lead.current_funnel_stage == DISCOVERY and int(result.intent_score) >= 8:
            lead.current_funnel_stage = CONSIDERATION
            lead.stage_entered_at = datetime.now()

            stage_entry = LeadFunnelStage(
                lead_id=lead_id,
                stage=CONSIDERATION,
                entered_at=datetime.now(),
                notes=f"Auto-progressed with intent score {result.intent_score}"
            )
            db.session.add(stage_entry)

        db.session.commit()

        return {
            "lead_id": lead_id,
            "intent_score": result.intent_score,
            "interest_level": result.interest_level,
            "reasoning": result.reasoning,
            "recommended_nurture": result.recommended_nurture
        }

    except Exception as e:
        db.session.rollback()
        return {"error": str(e)}


@shared_task(name="funnel.check_stage_progression")
def check_stage_progression():
    """
    Scheduled task: Check all leads for stage progression opportunities.

    Runs every 6 hours to identify leads ready to advance stages.

    Returns:
        Dict with counts of leads progressed
    """
    initialize_dspy()

    results = {
        "visits_to_discovery": 0,
        "discovery_to_consideration": 0,
        "errors": []
    }

    try:
        # Queue qualification for leads that have never been scored (fit_score is null).
        # Without this, new leads are permanently stuck in VISITS because the check
        # below only re-qualifies leads that already have fit_score >= 6.
        unscored_leads = db.session.query(Lead).filter(
            Lead.current_funnel_stage == VISITS,
            Lead.fit_score.is_(None),
            Lead.stage_entered_at < datetime.now() - timedelta(hours=1)
        ).limit(100).all()

        for lead in unscored_leads:
            try:
                qualify_visitor.delay(str(lead.id))
                results["visits_to_discovery"] += 1
            except Exception as e:
                results["errors"].append(f"Qualify {lead.id}: {str(e)}")

        # Check visits → discovery progression for already-scored leads
        visits_leads = db.session.query(Lead).filter(
            Lead.current_funnel_stage == VISITS,
            Lead.fit_score >= 6,
            Lead.stage_entered_at < datetime.now() - timedelta(days=3)
        ).limit(50).all()

        for lead in visits_leads:
            try:
                qualify_visitor.delay(str(lead.id))
                results["visits_to_discovery"] += 1
            except Exception as e:
                results["errors"].append(f"Lead {lead.id}: {str(e)}")

        # Check discovery → consideration progression
        discovery_leads = db.session.query(Lead).filter(
            Lead.current_funnel_stage == DISCOVERY,
            Lead.intent_score >= 8,
            Lead.engagement_count >= 5,
            Lead.stage_entered_at < datetime.now() - timedelta(days=7)
        ).limit(50).all()

        for lead in discovery_leads:
            try:
                result = update_interest_score.delay(lead.id)
                results["discovery_to_consideration"] += 1
            except Exception as e:
                results["errors"].append(f"Lead {lead.id}: {str(e)}")

        return results

    except Exception as e:
        return {"error": str(e), "results": results}


@shared_task(name="funnel.churn_risk_analysis")
def churn_risk_analysis():
    """
    Scheduled task: Analyze churn risk for customers in retention stage.

    Runs weekly on Mondays to identify at-risk customers.

    Returns:
        Dict with count of at-risk customers and actions taken
    """
    initialize_dspy()

    results = {
        "analyzed": 0,
        "high_risk": 0,
        "critical_risk": 0,
        "actions_triggered": [],
        "errors": []
    }

    try:
        # Get customers in retention stage
        retention_customers = db.session.query(Lead).filter(
            Lead.current_funnel_stage == RETENTION
        ).limit(100).all()

        module = ChurnPredictorModule()

        for lead in retention_customers:
            try:
                # Prepare usage data (placeholder - would come from actual product usage)
                product_usage = json.dumps({
                    "last_login_days_ago": 7,
                    "monthly_active_days": 12,
                    "features_used": 5,
                    "total_features": 10,
                    "support_tickets_open": 0,
                    "support_tickets_resolved": 3,
                    "nps_score": 8,
                    "adoption_rate": 0.5
                })

                days_since_conversion = (datetime.now() - lead.stage_entered_at).days if lead.stage_entered_at else 30

                result = module(
                    lead_name=lead.name,
                    company_name=lead.company_name or "Unknown",
                    days_since_conversion=days_since_conversion,
                    product_usage=product_usage,
                    engagement_trend="stable",
                    recent_engagement_count=lead.engagement_count or 0,
                    last_engagement_days_ago=(datetime.now() - lead.last_engagement_at).days if lead.last_engagement_at else 30,
                    contract_renewal_days=90,
                    expansion_opportunities=False,
                    negative_sentiment_detected=False
                )

                churn_prob = float(result.churn_probability)

                results["analyzed"] += 1

                if churn_prob >= 0.7:
                    results["critical_risk"] += 1
                    results["actions_triggered"].append({
                        "lead_id": lead.id,
                        "action": "executive_escalation",
                        "churn_probability": churn_prob
                    })
                elif churn_prob >= 0.5:
                    results["high_risk"] += 1
                    results["actions_triggered"].append({
                        "lead_id": lead.id,
                        "action": "check_in_call",
                        "churn_probability": churn_prob
                    })

            except Exception as e:
                results["errors"].append(f"Lead {lead.id}: {str(e)}")

        return results

    except Exception as e:
        return {"error": str(e), "results": results}


@shared_task(name="funnel.discover_leads_via_search")
def discover_leads_via_search(niche: str, max_leads: int = 50, account_id: str = None):
    """
    Discover new leads via SearXNG-powered web search.

    Uses the Lead Discovery MCP server to find companies in the specified niche,
    creates new lead records, and triggers enrichment.

    Args:
        niche: Industry/niche to target (e.g., "B2B SaaS revenue operations")
        max_leads: Maximum number of leads to discover (default: 50)
        account_id: Account ID to assign leads to (optional, for future multi-tenancy)

    Returns:
        Dict with discovery results
    """
    from src.agents.funnel_discovery import FunnelDiscoveryAgent
    from src.models.core import Account

    goal = (
        f"Discover companies matching ICP in niche '{niche}'. "
        f"Call get_icp_config first. Then call discover_companies via MCP. "
        f"For each result not in get_existing_companies, call save_lead. "
        f"Limit to {max_leads} new leads."
    )

    if account_id:
        FunnelDiscoveryAgent(account_id=int(account_id)).execute(goal)
    else:
        for row in db.session.query(Account.id).all():
            try:
                FunnelDiscoveryAgent(account_id=row.id).execute(goal)
            except Exception:
                log.exception("discover_leads_via_search failed for account_id=%s", row.id)

    return {"status": "ok", "niche": niche}


@shared_task(name="funnel.discover_buying_signals")
def discover_buying_signals(niche: str, signal_type: str = "hiring", max_results: int = 20):
    """
    Find companies showing buying signals (hiring, funding, expansion).

    Identifies companies with budget availability indicators and creates
    engagement events for existing leads or discovers new ones.

    Args:
        niche: Industry to search (e.g., "B2B SaaS")
        signal_type: "hiring", "funding", or "expansion"
        max_results: Maximum signals to discover (default: 20)

    Returns:
        Dict with buying signals found
    """
    from src.agents.funnel_discovery import FunnelDiscoveryAgent
    from src.models.core import Account

    goal = (
        f"Find companies showing '{signal_type}' buying signals in niche '{niche}'. "
        f"Use find_buying_signals via MCP. For each company not already in "
        f"get_existing_companies, call save_lead with source='buying_signal' "
        f"and relevant notes. Limit to {max_results} signals."
    )

    for row in db.session.query(Account.id).all():
        try:
            FunnelDiscoveryAgent(account_id=row.id).execute(goal)
        except Exception:
            log.exception("discover_buying_signals failed for account_id=%s", row.id)

    return {"status": "ok", "niche": niche, "signal_type": signal_type}


@shared_task(name="funnel.orchestration_job")
def funnel_orchestration_job():
    """
    Main orchestration job that runs periodically.

    Replaces the old sourcing_job from leads.tasks.
    """
    results = {
        "timestamp": datetime.now().isoformat(),
        "stage_progression": None,
        "churn_analysis": None,
        "errors": []
    }

    try:
        # Run stage progression check
        results["stage_progression"] = check_stage_progression()

        # Run churn analysis (only on Mondays)
        if datetime.now().weekday() == 0:  # Monday
            results["churn_analysis"] = churn_risk_analysis()

        return results

    except Exception as e:
        results["errors"].append(str(e))
        return results


@shared_task(name="funnel.aggregate_daily_metrics")
def aggregate_daily_metrics():
    """
    Aggregate funnel metrics for the previous day.

    Populates funnel_metrics_daily table with:
    - Entries per stage
    - Exits per stage
    - Conversions to next stage
    - Conversion rates
    - Average time in stage

    Runs daily at 1am UTC.

    Returns:
        Dict with aggregation results
    """
    yesterday = (datetime.now() - timedelta(days=1)).date()

    results = {
        "date": yesterday.isoformat(),
        "stages_aggregated": 0,
        "errors": []
    }

    try:
        # Get all stage entries for yesterday
        stage_entries = db.session.query(
            LeadFunnelStage.stage,
            db.func.count(LeadFunnelStage.id).label('count')
        ).filter(
            db.func.date(LeadFunnelStage.entered_at) == yesterday
        ).group_by(LeadFunnelStage.stage).all()

        # Get all stage exits for yesterday
        stage_exits = db.session.query(
            LeadFunnelStage.stage,
            db.func.count(LeadFunnelStage.id).label('count')
        ).filter(
            LeadFunnelStage.exited_at.isnot(None),
            db.func.date(LeadFunnelStage.exited_at) == yesterday
        ).group_by(LeadFunnelStage.stage).all()

        # Convert to dicts for easy lookup
        entries_dict = {row.stage: row.count for row in stage_entries}
        exits_dict = {row.stage: row.count for row in stage_exits}

        # Calculate average time in each stage (for stages that exited)
        avg_times = db.session.query(
            LeadFunnelStage.stage,
            db.func.avg(
                db.func.extract('epoch', LeadFunnelStage.exited_at - LeadFunnelStage.entered_at) / 3600
            ).label('avg_hours')
        ).filter(
            LeadFunnelStage.exited_at.isnot(None),
            db.func.date(LeadFunnelStage.exited_at) == yesterday
        ).group_by(LeadFunnelStage.stage).all()

        avg_times_dict = {row.stage: float(row.avg_hours) if row.avg_hours else 0 for row in avg_times}

        # Calculate conversions (leads that moved to next stage)
        # This is approximate - just count entries to next stages
        stage_order = ['visits', 'discovery', 'consideration', 'conversion', 'retention']
        stage_to_next = {
            'visits': 'discovery',
            'discovery': 'consideration',
            'consideration': 'conversion',
            'conversion': 'retention'
        }

        # For each stage, save or update metrics
        for stage in stage_order:
            entries = entries_dict.get(stage, 0)
            exits = exits_dict.get(stage, 0)
            avg_hours = avg_times_dict.get(stage, 0.0)

            # Calculate conversions to next stage
            next_stage = stage_to_next.get(stage)
            conversions = entries_dict.get(next_stage, 0) if next_stage else 0

            # Calculate conversion rate
            conversion_rate = (conversions / entries * 100) if entries > 0 else 0.0

            # Check if metric already exists for this date/stage
            existing_metric = db.session.query(FunnelMetricsDaily).filter(
                FunnelMetricsDaily.metric_date == yesterday,
                FunnelMetricsDaily.stage == stage,
                FunnelMetricsDaily.source.is_(None),
                FunnelMetricsDaily.campaign.is_(None)
            ).first()

            if existing_metric:
                # Update existing
                existing_metric.entries = entries
                existing_metric.exits = exits
                existing_metric.conversions_to_next = conversions
                existing_metric.conversion_rate = conversion_rate
                existing_metric.avg_time_in_stage_hours = avg_hours
            else:
                # Create new
                metric = FunnelMetricsDaily(
                    metric_date=yesterday,
                    stage=stage,
                    source=None,  # Aggregate across all sources
                    campaign=None,  # Aggregate across all campaigns
                    entries=entries,
                    exits=exits,
                    conversions_to_next=conversions,
                    conversion_rate=conversion_rate,
                    avg_time_in_stage_hours=avg_hours,
                    total_cost=None,
                    cost_per_entry=None
                )
                db.session.add(metric)

            results["stages_aggregated"] += 1

        db.session.commit()

        return results

    except Exception as e:
        db.session.rollback()
        results["errors"].append(str(e))
        return results
