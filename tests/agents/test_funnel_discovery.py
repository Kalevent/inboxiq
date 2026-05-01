# tests/agents/test_funnel_discovery.py
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


def test_get_existing_companies_returns_company_names(full_app):
    from src.agents.funnel_discovery import FunnelDiscoveryAgent
    from src.models.leads import Lead
    from src.extensions import db

    with full_app.app_context():
        db.session.add(Lead(
            id="fx1", account_id=1, name="Org", email="a@org.com",
            company_name="OrgCo", source="manual", status="New Lead",
            fit_score=7, deleted=False,
        ))
        db.session.commit()

        agent = FunnelDiscoveryAgent(account_id=1)
        names = agent._tool_get_existing_companies()
        assert "OrgCo" in names


def test_save_lead_creates_row_and_rejects_duplicates(full_app):
    from src.agents.funnel_discovery import FunnelDiscoveryAgent
    from src.extensions import db

    with full_app.app_context():
        agent = FunnelDiscoveryAgent(account_id=1)
        result = agent._tool_save_lead(
            company_name="NewCo",
            email="contact@newco.com",
            industry="B2B SaaS",
            fit_score=7,
            source="searxng_discovery",
            notes="Hiring head of support",
        )
        assert result["created"] is True

        result2 = agent._tool_save_lead(
            company_name="NewCo",
            email="contact@newco.com",
            industry="B2B SaaS",
            fit_score=7,
            source="searxng_discovery",
            notes="Hiring head of support",
        )
        assert result2["created"] is False
        assert result2["reason"] == "duplicate"


def test_save_lead_rejects_low_fit_score(full_app):
    from src.agents.funnel_discovery import FunnelDiscoveryAgent
    from src.extensions import db

    with full_app.app_context():
        agent = FunnelDiscoveryAgent(account_id=1)
        result = agent._tool_save_lead(
            company_name="LowFit",
            email="x@lowfit.com",
            industry="B2B SaaS",
            fit_score=3,
            source="searxng_discovery",
        )
        assert result["created"] is False
        assert result["reason"] == "fit_score_too_low"
