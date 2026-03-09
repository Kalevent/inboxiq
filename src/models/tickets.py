from datetime import datetime
from uuid import uuid4
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import TSVECTOR
from src.extensions import db

try:  # Optional pgvector support
    from pgvector.sqlalchemy import Vector  # type: ignore
except Exception:
    Vector = None

class Ticket(db.Model):
    __tablename__ = "inboxiq_tickets"
    __table_args__ = (db.UniqueConstraint("message_id", "provider", name="uq_ticket_message_provider"),)

    id = db.Column(db.String(64), primary_key=True, default=lambda: str(uuid4()), nullable=False)
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    subject = db.Column(db.String(500), nullable=False)
    from_email = db.Column(db.String(255), nullable=False)
    body_preview = db.Column(db.Text, nullable=True)
    category = db.Column(db.String(64), nullable=False, default="support")
    priority = db.Column(db.String(8), nullable=False, default="P2")
    sentiment = db.Column(db.String(32), nullable=False, default="neutral")
    entities = db.Column(db.JSON, nullable=False, default=dict)
    status = db.Column(db.String(32), nullable=False, default="new")
    message_id = db.Column(db.String(255), nullable=False)
    provider = db.Column(db.String(32), nullable=True)
    provider_thread_url = db.Column(db.String(512), nullable=True)
    provider_message_id = db.Column(db.String(255), nullable=True)
    provider_thread_id = db.Column(db.String(255), nullable=True)
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
    llm_model = db.Column(db.String(100), nullable=True)
    llm_tokens_in = db.Column(db.Integer, nullable=False, default=0, server_default='0')
    llm_tokens_out = db.Column(db.Integer, nullable=False, default=0, server_default='0')
    llm_cost_usd = db.Column(db.Numeric(12, 8), nullable=False, default=0, server_default='0')
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


# ── Native Inbox Intelligence ────────────────────────────────────────────────

class SenderProfile(db.Model):
    """
    Domain-level classification cache that improves over time from the account's
    own inbox behaviour.  account_id=NULL means a global/shared profile that all
    new accounts inherit on day one, giving instant warmup with no prior emails.

    Confidence thresholds (see native_inbox_intelligence_pipeline.md):
      ≥ 0.85  → bypass DSPy entirely, apply category instantly
      0.5–0.85 → run DSPy with sender_hint input field
      < 0.5 / unknown → full DSPy pipeline, no prior
    """
    __tablename__ = "sender_profiles"
    __table_args__ = (
        db.UniqueConstraint("account_id", "domain", name="uq_sender_profile_account_domain"),
        db.Index("ix_sender_profiles_domain", "domain"),
    )

    id            = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid4()))
    account_id    = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=True)  # NULL = global
    domain        = db.Column(db.String(255), nullable=False)
    category      = db.Column(db.String(64), nullable=False)
    confidence    = db.Column(db.Float, nullable=False, default=0.5)
    sample_size   = db.Column(db.Integer, nullable=False, default=0)
    user_verified = db.Column(db.Boolean, nullable=False, default=False)  # True on explicit user correction
    last_seen_at  = db.Column(db.DateTime(timezone=True), nullable=True)
    created_at    = db.Column(db.DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at    = db.Column(db.DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "account_id": self.account_id,
            "domain": self.domain,
            "category": self.category,
            "confidence": self.confidence,
            "sample_size": self.sample_size,
            "user_verified": self.user_verified,
            "last_seen_at": self.last_seen_at.isoformat() if self.last_seen_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class ClassificationCorrection(db.Model):
    """
    Passive feedback captured when Oliver moves an email between labels in Gmail
    or Outlook — no action required from him beyond normal inbox behaviour.

    On each poll we compare the current provider label set against InboxIQ's
    last-applied label. A mismatch creates a ClassificationCorrection and
    upserts the SenderProfile so future emails from the same domain are
    classified correctly.

    signal_source values: label_move | manual_edit | draft_deleted | spam_flag
    """
    __tablename__ = "classification_corrections"
    __table_args__ = (
        db.Index("ix_classification_corrections_account", "account_id"),
        db.Index("ix_classification_corrections_domain", "sender_domain"),
    )

    id                 = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid4()))
    account_id         = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=False)
    ticket_id          = db.Column(db.String(64), db.ForeignKey("inboxiq_tickets.id"), nullable=True)
    sender_domain      = db.Column(db.String(255), nullable=False)
    original_category  = db.Column(db.String(64), nullable=True)
    corrected_category = db.Column(db.String(64), nullable=False)
    signal_source      = db.Column(db.String(32), nullable=False)
    created_at         = db.Column(db.DateTime(timezone=True), server_default=func.now(), nullable=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "account_id": self.account_id,
            "ticket_id": self.ticket_id,
            "sender_domain": self.sender_domain,
            "original_category": self.original_category,
            "corrected_category": self.corrected_category,
            "signal_source": self.signal_source,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# Funnel v2.0 Models

