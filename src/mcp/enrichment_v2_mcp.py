"""
Enrichment v2.0 MCP server for Leads Funnel v2.0

Enhanced lead enrichment with:
- Company firmographics (industry, size, funding, tech stack)
- Buying committee discovery (multi-contact identification)
- Enhanced verification (email + phone + social profiles)
- Intent signal detection (job posts, funding, news)
- ICP fit scoring

Replaces lead_enrichment_mcp.py with comprehensive B2B data enrichment.

Tools:
- enrich_company: Get firmographics and company data
- find_buying_committee: Identify decision-makers across buying roles
- verify_contact: Enhanced verification with social profiles
- detect_intent_signals: Find external buying intent signals
- calculate_fit_score: Calculate ICP fit score (0-10)
- enrich_lead_full: All-in-one enrichment (company + committee + intent)

Env:
- CLEARBIT_API_KEY: Clearbit API for company enrichment (optional)
- HUNTER_API_KEY: Hunter.io — domain email search (leads/tasks.py) + email verification (verify_contact tool)
- MCP_DATABASE_URL or DATABASE_URL: PostgreSQL connection string
"""
from __future__ import annotations

import logging
import os
import re
import time
from typing import Any, Dict, List, Optional
import requests
import psycopg2
from psycopg2.extras import RealDictCursor
from urllib.parse import quote, urlparse as _urlparse

try:
    from mcp.server.fastmcp import FastMCP, Context, ToolError
except ImportError:
    from mcp.server.fastmcp import FastMCP, Context
    try:
        from mcp.types import ToolError
    except ImportError:
        class ToolError(Exception):
            pass


DATABASE_URL = (
    os.getenv("MCP_DATABASE_URL")
    or os.getenv("DATABASE_URL")
    or os.getenv("DATABASE_DEV_URL")
)

logger = logging.getLogger(__name__)

mcp = FastMCP("enrichment-v2-mcp")

# External API keys (optional)
CLEARBIT_API_KEY = os.getenv("CLEARBIT_API_KEY")
HUNTER_API_KEY = os.getenv("HUNTER_API_KEY")

# Free plan limits: 25 domain searches / month, 50 verifications / month
_HUNTER_FREE_LIMITS = {"searches": 25, "verifications": 50}
_hunter_credits_cache: dict = {"data": None, "fetched_at": 0.0}
_HUNTER_CREDITS_TTL = 3600  # re-check once per hour


def _search_web(query: str, max_results: int = 25) -> List[Dict[str, Any]]:
    """Search using SearXNG."""
    searxng_url = os.getenv("SEARXNG_URL", "https://ranger-search.kalevent.com")
    try:
        url = f"{searxng_url}/search?q={quote(query)}&format=json"
        response = requests.get(url, timeout=30)
        if response.status_code == 200:
            data = response.json()
            return data.get("results", [])[:max_results]
        else:
            logger.error("Search failed with status %s", response.status_code)
            return []
    except Exception as e:
        logger.error("Search error: %s", e)
        return []


def _get_hunter_credits() -> dict:
    """
    Return remaining Hunter.io credits from the /v2/account endpoint.
    Result is cached for 1 hour so the check itself costs nothing.
    Returns {"searches": 0, "verifications": 0} on any failure.
    """
    now = time.time()
    if _hunter_credits_cache["data"] and (now - _hunter_credits_cache["fetched_at"]) < _HUNTER_CREDITS_TTL:
        return _hunter_credits_cache["data"]

    if not HUNTER_API_KEY:
        return {"searches": 0, "verifications": 0}

    try:
        resp = requests.get(
            "https://api.hunter.io/v2/account",
            params={"api_key": HUNTER_API_KEY},
            timeout=10,
        )
        if resp.status_code == 200:
            req = resp.json().get("data", {}).get("requests", {})
            credits = {
                "searches": req.get("searches", {}).get("available", 0),
                "verifications": req.get("verifications", {}).get("available", 0),
            }
            _hunter_credits_cache["data"] = credits
            _hunter_credits_cache["fetched_at"] = now
            return credits
    except Exception:
        pass

    return {"searches": 0, "verifications": 0}


