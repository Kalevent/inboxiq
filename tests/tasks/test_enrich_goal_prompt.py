import inspect
from src.tasks import linkedin as linkedin_tasks


def _enrich_source() -> str:
    return inspect.getsource(linkedin_tasks.enrich_linkedin_urls)


def test_enrich_goal_includes_skip_directive():
    src = _enrich_source()
    assert "SKIP" in src, "goal must use uppercase SKIP to make the directive prominent"


def test_enrich_goal_forbids_calling_enrich_when_no_match():
    src = _enrich_source()
    assert "do not call enrich_lead_linkedin_url" in src.lower()


def test_enrich_goal_caps_lead_count():
    src = _enrich_source()
    assert "10 leads" in src or "10 prospects" in src or "after 10" in src.lower()
