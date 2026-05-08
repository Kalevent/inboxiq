"""Tests for the ICP A/B experiment models. Three models work together to
enable parallel ICP testing: one experiment owns two variants and many
lead assignments. See docs/superpowers/specs/2026-05-08-icp-ab-parallel-testing-design.md."""
import os
import pytest

os.environ.setdefault("APP_ENV", "test")

from src.app import create_app
from src.extensions import db as _db


@pytest.fixture
def app():
    from sqlalchemy.pool import StaticPool
    from src.models.core import Account
    from src.models.marketing import ICPExperiment

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
        ICPExperiment.__table__.create(_db.engine, checkfirst=True)
        yield app
        _db.session.remove()
        ICPExperiment.__table__.drop(_db.engine, checkfirst=True)
        Account.__table__.drop(_db.engine, checkfirst=True)


@pytest.fixture
def db(app):
    return _db


def test_icp_experiment_create_with_defaults(app, db):
    from src.models.core import Account
    from src.models.marketing import ICPExperiment

    a = Account(name="t")
    db.session.add(a); db.session.flush()
    exp = ICPExperiment(account_id=a.id, name="Founder vs Co-founder Q2")
    db.session.add(exp); db.session.commit()

    assert exp.id is not None
    assert len(exp.id) == 36 or len(exp.id) >= 32  # uuid format
    assert exp.status == "running"
    assert exp.traffic_split == {"A": 50, "B": 50}
    assert exp.winner_variant is None
    assert exp.created_at is not None
