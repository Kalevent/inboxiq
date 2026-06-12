from uuid import uuid4
from sqlalchemy.sql import func
from src.extensions import db

try:  # Optional pgvector support
    from pgvector.sqlalchemy import Vector  # type: ignore
except Exception:
    Vector = None

class AutomationStudioWaitlist(db.Model):
    """Track waitlist signups for Automation Studio beta launch."""
    __tablename__ = "automation_studio_waitlist"
    __table_args__ = (
        db.Index("ix_automation_studio_waitlist_email", "email"),
        db.Index("ix_automation_studio_waitlist_beta_qualified", "beta_qualified"),
    )

    id = db.Column(db.String(64), primary_key=True, default=lambda: str(uuid4()))
    email = db.Column(db.String(255), nullable=False, unique=True, index=True)

    # Qualification data (collected during discovery call)
    company_name = db.Column(db.String(255), nullable=True)
    role = db.Column(db.String(128), nullable=True)
    team_size = db.Column(db.Integer, nullable=True)
    ticket_volume_per_week = db.Column(db.Integer, nullable=True)

    # Pain points (from interview)
    biggest_pain_point = db.Column(db.Text, nullable=True)
    desired_rule_example = db.Column(db.Text, nullable=True)
    pain_score = db.Column(db.SmallInteger, nullable=True)  # 1-10 scale

    # Engagement tracking
    opened_email = db.Column(db.Boolean, default=False, nullable=False)
    clicked_demo = db.Column(db.Boolean, default=False, nullable=False)
    scheduled_interview = db.Column(db.Boolean, default=False, nullable=False)
    interview_completed = db.Column(db.Boolean, default=False, nullable=False)
    beta_qualified = db.Column(db.Boolean, default=False, nullable=False)
    beta_committed = db.Column(db.Boolean, default=False, nullable=False)

    # Source tracking
    source = db.Column(db.String(64), nullable=True)  # "homepage", "linkedin", "email"
    utm_source = db.Column(db.String(128), nullable=True)
    utm_campaign = db.Column(db.String(128), nullable=True)
    utm_medium = db.Column(db.String(128), nullable=True)

    # Timestamps
    signed_up_at = db.Column(db.DateTime(timezone=True), server_default=func.now(), nullable=False)
    interview_scheduled_at = db.Column(db.DateTime(timezone=True), nullable=True)
    interview_completed_at = db.Column(db.DateTime(timezone=True), nullable=True)
    beta_committed_at = db.Column(db.DateTime(timezone=True), nullable=True)

    created_at = db.Column(db.DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "email": self.email,
            "company_name": self.company_name,
            "role": self.role,
            "team_size": self.team_size,
            "pain_score": self.pain_score,
            "beta_qualified": self.beta_qualified,
            "beta_committed": self.beta_committed,
            "source": self.source,
            "signed_up_at": self.signed_up_at.isoformat() if self.signed_up_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class AutomationRule(db.Model):
    """
    User-created automation rules for Automation Studio.

    Allows users to create custom workflows through the UI with:
    - Triggers (when to run)
    - Conditions (what to check)
    - Actions (what to do)

    Each rule execution is traced with OpenTelemetry for debugging.
    """
    __tablename__ = "automation_rules"
    __table_args__ = (
        db.Index("ix_automation_rules_account_enabled", "account_id", "enabled"),
    )

    id = db.Column(db.String(64), primary_key=True, default=lambda: str(uuid4()))
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=False, index=True)

    # Basic metadata
    name = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=True)
    enabled = db.Column(db.Boolean, default=True, nullable=False, index=True)

    # Rule definition (JSON)
    trigger = db.Column(db.JSON, nullable=False)
    # {"event": "ticket.created", "object": "ticket"}

    conditions = db.Column(db.JSON, nullable=False, default=list)
    # [
    #   {"field": "priority", "operator": "equals", "value": "P1"},
    #   {"field": "category", "operator": "equals", "value": "billing"}
    # ]

    condition_logic = db.Column(db.String(16), default="AND", nullable=False)
    # "AND" or "OR"

    actions = db.Column(db.JSON, nullable=False, default=list)
    # [
    #   {"type": "assign", "team": "finance"},
    #   {"type": "notify", "channel": "slack", "message": "..."}
    # ]

    # Execution control
    stop_on_error = db.Column(db.Boolean, default=False, nullable=False)

    # Template metadata
    is_template = db.Column(db.Boolean, default=False, nullable=False)
    template_category = db.Column(db.String(64), nullable=True)  # "routing", "escalation", "notification"
    cloned_from_template_id = db.Column(db.String(64), nullable=True)

    # Analytics
    execution_count = db.Column(db.Integer, default=0, nullable=False)
    success_count = db.Column(db.Integer, default=0, nullable=False)
    error_count = db.Column(db.Integer, default=0, nullable=False)
    last_executed_at = db.Column(db.DateTime(timezone=True), nullable=True)

    # Performance tracking
    avg_execution_time_ms = db.Column(db.Float, nullable=True)
    estimated_time_saved_hours = db.Column(db.Float, default=0.0, nullable=False)

    # ROI tracking (added for Automation Studio)
    baseline_time_per_execution = db.Column(db.Integer, default=180)  # seconds (default: 3 minutes)
    baseline_cost_per_execution = db.Column(db.Numeric(10, 2), default=0.75)  # dollars per execution
    total_time_saved_seconds = db.Column(db.Integer, default=0)
    total_cost_saved = db.Column(db.Numeric(10, 2), default=0)
    accuracy_rate = db.Column(db.Numeric(5, 2))  # percentage (0.00-1.00)
    total_executions = db.Column(db.Integer, default=0)  # Total executions
    successful_executions = db.Column(db.Integer, default=0)  # Successful executions

    # Discovery metadata (how was this rule created?)
    source = db.Column(db.String(32), default="user_created")  # "ai_suggested", "user_created", "template"
    suggestion_id = db.Column(db.String(64), db.ForeignKey("automation_suggestions.id"), nullable=True)

    # Audit
    created_by_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    account = db.relationship("Account", backref="automation_rules")
    created_by = db.relationship("User", foreign_keys=[created_by_user_id])
    executions = db.relationship("AutomationRuleExecution", backref="rule", cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id,
            "account_id": self.account_id,
            "name": self.name,
            "description": self.description,
            "enabled": self.enabled,
            "trigger": self.trigger,
            "conditions": self.conditions,
            "condition_logic": self.condition_logic,
            "actions": self.actions,
            "stop_on_error": self.stop_on_error,
            "is_template": self.is_template,
            "template_category": self.template_category,
            "execution_count": self.execution_count,
            "success_count": self.success_count,
            "error_count": self.error_count,
            "last_executed_at": self.last_executed_at.isoformat() if self.last_executed_at else None,
            "avg_execution_time_ms": self.avg_execution_time_ms,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class ApprovalPolicy(db.Model):
    """
    Prior authorisation policy — defines which emails are auto-sent directly
    without waiting for the owner to review the draft in Gmail/Outlook.

    When an email's category, email_type, and sentiment match a policy's
    conditions AND the DSPy reply_confidence meets the threshold, InboxIQ
    sends the reply directly via the Gmail/Outlook API instead of creating
    a draft. The owner never sees it in their draft queue.

    All other emails follow the normal flow: draft created, owner decides.
    """
    __tablename__ = "approval_policies"
    __table_args__ = (
        db.Index("ix_approval_policies_account_enabled", "account_id", "enabled"),
    )

    id = db.Column(db.String(64), primary_key=True, default=lambda: str(uuid4()))
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=False, index=True)

    name = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=True)
    enabled = db.Column(db.Boolean, default=True, nullable=False)

    # Conditions — same DSL as AutomationRule.conditions
    # [{"field": "category", "operator": "equals", "value": "support"},
    #  {"field": "email_type", "operator": "equals", "value": "password_reset"}]
    conditions = db.Column(db.JSON, nullable=False, default=list)
    condition_logic = db.Column(db.String(16), default="AND", nullable=False)  # AND | OR

    # Minimum reply confidence from DSPy before auto-send fires (0.0–1.0)
    min_confidence = db.Column(db.Float, nullable=False, default=0.85)

    # Audit
    created_at = db.Column(db.DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    account = db.relationship("Account", backref="approval_policies")

    def to_dict(self):
        return {
            "id": self.id,
            "account_id": self.account_id,
            "name": self.name,
            "description": self.description,
            "enabled": self.enabled,
            "conditions": self.conditions,
            "condition_logic": self.condition_logic,
            "min_confidence": self.min_confidence,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class AutomationRuleExecution(db.Model):
    """
    Log of automation rule executions for debugging and analytics.

    Stores:
    - Execution results (matched, executed, success)
    - Condition evaluation details
    - Action execution results
    - OpenTelemetry trace ID for deep debugging

    Users can view execution history with links to Phoenix traces.
    """
    __tablename__ = "automation_rule_executions"
    __table_args__ = (
        db.Index("ix_automation_rule_executions_rule_id", "rule_id"),
        db.Index("ix_automation_rule_executions_ticket_id", "ticket_id"),
        db.Index("ix_automation_rule_executions_trace_id", "trace_id"),
        db.Index("ix_automation_rule_executions_created_at", "created_at"),
    )

    id = db.Column(db.String(64), primary_key=True, default=lambda: str(uuid4()))
    rule_id = db.Column(db.String(64), db.ForeignKey("automation_rules.id"), nullable=False)
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=False, index=True)

    # OpenTelemetry trace ID (hex string, 32 chars) - CRITICAL for debugging
    trace_id = db.Column(db.String(32), nullable=False, index=True)

    # Context
    ticket_id = db.Column(db.String(64), db.ForeignKey("inboxiq_tickets.id"), nullable=True)
    lead_id = db.Column(db.String(64), db.ForeignKey("leads.id"), nullable=True)
    trigger_event = db.Column(db.String(64), nullable=False)  # "ticket.created", "ticket.updated", etc.

    # Execution details
    matched = db.Column(db.Boolean, nullable=False)  # Did conditions match?
    executed = db.Column(db.Boolean, nullable=False)  # Did actions execute?
    success = db.Column(db.Boolean, nullable=False)  # Did actions succeed?
    error_message = db.Column(db.Text, nullable=True)

    # Performance
    execution_time_ms = db.Column(db.Float, nullable=True)

    # Trigger context (SANITIZED - no PII)
    trigger_type = db.Column(db.String(50))  # email, webhook, stripe, manual, etc.
    trigger_context = db.Column(db.JSON, nullable=True)  # Sanitized trigger data

    # Audit trail (detailed results)
    conditions_evaluated = db.Column(db.JSON, nullable=True)
    # [{"field": "priority", "expected": "P1", "actual": "P1", "matched": true}]

    actions_executed = db.Column(db.JSON, nullable=True)
    # [{"type": "assign", "success": true, "result": "Assigned to team: finance"}]

    # ROI tracking (for accuracy calculation)
    ticket_reassigned = db.Column(db.Boolean, default=False)  # Was ticket manually reassigned after automation?
    reassignment_timestamp = db.Column(db.DateTime(timezone=True), nullable=True)

    created_at = db.Column(db.DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    account = db.relationship("Account")
    ticket = db.relationship("Ticket", foreign_keys=[ticket_id])
    lead = db.relationship("Lead", foreign_keys=[lead_id])

    def to_dict(self):
        return {
            "id": self.id,
            "rule_id": self.rule_id,
            "account_id": self.account_id,
            "trace_id": self.trace_id,
            "ticket_id": self.ticket_id,
            "lead_id": self.lead_id,
            "trigger_event": self.trigger_event,
            "trigger_type": self.trigger_type,
            "matched": self.matched,
            "executed": self.executed,
            "success": self.success,
            "error_message": self.error_message,
            "execution_time_ms": self.execution_time_ms,
            "conditions_evaluated": self.conditions_evaluated,
            "actions_executed": self.actions_executed,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class WebhookProvider(db.Model):
    """
    Stores encrypted credentials for external integrations (Sage, QuickBooks, Stripe, etc.)
    Supports both source providers (Stripe, Square, PayPal) and destination providers (Sage, QuickBooks)
    """
    __tablename__ = "webhook_providers"

    id = db.Column(db.String(64), primary_key=True, default=lambda: str(uuid4()))
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=False, index=True)

    # Provider configuration
    provider_type = db.Column(db.String(64), nullable=False)  # "sage", "quickbooks", "stripe", "square", "paypal", "slack", "custom"
    configuration_name = db.Column(db.String(255), nullable=False)  # User-friendly name (e.g., "Production Sage")
    environment = db.Column(db.String(16), default="production")  # "production" or "sandbox"

    # Encrypted credentials (stored as encrypted JSON blob)
    # Example for Sage: {"api_key": "xxx", "company_id": "123", "endpoint": "https://api.sage.com/v3"}
    # Example for QuickBooks: {"client_id": "xxx", "client_secret": "yyy", "realm_id": "zzz"}
    credentials_encrypted = db.Column(db.Text, nullable=False)

    # For source providers (Stripe, Square, PayPal) that send webhooks TO InboxIQ
    webhook_signing_secret_encrypted = db.Column(db.Text, nullable=True)  # For signature verification
    api_key_encrypted = db.Column(db.Text, nullable=True)  # For pulling historical data (optional)
    destination_provider_id = db.Column(db.String(64), db.ForeignKey("webhook_providers.id"), nullable=True)  # Where to route data

    # Metadata
    enabled = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), onupdate=func.now())
    last_used_at = db.Column(db.DateTime(timezone=True), nullable=True)

    # Usage tracking
    total_requests = db.Column(db.Integer, default=0)
    failed_requests = db.Column(db.Integer, default=0)

    # Relationships
    account = db.relationship("Account")
    destination_provider = db.relationship("WebhookProvider", remote_side=[id], foreign_keys=[destination_provider_id])

    def to_dict(self, include_credentials=False):
        """
        Convert to dictionary for API responses
        By default, credentials are NOT included for security
        """
        result = {
            "id": self.id,
            "account_id": self.account_id,
            "provider_type": self.provider_type,
            "configuration_name": self.configuration_name,
            "environment": self.environment,
            "enabled": self.enabled,
            "destination_provider_id": self.destination_provider_id,
            "total_requests": self.total_requests,
            "failed_requests": self.failed_requests,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "last_used_at": self.last_used_at.isoformat() if self.last_used_at else None,
        }

        # Only include credentials if explicitly requested (for internal use)
        if include_credentials:
            result["has_credentials"] = bool(self.credentials_encrypted)
            result["has_webhook_secret"] = bool(self.webhook_signing_secret_encrypted)
            result["has_api_key"] = bool(self.api_key_encrypted)

        return result


