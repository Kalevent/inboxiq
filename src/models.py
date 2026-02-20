from datetime import datetime
from uuid import uuid4
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import TSVECTOR
from src.extensions import db
from datetime import datetime

try:  # Optional pgvector support; falls back to JSON if not installed
    from pgvector.sqlalchemy import Vector  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    Vector = None


class Account(db.Model):
    __tablename__ = "accounts"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    seats_limit = db.Column(db.Integer, nullable=False, default=1)
    seats_used = db.Column(db.Integer, nullable=False, default=1)
    developer_access = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    users = db.relationship("User", backref="account", lazy=True)

class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    name = db.Column(db.String(255), nullable=True)
    password_hash = db.Column(db.String(255), nullable=True)
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class InboxConnection(db.Model):
    __tablename__ = "inbox_connections"
    __table_args__ = (db.UniqueConstraint("user_id", "provider", name="uq_user_provider_inbox"),)

    id = db.Column(db.String(64), primary_key=True, default=lambda: str(uuid4()), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=True)
    provider = db.Column(db.String(32), nullable=False)
    email_address = db.Column(db.String(255), nullable=True)
    status = db.Column(db.String(32), nullable=False, default="connected")
    access_token = db.Column(db.Text, nullable=True)
    refresh_token = db.Column(db.Text, nullable=True)
    token_expires_at = db.Column(db.DateTime(timezone=True), nullable=True)
    scopes = db.Column(db.JSON, nullable=False, default=list)
    metadata_json = db.Column("metadata", db.JSON, nullable=False, default=dict)
    created_at = db.Column(db.DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "provider": self.provider,
            "email_address": self.email_address,
            "status": self.status,
            "scopes": self.scopes or [],
            "metadata": self.metadata_json or {},
            "token_expires_at": self.token_expires_at.isoformat() if self.token_expires_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class Ticket(db.Model):
    __tablename__ = "inboxiq_tickets"
    __table_args__ = (db.UniqueConstraint("message_id", "provider", name="uq_ticket_message_provider"),)

    id = db.Column(db.String(64), primary_key=True, default=lambda: str(uuid4()), nullable=False)
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    subject = db.Column(db.String(500), nullable=False)
    from_email = db.Column(db.String(255), nullable=False)
    body_preview = db.Column(db.Text, nullable=True)
    category = db.Column(db.String(64), nullable=False, default="general")
    priority = db.Column(db.String(8), nullable=False, default="P2")
    sentiment = db.Column(db.String(32), nullable=False, default="neutral")
    entities = db.Column(db.JSON, nullable=False, default=dict)
    status = db.Column(db.String(32), nullable=False, default="new")
    message_id = db.Column(db.String(255), nullable=False)
    provider = db.Column(db.String(32), nullable=True)
    provider_thread_url = db.Column(db.String(512), nullable=True)
    decision = db.Column(db.JSON, nullable=False, default=dict)
    manual_override = db.Column(db.Boolean, default=False, nullable=False)
    override_metadata = db.Column(db.JSON, nullable=False, default=dict)
    due_at = db.Column(db.DateTime(timezone=True), nullable=True)
    summary = db.Column(db.Text, nullable=True)
    last_question = db.Column(db.Text, nullable=True)
    owner = db.Column(db.String(128), nullable=True)
    team = db.Column(db.String(128), nullable=True)
    assigned_to = db.Column(db.String(128), nullable=True)
    search_vec = db.Column(TSVECTOR, nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    @property
    def action_required(self):
        # Stored within the decision blob to avoid schema churn; may be bool or "optional".
        decision = self.decision or {}
        explicit = decision.get("action_required")

        # Respect status overrides to keep UI/dashboards consistent even if decision lags.
        if self.status == "auto_handled":
            return False
        if self.status == "optional":
            return "optional"
        if explicit is not None:
            return explicit
        if self.status in ("new", "open", "needs_review"):
            return True
        return explicit

    @action_required.setter
    def action_required(self, value):
        decision = self.decision or {}
        decision["action_required"] = value
        self.decision = decision

    def to_dict(self) -> dict:
        decision = self.decision or {}
        provider = (self.provider or decision.get("provider") or "email").lower()
        def _channel_from_provider(provider_val: str) -> str:
            email_providers = {
                "gmail",
                "outlook",
                "imap",
                "email",
                "google",
                "gsuite",
                "google_oauth",
                "ms_graph",
                "microsoft",
                "office365",
                "exchange",
                "ews",
                "smtp",
            }
            if provider_val in email_providers:
                return "email"
            if provider_val in {"feedback"}:
                return "feedback"
            if provider_val in {"web", "form", "forms"}:
                return "form"
            if provider_val in {"chat", "intercom", "slack"}:
                return "chat"
            if provider_val in {"crm", "hubspot", "salesforce"}:
                return "crm"
            if provider_val in {"api", "webhook"}:
                return "api"
            return "other"

        def _infer_use_case() -> str:
            hint = (decision.get("use_case") or "").lower()
            if hint:
                return hint
            category = (self.category or decision.get("category") or "").lower()
            intent = (decision.get("intent") or "").lower()
            subject = (self.subject or "").lower()
            tokens = f"{category} {intent} {subject}"
            if any(term in tokens for term in ("claim", "claims", "insurance")):
                return "claims"
            if any(term in tokens for term in ("hr", "people", "payroll", "benefits")):
                return "hr"
            if any(term in tokens for term in ("finance", "billing", "invoice", "refund", "payment")):
                return "finance"
            return "support"

        def _decision_outcome() -> str:
            action_required = self.action_required
            if action_required is True:
                return "action_required"
            if action_required == "optional":
                return "needs_review"
            if action_required is False:
                return "auto_handled"
            return "action_required"

        return {
            "id": self.id,
            "account_uid": None,
            "user_id": self.user_id,
            "subject": self.subject,
            "from_email": self.from_email,
            "body_preview": self.body_preview,
            "category": self.category,
            "priority": self.priority,
            "sentiment": self.sentiment,
            "entities": self.entities or {},
            "status": self.status,
            "message_id": self.message_id,
            "provider": provider,
            "provider_thread_url": self.provider_thread_url,
            "decision": decision,
            "manual_override": self.manual_override,
            "override_metadata": self.override_metadata or {},
            "due_at": self.due_at.isoformat() if self.due_at else None,
            "summary": self.summary,
            "last_question": self.last_question,
            "intent": decision.get("intent"),
            "risk_flag": decision.get("risk_flag"),
            "owner": self.owner or decision.get("owner"),
            "team": self.team or decision.get("team"),
            "assigned_to": self.assigned_to,
            "channel": _channel_from_provider(provider),
            "use_case": _infer_use_case(),
            "decision_type": decision.get("decision_type") or "triage",
            "decision_outcome": _decision_outcome(),
            "confidence": decision.get("confidence"),
            "decision_trace": decision.get("decision_trace") or [],
            "draft_reply": bool(decision.get("reply_text") or decision.get("draft_reply")),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "action_required": self.action_required,
        }


class TicketEmbedding(db.Model):
    """
    Persist embeddings for tickets (manual overrides / feedback) to enable vector search.
    Uses pgvector if available; otherwise falls back to JSON storage for portability.
    """
    __tablename__ = "ticket_embeddings"
    __table_args__ = (db.UniqueConstraint("ticket_id", name="uq_ticket_embedding_ticket"),)

    id = db.Column(db.String(64), primary_key=True, default=lambda: str(uuid4()), nullable=False)
    ticket_id = db.Column(db.String(64), db.ForeignKey("inboxiq_tickets.id"), nullable=False, index=True)
    model = db.Column(db.String(128), nullable=True)
    dim = db.Column(db.Integer, nullable=True)
    embedding = db.Column(Vector(1536)) if Vector else db.Column(db.JSON, nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "ticket_id": self.ticket_id,
            "model": self.model,
            "dim": self.dim,
            "embedding": self.embedding,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class TriageLabelConfig(db.Model):
    """
    Configurable label sets for DSPy triage (optionally account-scoped).
    """
    __tablename__ = "triage_label_configs"
    __table_args__ = (db.Index("ix_triage_label_configs_account", "account_id"),)

    id = db.Column(db.String(64), primary_key=True, default=lambda: str(uuid4()), nullable=False)
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=True)
    name = db.Column(db.String(128), nullable=False, default="default")
    labels = db.Column(db.JSON, nullable=False, default=dict)
    created_at = db.Column(db.DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "account_id": self.account_id,
            "name": self.name,
            "labels": self.labels or {},
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class DspyTrainingMetric(db.Model):
    """
    Track DSPy training metrics for historical monitoring.

    Core accuracy focuses on action_required + priority (most important fields).
    Weighted accuracy gives partial credit for other fields.
    Per-field accuracy is stored in metadata_json.
    """
    __tablename__ = "dspy_training_metrics"
    __table_args__ = (db.Index("ix_dspy_training_metrics_account", "account_id"),)

    id = db.Column(db.String(64), primary_key=True, default=lambda: str(uuid4()), nullable=False)
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=True)
    model_id = db.Column(db.String(128), nullable=False)
    provider = db.Column(db.String(32), nullable=False, default="openai")
    sample_count = db.Column(db.Integer, nullable=False, default=0)
    seed_count = db.Column(db.Integer, nullable=True, default=0)
    eval_count = db.Column(db.Integer, nullable=True)
    train_accuracy = db.Column(db.Float, nullable=True)  # Core accuracy (action_required + priority)
    eval_accuracy = db.Column(db.Float, nullable=True)  # Core accuracy on eval set
    train_weighted = db.Column(db.Float, nullable=True)  # Weighted accuracy across all fields
    eval_weighted = db.Column(db.Float, nullable=True)  # Weighted accuracy on eval set
    metadata_json = db.Column(db.Text, nullable=True)  # Per-field accuracy and other details
    created_at = db.Column(db.DateTime(timezone=True), server_default=func.now(), nullable=False)

    def to_dict(self) -> dict:
        import json
        metadata = {}
        if self.metadata_json:
            try:
                metadata = json.loads(self.metadata_json)
            except (json.JSONDecodeError, TypeError):
                pass
        return {
            "id": self.id,
            "account_id": self.account_id,
            "model_id": self.model_id,
            "provider": self.provider,
            "sample_count": self.sample_count,
            "seed_count": self.seed_count,
            "eval_count": self.eval_count,
            "train_accuracy": self.train_accuracy,
            "eval_accuracy": self.eval_accuracy,
            "train_weighted": self.train_weighted,
            "eval_weighted": self.eval_weighted,
            "metadata": metadata,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class AuthEvent(db.Model):
    """
    Authentication events: login attempts, password resets, JWT refresh failures, etc.
    """
    __tablename__ = "auth_events"
    id = db.Column(db.String(64), primary_key=True, default=lambda: str(uuid4()), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=True, index=True)
    email = db.Column(db.String(255), nullable=True, index=True)
    event = db.Column(db.String(64), nullable=False)  # e.g., login, password_reset_request, password_reset_complete, jwt_refresh_fail
    outcome = db.Column(db.String(32), nullable=False, default="unknown")  # success|fail|ignored
    reason = db.Column(db.String(255), nullable=True)
    ip = db.Column(db.String(64), nullable=True)
    user_agent = db.Column(db.String(300), nullable=True)
    metadata_json = db.Column("metadata", db.JSON, nullable=False, default=dict)
    created_at = db.Column(db.DateTime(timezone=True), server_default=func.now(), nullable=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "account_id": self.account_id,
            "email": self.email,
            "event": self.event,
            "outcome": self.outcome,
            "reason": self.reason,
            "ip": self.ip,
            "user_agent": self.user_agent,
            "metadata": self.metadata_json or {},
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class AgentEvent(db.Model):
    """
    Agent invocation telemetry: success/error/retry/timeout and latency.
    """
    __tablename__ = "agent_events"
    __table_args__ = (db.Index("ix_agent_events_agent_name", "agent_name"),)

    id = db.Column(db.String(64), primary_key=True, default=lambda: str(uuid4()), nullable=False)
    agent_id = db.Column(db.String(128), nullable=True)
    agent_name = db.Column(db.String(255), nullable=True)
    event = db.Column(db.String(32), nullable=False)  # invoke|success|error|retry|timeout
    status = db.Column(db.String(32), nullable=True)  # success|error|timeout
    ticket_id = db.Column(db.String(64), nullable=True)
    context = db.Column(db.JSON, nullable=False, default=dict)
    latency_ms = db.Column(db.Integer, nullable=True)
    error_message = db.Column(db.String(512), nullable=True)
    traceback = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), server_default=func.now(), nullable=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "agent_id": self.agent_id,
            "agent_name": self.agent_name,
            "event": self.event,
            "status": self.status,
            "ticket_id": self.ticket_id,
            "context": self.context or {},
            "latency_ms": self.latency_ms,
            "error_message": self.error_message,
            "traceback": self.traceback,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class AgentModel(db.Model):
    """
    Lightweight persisted agent spec; mirrors the legacy ai_agents table.
    """
    __tablename__ = "ai_agents"

    id = db.Column(db.String(64), primary_key=True, default=lambda: str(uuid4()), nullable=False)
    name = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(32), nullable=False, default="draft")
    mcp_servers = db.Column(db.JSON, nullable=False, default=list)
    capabilities = db.Column(db.JSON, nullable=False, default=list)
    triggers = db.Column(db.JSON, nullable=False, default=list)
    human_review = db.Column(db.JSON, nullable=False, default=dict)
    graph_node_ref = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), default=func.now(), nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), default=func.now(), onupdate=func.now(), nullable=False)


