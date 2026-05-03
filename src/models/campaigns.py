from datetime import datetime
from uuid import uuid4
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import TSVECTOR
from src.extensions import db

try:  # Optional pgvector support
    from pgvector.sqlalchemy import Vector  # type: ignore
except Exception:
    Vector = None

class CampaignSender(db.Model):
    """
    Approved email senders for campaigns (per account).
    Allows managing multiple campaign senders (e.g., Kofi, growth team members).
    """
    __tablename__ = "campaign_senders"
    __table_args__ = (
        db.Index("idx_campaign_sender_account", "account_id"),
    )

    id = db.Column(db.String(64), primary_key=True, default=lambda: str(uuid4()), nullable=False)
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=False, comment="Multi-tenancy")

    # Sender details
    email = db.Column(db.String(255), nullable=False, comment="Sender email (e.g., kofi@kalevent.com)")
    name = db.Column(db.String(255), nullable=False, comment="Display name (e.g., 'Kofi from Kalevent')")
    is_default = db.Column(db.Boolean, server_default="false", nullable=False, comment="Default sender for new campaigns")
    enabled = db.Column(db.Boolean, server_default="true", nullable=False, comment="Active sender")

    # Tracking
    created_at = db.Column(db.DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    def to_dict(self):
        return {
            "id": self.id,
            "email": self.email,
            "name": self.name,
            "is_default": self.is_default,
            "enabled": self.enabled,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class HunterDomainCache(db.Model):
    """
    Cache for Hunter.io domain email lookups to avoid duplicate API calls.
    Stores email patterns found for each domain.
    """
    __tablename__ = "hunter_domain_cache"
    __table_args__ = (
        db.UniqueConstraint("domain", name="uq_hunter_domain"),
        db.Index("idx_hunter_domain_created", "created_at"),
    )

    id = db.Column(db.String(64), primary_key=True, default=lambda: str(uuid4()), nullable=False)
    domain = db.Column(db.String(255), nullable=False, comment="Company domain (e.g., google.com)")

    # Cached data from Hunter.io
    emails = db.Column(db.JSON, nullable=True, comment="List of emails found for this domain")
    email_count = db.Column(db.Integer, default=0, comment="Number of emails found")

    # Metadata
    created_at = db.Column(db.DateTime(timezone=True), server_default=func.now(), nullable=False)
    expires_at = db.Column(db.DateTime(timezone=True), nullable=True, comment="Cache expiration (30 days)")

    def is_expired(self) -> bool:
        """Check if cache entry has expired."""
        if not self.expires_at:
            return True
        from datetime import datetime, timezone
        return datetime.now(timezone.utc) > self.expires_at

    def to_dict(self):
        return {
            "id": self.id,
            "domain": self.domain,
            "emails": self.emails,
            "email_count": self.email_count,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
        }


class EmailCampaign(db.Model):
    """
    Email campaign for automated outreach to leads.
    Supports multi-step sequences with personalization and tracking.
    """
    __tablename__ = "email_campaigns"
    __table_args__ = (
        db.Index("idx_email_campaign_status", "status"),
    )

    id = db.Column(db.String(64), primary_key=True, default=lambda: str(uuid4()), nullable=False)
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=True, comment="Multi-tenancy support")

    # Campaign details
    name = db.Column(db.String(255), nullable=False, comment="Campaign name (e.g., 'Automation Studio Beta Outreach')")
    subject_template = db.Column(db.String(500), nullable=False, comment="Email subject with {{variables}}")
    body_template = db.Column(db.Text, nullable=False, comment="Email body HTML/text with {{variables}}")
    from_email = db.Column(db.String(255), nullable=False, comment="Sender email address")
    from_name = db.Column(db.String(255), nullable=True, comment="Sender display name")

    # Sequence configuration
    follow_up_enabled = db.Column(db.Boolean, server_default="true", comment="Enable automated follow-ups")
    follow_up_delay_days = db.Column(db.JSON, nullable=False, default=list, comment="Follow-up delays: [3, 7] for Day 3 and Day 7")

    # Targeting
    target_funnel_stage = db.Column(db.String(50), nullable=True, comment="Target leads in this stage")
    target_source = db.Column(db.String(100), nullable=True, comment="Target leads from this source")

    # Campaign status
    status = db.Column(
        db.Enum("draft", "active", "paused", "completed", name="campaign_status_enum"),
        server_default="draft",
        nullable=False
    )
    max_recipients = db.Column(db.Integer, nullable=True, comment="Stop after X recipients (e.g., 10 for beta)")

    # Tracking
    total_sent = db.Column(db.Integer, server_default="0", nullable=False)
    total_opened = db.Column(db.Integer, server_default="0", nullable=False)
    total_clicked = db.Column(db.Integer, server_default="0", nullable=False)
    total_replied = db.Column(db.Integer, server_default="0", nullable=False)

    created_at = db.Column(db.DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    started_at = db.Column(db.DateTime(timezone=True), nullable=True)
    completed_at = db.Column(db.DateTime(timezone=True), nullable=True)


class EmailOutreach(db.Model):
    """
    Individual email sent as part of a campaign.
    Tracks delivery, opens, clicks, and replies.
    """
    __tablename__ = "email_outreaches"
    __table_args__ = (
        db.Index("idx_email_outreach_campaign", "campaign_id"),
        db.Index("idx_email_outreach_lead", "lead_id"),
        db.Index("idx_email_outreach_status", "status"),
        db.Index("idx_email_outreach_next_followup", "next_followup_at"),
    )

    id = db.Column(db.String(64), primary_key=True, default=lambda: str(uuid4()), nullable=False)
    campaign_id = db.Column(db.String(64), db.ForeignKey("email_campaigns.id", ondelete="CASCADE"), nullable=False)
    lead_id = db.Column(db.String(64), db.ForeignKey("leads.id", ondelete="CASCADE"), nullable=False)

    # Email content
    sequence_step = db.Column(db.Integer, server_default="0", nullable=False, comment="0=initial, 1=first follow-up, 2=second follow-up")
    subject = db.Column(db.String(500), nullable=False, comment="Rendered subject line")
    body_html = db.Column(db.Text, nullable=True, comment="Rendered HTML body")
    body_text = db.Column(db.Text, nullable=False, comment="Rendered plain text body")

    # Recipient info
    recipient_email = db.Column(db.String(255), nullable=False)
    recipient_name = db.Column(db.String(255), nullable=True)

    # Delivery status
    status = db.Column(
        db.Enum("pending", "sent", "delivered", "opened", "clicked", "replied", "bounced", "failed", "unsubscribed", name="outreach_status_enum"),
        server_default="pending",
        nullable=False
    )

    # AWS SES tracking
    ses_message_id = db.Column(db.String(255), nullable=True, comment="AWS SES Message ID")
    sent_at = db.Column(db.DateTime(timezone=True), nullable=True)
    delivered_at = db.Column(db.DateTime(timezone=True), nullable=True)
    first_opened_at = db.Column(db.DateTime(timezone=True), nullable=True)
    first_clicked_at = db.Column(db.DateTime(timezone=True), nullable=True)
    replied_at = db.Column(db.DateTime(timezone=True), nullable=True)

    # Engagement tracking
    open_count = db.Column(db.Integer, server_default="0", nullable=False)
    click_count = db.Column(db.Integer, server_default="0", nullable=False)

    # Follow-up scheduling
    next_followup_at = db.Column(db.DateTime(timezone=True), nullable=True, comment="When to send next follow-up")
    followup_sent = db.Column(db.Boolean, server_default="false", nullable=False)

    # Error handling
    error_message = db.Column(db.Text, nullable=True)
    retry_count = db.Column(db.Integer, server_default="0", nullable=False)

    # Unsubscribe
    unsubscribe_token = db.Column(db.String(64), nullable=True, unique=True, index=True, comment="Token embedded in unsubscribe link — one per outreach record")

    created_at = db.Column(db.DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


# ============================================================================
# Automation Studio Models
# ============================================================================


class NurtureEmailSend(db.Model):
    """
    Tracks individual nurture email sends for deduplication and A/B test analysis.

    One row per (lead, campaign_type, sequence_day) — the unique constraint prevents
    the same email from being sent twice to the same lead.

    ab_variant "A" = baseline (pain-point focus)
    ab_variant "B" = ROI/case-study focus
    """
    __tablename__ = "nurture_email_sends"
    __table_args__ = (
        db.UniqueConstraint("lead_id", "campaign_type", "sequence_day", name="uq_nurture_send"),
        db.Index("idx_nurture_ab", "campaign_type", "ab_variant", "sequence_day"),
    )

    id = db.Column(db.String(64), primary_key=True, default=lambda: str(uuid4()), nullable=False)
    lead_id = db.Column(db.String(64), db.ForeignKey("leads.id", ondelete="CASCADE"), nullable=False)
    campaign_type = db.Column(db.String(50), nullable=False, comment="discovery | consideration")
    sequence_day = db.Column(db.Integer, nullable=False, comment="1, 3, 7, 14, or 21")
    ab_variant = db.Column(db.String(1), nullable=True, comment="A or B")
    subject_line = db.Column(db.String(500), nullable=True, comment="Actual subject sent — for comparing variants")
    vertical = db.Column(db.String(50), nullable=True, comment="b2b_saas or ecommerce")
    opened = db.Column(db.Boolean, server_default="false", nullable=False)
    clicked = db.Column(db.Boolean, server_default="false", nullable=False)
    sent_at = db.Column(db.DateTime(timezone=True), nullable=False, server_default=func.now())
    opened_at = db.Column(db.DateTime(timezone=True), nullable=True)


class LinkedInProspect(db.Model):
    """Tracks a LinkedIn prospect through the 3-message outreach cadence."""
    __tablename__ = "linkedin_prospects"
    __table_args__ = (
        db.UniqueConstraint("account_id", "linkedin_url", name="uq_li_prospect_account_url"),
        db.Index("idx_li_prospect_account_status", "account_id", "status"),
        db.Index("idx_li_prospect_due", "message_2_due_at", "message_3_due_at"),
    )

    id = db.Column(db.String(64), primary_key=True, default=lambda: str(uuid4()))
    account_id = db.Column(db.Integer, nullable=False)
    lead_id = db.Column(db.String(64), db.ForeignKey("leads.id"), nullable=True)
    name = db.Column(db.String(255), nullable=False)
    company_name = db.Column(db.String(255), nullable=True)
    job_title = db.Column(db.String(255), nullable=True)
    industry = db.Column(db.String(100), nullable=True)
    linkedin_url = db.Column(db.String(500), nullable=False)
    source = db.Column(db.String(20), nullable=False, server_default="auto")
    status = db.Column(
        db.Enum(
            "pending",
            "connection_sent",
            "connected",
            "message_2_sent",
            "message_3_sent",
            "replied",
            "qualified",
            "disqualified",
            name="linkedin_prospect_status_enum",
        ),
        nullable=False,
        server_default="pending",
    )
    fit_score = db.Column(db.Integer, nullable=True)
    connection_sent_at = db.Column(db.DateTime(timezone=True), nullable=True)
    connected_at = db.Column(db.DateTime(timezone=True), nullable=True)
    message_2_due_at = db.Column(db.DateTime(timezone=True), nullable=True)
    message_2_sent_at = db.Column(db.DateTime(timezone=True), nullable=True)
    message_3_due_at = db.Column(db.DateTime(timezone=True), nullable=True)
    message_3_sent_at = db.Column(db.DateTime(timezone=True), nullable=True)
    msg_1_draft = db.Column(db.Text, nullable=True)
    msg_2_draft = db.Column(db.Text, nullable=True)
    msg_3_draft = db.Column(db.Text, nullable=True)
    suggested_post_id = db.Column(db.String(64), db.ForeignKey("blog_posts.id"), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), server_default=func.now())


class YouTubeVideo(db.Model):
    """One row per video (long form or short). Shorts link to parent via parent_video_id."""
    __tablename__ = "youtube_videos"
    __table_args__ = (
        db.Index("idx_youtube_videos_account_status", "account_id", "status"),
        db.Index("idx_youtube_videos_published", "account_id", "published_at"),
    )

    id = db.Column(db.String(64), primary_key=True, default=lambda: str(uuid4()), nullable=False)
    account_id = db.Column(db.Integer, nullable=False)
    blog_post_id = db.Column(db.String(64), db.ForeignKey("blog_posts.id"), nullable=True)
    icp_pain_point_id = db.Column(db.String(64), db.ForeignKey("icp_pain_points.id"), nullable=False)
    parent_video_id = db.Column(db.String(64), db.ForeignKey("youtube_videos.id"), nullable=True)

    # Content
    video_type = db.Column(db.String(20), nullable=False)  # "long_form" | "short"
    video_style = db.Column(db.String(20), nullable=False, default="avatar")  # "avatar" | "illustration"
    script = db.Column(db.Text, nullable=True)
    title = db.Column(db.String(100), nullable=True)
    description = db.Column(db.Text, nullable=True)
    tags = db.Column(db.JSON, nullable=True)
    thumbnail_prompt = db.Column(db.Text, nullable=True)

    # Illustration frames (avatar style leaves these null)
    illustration_prompts = db.Column(db.JSON, nullable=True)
    dalle_frame_urls = db.Column(db.JSON, nullable=True)

    # HeyGen
    heygen_job_id = db.Column(db.String(128), nullable=True)
    heygen_render_url = db.Column(db.String(512), nullable=True)

    # YouTube
    youtube_video_id = db.Column(db.String(64), nullable=True)
    youtube_url = db.Column(db.String(256), nullable=True)

    # UTM / funnel tracking
    utm_slug = db.Column(db.String(128), nullable=True, unique=True)
    utm_source = db.Column(db.String(64), nullable=False, default="youtube")
    utm_medium = db.Column(db.String(64), nullable=True)  # "long_form" | "short"
    utm_campaign = db.Column(db.String(128), nullable=True)

    # Status + timing
    status = db.Column(db.String(32), nullable=False, default="script_pending")
    script_generated_at = db.Column(db.DateTime(timezone=True), nullable=True)
    render_submitted_at = db.Column(db.DateTime(timezone=True), nullable=True)
    render_completed_at = db.Column(db.DateTime(timezone=True), nullable=True)
    published_at = db.Column(db.DateTime(timezone=True), nullable=True)

    # Performance (refreshed daily by digest task)
    view_count = db.Column(db.Integer, nullable=False, default=0)
    click_count = db.Column(db.Integer, nullable=False, default=0)

    created_at = db.Column(db.DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = db.Column(db.DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

