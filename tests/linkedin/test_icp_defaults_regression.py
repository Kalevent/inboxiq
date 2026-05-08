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