def get_conn():
    """Get database connection"""
    if DATABASE_URL:
        try:
            return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        except Exception as e:
            raise ToolError(f"Failed to connect to database: {e}")
    return None


@mcp.tool()
def find_email_for_domain(
    domain: str,
    full_name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Find a contact email address for a company domain using Hunter.io.

    First tries the Email Finder (name + domain → personal email) when a
    full_name is provided, then falls back to Domain Search and returns the
    first deliverable email found.  Returns an empty string when Hunter.io
    has no data, the API key is missing, or credits are exhausted.

    Args:
        domain: Company domain, e.g. "acme.com"
        full_name: Optional contact full name to try Email Finder first.

    Returns:
        Dict with:
          - email: str  (empty string if nothing found)
          - source: "email_finder" | "domain_search" | "none"
          - confidence: int (Hunter confidence score, 0-100)
    """
    empty = {"email": "", "source": "none", "confidence": 0}

    if not domain or not HUNTER_API_KEY:
        return empty

    credits = _get_hunter_credits()

    # --- Strategy 1: Email Finder (costs 1 search, highest precision) ---
    if full_name and credits.get("searches", 0) > 0:
        parts = full_name.strip().split()
        if len(parts) >= 2:
            try:
                resp = requests.get(
                    "https://api.hunter.io/v2/email-finder",
                    params={
                        "domain": domain,
                        "first_name": parts[0],
                        "last_name": " ".join(parts[1:]),
                        "api_key": HUNTER_API_KEY,
                    },
                    timeout=10,
                )
                if resp.status_code == 200:
                    data = resp.json().get("data", {})
                    email = data.get("email", "")
                    confidence = data.get("score", 0) or 0
                    if email and "@" in email and data.get("status") != "invalid":
                        _hunter_credits_cache["data"] = None  # bust cache
                        return {"email": email, "source": "email_finder", "confidence": confidence}
            except Exception as exc:
                logger.warning("Hunter email-finder failed for %s: %s", domain, exc)

    # --- Strategy 2: Domain Search (costs 1 search, returns first deliverable) ---
    if credits.get("searches", 0) > 0:
        try:
            resp = requests.get(
                "https://api.hunter.io/v2/domain-search",
                params={"domain": domain, "api_key": HUNTER_API_KEY, "limit": 5},
                timeout=10,
            )
            if resp.status_code == 200:
                emails_list = resp.json().get("data", {}).get("emails", [])
                _hunter_credits_cache["data"] = None  # bust cache
                for entry in emails_list:
                    if entry.get("type") == "personal" and entry.get("status") in ("valid", "accept_all"):
                        return {
                            "email": entry["value"],
                            "source": "domain_search",
                            "confidence": entry.get("confidence", 0),
                        }
                # Fallback: any non-invalid email
                for entry in emails_list:
                    if entry.get("status") != "invalid":
                        return {
                            "email": entry["value"],
                            "source": "domain_search",
                            "confidence": entry.get("confidence", 0),
                        }
        except Exception as exc:
            logger.warning("Hunter domain-search failed for %s: %s", domain, exc)

    return empty


# Blocks SSRF to cloud metadata, RFC-1918, and localhost from DB-sourced URLs.
_BLOCKED_HOST_RE = re.compile(
    r"^(localhost|127\.|0\.|10\.|172\.(1[6-9]|2[0-9]|3[01])\.|192\.168\.|169\.254\.)",
    re.IGNORECASE,
)


def _safe_external_url(url: str) -> str:
    """
    Validate that a URL is safe to visit externally (no SSRF targets).
    Returns the normalised URL on success; raises ValueError on rejection.
    Rejects: non-http(s) schemes, localhost/RFC-1918/cloud-metadata hosts,
    file:// and other non-HTTP schemes.
    """
    if not url:
        raise ValueError("empty URL")
    if "://" not in url:
        url = "https://" + url
    parsed = _urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"disallowed scheme: {parsed.scheme!r}")
    host = (parsed.hostname or "").lower()
    if not host:
        raise ValueError("no host in URL")
    if _BLOCKED_HOST_RE.match(host):
        raise ValueError(f"blocked host: {host!r}")
    return url


_EMAIL_REGEX = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
_THROWAWAY_DOMAINS = {
    "gmail.com", "yahoo.com", "hotmail.com", "outlook.com",
    "linkedin.com", "twitter.com", "facebook.com",
}
_SKIP_PREFIXES = ("noreply@", "no-reply@", "info@", "support@", "hello@", "admin@",
                  "contact@", "press@", "legal@", "privacy@", "abuse@")


def _is_business_email(email: str) -> bool:
    """Return True if email looks like a real personal business address."""
    e = email.lower()
    domain = e.split("@")[-1] if "@" in e else ""
    return (
        bool(domain)
        and domain not in _THROWAWAY_DOMAINS
        and not any(e.startswith(p) for p in _SKIP_PREFIXES)
    )


@mcp.tool()
def find_email_via_search(
    company_name: str,
    company_url: str = "",
    person_name: str = "",
) -> Dict[str, Any]:
    """
    Find a contact email for a company using SearXNG (Ranger) web search.

    Crafts a targeted query combining company name, person name, and domain,
    then extracts email addresses from result titles and snippets.  Returns
    the first business (non-generic) email found.

    Args:
        company_name: Company name, e.g. "Acme Corp"
        company_url: Company website URL (optional but improves accuracy)
        person_name: Specific person to search for (optional)

    Returns:
        Dict with email (str), source ("search"), confidence (int 0-100)
    """
    empty = {"email": "", "source": "none", "confidence": 0}
    if not company_name:
        return empty

    domain_hint = ""
    if company_url:
        try:
            safe_url = _safe_external_url(company_url)
            hostname = _urlparse(safe_url).hostname or ""
            if hostname and "linkedin.com" not in hostname:
                domain_hint = hostname.removeprefix("www.")
        except ValueError:
            pass  # untrusted/internal URL — skip site: hint

    # Build search queries from most to least specific
    queries = []
    if person_name and domain_hint:
        queries.append(f'"{person_name}" email site:{domain_hint}')
    if domain_hint:
        queries.append(f'"{company_name}" email contact site:{domain_hint}')
        queries.append(f'site:{domain_hint} email contact')
    if person_name:
        queries.append(f'"{person_name}" "{company_name}" email')
    queries.append(f'"{company_name}" email contact')

    for query in queries:
        try:
            results = _search_web(query, max_results=5)
            for result in results:
                for field in (result.get("title", ""), result.get("snippet", ""), result.get("url", "")):
                    for match in _EMAIL_REGEX.findall(field):
                        if _is_business_email(match):
                            return {"email": match.lower(), "source": "search", "confidence": 60}
        except Exception as exc:
            logger.warning("find_email_via_search failed for %s: %s", company_name, exc)

    return empty


@mcp.tool()
def find_email_via_playwright(
    url: str,
    max_pages: int = 3,
) -> Dict[str, Any]:
    """
    Visit a company website with Playwright and extract business email addresses.

    Visits the given URL then checks /contact, /about, and /team pages for
    email addresses embedded in the page.  Returns the first business
    (non-generic) email found.

    Args:
        url: Company website URL, e.g. "https://acme.com"
        max_pages: Maximum sub-pages to visit after the landing page (default 3)

    Returns:
        Dict with email (str), source ("playwright"), confidence (int 0-100),
        page_url (str) where the email was found.
    """
    empty = {"email": "", "source": "none", "confidence": 0, "page_url": ""}
    if not url:
        return empty

    try:
        url = _safe_external_url(url)
    except ValueError as exc:
        logger.warning("find_email_via_playwright rejected URL %r: %s", url, exc)
        return empty

    from urllib.parse import urlparse, urljoin
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
    except ImportError:
        logger.warning("playwright not installed; skipping find_email_via_playwright")
        return empty

    parsed = urlparse(url)

    # Pages to check: landing page + common contact paths
    candidate_paths = ["/contact", "/contact-us", "/about", "/about-us", "/team", "/our-team"]
    pages_to_visit = [url] + [urljoin(url, p) for p in candidate_paths]

    def _extract_emails_from_text(text: str) -> List[str]:
        return [e.lower() for e in _EMAIL_REGEX.findall(text) if _is_business_email(e)]

    visited = 0
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            page = browser.new_page()
            page.set_extra_http_headers({"User-Agent": "Mozilla/5.0 (compatible; KaleventBot/1.0)"})

            for page_url in pages_to_visit:
                if visited >= max_pages + 1:
                    break
                try:
                    page.goto(page_url, wait_until="domcontentloaded", timeout=12000)
                    content = page.content()
                    visited += 1
                    for email in _extract_emails_from_text(content):
                        browser.close()
                        return {
                            "email": email,
                            "source": "playwright",
                            "confidence": 85,
                            "page_url": page_url,
                        }
                except PWTimeout:
                    logger.debug("Playwright timeout on %s", page_url)
                except Exception as exc:
                    logger.debug("Playwright error on %s: %s", page_url, exc)

            browser.close()
    except Exception as exc:
        logger.warning("find_email_via_playwright failed for %s: %s", url, exc)

    return empty


@mcp.tool()
def enrich_company(
    domain: str,
    company_name: Optional[str] = None
) -> Dict[str, Any]:
    """
    Enrich company with firmographics, tech stack, and metadata.

    Uses Clearbit Enrichment API if available, otherwise returns basic data.

    Args:
        domain: Company domain (e.g., acme.com)
        company_name: Company name (optional, helps with matching)

    Returns:
        Dict with:
        - name, domain, description
        - industry, sector, tags
        - employee_count, employee_range
        - founded_year, location
        - funding (total_raised, last_round, investors)
        - tech_stack (technologies detected)
        - social_profiles (linkedin, twitter, facebook)
    """
    if not domain:
        raise ToolError("domain is required")

    enrichment_data = {
        "domain": domain,
        "company_name": company_name,
        "enriched": False,
        "data_source": "manual"
    }

    # Try Clearbit enrichment
    if CLEARBIT_API_KEY:
        try:
            headers = {"Authorization": f"Bearer {CLEARBIT_API_KEY}"}
            response = requests.get(
                f"https://company.clearbit.com/v2/companies/find?domain={domain}",
                headers=headers,
                timeout=10
            )

            if response.status_code == 200:
                data = response.json()
                enrichment_data.update({
                    "enriched": True,
                    "data_source": "clearbit",
                    "name": data.get("name"),
                    "description": data.get("description"),
                    "industry": data.get("industry"),
                    "sector": data.get("category", {}).get("sector"),
                    "tags": data.get("tags", []),
                    "employee_count": data.get("metrics", {}).get("employees"),
                    "employee_range": data.get("metrics", {}).get("employeesRange"),
                    "founded_year": data.get("foundedYear"),
                    "location": {
                        "city": data.get("geo", {}).get("city"),
                        "state": data.get("geo", {}).get("state"),
                        "country": data.get("geo", {}).get("country")
                    },
                    "funding": {
                        "total_raised": data.get("metrics", {}).get("raised"),
                        "last_round": data.get("metrics", {}).get("lastRoundType"),
                        "investors": data.get("investors", [])
                    },
                    "tech_stack": data.get("tech", []),
                    "social_profiles": {
                        "linkedin": data.get("linkedin", {}).get("handle"),
                        "twitter": data.get("twitter", {}).get("handle"),
                        "facebook": data.get("facebook", {}).get("handle")
                    }
                })
        except Exception as e:
            enrichment_data["enrichment_error"] = str(e)

    # Fallback: basic domain info
    if not enrichment_data["enriched"]:
        enrichment_data.update({
            "name": company_name or domain.split('.')[0].capitalize(),
            "description": None,
            "industry": None,
            "employee_count": None,
            "note": "No external enrichment available. Add CLEARBIT_API_KEY for full enrichment."
        })

    return enrichment_data


@mcp.tool()
def find_buying_committee(
    company_domain: str,
    company_name: Optional[str] = None,
    roles: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Identify buying committee members at target company.

    Searches for decision-makers across key roles:
    - Economic Buyer (VP/Director level)
    - Technical Buyer (Engineering lead, Architect)
    - End User (IC, Manager)
    - Champion (Internal advocate)

    Args:
        company_domain: Company domain
        company_name: Company name (optional)
        roles: Specific roles to search (default: all)

    Returns:
        Dict with:
        - company_domain: str
        - buying_committee: list of {name, linkedin_url, role_type, title, seniority_level, email}
    """
    if not company_domain:
        raise ToolError("company_domain is required")

    if not roles:
        roles = ["ceo", "cto", "vp", "director", "head", "manager", "lead"]

    role_mapping = {
        "ceo": "economic_buyer",
        "cfo": "economic_buyer",
        "vp": "economic_buyer",
        "director": "technical_buyer",
        "head": "technical_buyer",
        "manager": "end_user",
        "lead": "end_user"
    }

    committee = []
    seen: set = set()
    for role in roles[:4]:  # cap at 4 roles to limit SearXNG load
        try:
            query = f'site:linkedin.com/in "{role}" "{company_name or company_domain}"'
            results = _search_web(query, max_results=3)
            for r in results:
                url = r.get("url", "").split("?")[0]
                if "linkedin.com/in/" not in url or url in seen:
                    continue
                seen.add(url)
                role_type = role_mapping.get(role.split()[0].lower(), "end_user")
                committee.append({
                    "name": r.get("title", "").split("|")[0].strip(),
                    "linkedin_url": url,
                    "role_type": role_type,
                    "title": role,
                    "seniority_level": "senior" if role_type == "economic_buyer" else "mid",
                    "email": None,
                })
        except Exception as exc:
            logger.warning("find_buying_committee search failed for role %s: %s", role, exc)

    return {"company_domain": company_domain, "buying_committee": committee}


@mcp.tool()
def verify_contact(
    email: str,
    phone: Optional[str] = None,
    check_social: bool = False
) -> Dict[str, Any]:
    """
    Verify contact with enhanced checks: email deliverability, phone validation, social profiles.

    Args:
        email: Email address to verify
        phone: Phone number to validate (optional)
        check_social: Search for LinkedIn/Twitter profiles (default: False)

    Returns:
        Dict with:
        - email_valid: True if deliverable
        - email_status: valid, invalid, risky, unknown
        - phone_valid: True if valid format (if provided)
        - social_profiles: {linkedin, twitter} (if check_social=True)
    """
    if not email:
        raise ToolError("email is required")

    result = {
        "email": email,
        "email_valid": False,
        "email_status": "unknown",
        "verification_method": "basic"
    }

    # Basic email regex validation
    email_regex = re.compile(r"^[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}$", re.IGNORECASE)
    if not email_regex.match(email):
        result["email_valid"] = False
        result["email_status"] = "invalid"
        return result

    # Hunter.io verification — only if free credits remain
    if HUNTER_API_KEY and _get_hunter_credits()["verifications"] > 0:
        try:
            response = requests.get(
                "https://api.hunter.io/v2/email-verifier",
                params={"email": email, "api_key": HUNTER_API_KEY},
                timeout=10
            )
            if response.status_code == 200:
                data = response.json().get("data", {})
                result.update({
                    "verification_method": "hunter.io",
                    "email_valid": data.get("result") == "deliverable",
                    "email_status": data.get("result"),
                    "score": data.get("score"),
                    "mx_records": data.get("mx_records", False),
                    "smtp_check": data.get("smtp_check", False)
                })
        except Exception as e:
            result["verification_error"] = str(e)

    # MX record fallback if Hunter.io was unavailable or returned unknown
    if result["email_status"] == "unknown":
        domain = email.split("@")[1]
        try:
            import dns.resolver
            dns.resolver.resolve(domain, 'MX')
            result["email_valid"] = True
            result["email_status"] = "valid"
            result["verification_method"] = "mx_check"
        except:
            result["email_valid"] = False
            result["email_status"] = "risky"

    # Phone validation (basic format check)
    if phone:
        phone_clean = re.sub(r'[^\d+]', '', phone)
        result["phone"] = phone
        result["phone_valid"] = len(phone_clean) >= 10
        result["phone_formatted"] = phone_clean

    # Social profile search (placeholder)
    if check_social:
        result["social_profiles"] = {
            "linkedin": None,
            "twitter": None,
            "note": "Add LinkedIn/Twitter API for real profile search"
        }

    return result


@mcp.tool()
def detect_intent_signals(
    company_domain: str,
    company_name: Optional[str] = None,
    signal_types: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Detect external buying intent signals for a company.

    Signal types:
    - job_postings: Hiring for relevant roles
    - funding: Recent funding rounds
    - news: Company news mentions
    - tech_changes: Technology stack changes
    - website_changes: Website/product updates

    Args:
        company_domain: Company domain
        company_name: Company name (optional)
        signal_types: Types of signals to check (default: all)

    Returns:
        Dict with signals found, intent_score (0-12), and recommendations
    """
    if not company_domain:
        raise ToolError("company_domain is required")

    if not signal_types:
        signal_types = ["job_postings", "funding", "news", "tech_changes"]

    signals = []
    intent_score = 0

    # Job postings signal (placeholder - would use external API)
    if "job_postings" in signal_types:
        # Would integrate with Indeed, LinkedIn Jobs, or job board APIs
        signals.append({
            "type": "job_postings",
            "description": "Search job boards for relevant hiring",
            "intent_weight": 3,
            "note": "Add job board API integration"
        })

    # Funding signal (placeholder)
    if "funding" in signal_types:
        # Would integrate with Crunchbase API
        signals.append({
            "type": "funding",
            "description": "Check recent funding announcements",
            "intent_weight": 5,
            "note": "Add Crunchbase API integration"
        })

    # News mentions (placeholder)
    if "news" in signal_types:
        # Would use Google News API or NewsAPI
        signals.append({
            "type": "news",
            "description": "Monitor company news mentions",
            "intent_weight": 2,
            "note": "Add news monitoring API"
        })

    # Calculate intent score
    for signal in signals:
        intent_score += signal.get("intent_weight", 0)

    return {
        "company_domain": company_domain,
        "company_name": company_name,
        "signals_checked": signal_types,
        "signals_found": signals,
        "intent_score": min(intent_score, 12),  # Cap at 12
        "recommendation": "High intent" if intent_score >= 8 else "Medium intent" if intent_score >= 4 else "Low intent"
    }


@mcp.tool()
def calculate_fit_score(
    lead_id: str,
    icp_criteria: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Calculate ICP (Ideal Customer Profile) fit score for a lead.

    Scoring factors (0-10 scale):
    - Industry match (0-2 points)
    - Company size match (0-2 points)
    - Technology stack fit (0-2 points)
    - Geographic location (0-2 points)
    - Seniority level (0-2 points)

    Args:
        lead_id: Lead UUID
        icp_criteria: Optional custom ICP criteria (default: use system default)

    Returns:
        Dict with fit_score (0-10), breakdown by factor, and recommendations
    """
    conn = get_conn()
    if not conn:
        raise ToolError("Database connection required for fit scoring")

    with conn, conn.cursor() as cur:
        cur.execute("""
            SELECT
                id, name, email, company_name, industry,
                num_employees, current_funnel_stage
            FROM leads
            WHERE id = %s
        """, [lead_id])

        lead = cur.fetchone()
        if not lead:
            raise ToolError(f"Lead {lead_id} not found")

        # Default ICP criteria if not provided
        if not icp_criteria:
            icp_criteria = {
                "target_industries": ["SaaS", "Technology", "Financial Services"],
                "min_employees": 50,
                "max_employees": 5000,
                "target_locations": ["US", "CA", "UK"],
                "target_seniority": ["VP", "Director", "Head", "C-level"]
            }

        # Calculate score
        score_breakdown = {}
        total_score = 0

        # Industry match (0-2 points)
        industry_score = 0
        if lead['industry'] in icp_criteria.get("target_industries", []):
            industry_score = 2
        elif lead['industry']:
            industry_score = 1
        score_breakdown["industry"] = industry_score
        total_score += industry_score

        # Company size match (0-2 points)
        size_score = 0
        num_employees = lead['num_employees'] or 0
        if icp_criteria.get("min_employees", 0) <= num_employees <= icp_criteria.get("max_employees", 999999):
            size_score = 2
        elif num_employees > 0:
            size_score = 1
        score_breakdown["company_size"] = size_score
        total_score += size_score

        # Technology stack fit (0-2 points) - placeholder
        tech_score = 1  # Default medium fit
        score_breakdown["technology"] = tech_score
        total_score += tech_score

        # Geographic location (0-2 points) - placeholder
        geo_score = 1  # Default medium fit
        score_breakdown["geography"] = geo_score
        total_score += geo_score

        # Seniority level (0-2 points) - placeholder
        seniority_score = 1  # Default medium fit
        score_breakdown["seniority"] = seniority_score
        total_score += seniority_score

        # Update lead with calculated fit score
        cur.execute("""
            UPDATE leads
            SET fit_score = %s
            WHERE id = %s
        """, [total_score, lead_id])

        conn.commit()

        return {
            "lead_id": lead_id,
            "lead_name": lead['name'],
            "company_name": lead['company_name'],
            "fit_score": total_score,
            "score_breakdown": score_breakdown,
            "icp_match": "Strong" if total_score >= 8 else "Good" if total_score >= 6 else "Fair" if total_score >= 4 else "Weak",
            "recommendation": "Prioritize for outreach" if total_score >= 7 else "Standard follow-up" if total_score >= 5 else "Low priority"
        }


@mcp.tool()
def enrich_lead_full(
    lead_id: str,
    company_domain: Optional[str] = None
) -> Dict[str, Any]:
    """
    All-in-one lead enrichment: company data + buying committee + intent signals + fit score.

    Args:
        lead_id: Lead UUID
        company_domain: Company domain (optional, will use lead's email domain if not provided)

    Returns:
        Dict with all enrichment data combined
    """
    conn = get_conn()
    if not conn:
        raise ToolError("Database connection required for full enrichment")

    with conn, conn.cursor() as cur:
        cur.execute("""
            SELECT id, name, email, company_name FROM leads WHERE id = %s
        """, [lead_id])

        lead = cur.fetchone()
        if not lead:
            raise ToolError(f"Lead {lead_id} not found")

        # Extract domain from email if not provided
        if not company_domain and lead['email']:
            company_domain = lead['email'].split('@')[1]

        if not company_domain:
            raise ToolError("company_domain required (cannot infer from lead data)")

        # Run all enrichment steps
        company_data = enrich_company(domain=company_domain, company_name=lead['company_name'])
        committee_data = find_buying_committee(company_domain=company_domain, company_name=lead['company_name'])
        intent_data = detect_intent_signals(company_domain=company_domain, company_name=lead['company_name'])
        fit_data = calculate_fit_score(lead_id=lead_id)

        return {
            "lead_id": lead_id,
            "lead_name": lead['name'],
            "lead_email": lead['email'],
            "company_enrichment": company_data,
            "buying_committee": committee_data,
            "intent_signals": intent_data,
            "fit_score_analysis": fit_data,
            "enrichment_complete": True
        }


if __name__ == "__main__":
    mcp.run()
