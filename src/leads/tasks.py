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
from src.models.leads import Lead


@shared_task(name="leads.enrich_lead_with_email", bind=True, max_retries=2, queue="leads")
def enrich_lead_with_email(self, lead_id: str, domain: str) -> Dict[str, Any]:
    """
    Find and enrich lead email address using Hunter.io API with domain caching.

    Args:
        lead_id: Lead UUID
        domain: Company domain (e.g., "acme.com")

    Returns:
        Dict with enrichment results

    Note:
        Requires HUNTER_API_KEY environment variable.
        Fails gracefully if API key is missing or rate limit exceeded.
        Uses domain-level caching to avoid duplicate API calls (30-day cache).
    """
    import os
    import requests
    from datetime import datetime, timedelta, timezone as tz
    from src.models import HunterDomainCache

    # Check if API key is configured
    api_key = os.getenv("HUNTER_API_KEY")
    if not api_key:
        return {
            "success": False,
            "error": "HUNTER_API_KEY not configured",
            "lead_id": lead_id,
            "skip": True  # Don't retry
        }

    # Check remaining free-tier credits before making any API call
    def _hunter_searches_available() -> int:
        try:
            resp = requests.get(
                "https://api.hunter.io/v2/account",
                params={"api_key": api_key},
                timeout=10,
            )
            if resp.status_code == 200:
                req = resp.json().get("data", {}).get("requests", {})
                return req.get("searches", {}).get("available", 0)
        except Exception:
            pass
        return 0

    lead = db.session.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        return {"error": f"Lead {lead_id} not found"}

    # Skip if lead already has a usable email — no credit needed
    if lead.email and "@" in lead.email:
        return {"success": True, "lead_id": lead_id, "skip": True, "reason": "email_already_known"}

    # Check cache first
    cache = HunterDomainCache.query.filter_by(domain=domain).first()
    emails = None
    from_cache = False

    if cache and not cache.is_expired():
        # Use cached results - no API call needed!
        emails = cache.emails or []
        from_cache = True
    else:
        # Hard cap: free plan = 25 searches/month. Count how many we've already
        # used this calendar month across all leads to avoid burning credits on
        # low-value lookups. Cache hits don't count against this.
        from src.models import HunterDomainCache as _HDC
        now_utc = datetime.now(tz())
        month_start = now_utc.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        HUNTER_FREE_MONTHLY_CAP = int(os.getenv("HUNTER_MONTHLY_CAP", "25"))
        searches_this_month = _HDC.query.filter(
            _HDC.created_at >= month_start,
        ).count()
        if searches_this_month >= HUNTER_FREE_MONTHLY_CAP:
            return {
                "success": False,
                "error": f"Hunter.io monthly cap reached ({HUNTER_FREE_MONTHLY_CAP} searches). Resets on the 1st.",
                "lead_id": lead_id,
                "skip": True,
            }

        # Also check live available credits as a secondary guard
        if _hunter_searches_available() == 0:
            return {
                "success": False,
                "error": "Hunter.io monthly search credits exhausted",
                "lead_id": lead_id,
                "skip": True,
            }

        # Cache miss or expired - call Hunter.io API
        try:
            # Call Hunter.io Domain Search API
            url = "https://api.hunter.io/v2/domain-search"
            params = {
                "domain": domain,
                "api_key": api_key,
                "limit": 10  # Get top 10 emails
            }

            response = requests.get(url, params=params, timeout=10)

            if response.status_code == 401:
                return {
                    "success": False,
                    "error": "Invalid Hunter.io API key",
                    "lead_id": lead_id,
                    "skip": True
                }

            if response.status_code == 429:
                # Rate limit - retry later
                if self.request.retries < self.max_retries:
                    raise self.retry(countdown=3600)  # Retry after 1 hour
                return {
                    "success": False,
                    "error": "Hunter.io rate limit exceeded",
                    "lead_id": lead_id
                }

            if response.status_code != 200:
                return {
                    "success": False,
                    "error": f"Hunter.io API error: {response.status_code}",
                    "lead_id": lead_id
                }

            data = response.json()
            emails = data.get("data", {}).get("emails", [])

            # Store in cache — longer TTL for empty results (don't re-check blank domains)
            ttl_days = 90 if emails else 180
            if cache:
                cache.emails = emails
                cache.email_count = len(emails)
                cache.created_at = datetime.now(tz.utc)
                cache.expires_at = datetime.now(tz.utc) + timedelta(days=ttl_days)
            else:
                cache = HunterDomainCache(
                    domain=domain,
                    emails=emails,
                    email_count=len(emails),
                    expires_at=datetime.now(tz.utc) + timedelta(days=ttl_days)
                )
                db.session.add(cache)
            db.session.commit()

        except requests.exceptions.Timeout:
            return {
                "success": False,
                "error": "Hunter.io API timeout",
                "lead_id": lead_id
            }
        except Exception as e:
            db.session.rollback()
            # Retry on unexpected errors
            if self.request.retries < self.max_retries:
                raise self.retry(exc=e, countdown=300)
            return {
                "success": False,
                "error": str(e),
                "lead_id": lead_id
            }

    # Now use the emails (from cache or fresh API call)
    if not emails:
        return {
            "success": False,
            "error": "No emails found for domain",
            "lead_id": lead_id,
            "domain": domain,
            "from_cache": from_cache
        }

    # Blocked domains — not real work email addresses
    _BLOCKED_DOMAINS = {
        "linkedin.com", "twitter.com", "facebook.com", "instagram.com",
        "gmail.com", "yahoo.com", "hotmail.com", "outlook.com",
        "indeed.com", "glassdoor.com", "greenhouse.io", "lever.co",
        "workday.com", "jobs.com", "ziprecruiter.com",
    }
    # Role-based prefixes — not personal, unlikely to be read
    _BLOCKED_PREFIXES = {
        "info", "contact", "support", "hello", "admin", "noreply",
        "no-reply", "team", "hr", "jobs", "careers", "press",
        "sales", "marketing", "billing", "help", "mail",
    }
    _MIN_CONFIDENCE = 50  # Require at least 50% confidence from Hunter.io

    def _is_quality_email(email_data: dict) -> bool:
        email = (email_data.get("value") or "").lower()
        if not email or "@" not in email:
            return False
        prefix, at_domain = email.split("@", 1)
        if at_domain in _BLOCKED_DOMAINS:
            return False
        if prefix in _BLOCKED_PREFIXES:
            return False
        if (email_data.get("confidence") or 0) < _MIN_CONFIDENCE:
            return False
        return True

    quality_emails = [e for e in emails if _is_quality_email(e)]

    if not quality_emails:
        return {
            "success": False,
            "error": f"No quality emails found for domain (filtered {len(emails)} low-quality results)",
            "lead_id": lead_id,
            "domain": domain,
            "from_cache": from_cache
        }

    # Try to match lead name to found emails
    lead_name = (lead.name or "").lower()
    best_match = None
    best_score = 0

    for email_data in quality_emails:
        email = email_data.get("value")
        first_name = (email_data.get("first_name") or "").lower()
        last_name = (email_data.get("last_name") or "").lower()
        full_name = f"{first_name} {last_name}".strip()

        # Simple name matching score
        score = 0
        if first_name and first_name in lead_name:
            score += 5
        if last_name and last_name in lead_name:
            score += 5
        if full_name and full_name in lead_name:
            score += 10

        # Prefer emails with higher confidence
        confidence = email_data.get("confidence", 0)
        score += confidence / 10

        if score > best_score:
            best_score = score
            best_match = email_data

    # Fallback: use highest-confidence quality email if no name match
    if not best_match:
        best_match = max(quality_emails, key=lambda e: e.get("confidence", 0))

    # Update lead with email
    if best_match:
        lead.email = best_match.get("value")

        # Add enrichment note
        source = "Hunter.io cache" if from_cache else "Hunter.io"
        enrichment_note = f"\n\nEmail found via {source}: {best_match.get('value')}"
        enrichment_note += f"\nConfidence: {best_match.get('confidence', 0)}%"
        enrichment_note += f"\nEnriched: {datetime.now().isoformat()}"

        if lead.notes:
            lead.notes += enrichment_note
        else:
            lead.notes = enrichment_note

        db.session.commit()

        return {
            "success": True,
            "lead_id": lead_id,
            "email": best_match.get("value"),
            "confidence": best_match.get("confidence"),
            "domain": domain,
            "from_cache": from_cache
        }


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
            raise self.retry(exc=e, countdown=60 * (self.request.retries + 1)) from e
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
        stmt = text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text
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
