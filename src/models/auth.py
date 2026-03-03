from datetime import datetime
from uuid import uuid4
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import TSVECTOR
from src.extensions import db

try:  # Optional pgvector support
    from pgvector.sqlalchemy import Vector  # type: ignore
except Exception:
    Vector = None

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


