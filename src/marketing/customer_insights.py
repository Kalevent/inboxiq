"""
Customer insights extraction using DSPy intelligence.

Analyzes customer conversations, feedback, and behavior to extract:
- Feature requests and priorities
- Pain points and use cases
- Sentiment and satisfaction trends
- Competitive intelligence

Uses DSPy to process:
- Support tickets and conversations
- Trial onboarding feedback
- Demo notes and sales conversations
- Product usage patterns
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Any, Optional
import dspy

from src.extensions import db
from src.models.core import User, Account
from src.models.leads import Lead
from src.models.tickets import Ticket

logger = logging.getLogger(__name__)


class FeatureRequestExtractor(dspy.Signature):
    """
    Extract feature requests from customer conversations.

    Identifies explicit and implicit feature requests, pain points, and use cases.
    """
    conversation_text = dspy.InputField(desc="Customer conversation or ticket content")
    customer_industry = dspy.InputField(desc="Customer's industry/vertical")
    customer_role = dspy.InputField(desc="Customer's role/title")
    conversation_context = dspy.InputField(desc="Context: trial, support_ticket, demo, feedback")

    feature_requests = dspy.OutputField(desc="Comma-separated list of requested features")
    pain_points = dspy.OutputField(desc="Comma-separated list of pain points mentioned")
    use_cases = dspy.OutputField(desc="Specific use case scenarios described")
    urgency = dspy.OutputField(desc="Urgency level: low, medium, high, critical")
    sentiment = dspy.OutputField(desc="Overall sentiment: negative, neutral, positive, enthusiastic")


class FeaturePrioritizer(dspy.Signature):
    """
    Prioritize features based on customer feedback.

    Analyzes aggregate feature requests to determine priorities.
    """
    feature_requests_summary = dspy.InputField(desc="JSON summary of all feature requests: [{feature, count, industries, urgency}]")
    current_roadmap = dspy.InputField(desc="Current planned features (comma-separated)")
    product_vision = dspy.InputField(desc="Product vision and strategic goals")
    resource_constraints = dspy.InputField(desc="Team size and timeline constraints")

    top_priorities = dspy.OutputField(desc="Top 5 features to build next (comma-separated)")
    quick_wins = dspy.OutputField(desc="Low-effort, high-impact features")
    strategic_bets = dspy.OutputField(desc="High-effort features for competitive differentiation")
    reasoning = dspy.OutputField(desc="Prioritization rationale")


class UseCaseAnalyzer(dspy.Signature):
    """
    Analyze and categorize customer use cases.

    Identifies patterns in how customers use or want to use the product.
    """
    use_cases_raw = dspy.InputField(desc="List of raw use case descriptions from customers")
    industry_context = dspy.InputField(desc="Industries represented in data")

    use_case_categories = dspy.OutputField(desc="JSON of categorized use cases: [{category, description, frequency, industries}]")
    emerging_patterns = dspy.OutputField(desc="Comma-separated list of emerging usage patterns")
    vertical_specific_needs = dspy.OutputField(desc="JSON of industry-specific requirements: {healthcare: [...], insurance: [...]}")
    expansion_opportunities = dspy.OutputField(desc="Product expansion opportunities based on use cases")


class CustomerInsightsModule(dspy.Module):
    """
    Complete customer insights intelligence module.

    Processes customer data to extract actionable insights.
    """

    def __init__(self):
        super().__init__()
        self.feature_extractor = dspy.ChainOfThought(FeatureRequestExtractor)
        self.feature_prioritizer = dspy.ChainOfThought(FeaturePrioritizer)
        self.use_case_analyzer = dspy.ChainOfThought(UseCaseAnalyzer)

    def extract_insights_from_ticket(self, ticket: Ticket) -> Dict[str, Any]:
        """
        Extract insights from a support ticket.

        Args:
            ticket: Ticket object

        Returns:
            Extracted insights dict
        """
        # Get customer context
        account = db.session.get(Account, ticket.account_id) if ticket.account_id else None
        industry = account.industry if account and hasattr(account, 'industry') else "unknown"

        # Build conversation text
        conversation_text = f"Subject: {ticket.subject or ''}\n\nBody: {ticket.snippet or ticket.body_preview or ''}"

        # Extract insights
        result = self.feature_extractor(
            conversation_text=conversation_text,
            customer_industry=industry,
            customer_role="unknown",
            conversation_context="support_ticket"
        )

        return {
            "ticket_id": ticket.id,
            "feature_requests": [f.strip() for f in result.feature_requests.split(',') if f.strip()],
            "pain_points": [p.strip() for p in result.pain_points.split(',') if p.strip()],
            "use_cases": result.use_cases,
            "urgency": result.urgency,
            "sentiment": result.sentiment,
            "industry": industry
        }

    def extract_insights_from_lead(self, lead: Lead) -> Dict[str, Any]:
        """
        Extract insights from lead interactions.

        Args:
            lead: Lead object

        Returns:
            Extracted insights dict
        """
        # Build conversation text from lead notes/interactions
        conversation_text = f"Company: {lead.company_name or 'Unknown'}\n"
        conversation_text += f"Pain points: {lead.pain_points or 'Not specified'}\n"
        if hasattr(lead, 'notes') and lead.notes:
            conversation_text += f"Notes: {lead.notes}\n"

        # Extract insights
        result = self.feature_extractor(
            conversation_text=conversation_text,
            customer_industry=lead.industry or "B2B SaaS",
            customer_role=lead.title or "Operations",
            conversation_context="demo"
        )

        return {
            "lead_id": lead.id,
            "feature_requests": [f.strip() for f in result.feature_requests.split(',') if f.strip()],
            "pain_points": [p.strip() for p in result.pain_points.split(',') if p.strip()],
            "use_cases": result.use_cases,
            "urgency": result.urgency,
            "sentiment": result.sentiment,
            "industry": lead.industry
        }


def analyze_recent_customer_feedback(days_back: int = 30) -> Dict[str, Any]:
    """
    Analyze recent customer feedback across all sources.

    Args:
        days_back: Number of days to look back

    Returns:
        Comprehensive insights report
    """
    from src.dspy import _configure_dspy

    # Configure DSPy
    _configure_dspy()

    insights_module = CustomerInsightsModule()

    # Date range
    start_date = datetime.now(timezone.utc) - timedelta(days=days_back)

    # Collect insights from tickets
    recent_tickets = db.session.query(Ticket).filter(
        Ticket.created_at >= start_date,
        Ticket.deleted == False  # noqa: E712
    ).limit(200).all()

    ticket_insights = []
    for ticket in recent_tickets:
        try:
            insight = insights_module.extract_insights_from_ticket(ticket)
            ticket_insights.append(insight)
        except Exception as e:
            logger.error(f"Failed to extract insights from ticket {ticket.id}: {e}")

    # Collect insights from leads
    recent_leads = db.session.query(Lead).filter(
        Lead.created_at >= start_date,
        Lead.deleted == False  # noqa: E712
    ).limit(100).all()

    lead_insights = []
    for lead in recent_leads:
        try:
            insight = insights_module.extract_insights_from_lead(lead)
            lead_insights.append(insight)
        except Exception as e:
            logger.error(f"Failed to extract insights from lead {lead.id}: {e}")

    # Aggregate feature requests
    feature_counts = {}
    pain_point_counts = {}
    use_cases_raw = []
    industries_seen = set()

    for insight in ticket_insights + lead_insights:
        industries_seen.add(insight.get("industry", "unknown"))

        for feature in insight.get("feature_requests", []):
            if feature:
                feature_counts[feature] = feature_counts.get(feature, 0) + 1

        for pain in insight.get("pain_points", []):
            if pain:
                pain_point_counts[pain] = pain_point_counts.get(pain, 0) + 1

        use_case = insight.get("use_cases")
        if use_case:
            use_cases_raw.append(use_case)

    # Analyze sentiment distribution
    sentiment_counts = {
        "negative": sum(1 for i in ticket_insights + lead_insights if i.get("sentiment") == "negative"),
        "neutral": sum(1 for i in ticket_insights + lead_insights if i.get("sentiment") == "neutral"),
        "positive": sum(1 for i in ticket_insights + lead_insights if i.get("sentiment") == "positive"),
        "enthusiastic": sum(1 for i in ticket_insights + lead_insights if i.get("sentiment") == "enthusiastic")
    }

    # Sort features by frequency
    top_features = sorted(feature_counts.items(), key=lambda x: x[1], reverse=True)[:10]
    top_pain_points = sorted(pain_point_counts.items(), key=lambda x: x[1], reverse=True)[:10]

    logger.info(f"Analyzed {len(ticket_insights)} tickets and {len(lead_insights)} leads for insights")

    return {
        "period": {
            "start": start_date.isoformat(),
            "end": datetime.now(timezone.utc).isoformat(),
            "days": days_back
        },
        "data_sources": {
            "tickets_analyzed": len(ticket_insights),
            "leads_analyzed": len(lead_insights),
            "industries_represented": list(industries_seen)
        },
        "feature_requests": {
            "total_unique": len(feature_counts),
            "top_10": [{"feature": f, "mentions": c} for f, c in top_features],
            "all_counts": feature_counts
        },
        "pain_points": {
            "total_unique": len(pain_point_counts),
            "top_10": [{"pain_point": p, "mentions": c} for p, c in top_pain_points],
            "all_counts": pain_point_counts
        },
        "use_cases": {
            "total_collected": len(use_cases_raw),
            "raw_use_cases": use_cases_raw[:50]  # Limit for response size
        },
        "sentiment": sentiment_counts
    }


def generate_feature_roadmap_recommendations(
    current_roadmap: Optional[List[str]] = None,
    resource_constraints: str = "2 engineers, 6-week sprints"
) -> Dict[str, Any]:
    """
    Generate feature roadmap recommendations based on customer insights.

    Args:
        current_roadmap: List of currently planned features
        resource_constraints: Team constraints

    Returns:
        Prioritized feature recommendations
    """
    from src.dspy import _configure_dspy

    # Configure DSPy
    _configure_dspy()

    insights_module = CustomerInsightsModule()

    # Get recent feedback
    feedback = analyze_recent_customer_feedback(days_back=90)

    # Build feature requests summary
    feature_summary = []
    for item in feedback["feature_requests"]["top_10"]:
        feature_summary.append({
            "feature": item["feature"],
            "count": item["mentions"],
            "urgency": "medium"  # Could enhance with urgency analysis
        })

    # Prioritize features
    result = insights_module.feature_prioritizer(
        feature_requests_summary=str(feature_summary),
        current_roadmap=", ".join(current_roadmap or ["No roadmap specified"]),
        product_vision="Intelligent inbox automation with AI-powered triage and workflow automation",
        resource_constraints=resource_constraints
    )

    return {
        "top_priorities": [p.strip() for p in result.top_priorities.split(',')],
        "quick_wins": [q.strip() for q in result.quick_wins.split(',') if q.strip()],
        "strategic_bets": [s.strip() for s in result.strategic_bets.split(',') if s.strip()],
        "reasoning": result.reasoning,
        "based_on": {
            "customer_inputs": len(feedback["data_sources"]["tickets_analyzed"]) + len(feedback["data_sources"]["leads_analyzed"]),
            "time_period": f"Last {feedback['period']['days']} days",
            "industries": feedback["data_sources"]["industries_represented"]
        }
    }


def track_feature_request(
    customer_email: str,
    feature_description: str,
    urgency: str = "medium",
    source: str = "support_ticket"
) -> Dict[str, Any]:
    """
    Track a specific feature request from a customer.

    Args:
        customer_email: Customer email
        feature_description: Description of requested feature
        urgency: low, medium, high, critical
        source: Where request came from

    Returns:
        Tracked feature request record
    """
    # TODO: Implement feature request tracking table
    # For now, log it

    logger.info(f"Feature request from {customer_email}: {feature_description} (urgency: {urgency}, source: {source})")

    return {
        "status": "tracked",
        "customer_email": customer_email,
        "feature": feature_description,
        "urgency": urgency,
        "source": source,
        "tracked_at": datetime.now(timezone.utc).isoformat()
    }


def get_customer_insights_dashboard() -> Dict[str, Any]:
    """
    Get comprehensive customer insights dashboard data.

    Returns:
        Dashboard data with feature requests, pain points, sentiment, etc.
    """
    # Analyze last 30 days
    insights_30d = analyze_recent_customer_feedback(days_back=30)

    # Analyze last 90 days for trends
    insights_90d = analyze_recent_customer_feedback(days_back=90)

    # Generate roadmap recommendations
    roadmap = generate_feature_roadmap_recommendations(
        current_roadmap=[
            "Advanced workflow automation",
            "Multi-inbox support",
            "API integrations"
        ]
    )

    return {
        "last_30_days": insights_30d,
        "last_90_days": {
            "total_feedback_items": insights_90d["data_sources"]["tickets_analyzed"] + insights_90d["data_sources"]["leads_analyzed"],
            "top_features": insights_90d["feature_requests"]["top_10"][:5],
            "sentiment_trend": insights_90d["sentiment"]
        },
        "roadmap_recommendations": roadmap,
        "generated_at": datetime.now(timezone.utc).isoformat()
    }
