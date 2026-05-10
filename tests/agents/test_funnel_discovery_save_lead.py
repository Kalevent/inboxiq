import pytest


@pytest.fixture
def full_app(app):
    from src.models.leads import Lead
    from src.models.marketing import ICPConfig
    from src.extensions import db as _db
    with app.app_context():
        Lead.__table__.create(_db.engine, checkfirst=True)
        ICPConfig.__table__.create(_db.engine, checkfirst=True)
        yield app
        ICPConfig.__table__.drop(_db.engine, checkfirst=True)
        Lead.__table__.drop(_db.engine, checkfirst=True)


@pytest.mark.parametrize("company_name", [
    "$12",
    "Series B",
    "Exclusive",
    "Apply With MISD",
    "10 Fastest",
    "30 Top B2B SaaS Companies & Startups [2026]",
    "Understanding Seed Rounds, Series A, B, and C",
    "abc",
    "Yuma AI Raises $5 Million to Transform E",
    "Harver Series B Funding",
])
def test_save_lead_rejects_garbage_company_name(full_app, company_name):
    from src.agents.funnel_discovery import FunnelDiscoveryAgent

    with full_app.app_context():
        agent = FunnelDiscoveryAgent(account_id=1)
        result = agent._tool_save_lead(
            company_name=company_name,
            email="x@example.com",
            industry="SaaS",
            fit_score=7,
            source="searxng_discovery",
        )
        assert result["created"] is False, f"expected created=False for {company_name!r}, got {result}"
        assert result["reason"] == "not_a_company", f"expected reason=not_a_company for {company_name!r}, got {result}"
