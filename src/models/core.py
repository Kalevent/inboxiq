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
    deleted_at = db.Column(db.DateTime(timezone=True), nullable=True, index=True)
    created_at = db.Column(db.DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    users = db.relationship("User", backref="account", lazy=True)

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None

class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    name = db.Column(db.String(255), nullable=True)
    password_hash = db.Column(db.String(255), nullable=True)
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=False)
    role = db.Column(db.String(32), nullable=False, server_default="agent",
                     comment="owner | admin | agent | viewer | billing")
    mfa_setup_required = db.Column(db.Boolean, nullable=False, server_default="false",
                                   comment="True for invited sub-users until they configure TOTP or a passkey")
    created_at = db.Column(db.DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class InboxConnection(db.Model):
    __tablename__ = "inbox_connections"
    __table_args__ = (db.UniqueConstraint("account_id", "email_address", name="uq_account_email_inbox"),)

    id = db.Column(db.String(64), primary_key=True, default=lambda: str(uuid4()), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=True)
    provider = db.Column(db.String(32), nullable=False)
    email_address = db.Column(db.String(255), nullable=True)
    display_name = db.Column(db.String(100), nullable=True)
    status = db.Column(db.String(32), nullable=False, default="connected")
    access_token = db.Column(db.Text, nullable=True)
    refresh_token = db.Column(db.Text, nullable=True)
    token_expires_at = db.Column(db.DateTime(timezone=True), nullable=True)
    scopes = db.Column(db.JSON, nullable=False, default=list)
    metadata_json = db.Column("metadata", db.JSON, nullable=False, default=dict)
    invite_token = db.Column(db.String(256), nullable=True)
    invite_token_expires_at = db.Column(db.DateTime(timezone=True), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "provider": self.provider,
            "email_address": self.email_address,
            "display_name": self.display_name,
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
    draft_reply_enabled = db.Column(db.Boolean, nullable=False, default=True)
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


# Permitted provider/model combinations for BYOL (Bring Your Own LLM).
# Customers supply a base_url and api_key — we restrict which models they can
# select to avoid sending data to arbitrary unknown endpoints.
ALLOWED_LLM_PROVIDERS = {
    "openai": {
        "label": "OpenAI (your own API key)",
        "models": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo"],
        "base_url": "https://api.openai.com/v1",
        "base_url_editable": False,
    },
    "anthropic": {
        "label": "Anthropic (your own API key)",
        "models": ["claude-opus-4-6", "claude-sonnet-4-6", "claude-haiku-4-5-20251001"],
        "base_url": "https://api.anthropic.com",
        "base_url_editable": False,
    },
    "ollama": {
        "label": "Ollama (self-hosted)",
        "models": ["llama3.2", "llama3.1", "mistral", "phi4", "qwen2.5"],
        "base_url": None,  # Customer must provide
        "base_url_editable": True,
    },
    "openai_compatible": {
        "label": "OpenAI-compatible endpoint",
        "models": [],  # Customer specifies model name
        "base_url": None,  # Customer must provide
        "base_url_editable": True,
    },
}


class AccountLLMConfig(db.Model):
    """
    Per-account LLM provider configuration for BYOL (Bring Your Own LLM).

    When set, all AI inference for the account is routed to the customer's
    own endpoint instead of InboxIQ's default OpenAI key. This means:
    - The customer's API key is used (cost is theirs)
    - Email content goes to their chosen endpoint (data stays with them)
    - InboxIQ's OpenAI key is NOT used for this account

    api_key_enc is stored Fernet-encrypted via src/crypto.py.
    """
    __tablename__ = "account_llm_configs"

    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"), primary_key=True)
    provider = db.Column(db.String(32), nullable=False, comment="openai | anthropic | ollama | openai_compatible")
    base_url = db.Column(db.String(512), nullable=True, comment="Required for ollama/openai_compatible, fixed for openai/anthropic")
    model = db.Column(db.String(128), nullable=False)
    api_key_enc = db.Column(db.Text, nullable=True, comment="Fernet-encrypted API key; null for providers that don't need one (local ollama)")
    enabled = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    def to_dict(self) -> dict:
        return {
            "account_id": self.account_id,
            "provider": self.provider,
            "base_url": self.base_url,
            "model": self.model,
            "has_api_key": bool(self.api_key_enc),
            "enabled": self.enabled,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class MailboxSyncPreference(db.Model):
    """
    Per-account mapping from InboxIQ canonical categories to the label/folder
    names the user wants to see in Gmail or Outlook.  Defaults are applied
    automatically; Oliver can rename them from Settings → Categories.

    Example: canonical_category="Transactions", provider="gmail",
             provider_label="Receipts"  → Gmail label becomes "InboxIQ · Receipts"
    """
    __tablename__ = "mailbox_sync_preferences"
    __table_args__ = (
        db.UniqueConstraint(
            "account_id", "provider", "canonical_category",
            name="uq_mailbox_sync_pref",
        ),
        db.Index("ix_mailbox_sync_pref_account", "account_id"),
    )

    id                 = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid4()))
    account_id         = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=False)
    provider           = db.Column(db.String(32), nullable=False)   # gmail | outlook
    canonical_category = db.Column(db.String(64), nullable=False)
    provider_label     = db.Column(db.String(128), nullable=False)
    enabled            = db.Column(db.Boolean, nullable=False, default=True)
    created_at         = db.Column(db.DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at         = db.Column(db.DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "account_id": self.account_id,
            "provider": self.provider,
            "canonical_category": self.canonical_category,
            "provider_label": self.provider_label,
            "enabled": self.enabled,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }



