"""
Lead Discovery MCP Server - Autonomous lead generation using SearXNG.

This MCP server provides tools for discovering potential leads through web search,
finding decision makers, identifying buying signals, and enriching company data.

Tools:
- discover_companies: Find companies in a specific niche/industry
- find_decision_makers: Locate decision makers at target companies
- find_buying_signals: Identify companies showing buying intent
- enrich_company: Get additional company information
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

try:
    from mcp.server.fastmcp import FastMCP, Context, ToolError
except ImportError:
    from mcp.server.fastmcp import FastMCP, Context

    class ToolError(Exception):
        """Fallback ToolError."""
        pass


logger = logging.getLogger("ranger.lead_discovery_mcp")
mcp = FastMCP("lead-discovery")


def extract_domain(url: str) -> str:
    """Extract clean domain from URL."""
    try:
        parsed = urlparse(url)
        domain = parsed.netloc or parsed.path
        # Remove www. prefix
        domain = re.sub(r'^www\.', '', domain)
        return domain
    except Exception:
        return url


def extract_company_name(title: str) -> str:
    """Extract company name from search result title."""
    # Common patterns: "Company Name - About", "Company Name | Services", etc.
    name = re.split(r'[\-\|–:]', title)[0].strip()
    # Remove common suffixes
    name = re.sub(r'\s+(Inc|LLC|Ltd|Corporation|Corp|Company|Co)\.?$', '', name, flags=re.IGNORECASE)
    return name.strip()


@mcp.tool()
async def discover_companies(
    query: str,
    niche: str = "",
    location: str = "",
    max_results: int = 25,
    mcp_context: Context | None = None,
) -> Dict[str, Any]:
    """
    Discover companies in a specific niche using web search.

    This tool searches the web for companies matching your criteria and returns
    structured company data including domain, name, and description.

    Args:
        query: Search query (e.g., "B2B SaaS revenue operations")
        niche: Optional niche/industry filter (e.g., "SaaS", "E-commerce")
        location: Optional location filter (e.g., "San Francisco", "Remote")
        max_results: Maximum number of companies to return (default: 25)

    Returns:
        Dictionary with discovered companies and metadata
    """
    try:
        # Import search tool dynamically to avoid circular imports
        from src.mcp.search_mcp import _search_tool, _ctx

        # Build search query
        search_query = query
        if niche:
            search_query += f" {niche}"
        if location:
            search_query += f" {location}"

        # Add context to focus on company websites
        search_query += " company website"

        logger.info(f"[discover_companies] Searching: {search_query}")

        # Execute search
        results = await _search_tool.search(_ctx, search_query, context=None)

        # Process results into company records
        companies = []
        seen_domains = set()

        for result in results:
            if "error" in result:
                continue

            domain = extract_domain(result.get("url", ""))
            if not domain or domain in seen_domains:
                continue

            # Filter out non-company domains
            if any(
                exclude in domain.lower()
                for exclude in ["linkedin.com", "facebook.com", "twitter.com", "youtube.com", "wikipedia.org"]
            ):
                continue

            company_name = extract_company_name(result.get("title", ""))
            snippet = result.get("snippet", "")

            companies.append(
                {
                    "name": company_name,
                    "domain": domain,
                    "url": result.get("url"),
                    "description": snippet[:200] if snippet else "",
                    "source": "searxng",
                    "query": search_query,
                }
            )

            seen_domains.add(domain)

            if len(companies) >= max_results:
                break

        logger.info(f"[discover_companies] Found {len(companies)} companies")

        return {
            "query": query,
            "niche": niche,
            "location": location,
            "companies": companies,
            "count": len(companies),
            "metadata": {"source": "searxng", "max_results": max_results},
        }

    except Exception as exc:
        logger.exception(f"[discover_companies] Error: {exc}")
        raise ToolError(f"Company discovery failed: {exc}") from exc


@mcp.tool()
async def find_decision_makers(
    company_domain: str,
    job_titles: Optional[List[str]] = None,
    max_results: int = 10,
    mcp_context: Context | None = None,
) -> Dict[str, Any]:
    """
    Find decision makers at a company via LinkedIn search.

    Searches LinkedIn for profiles of people in leadership positions at the
    specified company. Useful for identifying potential contacts.

    Args:
        company_domain: Company website domain (e.g., "acme.com")
        job_titles: Target job titles (default: VP/Director/Head/Chief roles)
        max_results: Maximum number of contacts to return (default: 10)

    Returns:
        Dictionary with discovered contacts and LinkedIn profiles
    """
    try:
        from src.mcp.search_mcp import _search_tool, _ctx

        if not job_titles:
            job_titles = ["VP", "Vice President", "Director", "Head of", "Chief", "Manager"]

        # Build LinkedIn search query
        company_name = company_domain.split(".")[0]  # Extract company name from domain
        title_query = " OR ".join(job_titles)
        search_query = f'site:linkedin.com/in {company_name} "{title_query}"'

        logger.info(f"[find_decision_makers] Searching: {search_query}")

        # Execute search
        results = await _search_tool.search(_ctx, search_query, context=None)

        # Process results into contact records
        contacts = []
        for result in results:
            if "error" in result:
                continue

            linkedin_url = result.get("url", "")
            if "linkedin.com/in/" not in linkedin_url:
                continue

            title = result.get("title", "")
            snippet = result.get("snippet", "")

            # Extract name from title (usually "Name - Title at Company")
            name_match = re.match(r'^([^-\|]+)', title)
            name = name_match.group(1).strip() if name_match else title.split("-")[0].strip()

            # Extract job title from snippet or title
            job_title = ""
            for target_title in job_titles:
                if target_title.lower() in title.lower() or target_title.lower() in snippet.lower():
                    job_title = target_title
                    break

            contacts.append(
                {
                    "name": name,
                    "job_title": job_title,
                    "linkedin_url": linkedin_url,
                    "company_domain": company_domain,
                    "snippet": snippet[:150] if snippet else "",
                }
            )

            if len(contacts) >= max_results:
                break

        logger.info(f"[find_decision_makers] Found {len(contacts)} contacts")

        return {
            "company_domain": company_domain,
            "contacts": contacts,
            "count": len(contacts),
            "metadata": {"source": "linkedin_search", "job_titles": job_titles},
        }

    except Exception as exc:
        logger.exception(f"[find_decision_makers] Error: {exc}")
        raise ToolError(f"Decision maker search failed: {exc}") from exc


@mcp.tool()
async def find_buying_signals(
    niche: str,
    signal_type: str = "hiring",
    max_results: int = 20,
    mcp_context: Context | None = None,
) -> Dict[str, Any]:
    """
    Find companies showing buying signals (hiring, funding, expansion).

    Identifies companies with indicators of budget availability or growth,
    which are often strong signals for sales opportunities.

    Args:
        niche: Industry/niche to search (e.g., "B2B SaaS")
        signal_type: Type of signal - "hiring", "funding", or "expansion"
        max_results: Maximum number of signals to return (default: 20)

    Returns:
        Dictionary with companies showing buying signals
    """
    try:
        from src.mcp.search_mcp import _search_tool, _ctx

        # Define search queries for different signal types
        queries = {
            "hiring": f'site:linkedin.com/jobs "{niche}" OR site:greenhouse.io "{niche}"',
            "funding": f'"{niche}" companies "raised funding" OR "series A" OR "series B" OR "seed round"',
            "expansion": f'"{niche}" companies "opening office" OR "expanding team" OR "new location"',
        }

        search_query = queries.get(signal_type, queries["hiring"])

        logger.info(f"[find_buying_signals] Searching: {search_query}")

        # Execute search
        results = await _search_tool.search(_ctx, search_query, context=None)

        # Process results into signal records
        signals = []
        seen_domains = set()

        for result in results:
            if "error" in result:
                continue

            url = result.get("url", "")
            domain = extract_domain(url)

            # Skip if we've already seen this domain
            if domain in seen_domains:
                continue

            # Extract company name from job posting or article
            title = result.get("title", "")
            company_name = extract_company_name(title)

            signals.append(
                {
                    "company_name": company_name,
                    "domain": domain,
                    "signal_type": signal_type,
                    "title": title,
                    "url": url,
                    "snippet": result.get("snippet", "")[:150],
                    "source": "searxng",
                }
            )

            seen_domains.add(domain)

            if len(signals) >= max_results:
                break

        logger.info(f"[find_buying_signals] Found {len(signals)} signals")

        return {
            "niche": niche,
            "signal_type": signal_type,
            "signals": signals,
            "count": len(signals),
            "metadata": {"source": "searxng", "query": search_query},
        }

    except Exception as exc:
        logger.exception(f"[find_buying_signals] Error: {exc}")
        raise ToolError(f"Buying signal search failed: {exc}") from exc


@mcp.tool()
async def enrich_company(
    company_domain: str,
    search_depth: str = "basic",
    mcp_context: Context | None = None,
) -> Dict[str, Any]:
    """
    Enrich company data by searching for additional information.

    Searches for company information including about pages, contact pages,
    pricing, and other relevant data to build a complete company profile.

    Args:
        company_domain: Company website domain (e.g., "acme.com")
        search_depth: "basic" or "detailed" (affects number of searches)

    Returns:
        Dictionary with enriched company information
    """
    try:
        from src.mcp.search_mcp import _search_tool, _ctx

        enriched_data = {
            "domain": company_domain,
            "pages": {},
            "metadata": {},
        }

        # Define search queries for different types of pages
        searches = {
            "about": f'site:{company_domain} "about" OR "about us" OR "company"',
            "contact": f'site:{company_domain} "contact" OR "contact us" OR "get in touch"',
            "pricing": f'site:{company_domain} "pricing" OR "plans" OR "packages"',
        }

        if search_depth == "detailed":
            searches.update(
                {
                    "customers": f'site:{company_domain} "customers" OR "case studies" OR "testimonials"',
                    "team": f'site:{company_domain} "team" OR "leadership" OR "about our team"',
                }
            )

        # Execute searches
        for page_type, query in searches.items():
            try:
                results = await _search_tool.search(_ctx, query, context=None)

                if results and not any("error" in r for r in results):
                    top_result = results[0]
                    enriched_data["pages"][page_type] = {
                        "url": top_result.get("url"),
                        "title": top_result.get("title"),
                        "snippet": top_result.get("snippet", "")[:200],
                    }
            except Exception as e:
                logger.warning(f"[enrich_company] Failed to fetch {page_type} page: {e}")

        # General company search for metadata
        try:
            general_query = f'"{company_domain}" company'
            results = await _search_tool.search(_ctx, general_query, context=None)

            if results and not any("error" in r for r in results):
                enriched_data["metadata"]["description"] = results[0].get("snippet", "")[:300]
        except Exception as e:
            logger.warning(f"[enrich_company] Failed to fetch general metadata: {e}")

        logger.info(f"[enrich_company] Enriched {company_domain} with {len(enriched_data['pages'])} pages")

        return enriched_data

    except Exception as exc:
        logger.exception(f"[enrich_company] Error: {exc}")
        raise ToolError(f"Company enrichment failed: {exc}") from exc


if __name__ == "__main__":
    mcp.run(transport="stdio")
