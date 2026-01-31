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
    created_at = db.Column(db.DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    users = db.relationship("User", backref="account", lazy=True)

class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
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
    """
    __tablename__ = "dspy_training_metrics"
    __table_args__ = (db.Index("ix_dspy_training_metrics_account", "account_id"),)

    id = db.Column(db.String(64), primary_key=True, default=lambda: str(uuid4()), nullable=False)
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=True)
    model_id = db.Column(db.String(128), nullable=False)
    provider = db.Column(db.String(32), nullable=False, default="openai")
    sample_count = db.Column(db.Integer, nullable=False, default=0)
    eval_count = db.Column(db.Integer, nullable=True)
    train_accuracy = db.Column(db.Float, nullable=True)
    eval_accuracy = db.Column(db.Float, nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), server_default=func.now(), nullable=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "account_id": self.account_id,
            "model_id": self.model_id,
            "provider": self.provider,
            "sample_count": self.sample_count,
            "eval_count": self.eval_count,
            "train_accuracy": self.train_accuracy,
            "eval_accuracy": self.eval_accuracy,
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
    """
    __tablename__ = "leads"

    id = db.Column(db.String(64), primary_key=True, default=lambda: str(uuid4()), nullable=False)
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
    created_at = db.Column(db.DateTime(timezone=True), nullable=True)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
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
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class BlogPost(db.Model):
    __tablename__ = "blog_posts"
    __table_args__ = (db.UniqueConstraint("slug", name="uq_blog_slug"),)

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