class MCPServerCatalog(db.Model):
    """
    Allowed MCP server definitions for agent use.
    """
    __tablename__ = "mcp_server_catalog"

    id = db.Column(db.String(64), primary_key=True, default=lambda: str(uuid4()), nullable=False)
    label = db.Column(db.String(255), unique=True, nullable=False)
    command = db.Column(db.JSON, nullable=False)  # string or list[str]
    env = db.Column(db.JSON, nullable=True)
    cwd = db.Column(db.String(512), nullable=True)
    enabled = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime(timezone=True), default=func.now(), nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), default=func.now(), onupdate=func.now(), nullable=False)


class Testimonial(db.Model):
    __tablename__ = "inboxiq_testimonials"

    id = db.Column(db.String(64), primary_key=True, default=lambda: str(uuid4()), nullable=False)
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    rating = db.Column(db.SmallInteger, nullable=False)
    message = db.Column(db.Text, nullable=False)
    consent_public = db.Column(db.Boolean, nullable=False, default=False)
    source = db.Column(db.String(32), nullable=False, default="in_app")
    status = db.Column(db.String(32), nullable=False, default="pending")
    created_at = db.Column(db.DateTime(timezone=True), server_default=func.now(), nullable=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "account_id": self.account_id,
            "user_id": self.user_id,
            "rating": self.rating,
            "message": self.message,
            "consent_public": self.consent_public,
            "source": self.source,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Feedback(db.Model):
    __tablename__ = "inboxiq_feedback"

    id = db.Column(db.String(64), primary_key=True, default=lambda: str(uuid4()), nullable=False)
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    message = db.Column(db.Text, nullable=False)
    context = db.Column(db.Text, nullable=True)
    urgency = db.Column(db.SmallInteger, nullable=False, default=3)
    source = db.Column(db.String(32), nullable=False, default="in_app")
    status = db.Column(db.String(32), nullable=False, default="new")
    action_required = db.Column(db.String(16), nullable=False, default="optional")
    metadata_json = db.Column(db.JSON, nullable=False, default=dict)
    ai_decision_json = db.Column(db.JSON, nullable=False, default=dict)
    ticket_id = db.Column(db.String(64), db.ForeignKey("inboxiq_tickets.id"), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), server_default=func.now(), nullable=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "account_id": self.account_id,
            "user_id": self.user_id,
            "message": self.message,
            "context": self.context,
            "urgency": self.urgency,
            "source": self.source,
            "status": self.status,
            "action_required": self.action_required,
            "metadata": self.metadata_json or {},
            "decision": self.ai_decision_json or {},
            "ticket_id": self.ticket_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class IntakeToken(db.Model):
    __tablename__ = "intake_tokens"
    __table_args__ = (db.UniqueConstraint("token_hash", name="uq_intake_token_hash"),)

    id = db.Column(db.String(64), primary_key=True, default=lambda: str(uuid4()), nullable=False)
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=False)
    label = db.Column(db.String(128), nullable=True)
    token_hash = db.Column(db.String(128), nullable=False)
    revoked_at = db.Column(db.DateTime(timezone=True), nullable=True)
    expires_at = db.Column(db.DateTime(timezone=True), nullable=True)
    allowed_ips = db.Column(db.JSON, nullable=False, default=list)
    created_at = db.Column(db.DateTime(timezone=True), server_default=func.now(), nullable=False)

    def is_active(self) -> bool:
        return self.revoked_at is None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "account_id": self.account_id,
            "label": self.label,
            "token": None,  # never expose the hash
            "allowed_ips": self.allowed_ips or [],
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "revoked_at": self.revoked_at.isoformat() if self.revoked_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Passkey(db.Model):
    __tablename__ = "passkeys"
    __table_args__ = (db.UniqueConstraint("credential_id", name="uq_passkey_credential"),)

    id = db.Column(db.String(64), primary_key=True, default=lambda: str(uuid4()), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    label = db.Column(db.String(128), nullable=True)
    credential_id = db.Column(db.String(512), nullable=False)
    public_key = db.Column(db.Text, nullable=False)
    sign_count = db.Column(db.Integer, nullable=False, default=0)
    transports = db.Column(db.JSON, nullable=False, default=list)
    last_used_at = db.Column(db.DateTime(timezone=True), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), server_default=func.now(), nullable=False)

    def to_dict(self):
        return {
            "id": self.id,
            "label": self.label or "Passkey",
            "credential_id": self.credential_id,
            "sign_count": self.sign_count,
            "transports": self.transports or [],
            "last_used_at": self.last_used_at.isoformat() if self.last_used_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class TOTPDevice(db.Model):
    __tablename__ = "totp_devices"

    id = db.Column(db.String(64), primary_key=True, default=lambda: str(uuid4()), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    secret = db.Column(db.String(64), nullable=False)
    verified_at = db.Column(db.DateTime(timezone=True), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), server_default=func.now(), nullable=False)

    def is_verified(self) -> bool:
        return self.verified_at is not None

    def to_dict(self):
        return {
            "id": self.id,
            "verified": self.is_verified(),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "verified_at": self.verified_at.isoformat() if self.verified_at else None,
        }


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


class BlogPost(db.Model):
    __tablename__ = "blog_posts"
    __table_args__ = (
        db.UniqueConstraint("slug", name="uq_blog_slug"),
        db.Index("idx_blog_posts_generated", "generated_content_id"),
    )

    id = db.Column(db.String(64), primary_key=True, default=lambda: str(uuid4()), nullable=False)
    title = db.Column(db.String(255), nullable=False)
    slug = db.Column(db.String(255), nullable=False, index=True)
    status = db.Column(db.String(32), nullable=False, default="draft")  # draft|queued|generating|ready|failed|published
    funnel_stage = db.Column(db.String(16), nullable=True)
    primary_keyword = db.Column(db.String(255), nullable=True)
    secondary_keywords = db.Column(db.JSON, nullable=False, default=list)
    summary = db.Column(db.Text, nullable=True)
    excerpt = db.Column(db.Text, nullable=True)
    content_html = db.Column(db.Text, nullable=True)
    markdown = db.Column(db.Text, nullable=True)
    rendered_html = db.Column(db.Text, nullable=True)
    brief_json = db.Column(db.JSON, nullable=True)
    last_prompt = db.Column(db.Text, nullable=True)
    meta_description = db.Column(db.Text, nullable=True)
    canonical_url = db.Column(db.String(512), nullable=True)
    hero_image_url = db.Column(db.String(1024), nullable=True)
    hero_image_alt = db.Column(db.String(255), nullable=True)
    word_count = db.Column(db.Integer, nullable=True)
    read_time_minutes = db.Column(db.SmallInteger, nullable=True)
    internal_links = db.Column(db.JSON, nullable=False, default=list)

    # Funnel v2.0: Link to generated_content table
    generated_content_id = db.Column(db.String(64), db.ForeignKey("generated_content.id"), nullable=True)
    auto_generated = db.Column(db.Boolean, server_default="false")
    dspy_quality_score = db.Column(db.Float, nullable=True)

    published_at = db.Column(db.DateTime(timezone=True), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "slug": self.slug,
            "status": self.status,
            "funnel_stage": self.funnel_stage,
            "primary_keyword": self.primary_keyword,
            "secondary_keywords": self.secondary_keywords or [],
            "summary": self.summary,
            "excerpt": self.excerpt,
            "content_html": self.content_html,
            "markdown": self.markdown,
            "rendered_html": self.rendered_html,
            "brief_json": self.brief_json or {},
            "last_prompt": self.last_prompt,
            "meta_description": self.meta_description,
            "canonical_url": self.canonical_url,
            "hero_image_url": self.hero_image_url,
            "hero_image_alt": self.hero_image_alt,
            "word_count": self.word_count,
            "read_time_minutes": self.read_time_minutes,
            "internal_links": self.internal_links or [],
            "generated_content_id": self.generated_content_id,
            "auto_generated": self.auto_generated,
            "dspy_quality_score": self.dspy_quality_score,
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class DraftReplyFeedback(db.Model):
    """
    Track human feedback on AI-generated draft replies for continuous improvement.
    Used for training DSPy reply optimization and measuring reply quality metrics.
    """
    __tablename__ = "draft_reply_feedback"
    __table_args__ = (db.Index("ix_draft_reply_feedback_ticket", "ticket_id"),)

    id = db.Column(db.String(64), primary_key=True, default=lambda: str(uuid4()), nullable=False)
    ticket_id = db.Column(db.String(64), db.ForeignKey("inboxiq_tickets.id"), nullable=False)
    draft_text = db.Column(db.Text, nullable=False)
    final_text = db.Column(db.Text, nullable=True)
    feedback_type = db.Column(db.String(32), nullable=False)  # accepted|edited|rejected
    edit_distance = db.Column(db.Integer, nullable=True)
    helpfulness_score = db.Column(db.SmallInteger, nullable=True)  # 1-5 rating
    time_saved_seconds = db.Column(db.Integer, nullable=True)
    metadata_json = db.Column("metadata", db.JSON, nullable=False, default=dict)
    created_at = db.Column(db.DateTime(timezone=True), server_default=func.now(), nullable=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "ticket_id": self.ticket_id,
            "draft_text": self.draft_text,
            "final_text": self.final_text,
            "feedback_type": self.feedback_type,
            "edit_distance": self.edit_distance,
            "helpfulness_score": self.helpfulness_score,
            "time_saved_seconds": self.time_saved_seconds,
            "metadata": self.metadata_json or {},
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class AccountFeatureFlags(db.Model):
    """
    Account-level feature flag overrides for gating features beyond plan limits.
    Enables A/B testing and gradual rollout of features like draft_reply.
    """
    __tablename__ = "account_feature_flags"

    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"), primary_key=True)
    draft_reply_enabled = db.Column(db.Boolean, nullable=False, default=False)
    draft_reply_auto_approve = db.Column(db.Boolean, nullable=False, default=False)  # Future: auto-send low-risk replies
    draft_reply_min_confidence = db.Column(db.Float, nullable=False, default=0.7)
    created_at = db.Column(db.DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    def to_dict(self) -> dict:
        return {
            "account_id": self.account_id,
            "draft_reply_enabled": self.draft_reply_enabled,
            "draft_reply_auto_approve": self.draft_reply_auto_approve,
            "draft_reply_min_confidence": self.draft_reply_min_confidence,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class KBIntegration(db.Model):
    """Knowledge base integration configuration (per account)."""
    __tablename__ = "kb_integrations"

    id = db.Column(db.String(64), primary_key=True, default=lambda: str(uuid4()), nullable=False)
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=False, index=True)
    integration_type = db.Column(db.String(50), nullable=False)  # "file_upload", "zendesk", "notion", etc.
    status = db.Column(db.String(20), default="active")  # "active", "paused", "error"

    # Configuration (JSON)
    config_json = db.Column("config", db.JSON, nullable=False, default=dict)

    # Sync metadata
    last_sync_at = db.Column(db.DateTime(timezone=True), nullable=True)
    last_sync_status = db.Column(db.String(20), nullable=True)  # "success", "failed"
    last_sync_error = db.Column(db.Text, nullable=True)
    article_count = db.Column(db.Integer, default=0)

    created_at = db.Column(db.DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    account = db.relationship("Account", backref="kb_integrations")
    articles = db.relationship("KBArticle", backref="integration", cascade="all, delete-orphan")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "account_id": self.account_id,
            "integration_type": self.integration_type,
            "status": self.status,
            "config": self.config_json or {},
            "last_sync_at": self.last_sync_at.isoformat() if self.last_sync_at else None,
            "last_sync_status": self.last_sync_status,
            "last_sync_error": self.last_sync_error,
            "article_count": self.article_count,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class KBArticle(db.Model):
    """Knowledge base article content."""
    __tablename__ = "kb_articles"
    __table_args__ = (
        db.Index("ix_kb_articles_integration_title", "integration_id", "title"),
        db.Index("ix_kb_articles_external_id", "external_id"),
    )

    id = db.Column(db.String(64), primary_key=True, default=lambda: str(uuid4()), nullable=False)
    integration_id = db.Column(db.String(64), db.ForeignKey("kb_integrations.id"), nullable=False, index=True)

    # Article metadata
    external_id = db.Column(db.String(255), nullable=True)  # ID from external system (Zendesk, etc.)
    title = db.Column(db.String(500), nullable=False)
    content = db.Column(db.Text, nullable=False)
    url = db.Column(db.String(1000), nullable=True)

    # Categorization
    category = db.Column(db.String(255), nullable=True)
    tags_json = db.Column("tags", db.JSON, nullable=True)  # ["billing", "refunds"]
    language = db.Column(db.String(10), default="en")

    # Sync tracking
    external_updated_at = db.Column(db.DateTime(timezone=True), nullable=True)
    synced_at = db.Column(db.DateTime(timezone=True), server_default=func.now())

    created_at = db.Column(db.DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    embeddings = db.relationship("KBArticleEmbedding", backref="article", cascade="all, delete-orphan")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "integration_id": self.integration_id,
            "external_id": self.external_id,
            "title": self.title,
            "content": self.content,
            "url": self.url,
            "category": self.category,
            "tags": self.tags_json or [],
            "language": self.language,
            "external_updated_at": self.external_updated_at.isoformat() if self.external_updated_at else None,
            "synced_at": self.synced_at.isoformat() if self.synced_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class KBArticleEmbedding(db.Model):
    """Vector embeddings for KB articles (semantic search)."""
    __tablename__ = "kb_article_embeddings"

    id = db.Column(db.String(64), primary_key=True, default=lambda: str(uuid4()), nullable=False)
    article_id = db.Column(db.String(64), db.ForeignKey("kb_articles.id"), nullable=False, index=True)

    # Embedding data (same pattern as TicketEmbedding)
    embedding_model = db.Column(db.String(100), default="text-embedding-3-small")
    embedding_vector = db.Column(Vector(1536)) if Vector else db.Column(db.JSON, nullable=True)
    embedding_json = db.Column(db.JSON, nullable=True)  # JSON fallback if pgvector unavailable

    created_at = db.Column(db.DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Vector index for cosine similarity search
    if Vector:
        __table_args__ = (
            db.Index(
                "ix_kb_article_embeddings_vector",
                "embedding_vector",
                postgresql_using="ivfflat",
                postgresql_with={"lists": 100},
                postgresql_ops={"embedding_vector": "vector_cosine_ops"},
            ),
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "article_id": self.article_id,
            "embedding_model": self.embedding_model,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class TriageConfig(db.Model):
    """
    Per-account triage configuration for customizable SLA mappings, fallback messages,
    decision thresholds, and other triage-related settings.

    If no config exists for an account, system-wide defaults are used.
    """
    __tablename__ = "triage_configs"
    __table_args__ = (
        db.UniqueConstraint("account_id", name="uq_triage_config_account"),
        db.Index("ix_triage_configs_account", "account_id"),
    )

    id = db.Column(db.String(64), primary_key=True, default=lambda: str(uuid4()), nullable=False)
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=False)

    # SLA mappings: {"P0": "2h", "P1": "4h", "P2": "24h", "P3": "48h", "P4": "1w"}
    sla_mappings = db.Column(db.JSON, nullable=False, default=dict)

    # SLA durations in hours for compute_due_at: {"P0": 1, "P1": 4, "P2": 24, "P3": 48, "P4": 168}
    sla_hours = db.Column(db.JSON, nullable=False, default=dict)

    # Fallback messages for "Why this decision" text
    # {"action_required": "...", "optional": "...", "auto_handled": "...", "needs_review": "..."}
    fallback_messages = db.Column(db.JSON, nullable=False, default=dict)

    # Default owner/team/category when not specified
    default_owner = db.Column(db.String(128), nullable=True)
    default_team = db.Column(db.String(128), nullable=True)
    default_category = db.Column(db.String(64), nullable=True)
    default_priority = db.Column(db.String(8), nullable=True)

    # Decision thresholds
    confidence_threshold = db.Column(db.Float, nullable=True)  # Default 0.7 for draft reply
    p2_neutral_auto_handle = db.Column(db.Boolean, nullable=False, default=True)  # Auto-handle P2 neutral emails

    # Body preview and summary limits
    body_preview_limit = db.Column(db.Integer, nullable=True)  # Default 240
    summary_limit = db.Column(db.Integer, nullable=True)  # Default 280

    # Training settings
    train_min_samples = db.Column(db.Integer, nullable=True)  # Default 20
    poll_stale_minutes = db.Column(db.Integer, nullable=True)  # Default 30

    created_at = db.Column(db.DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "account_id": self.account_id,
            "sla_mappings": self.sla_mappings or {},
            "sla_hours": self.sla_hours or {},
            "fallback_messages": self.fallback_messages or {},
            "default_owner": self.default_owner,
            "default_team": self.default_team,
            "default_category": self.default_category,
            "default_priority": self.default_priority,
            "confidence_threshold": self.confidence_threshold,
            "p2_neutral_auto_handle": self.p2_neutral_auto_handle,
            "body_preview_limit": self.body_preview_limit,
            "summary_limit": self.summary_limit,
            "train_min_samples": self.train_min_samples,
            "poll_stale_minutes": self.poll_stale_minutes,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


# Funnel v2.0 Models

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


class GeneratedContent(db.Model):
    """
    Tracks all DSPy-generated content (blogs, emails, case studies, landing pages).
    Stores full generation pipeline outputs and quality metrics.
    """
    __tablename__ = "generated_content"
    __table_args__ = (
        db.Index("idx_generated_content_type", "content_type", "status"),
        db.Index("idx_generated_content_published", "published_at", postgresql_where=db.text("published_at IS NOT NULL")),
        db.Index("idx_generated_content_funnel_stage", "funnel_stage"),
    )

    id = db.Column(db.String(64), primary_key=True, default=lambda: str(uuid4()), nullable=False)
    content_type = db.Column(db.String(50), nullable=False, comment="blog_post | email | case_study | landing_page | social_post")
    title = db.Column(db.String(500), nullable=True)
    slug = db.Column(db.String(200), nullable=True)
    content = db.Column(db.Text, nullable=False)
    meta_data = db.Column(db.JSON, nullable=True, comment="{meta_title, meta_description, target_keywords, seo_score, word_count}")
    generation_pipeline = db.Column(db.JSON, nullable=True, comment="{topic_module_output, outline_module_output, writer_output, editor_output, seo_output}")
    dspy_version = db.Column(db.String(50), nullable=True, comment="Track which DSPy model version generated this")
    quality_score = db.Column(db.Float, nullable=True, comment="Human feedback: 0-10")
    status = db.Column(db.String(50), server_default="draft", comment="draft | published | archived")
    published_at = db.Column(db.DateTime(timezone=True), nullable=True)
    funnel_stage = db.Column(db.String(50), nullable=True, comment="Which funnel stage this content supports")
    target_audience_json = db.Column("target_audience", db.JSON, nullable=True, comment="ICP characteristics")
    performance_metrics = db.Column(db.JSON, nullable=True, comment="{views, engagement_rate, conversions, seo_ranking}")
    created_at = db.Column(db.DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "content_type": self.content_type,
            "title": self.title,
            "slug": self.slug,
            "content": self.content,
            "meta_data": self.meta_data or {},
            "generation_pipeline": self.generation_pipeline or {},
            "dspy_version": self.dspy_version,
            "quality_score": self.quality_score,
            "status": self.status,
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "funnel_stage": self.funnel_stage,
            "target_audience": self.target_audience_json or {},
            "performance_metrics": self.performance_metrics or {},
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class PitchedBlogTopic(db.Model):
    """
    Manually pitched blog topics that can be used for content generation.
    Allows users to submit topic ideas in addition to auto-generated topics.
    """
    __tablename__ = "pitched_blog_topics"
    __table_args__ = (
        db.Index("idx_pitched_topics_status", "status"),
        db.Index("idx_pitched_topics_created", "created_at"),
    )

    id = db.Column(db.String(64), primary_key=True, default=lambda: str(uuid4()), nullable=False)
    title = db.Column(db.String(500), nullable=False, comment="Working title or topic idea")
    description = db.Column(db.Text, nullable=True, comment="Optional description or angle")
    target_keyword = db.Column(db.String(255), nullable=True, comment="Primary keyword to target")
    secondary_keywords = db.Column(db.JSON, nullable=False, default=list, comment="Additional keywords")
    funnel_stage = db.Column(db.String(50), nullable=True, comment="discovery | consideration | decision")
    target_audience = db.Column(db.String(500), nullable=True, comment="Target audience/persona")
    niche = db.Column(db.String(255), nullable=True, comment="Blog niche (e.g., Revenue Operations)")
    pitch_notes = db.Column(db.Text, nullable=True, comment="Additional notes from submitter")

    status = db.Column(db.String(50), nullable=False, default="pending", comment="pending | approved | rejected | generated")
    priority = db.Column(db.SmallInteger, nullable=False, default=3, comment="1=high, 2=medium, 3=low")

    # Tracking fields
    submitted_by = db.Column(db.String(255), nullable=True, comment="Email of submitter")
    reviewed_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    reviewed_at = db.Column(db.DateTime(timezone=True), nullable=True)
    generated_content_id = db.Column(db.String(64), db.ForeignKey("generated_content.id"), nullable=True, comment="Link to generated content if used")

    created_at = db.Column(db.DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "target_keyword": self.target_keyword,
            "secondary_keywords": self.secondary_keywords or [],
            "funnel_stage": self.funnel_stage,
            "target_audience": self.target_audience,
            "niche": self.niche,
            "pitch_notes": self.pitch_notes,
            "status": self.status,
            "priority": self.priority,
            "submitted_by": self.submitted_by,
            "reviewed_at": self.reviewed_at.isoformat() if self.reviewed_at else None,
            "generated_content_id": self.generated_content_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


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
        db.Enum("pending", "sent", "delivered", "opened", "clicked", "replied", "bounced", "failed", name="outreach_status_enum"),
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

    created_at = db.Column(db.DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


# ============================================================================
# Automation Studio Models
# ============================================================================


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

class DeveloperAccessRequest(db.Model):
    """Request for developer API access. Must be approved before RegisteredApp can be created."""
    __tablename__ = "developer_access_requests"

    id            = db.Column(db.String(64), primary_key=True, default=lambda: str(uuid4()))
    account_id    = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=False)
    full_name     = db.Column(db.String(255), nullable=False)
    company       = db.Column(db.String(255), nullable=False)
    use_case      = db.Column(db.Text, nullable=False)       # what they are building
    scopes        = db.Column(db.JSON, nullable=False)       # requested scopes
    callback_url  = db.Column(db.String(2048), nullable=True)
    agreed_tos    = db.Column(db.Boolean, nullable=False, default=False)
    status        = db.Column(db.String(32), nullable=False, default="pending")  # pending | approved | rejected
    reviewed_by   = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    reviewed_at   = db.Column(db.DateTime(timezone=True), nullable=True)
    created_at    = db.Column(db.DateTime(timezone=True), server_default=func.now(), nullable=False)


class RegisteredApp(db.Model):
    """A developer app registered to connect an external system to InboxIQ."""
    __tablename__ = "registered_apps"
    __table_args__ = (db.UniqueConstraint("client_id", name="uq_registered_app_client_id"),)

    id                 = db.Column(db.String(64), primary_key=True, default=lambda: str(uuid4()))
    account_id         = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=False)
    name               = db.Column(db.String(255), nullable=False)
    client_id          = db.Column(db.String(64), nullable=False)       # public, auto-generated
    client_secret_enc  = db.Column(db.String(512), nullable=False)      # encrypted, shown once at creation
    webhook_url        = db.Column(db.String(2048), nullable=True)      # where InboxIQ posts events
    webhook_secret_enc = db.Column(db.String(512), nullable=True)       # HMAC key for outbound events
    scopes             = db.Column(db.JSON, nullable=False, default=list)
    allowed_ips        = db.Column(db.JSON, nullable=False, default=list)
    status             = db.Column(db.String(32), nullable=False, default="active")  # active | suspended
    created_at         = db.Column(db.DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_used_at       = db.Column(db.DateTime(timezone=True), nullable=True)
