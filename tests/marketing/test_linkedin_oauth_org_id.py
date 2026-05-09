"""Tests for _fetch_admin_organization_id helper in src/social_auth/routes.py."""
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
