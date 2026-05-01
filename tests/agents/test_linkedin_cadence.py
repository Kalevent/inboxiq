# tests/agents/test_linkedin_cadence.py
import pytest
from unittest.mock import patch, MagicMock
from sqlalchemy.pool import StaticPool


@pytest.fixture
def full_app(app):
    """Extend conftest app with Lead, LinkedInProspect, ICPConfig tables."""
    from src.models.leads import Lead
    from src.models.campaigns import LinkedInProspect
    from src.models.marketing import ICPConfig
    from src.extensions import db as _db
    with app.app_context():
        Lead.__table__.create(_db.engine, checkfirst=True)
        LinkedInProspect.__table__.create(_db.engine, checkfirst=True)
        ICPConfig.__table__.create(_db.engine, checkfirst=True)
        yield app
        ICPConfig.__table__.drop(_db.engine, checkfirst=True)
        LinkedInProspect.__table__.drop(_db.engine, checkfirst=True)
        Lead.__table__.drop(_db.engine, checkfirst=True)


def test_get_qualifying_leads_returns_leads_with_no_linkedin(full_app):
    """get_qualifying_leads returns fit_score >= 7, linkedin_url IS NULL leads."""
    from src.agents.linkedin_cadence import LinkedInCadenceAgent
    from src.models.leads import Lead
    from src.extensions import db

    with full_app.app_context():
        db.session.add(Lead(
            id="l1", account_id=1, name="Ada", email="ada@co.com",
            company_name="Co", source="manual", status="New Lead",
            fit_score=8, deleted=False, linkedin_url=None,
        ))
        db.session.add(Lead(
            id="l2", account_id=1, name="Bob", email="bob@co.com",
            company_name="Co", source="manual", status="New Lead",
            fit_score=5, deleted=False, linkedin_url=None,
        ))
        db.session.commit()

        agent = LinkedInCadenceAgent(account_id=1)
        leads = agent._tool_get_qualifying_leads()
        assert len(leads) == 1
        assert leads[0]["id"] == "l1"


def test_add_to_prospect_queue_creates_prospect(full_app):
    """add_to_prospect_queue creates a LinkedInProspect for a qualifying lead."""
    from src.agents.linkedin_cadence import LinkedInCadenceAgent
    from src.models.leads import Lead
    from src.models.campaigns import LinkedInProspect
    from src.extensions import db

    with full_app.app_context():
        db.session.add(Lead(
            id="l3", account_id=1, name="Carol", email="carol@co.com",
            company_name="Co", source="manual", status="New Lead",
            fit_score=9, deleted=False, linkedin_url="https://linkedin.com/in/carol",
        ))
        db.session.commit()

        agent = LinkedInCadenceAgent(account_id=1)
        result = agent._tool_add_to_prospect_queue(lead_id="l3")
        assert result["created"] is True

        p = db.session.query(LinkedInProspect).filter_by(lead_id="l3").first()
        assert p is not None
        assert p.status == "pending"


def test_enrich_lead_linkedin_url_saves_url(full_app):
    """enrich_lead_linkedin_url stores a valid LinkedIn URL on the Lead."""
    from src.agents.linkedin_cadence import LinkedInCadenceAgent
    from src.models.leads import Lead
    from src.extensions import db

    with full_app.app_context():
        db.session.add(Lead(
            id="l4", account_id=1, name="Dave", email="dave@co.com",
            company_name="Co", source="manual", status="New Lead",
            fit_score=8, deleted=False, linkedin_url=None,
        ))
        db.session.commit()

        agent = LinkedInCadenceAgent(account_id=1)
        result = agent._tool_enrich_lead_linkedin_url(
            lead_id="l4",
            linkedin_url="https://linkedin.com/in/dave?trk=foo",
        )
        assert result["saved"] is True
        lead = db.session.query(Lead).filter_by(id="l4").first()
        assert lead.linkedin_url == "https://linkedin.com/in/dave"


def test_enrich_lead_linkedin_url_rejects_invalid_url(full_app):
    """enrich_lead_linkedin_url rejects non-LinkedIn URLs."""
    from src.agents.linkedin_cadence import LinkedInCadenceAgent
    from src.models.leads import Lead
    from src.extensions import db

    with full_app.app_context():
        db.session.add(Lead(
            id="l5", account_id=1, name="Eve", email="eve@co.com",
            company_name="Co", source="manual", status="New Lead",
            fit_score=8, deleted=False, linkedin_url=None,
        ))
        db.session.commit()

        agent = LinkedInCadenceAgent(account_id=1)
        result = agent._tool_enrich_lead_linkedin_url(
            lead_id="l5",
            linkedin_url="https://evil.com/in/evil",
        )
        assert result["saved"] is False
        assert "invalid" in result["error"]
