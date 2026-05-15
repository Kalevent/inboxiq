from datetime import datetime
from uuid import uuid4
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import TSVECTOR
from src.extensions import db

try:  # Optional pgvector support
    from pgvector.sqlalchemy import Vector  # type: ignore
except Exception:
    Vector = None

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


class AppProductAccess(db.Model):
    """Per-product access request for a registered app."""
    __tablename__ = "app_product_access"
    __table_args__ = (
        db.UniqueConstraint("app_id", "product_slug", name="uq_app_product"),
    )

    id           = db.Column(db.String(64), primary_key=True, default=lambda: str(uuid4()))
    app_id       = db.Column(db.String(64), db.ForeignKey("registered_apps.id", ondelete="CASCADE"), nullable=False)
    account_id   = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=False)
    product_slug = db.Column(db.String(64), nullable=False)
    status       = db.Column(db.String(32), nullable=False, default="pending")  # pending | approved | rejected
    use_case     = db.Column(db.Text, nullable=True)
    webhook_url  = db.Column(db.String(2048), nullable=True)
    requested_at = db.Column(db.DateTime(timezone=True), server_default=func.now(), nullable=False)
    approved_at  = db.Column(db.DateTime(timezone=True), nullable=True)
    reviewed_by  = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)

