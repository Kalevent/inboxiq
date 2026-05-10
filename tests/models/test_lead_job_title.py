from src.models.leads import Lead
from src.models.campaigns import LinkedInProspect


def test_lead_has_job_title_column():
    assert "job_title" in Lead.__table__.columns
    col = Lead.__table__.columns["job_title"]
    assert col.nullable is True
    assert str(col.type).startswith("VARCHAR")


def test_linkedin_prospect_has_job_title_column():
    assert "job_title" in LinkedInProspect.__table__.columns
    col = LinkedInProspect.__table__.columns["job_title"]
    assert col.nullable is True
