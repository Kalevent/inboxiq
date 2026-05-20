# tests/marketing/test_comparison_pages.py
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


def test_vs_zendesk_returns_200(client):
    r = client.get("/vs/zendesk")
    assert r.status_code == 200
    assert b"InboxIQ vs Zendesk" in r.data


def test_vs_freshdesk_returns_200(client):
    r = client.get("/vs/freshdesk")
    assert r.status_code == 200


def test_vs_intercom_returns_200(client):
    r = client.get("/vs/intercom")
    assert r.status_code == 200


def test_vs_front_returns_200(client):
    r = client.get("/vs/front")
    assert r.status_code == 200


def test_vs_helpscout_returns_200(client):
    r = client.get("/vs/helpscout")
    assert r.status_code == 200


def test_vs_groove_returns_200(client):
    r = client.get("/vs/groove")
    assert r.status_code == 200


def test_vs_unknown_returns_404(client):
    r = client.get("/vs/somerandomplatform")
    assert r.status_code == 404


def test_vs_page_contains_faqpage_schema(client):
    r = client.get("/vs/zendesk")
    assert b"FAQPage" in r.data
    assert b"application/ld+json" in r.data


def test_vs_page_contains_geo_phrases(client):
    r = client.get("/vs/zendesk")
    assert b"AI email triage" in r.data
    assert b"works inside Gmail and Outlook" in r.data
    assert b"no new dashboard" in r.data
