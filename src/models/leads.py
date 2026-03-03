from datetime import datetime
from uuid import uuid4
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import TSVECTOR
from src.extensions import db

try:  # Optional pgvector support
    from pgvector.sqlalchemy import Vector  # type: ignore
except Exception:
    Vector = None

class Lead(db.Model):
    """
    Lead model for the new InboxIQ app (independent of legacy schemas).
    Updated for Funnel v2.0 with stage tracking, scoring, and engagement metrics.
    """
    __tablename__ = "leads"
    __table_args__ = (
        db.Index("idx_leads_funnel_stage", "current_funnel_stage", "stage_entered_at"),
        db.Index("idx_leads_last_engagement", "last_engagement_at"),
        db.Index("idx_leads_fit_intent", "fit_score", "intent_score"),
        db.Index("idx_leads_account_id", "account_id"),
    )

    id = db.Column(db.String(64), primary_key=True, default=lambda: str(uuid4()), nullable=False)
    account_id = db.Column(db.Integer, nullable=True, default=2, comment="Multi-tenancy support - default account 2")
    name = db.Column(db.String(255), nullable=False)
    email = db.Column(db.String(255), nullable=False)
    phone = db.Column(db.String(50), nullable=True)
    company_name = db.Column(db.String(255), nullable=True)
    industry = db.Column(db.String(100), nullable=True)
    source = db.Column(db.String(100), nullable=False)
    utm_source = db.Column(db.String(100), nullable=True)
    utm_medium = db.Column(db.String(100), nullable=True)
    utm_campaign = db.Column(db.String(100), nullable=True)
    utm_term = db.Column(db.String(100), nullable=True)
    status = db.Column(
        db.Enum(
            "New Lead",
            "Contacted",
            "Qualified",
            "Closed Won",
            "Closed Lost",
            name="lead_status_enum",
        ),
        nullable=False,
    )
    num_employees = db.Column(db.Integer, nullable=True)
    qualification_status = db.Column(db.String(50), nullable=True)
    score = db.Column(db.Integer, nullable=True)
    follow_up_date = db.Column(db.DateTime(timezone=True), nullable=True)
    first_contact_date = db.Column(db.DateTime(timezone=True), nullable=True)
    next_contact_date = db.Column(db.DateTime(timezone=True), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    campaign_id = db.Column(db.String(64), nullable=True)
    sales_agent_id = db.Column(db.String(64), nullable=True)

    # Funnel v2.0 columns
    current_funnel_stage = db.Column(db.String(50), server_default="visits", comment="visits | discovery | consideration | conversion | retention")
    stage_entered_at = db.Column(db.DateTime(timezone=True), server_default=func.now())
    fit_score = db.Column(db.Integer, server_default="0", comment="ICP fit 0-10")
    intent_score = db.Column(db.Integer, server_default="0", comment="Buying intent 0-12")
    conversion_probability = db.Column(db.Float, nullable=True, comment="DSPy prediction")
    last_engagement_at = db.Column(db.DateTime(timezone=True), nullable=True)
    engagement_count = db.Column(db.Integer, server_default="0")
    first_attribution_source = db.Column(db.String(100), nullable=True)
    first_attribution_campaign = db.Column(db.String(100), nullable=True)
    company_size_bucket = db.Column(db.String(50), nullable=True, comment="50-100, 101-300, 301-500")
    buying_committee_json = db.Column("buying_committee", db.JSON, nullable=True, comment="[{name, title, email, role}]")
    objections_json = db.Column("objections", db.JSON, nullable=True, comment="DSPy-detected objections")
    recommended_assets_json = db.Column("recommended_assets", db.JSON, nullable=True, comment="DSPy recommendations")

    created_at = db.Column(db.DateTime(timezone=True), nullable=True)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "account_id": self.account_id,
            "name": self.name,
            "email": self.email,
            "phone": self.phone,
            "company_name": self.company_name,
            "industry": self.industry,
            "source": self.source,
            "utm_source": self.utm_source,
            "utm_medium": self.utm_medium,
            "utm_campaign": self.utm_campaign,
            "utm_term": self.utm_term,
            "status": self.status,
            "num_employees": self.num_employees,
            "qualification_status": self.qualification_status,
            "score": self.score,
            "follow_up_date": self.follow_up_date.isoformat() if self.follow_up_date else None,
            "first_contact_date": self.first_contact_date.isoformat() if self.first_contact_date else None,
            "next_contact_date": self.next_contact_date.isoformat() if self.next_contact_date else None,
            "notes": self.notes,
            "campaign_id": self.campaign_id,
            "sales_agent_id": self.sales_agent_id,
            # Funnel v2.0 fields
            "current_funnel_stage": self.current_funnel_stage,
            "stage_entered_at": self.stage_entered_at.isoformat() if self.stage_entered_at else None,
            "fit_score": self.fit_score,
            "intent_score": self.intent_score,
            "conversion_probability": self.conversion_probability,
            "last_engagement_at": self.last_engagement_at.isoformat() if self.last_engagement_at else None,
            "engagement_count": self.engagement_count,
            "first_attribution_source": self.first_attribution_source,
            "first_attribution_campaign": self.first_attribution_campaign,
            "company_size_bucket": self.company_size_bucket,
            "buying_committee": self.buying_committee_json or [],
            "objections": self.objections_json or [],
            "recommended_assets": self.recommended_assets_json or [],
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class LeadFunnelStage(db.Model):
    """
    Track lead progression through funnel stages (Visits → Discovery → Consideration → Conversion → Retention).
    Each row represents a single stage entry/exit event for historical tracking.
    """
    __tablename__ = "lead_funnel_stages"
    __table_args__ = (
        db.Index("idx_funnel_stage_lead", "lead_id"),
        db.Index("idx_funnel_stage", "stage", "entered_at"),
    )

    id = db.Column(db.String(64), primary_key=True, default=lambda: str(uuid4()), nullable=False)
    lead_id = db.Column(db.String(64), db.ForeignKey("leads.id", ondelete="CASCADE"), nullable=False)
    stage = db.Column(db.String(50), nullable=False, comment="visits | discovery | consideration | conversion | retention")
    sub_stage = db.Column(db.String(100), nullable=True, comment="e.g. demo_requested, trial_active, onboarding")
    entered_at = db.Column(db.DateTime(timezone=True), nullable=False, server_default=func.now())
    exited_at = db.Column(db.DateTime(timezone=True), nullable=True)
    conversion_probability = db.Column(db.Float, nullable=True, comment="DSPy prediction at entry")
    notes = db.Column(db.Text, nullable=True)
    metadata_json = db.Column("metadata", db.JSON, nullable=True, comment="Stage-specific data")
    created_at = db.Column(db.DateTime(timezone=True), server_default=func.now(), nullable=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "lead_id": self.lead_id,
            "stage": self.stage,
            "sub_stage": self.sub_stage,
            "entered_at": self.entered_at.isoformat() if self.entered_at else None,
            "exited_at": self.exited_at.isoformat() if self.exited_at else None,
            "conversion_probability": self.conversion_probability,
            "notes": self.notes,
            "metadata": self.metadata_json or {},
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class LeadEngagementEvent(db.Model):
    """
    Record all engagement events: email opens, page visits, content downloads, etc.
    Used for engagement scoring and attribution analysis.
    """
    __tablename__ = "lead_engagement_events"
    __table_args__ = (
        db.Index("idx_engagement_lead", "lead_id", "created_at"),
        db.Index("idx_engagement_type", "event_type", "created_at"),
    )

    id = db.Column(db.String(64), primary_key=True, default=lambda: str(uuid4()), nullable=False)
    lead_id = db.Column(db.String(64), db.ForeignKey("leads.id", ondelete="CASCADE"), nullable=False)
    event_type = db.Column(db.String(100), nullable=False, comment="email_open, page_visit, content_download, etc.")
    event_source = db.Column(db.String(100), nullable=True, comment="email_campaign, website, linkedin, etc.")
    event_data = db.Column(db.JSON, nullable=True, comment="URL visited, campaign ID, etc.")
    utm_source = db.Column(db.String(100), nullable=True)
    utm_medium = db.Column(db.String(100), nullable=True)
    utm_campaign = db.Column(db.String(100), nullable=True)
    utm_content = db.Column(db.String(100), nullable=True)
    utm_term = db.Column(db.String(100), nullable=True)
    ip_address = db.Column(db.String(45), nullable=True)
    user_agent = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), server_default=func.now(), nullable=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "lead_id": self.lead_id,
            "event_type": self.event_type,
            "event_source": self.event_source,
            "event_data": self.event_data or {},
            "utm_source": self.utm_source,
            "utm_medium": self.utm_medium,
            "utm_campaign": self.utm_campaign,
            "utm_content": self.utm_content,
            "utm_term": self.utm_term,
            "ip_address": self.ip_address,
            "user_agent": self.user_agent,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class LeadAttribution(db.Model):
    """
    Multi-touch attribution tracking: records all touchpoints for each lead.
    Supports first-touch, last-touch, linear, and time-decay models.
    """
    __tablename__ = "lead_attribution"
    __table_args__ = (
        db.Index("idx_attribution_lead", "lead_id", "touchpoint_order"),
    )

    id = db.Column(db.String(64), primary_key=True, default=lambda: str(uuid4()), nullable=False)
    lead_id = db.Column(db.String(64), db.ForeignKey("leads.id", ondelete="CASCADE"), nullable=False)
    touchpoint_order = db.Column(db.Integer, nullable=False, comment="1st, 2nd, 3rd... touch")
    source = db.Column(db.String(100), nullable=False)
    medium = db.Column(db.String(100), nullable=True)
    campaign = db.Column(db.String(100), nullable=True)
    content = db.Column(db.String(255), nullable=True)
    term = db.Column(db.String(255), nullable=True)
    attribution_model = db.Column(db.String(50), server_default="first_touch", comment="first_touch, last_touch, linear, time_decay")
    attribution_weight = db.Column(db.Float, server_default="1.0")
    touched_at = db.Column(db.DateTime(timezone=True), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), server_default=func.now(), nullable=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "lead_id": self.lead_id,
            "touchpoint_order": self.touchpoint_order,
            "source": self.source,
            "medium": self.medium,
            "campaign": self.campaign,
            "content": self.content,
            "term": self.term,
            "attribution_model": self.attribution_model,
            "attribution_weight": self.attribution_weight,
            "touched_at": self.touched_at.isoformat() if self.touched_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class FunnelMetricsDaily(db.Model):
    """
    Pre-aggregated daily funnel metrics for fast dashboard queries.
    Reduces need to scan full event tables for historical reporting.
    """
    __tablename__ = "funnel_metrics_daily"
    __table_args__ = (
        db.Index("idx_funnel_metrics_date", "metric_date", "stage"),
        db.UniqueConstraint("metric_date", "stage", "source", "campaign", name="uq_funnel_metrics_date_stage_source_campaign"),
    )

    id = db.Column(db.String(64), primary_key=True, default=lambda: str(uuid4()), nullable=False)
    metric_date = db.Column(db.Date, nullable=False)
    stage = db.Column(db.String(50), nullable=False)
    source = db.Column(db.String(100), nullable=True)
    campaign = db.Column(db.String(100), nullable=True)
    entries = db.Column(db.Integer, server_default="0")
    exits = db.Column(db.Integer, server_default="0")
    conversions_to_next = db.Column(db.Integer, server_default="0")
    conversion_rate = db.Column(db.Float, nullable=True)
    avg_time_in_stage_hours = db.Column(db.Float, nullable=True)
    total_cost = db.Column(db.Numeric(10, 2), nullable=True, comment="if cost tracking enabled")
    cost_per_entry = db.Column(db.Numeric(10, 2), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), server_default=func.now(), nullable=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "metric_date": self.metric_date.isoformat() if self.metric_date else None,
            "stage": self.stage,
            "source": self.source,
            "campaign": self.campaign,
            "entries": self.entries,
            "exits": self.exits,
            "conversions_to_next": self.conversions_to_next,
            "conversion_rate": self.conversion_rate,
            "avg_time_in_stage_hours": self.avg_time_in_stage_hours,
            "total_cost": float(self.total_cost) if self.total_cost else None,
            "cost_per_entry": float(self.cost_per_entry) if self.cost_per_entry else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


