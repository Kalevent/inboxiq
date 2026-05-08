"""Shared fixtures for tests/marketing.

The SQLite + StaticPool app setup is identical across the test files; only
the set of model __table__ objects to create differs. _build_app handles
the boilerplate; fixtures are thin wrappers."""
import os
import pytest

os.environ.setdefault("APP_ENV", "test")

from src.app import create_app
from src.extensions import db as _db


def _build_app(*model_classes):
    """Yield a Flask app bound to a fresh in-memory SQLite with the given
    model __table__ objects created. PRAGMA foreign_keys = ON for cascade
    behaviour. Tables dropped in reverse on teardown.
    """
    from sqlalchemy import text
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
        for cls in model_classes:
            cls.__table__.create(_db.engine, checkfirst=True)
        # Enable cascade delete for SQLite (off by default).
        _db.engine.connect().execute(text("PRAGMA foreign_keys = ON"))
        yield app
        _db.session.remove()
        for cls in reversed(model_classes):
            cls.__table__.drop(_db.engine, checkfirst=True)


@pytest.fixture
def app():
    """Account + ICPExperiment tables — used by Task 1's test."""
    from src.models.core import Account
    from src.models.marketing import ICPExperiment
    yield from _build_app(Account, ICPExperiment)


@pytest.fixture
def app_with_variant():
    """Account + ICPExperiment + ICPVariant tables — used by Task 2's tests."""
    from src.models.core import Account
    from src.models.marketing import ICPExperiment, ICPVariant
    yield from _build_app(Account, ICPExperiment, ICPVariant)


@pytest.fixture
def app_full():
    """Account + Lead + ICPExperiment + ICPVariant + ICPLeadAssignment."""
    from src.models.core import Account
    from src.models.leads import Lead
    from src.models.marketing import ICPExperiment, ICPVariant, ICPLeadAssignment
    yield from _build_app(Account, Lead, ICPExperiment, ICPVariant, ICPLeadAssignment)


@pytest.fixture
def db(app):
    return _db


@pytest.fixture
def db_with_variant(app_with_variant):
    return _db


@pytest.fixture
def db_full(app_full):
    return _db
