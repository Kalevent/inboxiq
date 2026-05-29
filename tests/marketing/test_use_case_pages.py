import pytest
import os

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("INBOXIQ_ENCRYPTION_KEY", "test-encryption-key-for-unit-tests")

from src.app import create_app


@pytest.fixture
def client():
    app = create_app()
    app.config["TESTING"] = True
    app.config["SECRET_KEY"] = "test"
    with app.test_client() as c:
        yield c


def test_it_incidents_returns_200(client):
    r = client.get("/use-cases/it-incidents")
    assert r.status_code == 200
    assert b"IT Incident Management" in r.data


def test_it_requests_returns_200(client):
    r = client.get("/use-cases/it-requests")
    assert r.status_code == 200
    assert b"IT" in r.data and b"Request" in r.data


def test_approvals_returns_200(client):
    r = client.get("/use-cases/approvals")
    assert r.status_code == 200
    assert b"Approval" in r.data


def test_it_incidents_has_competitor_names(client):
    r = client.get("/use-cases/it-incidents")
    assert b"Freshservice" in r.data
    assert b"ServiceNow" in r.data


def test_approvals_has_kissflow(client):
    r = client.get("/use-cases/approvals")
    assert b"Kissflow" in r.data


def test_it_requests_has_per_inbox_pricing(client):
    r = client.get("/use-cases/it-requests")
    assert b"per inbox" in r.data or b"per-inbox" in r.data or b"per connected inbox" in r.data
