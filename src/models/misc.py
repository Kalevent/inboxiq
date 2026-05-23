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


class Booking(db.Model):
    __tablename__ = "inboxiq_bookings"

    id = db.Column(db.String(64), primary_key=True, default=lambda: str(uuid4()), nullable=False)
    token_hash = db.Column(db.String(64), unique=True, nullable=False, index=True)
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=False)
    ticket_id = db.Column(db.String(64), db.ForeignKey("inboxiq_tickets.id"), nullable=False)
    subject = db.Column(db.String(500), nullable=False, default="")
    requester_email = db.Column(db.String(255), nullable=False, default="")
    requester_name = db.Column(db.String(255), nullable=False, default="")
    duration_minutes = db.Column(db.Integer, nullable=False, default=30)
    status = db.Column(db.String(32), nullable=False, default="pending")
    slot_start = db.Column(db.DateTime(timezone=True), nullable=True)
    slot_end = db.Column(db.DateTime(timezone=True), nullable=True)
    booked_by_name = db.Column(db.String(255), nullable=True)
    booked_by_email = db.Column(db.String(255), nullable=True)
    calendar_event_id = db.Column(db.String(255), nullable=True)
    meet_link = db.Column(db.String(500), nullable=True)
    confirmed_at = db.Column(db.DateTime(timezone=True), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), server_default=func.now(), nullable=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "account_id": self.account_id,
            "ticket_id": self.ticket_id,
            "subject": self.subject,
            "requester_email": self.requester_email,
            "requester_name": self.requester_name,
            "duration_minutes": self.duration_minutes,
            "status": self.status,
            "slot_start": self.slot_start.isoformat() if self.slot_start else None,
            "slot_end": self.slot_end.isoformat() if self.slot_end else None,
            "booked_by_name": self.booked_by_name,
            "booked_by_email": self.booked_by_email,
            "meet_link": self.meet_link,
            "confirmed_at": self.confirmed_at.isoformat() if self.confirmed_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class AriaConversation(db.Model):
    """Chat widget conversations saved when a conclusive intent fires (book_demo or needs_human).
    Used as a source for DSPy training examples — export via admin AI & Training section."""
    __tablename__ = "aria_conversations"

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid4()), nullable=False)
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=True, index=True)
    visitor_name = db.Column(db.String(200), nullable=False, default="")
    visitor_email = db.Column(db.String(200), nullable=False, default="")
    branch = db.Column(db.String(20), nullable=False, default="demo")
    intent = db.Column(db.String(30), nullable=False)
    messages = db.Column(db.Text, nullable=False, default="[]")
    created_at = db.Column(db.DateTime(timezone=True), server_default=func.now(), nullable=False)
