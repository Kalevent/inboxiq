"""Tests for _fetch_admin_organization_id and _resolve_org_id helpers in src/social_auth/routes.py."""
from unittest.mock import MagicMock

import requests as http


def test_fetch_admin_organization_id_returns_first_admin_org(monkeypatch):
    """The helper should return the numeric ID of the first ADMINISTRATOR org."""
    from src.social_auth.routes import _fetch_admin_organization_id

    captured = {}

    def fake_get(url, params, headers, timeout):
        captured["url"] = url
        captured["params"] = params
        captured["headers"] = headers
        resp = MagicMock()
        resp.raise_for_status = lambda: None
        resp.json = lambda: {"elements": [
            {"organizationalTarget": "urn:li:organization:999"},
            {"organizationalTarget": "urn:li:organization:888"},
        ]}
        return resp

    monkeypatch.setattr(http, "get", fake_get)

    org_id = _fetch_admin_organization_id("TOKEN")
    assert org_id == "999"
    assert captured["url"] == "https://api.linkedin.com/v2/organizationAcls"
    assert captured["params"]["role"] == "ADMINISTRATOR"
    assert captured["headers"]["Authorization"] == "Bearer TOKEN"


def test_fetch_admin_organization_id_returns_none_on_empty(monkeypatch):
    """An empty elements list should yield None."""
    from src.social_auth.routes import _fetch_admin_organization_id

    def fake_get(url, params, headers, timeout):
        resp = MagicMock()
        resp.raise_for_status = lambda: None
        resp.json = lambda: {"elements": []}
        return resp

    monkeypatch.setattr(http, "get", fake_get)

    assert _fetch_admin_organization_id("TOKEN") is None


def test_fetch_admin_organization_id_returns_none_on_exception(monkeypatch):
    """Any exception (network error, HTTP error, etc.) should yield None."""
    from src.social_auth.routes import _fetch_admin_organization_id

    def fake_get(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(http, "get", fake_get)

    assert _fetch_admin_organization_id("TOKEN") is None


# ── _resolve_org_id tests ─────────────────────────────────────────────────────

def test_resolve_org_id_uses_fresh_when_present(app, db, kalevent_account):
    """When a fresh org_id is available it should be returned as-is."""
    from src.social_auth.routes import _resolve_org_id

    assert _resolve_org_id(account_id=2, fresh_org_id="999") == "999"


def test_resolve_org_id_preserves_existing_when_fresh_is_none(app, db, kalevent_account):
    """When the new fetch fails (returns None), the previously-persisted org_id must survive."""
    from src.models.core import InboxConnection
    from src.social_auth.routes import _resolve_org_id

    db.session.add(InboxConnection(
        id="li-x",
        account_id=2,
        user_id=1,
        provider="linkedin_social",
        status="connected",
        metadata_json={"org_id": "555"},
    ))
    db.session.commit()

    assert _resolve_org_id(account_id=2, fresh_org_id=None) == "555"


def test_resolve_org_id_returns_none_when_neither_present(app, db, kalevent_account):
    """With no fresh value and no prior connection, None should be returned."""
    from src.social_auth.routes import _resolve_org_id

    # kalevent_account exists (account_id=2) but there is no linkedin_social connection
    assert _resolve_org_id(account_id=2, fresh_org_id=None) is None
