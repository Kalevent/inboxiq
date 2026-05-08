"""Tests for the ICP A/B experiment models. Three models work together to
enable parallel ICP testing: one experiment owns two variants and many
lead assignments. See docs/superpowers/specs/2026-05-08-icp-ab-parallel-testing-design.md."""
import pytest


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


def _make_lead(db, account_id):
    from src.models.leads import Lead
    lead = Lead(account_id=account_id, name="Test Lead", email="test@example.com", source="test")
    db.session.add(lead); db.session.commit()
    return lead


def _make_experiment_with_variants(db):
    from src.models.core import Account
    from src.models.marketing import ICPExperiment, ICPVariant
    a = Account(name="t")
    db.session.add(a); db.session.flush()
    e = ICPExperiment(account_id=a.id, name="exp")
    db.session.add(e); db.session.flush()
    va = ICPVariant(experiment_id=e.id, label="A", titles=["Founder"], industries=["B2B SaaS"], geographies=["UK"])
    vb = ICPVariant(experiment_id=e.id, label="B", titles=["Co-founder"], industries=["B2B SaaS"], geographies=["UK"])
    db.session.add_all([va, vb]); db.session.commit()
    return e, va, vb, a


def test_icp_lead_assignment_create(app_full, db_full):
    from src.models.marketing import ICPLeadAssignment
    e, va, _, account = _make_experiment_with_variants(db_full)
    lead = _make_lead(db_full, account.id)
    asg = ICPLeadAssignment(experiment_id=e.id, variant_id=va.id, lead_id=lead.id)
    db_full.session.add(asg); db_full.session.commit()
    assert asg.status == "discovered"
    assert asg.score == 0


def test_icp_lead_assignment_lead_id_is_unique(app_full, db_full):
    """A lead can only be in one assignment, ever — keeps conversion math clean."""
    from sqlalchemy.exc import IntegrityError
    from src.models.marketing import ICPLeadAssignment
    e, va, vb, account = _make_experiment_with_variants(db_full)
    lead = _make_lead(db_full, account.id)
    db_full.session.add(ICPLeadAssignment(experiment_id=e.id, variant_id=va.id, lead_id=lead.id))
    db_full.session.commit()
    db_full.session.add(ICPLeadAssignment(experiment_id=e.id, variant_id=vb.id, lead_id=lead.id))
    with pytest.raises(IntegrityError):
        db_full.session.commit()
    db_full.session.rollback()


def test_icp_lead_assignment_cascade_delete_with_experiment(app_full, db_full):
    from src.models.marketing import ICPExperiment, ICPLeadAssignment
    e, va, _, account = _make_experiment_with_variants(db_full)
    lead = _make_lead(db_full, account.id)
    db_full.session.add(ICPLeadAssignment(experiment_id=e.id, variant_id=va.id, lead_id=lead.id))
    db_full.session.commit()
    assert ICPLeadAssignment.query.count() == 1
    db_full.session.delete(e); db_full.session.commit()
    assert ICPLeadAssignment.query.count() == 0
