"""
Celery tasks for Funnel Orchestration Agent

Automated tasks for:
- Lead discovery via web search
- Lead qualification
- Interest scoring
- Stage progression checks
- Churn risk analysis
"""
import os
import json
import asyncio
from datetime import datetime, timedelta
from celery import shared_task

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
    results = {
        "timestamp": datetime.now().isoformat(),
        "niche": niche,
        "discovered": 0,
        "enriched": 0,
        "errors": []
    }

    # Feature gate (quota incremented per lead found below, not here)
    if account_id:
        try:
            from src.features import feature_enabled
            from src.billing.quota import FeatureDisabled
            if not feature_enabled("lead_discovery", int(account_id)):
                return {**results, "status": "error", "error": "Lead discovery is not available on your current plan."}
        except FeatureDisabled as _fd:
            return {**results, "status": "error", "error": str(_fd)}
        except Exception as _qe:
            import logging as _log
            _log.getLogger(__name__).warning("Feature check failed for lead_discovery account=%s: %s", account_id, _qe)

    try:
        # Import lead discovery MCP tools dynamically
        from src.mcp.lead_discovery_mcp import discover_companies

        # Run async discovery in sync context
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            discovery_results = loop.run_until_complete(
                discover_companies(
                    query=niche,
                    niche=niche,
                    max_results=max_leads
                )
            )
        finally:
            loop.close()

        # Process discovered companies
        for company in discovery_results.get("companies", []):
            domain = company.get("domain")
            company_name = company.get("name")

            if not domain or not company_name:
                continue

            # Check if lead already exists (by company_name since no company_domain field)
            existing = db.session.query(Lead).filter(
                Lead.company_name == company_name,
                Lead.source == "searxng_discovery"
            ).first()

            if existing:
                results["errors"].append(f"Lead already exists: {company_name}")
                continue

            # Create new lead
            # Note: name, email, and status are required fields
            lead = Lead(
                name=company_name,  # Use company name as lead name
                email=f"contact@{domain}",  # Generate placeholder email from domain
                company_name=company_name,
                source="searxng_discovery",
                status="New Lead",  # Required enum field
                current_funnel_stage=VISITS,
                fit_score=5,  # Default, will be updated by qualification
                notes=f"Auto-discovered via search: {niche}\nDomain: {domain}\nURL: {company.get('url', '')}"
            )

            db.session.add(lead)
            db.session.flush()  # Get the lead ID

            # Create initial funnel stage entry
            stage_entry = LeadFunnelStage(
                lead_id=str(lead.id),
                stage=VISITS,
                entered_at=datetime.now(),
                notes=f"Discovered via web search for: {niche}"
            )
            db.session.add(stage_entry)

            results["discovered"] += 1

            # Count one lead discovered against plan quota
            if account_id:
                try:
                    from src.billing.quota import check_and_increment
                    check_and_increment("leads_discovered", int(account_id))
                except Exception as _qe:
                    import logging as _log
                    _log.getLogger(__name__).warning("Quota increment failed for leads_discovered account=%s: %s", account_id, _qe)

            # Trigger enrichment for new lead
            try:
                from src.leads.tasks import enrich_lead, enrich_lead_with_email

                # Enrich company data (about page, contact page, etc.)
                enrich_lead.apply_async(args=[str(lead.id)], queue='leads')

                # Enrich email address via Hunter.io (if API key configured)
                enrich_lead_with_email.apply_async(
                    args=[str(lead.id), domain],
                    queue='leads',
                    countdown=5  # Wait 5s to avoid rate limits
                )

                results["enriched"] += 1
            except ImportError:
                # If enrichment tasks don't exist, skip
                pass
            except Exception as e:
                results["errors"].append(f"Enrichment failed for {lead.id}: {str(e)}")

        db.session.commit()

        return results

    except Exception as e:
        db.session.rollback()
        results["errors"].append(str(e))
        return results


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
    results = {
        "timestamp": datetime.now().isoformat(),
        "niche": niche,
        "signal_type": signal_type,
        "signals_found": 0,
        "leads_updated": 0,
        "errors": []
    }

    try:
        from src.mcp.lead_discovery_mcp import find_buying_signals

        # Run async search
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            signal_results = loop.run_until_complete(
                find_buying_signals(
                    niche=niche,
                    signal_type=signal_type,
                    max_results=max_results
                )
            )
        finally:
            loop.close()

        _JOB_BOARD_DOMAINS = {
            "linkedin.com", "greenhouse.io", "boards.greenhouse.io", "lever.co",
            "jobs.lever.co", "indeed.com", "glassdoor.com", "ziprecruiter.com",
            "workday.com", "jobs.com", "monster.com", "wellfound.com", "angel.co",
        }

        # Process signals
        for signal in signal_results.get("signals", []):
            domain = signal.get("domain")
            company_name = signal.get("company_name")

            if not domain:
                continue

            # Skip job board domains — they are never the actual company domain
            if domain in _JOB_BOARD_DOMAINS or any(
                domain.endswith(f".{jb}") for jb in _JOB_BOARD_DOMAINS
            ):
                results["errors"].append(f"Skipped job board domain: {domain} ({company_name})")
                continue

            results["signals_found"] += 1

            # Find existing lead or create new one
            lead = db.session.query(Lead).filter(
                Lead.company_name == company_name
            ).first()

            if not lead:
                # Create new lead from buying signal
                lead = Lead(
                    name=company_name,
                    email=f"contact@{domain}",  # Placeholder - will be enriched
                    company_name=company_name,
                    source="buying_signal_discovery",
                    status="New Lead",
                    current_funnel_stage=VISITS,
                    fit_score=7,  # Higher score for buying signals
                    notes=f"Discovered via buying signal: {signal_type}\nSignal: {signal.get('title', 'N/A')}\nURL: {signal.get('url', 'N/A')}"
                )
                db.session.add(lead)
                db.session.flush()

                # Create initial funnel stage entry
                stage_entry = LeadFunnelStage(
                    lead_id=str(lead.id),
                    stage=VISITS,
                    entered_at=datetime.now(),
                    notes=f"Discovered via {signal_type} signal in {niche}"
                )
                db.session.add(stage_entry)

                # Trigger email enrichment for new lead
                try:
                    from src.leads.tasks import enrich_lead_with_email
                    enrich_lead_with_email.apply_async(
                        args=[str(lead.id), domain],
                        queue='leads',
                        countdown=10  # Wait 10s between requests
                    )
                except Exception as e:
                    results["errors"].append(f"Email enrichment failed for {lead.id}: {str(e)}")

            if lead:
                # Create engagement event for buying signal
                event = LeadEngagementEvent(
                    lead_id=str(lead.id),
                    event_type=f"buying_signal_{signal_type}",
                    event_data={
                        "signal_type": signal_type,
                        "title": signal.get("title"),
                        "url": signal.get("url"),
                        "snippet": signal.get("snippet")
                    },
                    created_at=datetime.now()
                )
                db.session.add(event)

                # Increment engagement count
                lead.engagement_count = (lead.engagement_count or 0) + 1
                lead.last_engagement_at = datetime.now()

                # Boost intent score for strong buying signals
                if signal_type == "hiring" and lead.intent_score:
                    lead.intent_score = min(lead.intent_score + 2, 10)

                results["leads_updated"] += 1

        db.session.commit()

        return results

    except Exception as e:
        db.session.rollback()
        results["errors"].append(str(e))
        return results


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
