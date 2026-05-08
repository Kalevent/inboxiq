"""Regression test for the production crash on GET /api/v1/linkedin/icp.

Commit e321b36 ('replace LinkedIn task bodies with LinkedInCadenceAgent
wrappers', 2026-05-01) removed _ICP_DEFAULTS from src/tasks/linkedin.py
when refactoring the task module. The endpoint api_get_icp at
src/api/v1/linkedin.py:186 still imports it, so the route 500s with
ImportError every time a logged-in user hits Settings -> LinkedIn ICP.

Crash report from the new flagging system surfaced this on 2026-05-08
14:59 UTC. Pinning the symbol with a regression test so the next
refactor can't silently delete it again.
"""


def test_icp_defaults_importable_from_tasks_linkedin():
    from src.tasks.linkedin import _ICP_DEFAULTS  # noqa: F401
    assert isinstance(_ICP_DEFAULTS, dict)
    for key in ("titles", "industries", "company_size_min", "company_size_max", "geographies"):
        assert key in _ICP_DEFAULTS, f"_ICP_DEFAULTS must keep {key} (api_get_icp returns this dict to the UI)"
    assert isinstance(_ICP_DEFAULTS["titles"], list) and _ICP_DEFAULTS["titles"]
    assert isinstance(_ICP_DEFAULTS["geographies"], list) and _ICP_DEFAULTS["geographies"]


def test_icp_defaults_match_source_of_truth_in_ICP_md():
    """ICP.md describes Oliver (ICP 1) as the canonical target customer.
    _ICP_DEFAULTS is the dict served to any account without an ICPConfig
    row, so it must reflect the documented ICP — otherwise new accounts
    start with a stale model.

    Specifically (from ICP.md):
    - 'Founder, co-founder, or head of operations'
    - B2B SaaS only (Software is a 2026-ago artefact, removed)
    - 10-50 employees
    - UK / EU primary; US secondary (Nigeria is ICP 2 / Sam, not Oliver)
    """
    from src.tasks.linkedin import _ICP_DEFAULTS

    titles_lower = [t.lower() for t in _ICP_DEFAULTS["titles"]]
    assert "founder" in titles_lower
    assert "co-founder" in titles_lower
    assert any("operations" in t for t in titles_lower), \
        "ICP.md names 'head of operations' as a target — must appear in titles"

    assert _ICP_DEFAULTS["industries"] == ["B2B SaaS"], \
        f"ICP.md scopes Oliver to B2B SaaS only, got {_ICP_DEFAULTS['industries']}"

    assert _ICP_DEFAULTS["company_size_min"] == 10
    assert _ICP_DEFAULTS["company_size_max"] == 50

    geos = _ICP_DEFAULTS["geographies"]
    assert "UK" in geos and "US" in geos
    assert "Nigeria" not in geos, \
        "Nigeria is ICP 2 (Sam, distribution/trading) — not Oliver. Remove from defaults."
