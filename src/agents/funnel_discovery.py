"""Funnel discovery agent — replaces discover_leads_via_search and discover_buying_signals task bodies."""
from __future__ import annotations

import logging
from typing import Any, Dict, List

from src.agents.base import BaseAgent
from src.extensions import db

log = logging.getLogger(__name__)

_LEAD_DISCOVERY_LABEL = "lead-discovery"
_ENRICHMENT_LABEL = "enrichment-v2"


class FunnelDiscoveryAgent(BaseAgent):
    """
    Discovers new leads and buying signals using lead-discovery and enrichment MCP servers.
    Writes qualifying companies to the Lead model.

    tool_calls: subclasses should append {"tool": name, "input": args} in each tool method
    """

    agent_name = "funnel_discovery"
    mcp_server_labels = [_LEAD_DISCOVERY_LABEL, _ENRICHMENT_LABEL]

    def _get_tools(self) -> list:
        return [
            self._tool_get_existing_companies,
            self._tool_get_icp_config,
            self._tool_discover_companies,
            self._tool_find_buying_signals,
            self._tool_find_decision_makers,
            self._tool_save_lead,
        ]

    def _tool_get_existing_companies(self) -> List[str]:
        """Return company names already in the leads table for this account (for dedup)."""
        from src.models.leads import Lead
        self.tool_calls.append({"tool": "get_existing_companies"})
        rows = db.session.query(Lead.company_name).filter_by(account_id=self.account_id).all()
        return [r.company_name for r in rows if r.company_name]

    def _tool_get_icp_config(self) -> Dict[str, Any]:
        """Return ICP config (titles, industries, size range, geographies) for this account."""
        from src.models.marketing import ICPConfig
        self.tool_calls.append({"tool": "get_icp_config"})
        _DEFAULTS = {
            "titles": ["Founder", "Head of Support", "Operations Lead", "Customer Success Lead"],
            "industries": ["B2B SaaS", "Software"],
            "company_size_min": 10,
            "company_size_max": 50,
            "geographies": ["UK", "US", "Nigeria"],
        }
        config = db.session.query(ICPConfig).filter_by(account_id=self.account_id).first()
        if not config:
            return _DEFAULTS
        return {
            "titles": config.titles or _DEFAULTS["titles"],
            "industries": config.industries or _DEFAULTS["industries"],
            "company_size_min": config.company_size_min or _DEFAULTS["company_size_min"],
            "company_size_max": config.company_size_max or _DEFAULTS["company_size_max"],
            "geographies": config.geographies or _DEFAULTS["geographies"],
        }

    def _tool_discover_companies(
        self,
        query: str,
        niche: str = "",
        location: str = "",
        max_results: int = 25,
    ) -> Dict[str, Any]:
        """Search SearXNG for companies matching ICP criteria. Returns list of companies with domain and description."""
        import asyncio
        from src.mcp.lead_discovery_mcp import discover_companies
        self.tool_calls.append({"tool": "discover_companies", "input": {"query": query}})
        return asyncio.run(discover_companies(query=query, niche=niche, location=location, max_results=max_results))

    def _tool_find_buying_signals(
        self,
        niche: str,
        signal_type: str = "hiring",
        max_results: int = 20,
    ) -> Dict[str, Any]:
        """Search for companies showing buying signals (hiring, funding, expansion). Returns signals list with company_name and domain."""
        import asyncio
        from src.mcp.lead_discovery_mcp import find_buying_signals
        self.tool_calls.append({"tool": "find_buying_signals", "input": {"niche": niche, "signal_type": signal_type}})
        return asyncio.run(find_buying_signals(niche=niche, signal_type=signal_type, max_results=max_results))

    def _tool_find_decision_makers(
        self,
        company_domain: str,
        job_titles: List[str] = None,
        max_results: int = 5,
    ) -> Dict[str, Any]:
        """Find decision maker LinkedIn profiles at a company. Returns contacts list with name, job_title, linkedin_url."""
        import asyncio
        from src.mcp.lead_discovery_mcp import find_decision_makers
        self.tool_calls.append({"tool": "find_decision_makers", "input": {"company_domain": company_domain}})
        return asyncio.run(find_decision_makers(company_domain=company_domain, job_titles=job_titles, max_results=max_results))

    def _tool_save_lead(
        self,
        company_name: str,
        email: str,
        industry: str,
        fit_score: int,
        source: str,
        notes: str = "",
        linkedin_url: str = "",
        name: str = "",
        num_employees: int = 0,
    ) -> Dict[str, Any]:
        """
        Persist a verified lead. Rejects if fit_score < 4 or company already exists
        for this source. Enqueues qualify_visitor after commit.
        """
        from src.models.leads import Lead
        from src.sanitize import sanitize_html
        self.tool_calls.append({"tool": "save_lead", "input": {"company_name": company_name}})

        safe_notes = sanitize_html(notes) if notes else ""

        if fit_score < 4:
            return {"created": False, "reason": "fit_score_too_low"}

        existing = db.session.query(Lead).filter_by(
            account_id=self.account_id,
            company_name=company_name,
            source=source,
        ).first()
        if existing:
            return {"created": False, "reason": "duplicate"}

        lead = Lead(
            account_id=self.account_id,
            name=name or company_name,
            email=email,
            company_name=company_name,
            industry=industry,
            num_employees=num_employees or None,
            linkedin_url=linkedin_url or None,
            source=source,
            fit_score=fit_score,
            status="New Lead",
            notes=safe_notes,
            deleted=False,
        )
        try:
            db.session.add(lead)
            db.session.commit()
        except Exception as exc:
            db.session.rollback()
            return {"created": False, "error": str(exc)}

        try:
            from src.funnel.tasks import qualify_visitor
            qualify_visitor.delay(str(lead.id))
        except Exception:
            log.warning("qualify_visitor.delay failed for lead %s", lead.id)

        return {"created": True, "lead_id": str(lead.id)}
