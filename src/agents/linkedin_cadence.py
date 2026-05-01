"""LinkedIn outreach cadence agent — replaces the four linkedin.* Celery task bodies."""
from __future__ import annotations

import logging
from typing import Any, Dict, List

from src.agents.base import BaseAgent
from src.extensions import db

log = logging.getLogger(__name__)

_LEAD_DISCOVERY_LABEL = "lead-discovery"
_PLAYWRIGHT_LABEL = "playwright-mcp"


class LinkedInCadenceAgent(BaseAgent):
    """
    Manages the full LinkedIn outreach loop:
      1. Enrich qualifying leads with LinkedIn URLs (via SearXNG + Playwright)
      2. Promote enriched leads into LinkedInProspect queue
      3. Draft outreach messages via DSPy
      4. Assemble and email the daily action digest

    tool_calls: subclasses should append {"tool": name, "input": args} in each tool method
    """

    agent_name = "linkedin_cadence"
    mcp_server_labels = [_LEAD_DISCOVERY_LABEL, _PLAYWRIGHT_LABEL]

    def _get_tools(self) -> list:
        return [
            self._tool_get_qualifying_leads,
            self._tool_find_decision_makers,
            self._tool_enrich_lead_linkedin_url,
            self._tool_add_to_prospect_queue,
            self._tool_get_pending_prospects,
            self._tool_get_relevant_blog_post,
            self._tool_save_drafted_messages,
            self._tool_send_digest_email,
        ]

    # -------------------------------------------------------------------------
    # Static tools
    # -------------------------------------------------------------------------

    def _tool_find_decision_makers(
        self,
        company_domain: str,
        job_titles: List[str] = None,
        max_results: int = 5,
    ) -> Dict[str, Any]:
        """Search LinkedIn for decision maker profiles at company_domain. Returns contacts with name, job_title, linkedin_url."""
        import asyncio
        from src.mcp.lead_discovery_mcp import find_decision_makers
        self.tool_calls.append({"tool": "find_decision_makers", "input": {"company_domain": company_domain}})
        return asyncio.run(find_decision_makers(company_domain=company_domain, job_titles=job_titles, max_results=max_results))

    def _tool_get_qualifying_leads(self) -> List[Dict[str, Any]]:
        """Return leads with fit_score >= 7 and no LinkedIn URL. Max 20 per run."""
        from src.models.leads import Lead
        self.tool_calls.append({"tool": "get_qualifying_leads"})
        leads = (
            db.session.query(Lead)
            .filter(
                Lead.account_id == self.account_id,
                Lead.fit_score >= 7,
                Lead.linkedin_url.is_(None),
                Lead.deleted.is_(False),
                Lead.company_name.isnot(None),
            )
            .order_by(Lead.created_at.asc())
            .limit(20)
            .all()
        )
        return [
            {
                "id": str(lead.id),
                "name": lead.name or "",
                "company_name": lead.company_name or "",
                "email": lead.email or "",
            }
            for lead in leads
        ]

    def _tool_enrich_lead_linkedin_url(self, lead_id: str, linkedin_url: str, name: str = "") -> Dict[str, Any]:
        """
        Save a verified LinkedIn URL (and optionally name) to a Lead.
        Call after find_decision_makers + browser_snapshot confirm the URL.
        """
        from src.models.leads import Lead
        clean_url = linkedin_url.split("?")[0]
        self.tool_calls.append({"tool": "enrich_lead_linkedin_url", "input": {"lead_id": lead_id, "linkedin_url": clean_url}})
        lead = db.session.query(Lead).filter_by(id=lead_id, account_id=self.account_id).first()
        if not lead:
            return {"saved": False, "error": "lead not found"}
        if not (clean_url.startswith("https://www.linkedin.com/") or clean_url.startswith("https://linkedin.com/")):
            return {"saved": False, "error": "invalid linkedin_url"}
        lead.linkedin_url = clean_url
        if name and (not lead.name or lead.name == lead.company_name):
            lead.name = name
        try:
            db.session.commit()
            return {"saved": True}
        except Exception as exc:
            db.session.rollback()
            return {"saved": False, "error": str(exc)}

    def _tool_add_to_prospect_queue(self, lead_id: str) -> Dict[str, Any]:
        """
        Create a LinkedInProspect row from a Lead that now has a LinkedIn URL.
        Idempotent — skips if prospect already exists for this linkedin_url.
        """
        from src.models.leads import Lead
        from src.models.campaigns import LinkedInProspect
        self.tool_calls.append({"tool": "add_to_prospect_queue", "input": {"lead_id": lead_id}})
        lead = db.session.query(Lead).filter_by(
            id=lead_id, account_id=self.account_id
        ).first()
        if not lead or not lead.linkedin_url:
            return {"created": False, "error": "lead not found or has no linkedin_url"}
        exists = db.session.query(LinkedInProspect).filter_by(
            account_id=self.account_id, linkedin_url=lead.linkedin_url
        ).first()
        if exists:
            return {"created": False, "reason": "already_exists"}
        prospect = LinkedInProspect(
            account_id=self.account_id,
            lead_id=lead.id,
            name=lead.name,
            company_name=lead.company_name,
            industry=lead.industry,
            linkedin_url=lead.linkedin_url,
            source="auto",
            status="pending",
            fit_score=lead.fit_score,
        )
        try:
            db.session.add(prospect)
            db.session.commit()
            return {"created": True}
        except Exception as exc:
            db.session.rollback()
            return {"created": False, "error": str(exc)}

    def _tool_get_pending_prospects(self) -> List[Dict[str, Any]]:
        """Return prospects with status=pending and no msg_1_draft yet."""
        from src.models.campaigns import LinkedInProspect
        self.tool_calls.append({"tool": "get_pending_prospects"})
        prospects = (
            db.session.query(LinkedInProspect)
            .filter(
                LinkedInProspect.account_id == self.account_id,
                LinkedInProspect.status == "pending",
                LinkedInProspect.msg_1_draft.is_(None),
            )
            .order_by(LinkedInProspect.created_at.asc())
            .all()
        )
        return [
            {
                "id": str(p.id),
                "name": p.name or "",
                "job_title": p.job_title or "",
                "company_name": p.company_name or "",
                "industry": p.industry or "",
            }
            for p in prospects
        ]

    def _tool_get_relevant_blog_post(self, industry: str, keywords: str = "") -> Dict[str, Any]:
        """
        Find a published blog post relevant to the prospect's industry or keywords.
        Returns post id, title, and public URL to include in message 2.
        """
        from src.models.content import BlogPost
        self.tool_calls.append({"tool": "get_relevant_blog_post", "input": {"industry": industry}})
        query = db.session.query(BlogPost).filter(BlogPost.status == "published")
        if industry:
            query = query.filter(BlogPost.title.ilike(f"%{industry.split()[0]}%"))
        post = query.order_by(BlogPost.published_at.desc()).first()
        if not post and industry:
            post = db.session.query(BlogPost).filter(BlogPost.status == "published").order_by(BlogPost.published_at.desc()).first()
        if not post:
            return {"found": False}
        return {
            "found": True,
            "id": str(post.id),
            "title": post.title,
            "url": f"https://kalevent.com/blog/{post.slug}",
        }

    def _tool_save_drafted_messages(
        self,
        prospect_id: str,
        msg_1: str,
        msg_2: str,
        msg_3: str,
        suggested_post_id: str = "",
    ) -> Dict[str, Any]:
        """Persist drafted outreach messages to a LinkedInProspect. Include suggested_post_id if a blog post was found."""
        from src.models.campaigns import LinkedInProspect
        self.tool_calls.append({"tool": "save_drafted_messages", "input": {"prospect_id": prospect_id}})
        prospect = db.session.query(LinkedInProspect).filter_by(
            id=prospect_id, account_id=self.account_id
        ).first()
        if not prospect:
            return {"saved": False, "error": "prospect not found"}
        from src.sanitize import sanitize_html
        prospect.msg_1_draft = sanitize_html(msg_1)
        prospect.msg_2_draft = sanitize_html(msg_2)
        prospect.msg_3_draft = sanitize_html(msg_3)
        if suggested_post_id:
            prospect.suggested_post_id = suggested_post_id
        try:
            db.session.commit()
            return {"saved": True}
        except Exception as exc:
            db.session.rollback()
            return {"saved": False, "error": str(exc)}

    def _tool_send_digest_email(self) -> Dict[str, Any]:
        """Collect all prospects due for action today and send the digest email."""
        from src.tasks.linkedin import _send_digest_core
        self.tool_calls.append({"tool": "send_digest_email"})
        return _send_digest_core(self.account_id)
