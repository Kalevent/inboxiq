from datetime import datetime
from uuid import uuid4
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import TSVECTOR
from src.extensions import db

try:  # Optional pgvector support
    from pgvector.sqlalchemy import Vector  # type: ignore
except Exception:
    Vector = None

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



