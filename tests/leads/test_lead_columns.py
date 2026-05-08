"""Tests for the new Lead.job_title and Lead.country columns added to
support strict matching in src/marketing/icp_match.py (Task 5.7)."""
import os
import pytest

os.environ.setdefault("APP_ENV", "test")

from src.app import create_app
from src.extensions import db as _db


@pytest.fixture
def app():
    from sqlalchemy.pool import StaticPool
    from src.models.core import Account
    from src.models.leads import Lead
    app = create_app()
    app.config["TESTING"] = True
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite://"
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
        "connect_args": {"check_same_thread": False},
        "poolclass": StaticPool,
    }
    app.config["SECRET_KEY"] = "test-secret"
    with app.app_context():
        Account.__table__.create(_db.engine, checkfirst=True)
        Lead.__table__.create(_db.engine, checkfirst=True)
        yield app
        _db.session.remove()
        Lead.__table__.drop(_db.engine, checkfirst=True)
        Account.__table__.drop(_db.engine, checkfirst=True)


@pytest.fixture
def db(app):
    return _db


def _make_account(db):
    from src.models.core import Account
    a = Account(name="t")
    db.session.add(a); db.session.flush()
    return a


def test_lead_has_job_title_column(app, db):
    """Lead.job_title is a String(120) nullable column added in Task 5.5."""
    from src.models.leads import Lead
    a = _make_account(db)
    lead = Lead(account_id=a.id, name="Test Lead", email="t@example.com", source="test", job_title="Founder")
    db.session.add(lead); db.session.commit()
    assert lead.job_title == "Founder"


def test_lead_has_country_column(app, db):
    """Lead.country is a String(64) nullable column added in Task 5.5."""
    from src.models.leads import Lead
    a = _make_account(db)
    lead = Lead(account_id=a.id, name="Test Lead", email="t@example.com", source="test", country="UK")
    db.session.add(lead); db.session.commit()
    assert lead.country == "UK"


def test_lead_job_title_is_nullable(app, db):
    """Existing leads created without job_title must still validate."""
    from src.models.leads import Lead
    a = _make_account(db)
    lead = Lead(account_id=a.id, name="Test Lead", email="t@example.com", source="test")
    db.session.add(lead); db.session.commit()
    assert lead.job_title is None


def test_lead_country_is_nullable(app, db):
    """Existing leads created without country must still validate."""
    from src.models.leads import Lead
    a = _make_account(db)
    lead = Lead(account_id=a.id, name="Test Lead", email="t@example.com", source="test")
    db.session.add(lead); db.session.commit()
    assert lead.country is None


def test_lead_country_has_named_index():
    """The country column has an index named idx_leads_country for the
    future geo-filter query path."""
    from src.models.leads import Lead
    indexes = {idx.name for idx in Lead.__table__.indexes}
    assert "idx_leads_country" in indexes
