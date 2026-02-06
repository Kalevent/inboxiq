"""
Celery tasks for lead management.

Legacy lead sourcing tasks have been migrated to src/funnel/tasks.py.
This module now contains only the sync_recipients task.
"""
from __future__ import annotations

from typing import Any, Dict, List
from datetime import datetime, timedelta

from celery import shared_task
from src.extensions import db
from src.models import Lead


@shared_task(name="leads.sync_recipients", bind=True, max_retries=0, queue="leads")
def sync_recipients(
    self,
    min_score: int = 0,
    status: str = "New Lead",
    max_age_hours: int | None = None,
    topics: List[str] | None = None,
) -> Dict[str, Any]:
    """
    Push eligible leads into newsletter recipients (deduped on email).
    """
    topics = topics or ["newsletter"]
    since = None
    if max_age_hours:
        since = datetime.utcnow() - timedelta(hours=max_age_hours)

    q = Lead.query.filter(Lead.status == status)
    if min_score:
        q = q.filter(Lead.score >= min_score)
    if since:
        q = q.filter(Lead.created_at >= since)

    leads = q.all()
    inserted = 0
    for lead in leads:
        email = (lead.email or "").strip()
        if not email:
            continue
        uid = str(uuid4())
        name = lead.name or lead.company_name or "Lead"
        topics_sql = "{" + ",".join([t.replace(",", "") for t in topics]) + "}"
        stmt = text(
            """
            INSERT INTO recipients (uid, email, name, is_unsubscribed, topics, suppressed, created_at)
            VALUES (:uid, :email, :name, false, :topics, false, NOW())
            ON CONFLICT (email) DO NOTHING
            """
        )
        try:
            db.session.execute(stmt, {"uid": uid, "email": email, "name": name, "topics": topics_sql})
            db.session.commit()
            inserted += 1
        except Exception:
            db.session.rollback()
            continue

    return {"status": "ok", "inserted": inserted, "candidates": len(leads)}
