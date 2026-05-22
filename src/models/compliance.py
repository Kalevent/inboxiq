from __future__ import annotations
from uuid import uuid4
from sqlalchemy.sql import func
from src.extensions import db


class ComplianceReport(db.Model):
    __tablename__ = "compliance_reports"

    id         = db.Column(db.String(64), primary_key=True, default=lambda: str(uuid4()))
    period     = db.Column(db.String(7), nullable=False)           # "2026-05"
    s3_key     = db.Column(db.String(512), nullable=False)
    summary    = db.Column(db.JSON, nullable=False, default=dict)  # {pass,warn,fail,error,total}
    created_at = db.Column(db.DateTime(timezone=True), server_default=func.now(), nullable=False)