class AutomationSuggestion(db.Model):
    """
    AI-discovered automation patterns suggested to users
    Generated by analyzing historical ticket/email routing patterns
    """
    __tablename__ = "automation_suggestions"

    id = db.Column(db.String(64), primary_key=True, default=lambda: str(uuid4()))
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=False, index=True)

    # Pattern details
    pattern_type = db.Column(db.String(64), nullable=False)  # "routing", "prioritization", "tagging", "escalation"
    confidence = db.Column(db.Numeric(5, 2), nullable=False)  # 0.00-1.00 (e.g., 0.87 = 87% confidence)

    # Human-readable suggestion
    plain_english = db.Column(db.Text, nullable=False)
    # Example: "I noticed 87% of billing tickets get assigned to Sarah. Want me to automate this?"

    # Generated workflow structure (ready to activate)
    workflow_json = db.Column(db.JSON, nullable=False)
    # Complete AutomationRule structure that can be saved directly

    # ROI estimates
    estimated_time_saved_per_week = db.Column(db.Integer, nullable=True)  # minutes
    estimated_cost_savings_per_month = db.Column(db.Numeric(10, 2), nullable=True)  # dollars
    estimated_accuracy = db.Column(db.Numeric(5, 2), nullable=True)  # percentage

    # Supporting evidence
    sample_ticket_ids = db.Column(db.JSON, nullable=True)  # List of ticket IDs that match this pattern
    pattern_occurrences = db.Column(db.Integer, default=0)  # How many times pattern occurred
    total_analyzed = db.Column(db.Integer, default=0)  # Total tickets analyzed

    # Status tracking
    status = db.Column(db.String(16), default="pending", nullable=False)  # "pending", "approved", "dismissed"
    dismissed_reason = db.Column(db.Text, nullable=True)
    approved_at = db.Column(db.DateTime(timezone=True), nullable=True)
    dismissed_at = db.Column(db.DateTime(timezone=True), nullable=True)
    created_rule_id = db.Column(db.String(64), db.ForeignKey("automation_rules.id"), nullable=True)  # If approved

    # Metadata
    created_at = db.Column(db.DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), onupdate=func.now())

    # Discovery metadata (how was this pattern found?)
    discovery_method = db.Column(db.String(64), default="dspy_pattern_extraction")  # "dspy_pattern_extraction", "rule_mining", "manual"
    lookback_days = db.Column(db.Integer, default=90)  # How many days of history analyzed

    # Relationships
    account = db.relationship("Account")
    created_rule = db.relationship("AutomationRule", foreign_keys=[created_rule_id])

    def to_dict(self):
        return {
            "id": self.id,
            "account_id": self.account_id,
            "pattern_type": self.pattern_type,
            "confidence": float(self.confidence) if self.confidence else None,
            "plain_english": self.plain_english,
            "workflow_json": self.workflow_json,
            "estimated_time_saved_per_week": self.estimated_time_saved_per_week,
            "estimated_cost_savings_per_month": float(self.estimated_cost_savings_per_month) if self.estimated_cost_savings_per_month else None,
            "estimated_accuracy": float(self.estimated_accuracy) if self.estimated_accuracy else None,
            "sample_ticket_ids": self.sample_ticket_ids,
            "pattern_occurrences": self.pattern_occurrences,
            "total_analyzed": self.total_analyzed,
            "status": self.status,
            "dismissed_reason": self.dismissed_reason,
            "approved_at": self.approved_at.isoformat() if self.approved_at else None,
            "dismissed_at": self.dismissed_at.isoformat() if self.dismissed_at else None,
            "created_rule_id": self.created_rule_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "discovery_method": self.discovery_method,
            "lookback_days": self.lookback_days,
        }


# ── Developer Platform ────────────────────────────────────────────────────────

