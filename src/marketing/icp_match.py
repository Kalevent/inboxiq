"""Applies an ICPVariant's filters to a Lead. Used by the experiment
branch of linkedin.discover_prospects to decide which (if any) variant
gets to claim a given lead."""
from __future__ import annotations


def _norm_list(values):
    return {str(v).strip().lower() for v in (values or []) if v}


def lead_matches_variant(lead, variant) -> bool:
    """Return True if the Lead satisfies all of the variant's non-empty filters.

    All filters are permissive when empty; non-empty filters require a match:
      - titles: lead.job_title must match one entry (case-insensitive)
      - industries: lead.industry must match one entry (case-insensitive)
      - geographies: lead.country must match one entry (case-insensitive)
      - company_size_min / company_size_max: lead.num_employees must be
        within range. None on either bound disables that side; None on
        lead.num_employees with any size bound set => no match.
    """
    titles = _norm_list(variant.titles)
    if titles:
        if not lead.job_title or str(lead.job_title).strip().lower() not in titles:
            return False

    industries = _norm_list(variant.industries)
    if industries:
        if not lead.industry or str(lead.industry).strip().lower() not in industries:
            return False

    geographies = _norm_list(variant.geographies)
    if geographies:
        if not lead.country or str(lead.country).strip().lower() not in geographies:
            return False

    size = lead.num_employees
    if variant.company_size_min is not None and (size is None or size < variant.company_size_min):
        return False
    if variant.company_size_max is not None and (size is None or size > variant.company_size_max):
        return False

    return True
