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


@pytest.fixture
def app_with_variant():
    """Same as `app` but also creates ICPVariant table."""
    from sqlalchemy import text
    from sqlalchemy.pool import StaticPool
    from src.models.core import Account
    from src.models.marketing import ICPExperiment, ICPVariant

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
        ICPVariant.__table__.create(_db.engine, checkfirst=True)
        # Enable foreign keys (for cascade delete) on SQLite
        with _db.engine.connect() as conn:
            conn.execute(text("PRAGMA foreign_keys = ON"))
            conn.commit()
        yield app
        _db.session.remove()
        ICPVariant.__table__.drop(_db.engine, checkfirst=True)
        ICPExperiment.__table__.drop(_db.engine, checkfirst=True)
        Account.__table__.drop(_db.engine, checkfirst=True)


@pytest.fixture
def db_with_variant(app_with_variant):
    return _db


def _make_experiment(db):
    from src.models.core import Account
    from src.models.marketing import ICPExperiment
    a = Account(name="t")
    db.session.add(a); db.session.flush()
    e = ICPExperiment(account_id=a.id, name="exp")
    db.session.add(e); db.session.commit()
    return e


def test_icp_variant_create_a_and_b(app_with_variant, db_with_variant):
    from src.models.marketing import ICPVariant
    db = db_with_variant
    e = _make_experiment(db)
    a = ICPVariant(experiment_id=e.id, label="A", titles=["Founder"], industries=["B2B SaaS"], geographies=["UK"])
    b = ICPVariant(experiment_id=e.id, label="B", titles=["Co-founder"], industries=["B2B SaaS"], geographies=["UK"])
    db.session.add_all([a, b]); db.session.commit()
    assert a.id and b.id and a.id != b.id


def test_icp_variant_unique_label_per_experiment(app_with_variant, db_with_variant):
    from sqlalchemy.exc import IntegrityError
    from src.models.marketing import ICPVariant
    db = db_with_variant
    e = _make_experiment(db)
    db.session.add(ICPVariant(experiment_id=e.id, label="A", titles=[], industries=[], geographies=[]))
    db.session.commit()
    db.session.add(ICPVariant(experiment_id=e.id, label="A", titles=[], industries=[], geographies=[]))
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


def test_icp_variant_label_must_be_a_or_b(app_with_variant, db_with_variant):
    from sqlalchemy.exc import IntegrityError
    from src.models.marketing import ICPVariant
    db = db_with_variant
    e = _make_experiment(db)
    db.session.add(ICPVariant(experiment_id=e.id, label="C", titles=[], industries=[], geographies=[]))
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


def test_icp_variant_cascade_delete_with_experiment(app_with_variant, db_with_variant):
    from src.models.marketing import ICPExperiment, ICPVariant
    db = db_with_variant
    e = _make_experiment(db)
    db.session.add(ICPVariant(experiment_id=e.id, label="A", titles=["x"], industries=["y"], geographies=["z"]))
    db.session.commit()
    assert ICPVariant.query.count() == 1
    db.session.delete(e); db.session.commit()
    assert ICPVariant.query.count() == 0, "deleting experiment should cascade-delete its variants"
