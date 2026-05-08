"""Tests for src/marketing/icp_match.py — applies a variant's ICP filters
to a Lead and reports whether the Lead qualifies.

All four filters (titles, industries, geographies, company size) are
strict-match: an empty filter is permissive, a non-empty filter must
match the corresponding Lead field (case-insensitive for string fields).
Lead.job_title or Lead.country being None with a non-empty filter set
means no match."""
from unittest.mock import MagicMock


def _fake_lead(industry=None, num_employees=None, job_title=None, country=None):
    lead = MagicMock(spec=["industry", "num_employees", "job_title", "country"])
    lead.industry = industry
    lead.num_employees = num_employees
    lead.job_title = job_title
    lead.country = country
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


def test_match_when_job_title_in_variant_titles():
    from src.marketing.icp_match import lead_matches_variant
    lead = _fake_lead(industry="B2B SaaS", num_employees=30, job_title="Founder")
    variant = _fake_variant(titles=["Founder", "Co-founder"], industries=["B2B SaaS"])
    assert lead_matches_variant(lead, variant) is True


def test_no_match_when_job_title_not_in_variant_titles():
    from src.marketing.icp_match import lead_matches_variant
    lead = _fake_lead(industry="B2B SaaS", num_employees=30, job_title="Sales Rep")
    variant = _fake_variant(titles=["Founder", "Co-founder"], industries=["B2B SaaS"])
    assert lead_matches_variant(lead, variant) is False


def test_match_titles_is_case_insensitive():
    from src.marketing.icp_match import lead_matches_variant
    lead = _fake_lead(industry="B2B SaaS", num_employees=30, job_title="founder")
    variant = _fake_variant(titles=["Founder", "Co-founder"], industries=["B2B SaaS"])
    assert lead_matches_variant(lead, variant) is True


def test_no_match_when_lead_job_title_is_none_and_filter_set():
    from src.marketing.icp_match import lead_matches_variant
    lead = _fake_lead(industry="B2B SaaS", num_employees=30, job_title=None)
    variant = _fake_variant(titles=["Founder", "Co-founder"], industries=["B2B SaaS"])
    assert lead_matches_variant(lead, variant) is False


def test_match_when_titles_filter_is_empty():
    """Permissive when variant.titles is [] regardless of lead.job_title."""
    from src.marketing.icp_match import lead_matches_variant
    lead = _fake_lead(industry="B2B SaaS", num_employees=30, job_title=None)
    variant = _fake_variant(titles=[], industries=["B2B SaaS"])
    assert lead_matches_variant(lead, variant) is True


def test_match_when_country_in_variant_geographies():
    from src.marketing.icp_match import lead_matches_variant
    lead = _fake_lead(industry="B2B SaaS", num_employees=30, country="UK")
    variant = _fake_variant(geographies=["UK", "EU", "US"], industries=["B2B SaaS"])
    assert lead_matches_variant(lead, variant) is True


def test_no_match_when_country_not_in_variant_geographies():
    from src.marketing.icp_match import lead_matches_variant
    lead = _fake_lead(industry="B2B SaaS", num_employees=30, country="Nigeria")
    variant = _fake_variant(geographies=["UK", "EU", "US"], industries=["B2B SaaS"])
    assert lead_matches_variant(lead, variant) is False


def test_match_geographies_is_case_insensitive():
    from src.marketing.icp_match import lead_matches_variant
    lead = _fake_lead(industry="B2B SaaS", num_employees=30, country="uk")
    variant = _fake_variant(geographies=["UK", "EU", "US"], industries=["B2B SaaS"])
    assert lead_matches_variant(lead, variant) is True


def test_no_match_when_lead_country_is_none_and_filter_set():
    from src.marketing.icp_match import lead_matches_variant
    lead = _fake_lead(industry="B2B SaaS", num_employees=30, country=None)
    variant = _fake_variant(geographies=["UK", "EU", "US"], industries=["B2B SaaS"])
    assert lead_matches_variant(lead, variant) is False


def test_match_when_geographies_filter_is_empty():
    """Permissive when variant.geographies is [] regardless of lead.country."""
    from src.marketing.icp_match import lead_matches_variant
    lead = _fake_lead(industry="B2B SaaS", num_employees=30, country=None)
    variant = _fake_variant(geographies=[], industries=["B2B SaaS"])
    assert lead_matches_variant(lead, variant) is True
