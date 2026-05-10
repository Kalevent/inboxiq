import pytest
from src.mcp.lead_discovery_mcp import extract_company_name, looks_like_real_company


@pytest.mark.parametrize("title,expected", [
    ("Sprinto - About Us", "Sprinto"),
    ("Acme Inc. | Customer Stories", "Acme"),
    ("Harver Series B Funding", "Harver Series B Funding"),
])
def test_extract_company_name_valid(title, expected):
    assert extract_company_name(title) == expected


@pytest.mark.parametrize("candidate", [
    "$12",
    "Series B",
    "30 Top B2B SaaS Companies & Startups [2026]",
    "Apply With MISD",
    "10 Fastest",
    "Exclusive",
    "Fundraising",
    "Understanding Seed Rounds, Series A, B, and C",
    "Yuma AI Raises $5 Million to Transform E",
    "Harver Series B Funding",
    "Acme Series A Round",
    "List of SaaS Investors & VC Firms",
    "How to Outsource Customer Support",
    "abc",
    "aaa",
    "a" * 71,
    "",
    "   ",
])
def test_looks_like_real_company_rejects_junk(candidate):
    assert looks_like_real_company(candidate) is False


@pytest.mark.parametrize("candidate", [
    "Sprinto",
    "Harver",
    "Acme Corporation",
    "Stripe",
    "Notion Labs",
    "Acme",
    "a" * 70,
])
def test_looks_like_real_company_accepts_real(candidate):
    assert looks_like_real_company(candidate) is True
