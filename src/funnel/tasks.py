"""
Celery tasks for Funnel Orchestration Agent

Automated tasks for:
- Lead qualification
- Interest scoring
- Stage progression checks
- Churn risk analysis
"""
import os
import json
from datetime import datetime, timedelta
from celery import shared_task

from src.extensions import db
from src.models import Lead, LeadFunnelStage, LeadEngagementEvent

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
            lead.current_funnel_stage = "discovery"
            lead.stage_entered_at = datetime.now()

            # Create stage history entry
            stage_entry = LeadFunnelStage(
                lead_id=lead_id,
                stage="discovery",
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
        if lead.current_funnel_stage == "discovery" and int(result.intent_score) >= 8:
            lead.current_funnel_stage = "consideration"
            lead.stage_entered_at = datetime.now()

            stage_entry = LeadFunnelStage(
                lead_id=lead_id,
                stage="consideration",
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
        # Check visits → discovery progression
        visits_leads = db.session.query(Lead).filter(
            Lead.current_funnel_stage == "visits",
            Lead.fit_score >= 6,
            Lead.stage_entered_at < datetime.now() - timedelta(days=3)
        ).limit(50).all()

        for lead in visits_leads:
            try:
                result = qualify_visitor.delay(lead.id)
                results["visits_to_discovery"] += 1
            except Exception as e:
                results["errors"].append(f"Lead {lead.id}: {str(e)}")

        # Check discovery → consideration progression
        discovery_leads = db.session.query(Lead).filter(
            Lead.current_funnel_stage == "discovery",
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
            Lead.current_funnel_stage == "retention"
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
