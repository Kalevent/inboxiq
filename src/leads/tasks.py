"""
Celery tasks for lead management.

Legacy lead sourcing tasks have been migrated to src/funnel/tasks.py.
This module contains sync_recipients and lead enrichment tasks.
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict, List
from datetime import datetime, timedelta
from uuid import uuid4

from celery import shared_task
from sqlalchemy import text
from src.extensions import db
from src.models import Lead


@shared_task(name="leads.enrich_lead", bind=True, max_retries=3, queue="leads")
def enrich_lead(self, lead_id: str) -> Dict[str, Any]:
    """
    Enrich lead data using Lead Discovery MCP server.

    Searches for company information including about pages, contact pages,
    pricing, and other relevant data to build a complete company profile.

    Args:
        lead_id: Lead UUID to enrich

    Returns:
        Dict with enrichment results
    """
    lead = db.session.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        return {"error": f"Lead {lead_id} not found"}

    # Extract domain from notes (format: "Domain: example.com")
    domain = None
    if lead.notes:
        import re
        domain_match = re.search(r'Domain:\s+([^\s\n]+)', lead.notes)
        if domain_match:
            domain = domain_match.group(1)

    if not domain:
        return {"error": f"Lead {lead_id} has no domain in notes to enrich"}

    try:
        from src.mcp.lead_discovery_mcp import enrich_company

        # Run async enrichment in sync context
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            enrichment_data = loop.run_until_complete(
                enrich_company(
                    company_domain=domain,
                    search_depth="basic"
                )
            )
        finally:
            loop.close()

        # Update lead with enriched data
        pages = enrichment_data.get("pages", {})
        metadata = enrichment_data.get("metadata", {})

        # Store enrichment data in notes
        enrichment_notes = []

        if "about" in pages:
            enrichment_notes.append(f"About: {pages['about']['url']}")

        if "contact" in pages:
            enrichment_notes.append(f"Contact: {pages['contact']['url']}")

        if "pricing" in pages:
            enrichment_notes.append(f"Pricing: {pages['pricing']['url']}")

        if metadata.get("description"):
            # Update lead description if empty
            if not lead.notes:
                lead.notes = metadata["description"][:500]

        if enrichment_notes:
            current_notes = lead.notes or ""
            lead.notes = f"{current_notes}\n\nEnriched data:\n" + "\n".join(enrichment_notes)

        # Store enrichment timestamp in notes (no last_enrichment_at field in model)
        if lead.notes:
            lead.notes += f"\n\nLast enriched: {datetime.now().isoformat()}"

        db.session.commit()

        return {
            "lead_id": lead_id,
            "domain": domain,
            "pages_found": len(pages),
            "enrichment_data": enrichment_data
        }

    except Exception as e:
        db.session.rollback()
        # Retry on failure
        if self.request.retries < self.max_retries:
            raise self.retry(exc=e, countdown=60 * (self.request.retries + 1))
        return {"error": str(e), "lead_id": lead_id}


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
