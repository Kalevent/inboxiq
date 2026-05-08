"""Tests for src/marketing/icp_match.py — applies a variant's ICP filters
to a Lead and reports whether the Lead qualifies.

Lead has no job_title or country today, so the titles and geographies
filters are permissive (always pass). Only industry and company size
are actually enforced. Documented as a known gap; revisit when
buying_committee filtering is added."""
from unittest.mock import MagicMock


def _fake_lead(industry=None, num_employees=None):
    lead = MagicMock(spec=["industry", "num_employees"])
    lead.industry = industry
    lead.num_employees = num_employees
    return lead


def _fake_variant(titles=None, industries=None, geographies=None, size_min=None, size_max=None):
    v = MagicMock()
    v.titles = titles or []
    v.industries = industries or []
    v.geographies = geographies or []
    v.company_size_min = size_min
    v.company_size_max = size_max
    return v


def test_match_when_industry_and_size_pass():
    from src.marketing.icp_match import lead_matches_variant
    lead = _fake_lead(industry="B2B SaaS", num_employees=30)
    variant = _fake_variant(industries=["B2B SaaS"], size_min=10, size_max=50)
    assert lead_matches_variant(lead, variant) is True


def test_no_match_when_industry_does_not_match():
    from src.marketing.icp_match import lead_matches_variant
    lead = _fake_lead(industry="Manufacturing", num_employees=30)
    variant = _fake_variant(industries=["B2B SaaS"])
    assert lead_matches_variant(lead, variant) is False


def test_match_is_case_insensitive_on_industry():
    from src.marketing.icp_match import lead_matches_variant
    lead = _fake_lead(industry="b2b saas", num_employees=30)
    variant = _fake_variant(industries=["B2B SaaS"])
    assert lead_matches_variant(lead, variant) is True


def test_no_match_when_num_employees_below_min():
    from src.marketing.icp_match import lead_matches_variant
    lead = _fake_lead(industry="B2B SaaS", num_employees=5)
    variant = _fake_variant(industries=["B2B SaaS"], size_min=10, size_max=50)
    assert lead_matches_variant(lead, variant) is False


def test_no_match_when_num_employees_above_max():
    from src.marketing.icp_match import lead_matches_variant
    lead = _fake_lead(industry="B2B SaaS", num_employees=500)
    variant = _fake_variant(industries=["B2B SaaS"], size_min=10, size_max=50)
    assert lead_matches_variant(lead, variant) is False


def test_match_when_size_filters_are_none():
    from src.marketing.icp_match import lead_matches_variant
    lead = _fake_lead(industry="B2B SaaS", num_employees=None)
    variant = _fake_variant(industries=["B2B SaaS"], size_min=None, size_max=None)
    assert lead_matches_variant(lead, variant) is True


def test_no_match_when_lead_has_no_employee_count_and_filter_set():
    """If variant requires a size range and lead.num_employees is None,
    we cannot confirm match — treat as no-match."""
    from src.marketing.icp_match import lead_matches_variant
    lead = _fake_lead(industry="B2B SaaS", num_employees=None)
    variant = _fake_variant(industries=["B2B SaaS"], size_min=10, size_max=50)
    assert lead_matches_variant(lead, variant) is False


def test_titles_filter_is_permissive_v1():
    """Lead has no job_title column today, so the variant.titles filter
    is permissive (always passes) until that gap is closed in a follow-up."""
    from src.marketing.icp_match import lead_matches_variant
    lead = _fake_lead(industry="B2B SaaS", num_employees=30)
    variant = _fake_variant(titles=["Founder", "Co-founder"], industries=["B2B SaaS"])
    assert lead_matches_variant(lead, variant) is True


def test_geographies_filter_is_permissive_v1():
    """Lead has no country column today, so variant.geographies is permissive."""
    from src.marketing.icp_match import lead_matches_variant
    lead = _fake_lead(industry="B2B SaaS", num_employees=30)
    variant = _fake_variant(geographies=["UK", "EU", "US"], industries=["B2B SaaS"])
    assert lead_matches_variant(lead, variant) is True
