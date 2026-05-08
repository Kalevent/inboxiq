import os
import pytest

os.environ.setdefault("APP_ENV", "test")

from src.app import create_app
from src.extensions import db as _db
from src.models.leads import Lead
from src.models.campaigns import LinkedInProspect
from src.models.marketing import ICPConfig, ICPExperiment, ICPVariant, ICPLeadAssignment


@pytest.fixture
def app():
    from sqlalchemy.pool import StaticPool

    app = create_app()
    app.config["TESTING"] = True
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite://"
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
        "connect_args": {"check_same_thread": False},
        "poolclass": StaticPool,
    }
    app.config["SECRET_KEY"] = "test-secret"
    with app.app_context():
        # Only create tables needed for LinkedIn prospect tests to avoid
        # circular-FK issues from the full schema on SQLite.
        Lead.__table__.create(_db.engine, checkfirst=True)
        LinkedInProspect.__table__.create(_db.engine, checkfirst=True)
        ICPConfig.__table__.create(_db.engine, checkfirst=True)
        ICPExperiment.__table__.create(_db.engine, checkfirst=True)
        ICPVariant.__table__.create(_db.engine, checkfirst=True)
        ICPLeadAssignment.__table__.create(_db.engine, checkfirst=True)
        yield app
        _db.session.remove()
        ICPLeadAssignment.__table__.drop(_db.engine, checkfirst=True)
        ICPVariant.__table__.drop(_db.engine, checkfirst=True)
        ICPExperiment.__table__.drop(_db.engine, checkfirst=True)
        ICPConfig.__table__.drop(_db.engine, checkfirst=True)
        LinkedInProspect.__table__.drop(_db.engine, checkfirst=True)
        Lead.__table__.drop(_db.engine, checkfirst=True)


@pytest.fixture
def db(app):
    return _db
