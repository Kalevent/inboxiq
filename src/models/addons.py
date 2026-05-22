from uuid import uuid4
from sqlalchemy.sql import func
from src.extensions import db


class AccountAddOn(db.Model):
    __tablename__ = "account_addons"
    __table_args__ = (
        db.UniqueConstraint("account_id", "addon_type", name="uq_account_addon_type"),
        db.Index("ix_account_addons_account_type", "account_id", "addon_type"),
    )

    id = db.Column(db.String(64), primary_key=True, default=lambda: str(uuid4()))
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=False, index=True)
    addon_type = db.Column(db.String(64), nullable=False)  # "finance"
    status = db.Column(db.String(32), nullable=False, default="inactive")  # active|inactive|cancelled

    # Stripe subscription tracking for this add-on
    stripe_subscription_id = db.Column(db.String(128), nullable=True)

    # Volume metering — reset monthly
    transactions_this_month = db.Column(db.Integer, nullable=False, default=0)
    billing_month = db.Column(db.String(7), nullable=True)  # "2026-05"

    # Add-on configuration:
    # {
    #   "mode": "direct_sync" | "csv_export",
    #   "stripe_provider_id": "<WebhookProvider id>",
    #   "qb_provider_id": "<WebhookProvider id>",   # Mode 1 only
    #   "csv_email": "accounting@company.com",       # Mode 2 only
    # }
    config_json = db.Column(db.JSON, nullable=False, default=dict)

    created_at = db.Column(db.DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    account = db.relationship("Account", backref="addons")

    def is_active(self) -> bool:
        return self.status == "active"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "account_id": self.account_id,
            "addon_type": self.addon_type,
            "status": self.status,
            "transactions_this_month": self.transactions_this_month,
            "billing_month": self.billing_month,
            "config_json": self.config_json,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
