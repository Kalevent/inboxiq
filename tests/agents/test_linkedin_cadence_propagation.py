# tests/agents/test_linkedin_cadence_propagation.py
import pytest


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


def test_enrich_persists_job_title(full_app):
    """enrich_lead_linkedin_url stores job_title on the Lead."""
    from src.agents.linkedin_cadence import LinkedInCadenceAgent
    from src.models.leads import Lead
    from src.extensions import db

    with full_app.app_context():
        lead = Lead(
            id="lj1",
            account_id=1,
            name="Jazmyne Cavitt",
            email="j@sprinto.com",
            company_name="Sprinto",
            source="searxng_discovery",
            status="New Lead",
            fit_score=7,
            deleted=False,
        )
        db.session.add(lead)
        db.session.commit()

        agent = LinkedInCadenceAgent(account_id=1)
        result = agent._tool_enrich_lead_linkedin_url(
            lead_id=str(lead.id),
            linkedin_url="https://www.linkedin.com/in/jazmyne-cavitt",
            name="Jazmyne Cavitt",
            job_title="Director, Customer Support",
        )
        assert result["saved"] is True
        db.session.refresh(lead)
        assert lead.job_title == "Director, Customer Support"
        assert lead.linkedin_url == "https://www.linkedin.com/in/jazmyne-cavitt"


def test_promote_copies_job_title(full_app):
    """add_to_prospect_queue copies job_title from Lead to LinkedInProspect."""
    from src.agents.linkedin_cadence import LinkedInCadenceAgent
    from src.models.leads import Lead
    from src.models.campaigns import LinkedInProspect
    from src.extensions import db

    with full_app.app_context():
        lead = Lead(
            id="lj2",
            account_id=1,
            name="Jazmyne Cavitt",
            email="j@sprinto.com",
            company_name="Sprinto",
            source="searxng_discovery",
            status="New Lead",
            fit_score=7,
            deleted=False,
            job_title="Director, Customer Support",
            linkedin_url="https://www.linkedin.com/in/jazmyne-cavitt",
        )
        db.session.add(lead)
        db.session.commit()

        agent = LinkedInCadenceAgent(account_id=1)
        result = agent._tool_add_to_prospect_queue(str(lead.id))
        assert result["created"] is True

        prospect = (
            db.session.query(LinkedInProspect)
            .filter_by(lead_id=lead.id)
            .one()
        )
        assert prospect.job_title == "Director, Customer Support"
