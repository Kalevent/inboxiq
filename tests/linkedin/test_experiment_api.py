"""Tests for /api/v1/linkedin/experiments REST endpoints (read-only)."""
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone

import pytest


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture(autouse=True)
def auth_bypass():
    """Patch JWT auth so all requests pass login_required_settings.
    Mirrors the pattern used in tests/youtube/test_youtube_api.py."""
    mock_user = MagicMock()
    mock_user.id = 1
    with (
        patch("src.settings.verify_jwt_in_request"),
        patch("src.settings.get_jwt", return_value={"account_id": 2}),
        patch("src.settings.get_jwt_identity", return_value="1"),
        patch("src.settings.account_allows_api", return_value=True),
        patch("src.extensions.db.session.get", return_value=mock_user),
    ):
        yield


def test_get_experiments_returns_account_experiments(client, app, db):
    from src.models.marketing import ICPExperiment

    with app.app_context():
        exp = ICPExperiment(
            id="exp-1",
            account_id=2,
            name="Founder vs Co-founder",
            status="running",
            traffic_split={"A": 50, "B": 50},
        )
        # Other-account experiment to confirm scoping
        exp_other = ICPExperiment(
            id="exp-other",
            account_id=99,
            name="Other account",
            status="running",
            traffic_split={"A": 50, "B": 50},
        )
        db.session.add_all([exp, exp_other])
        db.session.commit()

    resp = client.get("/api/v1/linkedin/experiments")
    assert resp.status_code == 200, resp.get_data(as_text=True)
    data = resp.get_json()
    assert "experiments" in data
    ids = [e["id"] for e in data["experiments"]]
    assert "exp-1" in ids
    assert "exp-other" not in ids
    summary = next(e for e in data["experiments"] if e["id"] == "exp-1")
    assert summary["name"] == "Founder vs Co-founder"
    assert summary["status"] == "running"
    assert summary["traffic_split"] == {"A": 50, "B": 50}
    assert summary["winner_variant"] is None


def test_get_experiment_includes_variants_and_metrics(client, app, db):
    from src.models.marketing import ICPExperiment, ICPVariant

    with app.app_context():
        exp = ICPExperiment(
            id="exp-1",
            account_id=2,
            name="x",
            status="running",
            traffic_split={"A": 50, "B": 50},
        )
        va = ICPVariant(
            id="va",
            experiment_id="exp-1",
            label="A",
            titles=["Founder"],
            industries=["B2B SaaS"],
            geographies=["UK"],
            company_size_min=10,
            company_size_max=50,
        )
        vb = ICPVariant(
            id="vb",
            experiment_id="exp-1",
            label="B",
            titles=["Co-founder"],
            industries=["B2B SaaS"],
            geographies=["UK"],
            company_size_min=10,
            company_size_max=50,
        )
        db.session.add_all([exp, va, vb])
        db.session.commit()

    fake_metrics = {
        "A": {"discovered": 10, "connected": 5, "replied": 1, "booked": 0, "conversion_pct": 1.0},
        "B": {"discovered": 8, "connected": 4, "replied": 2, "booked": 1, "conversion_pct": 2.5},
        "current_leader": "B",
        "lead_margin_pct": 1.5,
    }
    with patch("src.api.v1.linkedin.compute_experiment_metrics", return_value=fake_metrics):
        resp = client.get("/api/v1/linkedin/experiments/exp-1")

    assert resp.status_code == 200, resp.get_data(as_text=True)
    data = resp.get_json()
    assert data["id"] == "exp-1"
    assert len(data["variants"]) == 2
    labels = sorted(v["label"] for v in data["variants"])
    assert labels == ["A", "B"]
    a_variant = next(v for v in data["variants"] if v["label"] == "A")
    assert a_variant["titles"] == ["Founder"]
    assert a_variant["industries"] == ["B2B SaaS"]
    assert a_variant["company_size_min"] == 10
    assert data["metrics"]["current_leader"] == "B"
    assert data["metrics"]["lead_margin_pct"] == 1.5


def test_get_experiment_returns_404_for_unknown_id(client, app):
    # No row exists / wrong account — both should produce 404.
    resp = client.get("/api/v1/linkedin/experiments/exp-missing")
    assert resp.status_code == 404


def test_get_experiment_returns_404_for_other_account(client, app, db):
    """Cross-account access must 404 (not 403) so we don't leak existence."""
    from src.models.marketing import ICPExperiment

    with app.app_context():
        exp = ICPExperiment(
            id="exp-other",
            account_id=99,
            name="Other account experiment",
            status="running",
            traffic_split={"A": 50, "B": 50},
        )
        db.session.add(exp)
        db.session.commit()

    resp = client.get("/api/v1/linkedin/experiments/exp-other")
    assert resp.status_code == 404
