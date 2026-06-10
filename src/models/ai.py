from uuid import uuid4
from sqlalchemy.sql import func
from src.extensions import db

try:  # Optional pgvector support
    from pgvector.sqlalchemy import Vector  # type: ignore
except Exception:
    Vector = None

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
    trace_id = db.Column(db.String(32), nullable=True, index=True, comment="OpenTelemetry trace_id (32-hex) for Phoenix correlation")
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
            "trace_id": self.trace_id,
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


