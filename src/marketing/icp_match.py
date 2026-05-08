"""Applies an ICPVariant's filters to a Lead. Used by the experiment
branch of linkedin.discover_prospects to decide which (if any) variant
gets to claim a given lead.

Known gaps (v1 — permissive on these filters):
  - variant.titles: Lead has no job_title column. Titles live in
    lead.buying_committee_json; filtering will be added once we decide
    whether to match committee titles or move the filter to the
    LinkedInProspect layer.
  - variant.geographies: Lead has no country column. Will be added once
    Lead grows geographic data.
"""
from __future__ import annotations


def _norm_list(values):
    return {str(v).strip().lower() for v in (values or []) if v}


def lead_matches_variant(lead, variant) -> bool:
    """Return True if the Lead satisfies all of the variant's enforceable filters.

    Enforced (v1):
      - industries: lead.industry must match one entry (case-insensitive)
      - company_size_min / company_size_max: lead.num_employees must be
        within range (None on either bound disables that side; None on
        lead.num_employees with any size bound set => no match)

    Permissive (v1):
      - titles: Lead has no job_title; always passes
      - geographies: Lead has no country; always passes
    """
    industries = _norm_list(variant.industries)
    if industries:
        if not lead.industry or str(lead.industry).strip().lower() not in industries:
            return False

    size = lead.num_employees
    if variant.company_size_min is not None and (size is None or size < variant.company_size_min):
        return False
    if variant.company_size_max is not None and (size is None or size > variant.company_size_max):
        return False

    return True
