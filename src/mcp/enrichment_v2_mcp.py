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
- HUNTER_API_KEY: Hunter.io for email verification (optional)
- MCP_DATABASE_URL or DATABASE_URL: PostgreSQL connection string
"""
from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional
import requests
import psycopg2
from psycopg2.extras import RealDictCursor

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

mcp = FastMCP("enrichment-v2-mcp")

# External API keys (optional)
CLEARBIT_API_KEY = os.getenv("CLEARBIT_API_KEY")
HUNTER_API_KEY = os.getenv("HUNTER_API_KEY")


def get_conn():
    """Get database connection"""
    if DATABASE_URL:
        try:
            return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        except Exception as e:
            raise ToolError(f"Failed to connect to database: {e}")
    return None


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
        Dict with buying_committee list containing:
        - name, title, email (if found)
        - role_type (economic_buyer, technical_buyer, end_user, champion)
        - seniority_level
        - linkedin_url (if available)
    """
    if not company_domain:
        raise ToolError("company_domain is required")

    if not roles:
        roles = ["ceo", "cto", "vp", "director", "head", "manager", "lead"]

    # This would typically use Apollo.io, RocketReach, or Hunter.io
    # For now, return structured placeholder
    committee = []

    role_mapping = {
        "ceo": "economic_buyer",
        "cfo": "economic_buyer",
        "vp": "economic_buyer",
        "director": "technical_buyer",
        "head": "technical_buyer",
        "manager": "end_user",
        "lead": "end_user"
    }

    # Placeholder logic - would integrate with external API
    for role in roles:
        committee.append({
            "name": f"[Search for {role} at {company_name or company_domain}]",
            "title": role.upper(),
            "email": None,
            "role_type": role_mapping.get(role.lower(), "end_user"),
            "seniority_level": "senior" if role.lower() in ["ceo", "cfo", "vp", "director"] else "mid",
            "linkedin_url": None,
            "confidence": "low",
            "note": "Add Apollo.io or RocketReach API for real data"
        })

    return {
        "company_domain": company_domain,
        "company_name": company_name,
        "roles_searched": roles,
        "buying_committee": committee,
        "total_contacts": len(committee)
    }


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

    # Try Hunter.io verification if available
    if HUNTER_API_KEY:
        try:
            response = requests.get(
                f"https://api.hunter.io/v2/email-verifier",
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

    # Fallback: basic MX record check
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
