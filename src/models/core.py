from datetime import datetime
from uuid import uuid4
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import TSVECTOR
from src.extensions import db

try:  # Optional pgvector support
    from pgvector.sqlalchemy import Vector  # type: ignore
except Exception:
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
    role = db.Column(db.String(32), nullable=False, server_default="agent",
                     comment="owner | admin | agent | viewer | billing")
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


