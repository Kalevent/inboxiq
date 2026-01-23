from __future__ import annotations

from uuid import uuid4
from sqlalchemy import func

from src.extensions import db


class NewsletterDraft(db.Model):
    """
    Lightweight mirror of the legacy newsletter draft for publishing.
    """

    __tablename__ = "newsletter_draft"

    id = db.Column(db.String(), primary_key=True, unique=True, nullable=False, default=lambda: str(uuid4()))
    campaign_title = db.Column(db.String)
    audience = db.Column(db.String)
    brief_json = db.Column(db.JSON)
    status = db.Column(db.String, default="queued")
    rendered_html = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=func.now(), nullable=False)


class WhitepaperDraft(db.Model):
    """
    Lightweight mirror of the legacy whitepaper draft for publishing.
    """

    __tablename__ = "whitepaper_drafts"

    id = db.Column(db.String(), primary_key=True, unique=True, nullable=False, default=lambda: str(uuid4()))
    title = db.Column(db.String(200))
    brief_json = db.Column(db.JSON)
    markdown = db.Column(db.Text)
    pdf_url = db.Column(db.String)
    status = db.Column(db.String(40), default="queued")
    created_at = db.Column(db.DateTime, default=func.now(), nullable=False)
