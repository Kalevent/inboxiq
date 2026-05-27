# tests/developer/test_origin_check.py
import pytest
from unittest.mock import patch, MagicMock


def _make_app(allowed_origins=None, status="active"):
    app = MagicMock()
    app.id = "app-1"
    app.account_id = 1
    app.status = status
    app.allowed_origins = allowed_origins or []
    return app


def _make_access(product_slug="chat", status="approved"):
    acc = MagicMock()
    acc.product_slug = product_slug
    acc.status = status
    return acc


@pytest.fixture(scope="module")
def flask_app():
    from src.app import create_app
    a = create_app()
    a.config["TESTING"] = True
    return a


@pytest.fixture
def client(flask_app):
    return flask_app.test_client()


def _post_chat(client, client_id=None, origin=None):
    headers = {"Content-Type": "application/json"}
    if origin:
        headers["Origin"] = origin
    payload = {"body": "hello", "context": {"account_id": "1"}}
    if client_id:
        payload["context"]["client_id"] = client_id
    return client.post("/api/v1/chat/submit", json=payload, headers=headers)


def test_no_client_id_skips_origin_check(client):
    """Requests without client_id are never blocked (legacy behaviour)."""
    with patch("src.api.v1.intake.RegisteredApp") as MockApp, \
         patch("src.api.v1.intake.AppProductAccess"), \
         patch("src.features.feature_enabled", return_value=True), \
         patch("src.billing.quota.check_and_increment"), \
         patch("src.billing.quota.increment_signals"):
        MockApp.query.filter_by.return_value.first.return_value = None
        resp = _post_chat(client, client_id=None, origin="https://evil.com")
    # May 200 or 400 (account not found in mock) but NOT 403
    assert resp.status_code != 403


def test_allowed_origins_empty_permits_any_origin(client):
    """When allowed_origins is [], any Origin is permitted."""
    mock_app = _make_app(allowed_origins=[])
    mock_access = _make_access()
    with patch("src.api.v1.intake.RegisteredApp") as MockApp, \
         patch("src.api.v1.intake.AppProductAccess") as MockAccess, \
         patch("src.features.feature_enabled", return_value=True), \
         patch("src.billing.quota.check_and_increment"), \
         patch("src.billing.quota.increment_signals"):
        MockApp.query.filter_by.return_value.first.return_value = mock_app
        MockAccess.query.filter_by.return_value.first.return_value = mock_access
        resp = _post_chat(client, client_id="iq_test", origin="https://anyone.com")
    assert resp.status_code != 403


def test_origin_not_in_allowlist_returns_403(client):
    """When allowed_origins is set, an unlisted Origin gets 403."""
    mock_app = _make_app(allowed_origins=["https://mysite.com"])
    mock_access = _make_access()
    with patch("src.api.v1.intake.RegisteredApp") as MockApp, \
         patch("src.api.v1.intake.AppProductAccess") as MockAccess:
        MockApp.query.filter_by.return_value.first.return_value = mock_app
        MockAccess.query.filter_by.return_value.first.return_value = mock_access
        resp = _post_chat(client, client_id="iq_test", origin="https://evil.com")
    assert resp.status_code == 403


def test_origin_in_allowlist_is_permitted(client):
    """When allowed_origins is set, a listed Origin is permitted."""
    mock_app = _make_app(allowed_origins=["https://mysite.com"])
    mock_access = _make_access()
    with patch("src.api.v1.intake.RegisteredApp") as MockApp, \
         patch("src.api.v1.intake.AppProductAccess") as MockAccess, \
         patch("src.features.feature_enabled", return_value=True), \
         patch("src.billing.quota.check_and_increment"), \
         patch("src.billing.quota.increment_signals"):
        MockApp.query.filter_by.return_value.first.return_value = mock_app
        MockAccess.query.filter_by.return_value.first.return_value = mock_access
        resp = _post_chat(client, client_id="iq_test", origin="https://mysite.com")
    assert resp.status_code != 403


def test_suspended_app_returns_403(client):
    """A suspended app cannot use the chat endpoint regardless of origin.

    The route queries RegisteredApp with status="active" — a suspended app
    won't match, so .first() returns None, triggering the invalid client_id 403.
    """
    with patch("src.api.v1.intake.RegisteredApp") as MockApp:
        # Suspended app: status="active" filter finds nothing
        MockApp.query.filter_by.return_value.first.return_value = None
        resp = _post_chat(client, client_id="iq_test", origin="https://mysite.com")
    assert resp.status_code == 403


def test_chat_product_not_approved_returns_403(client):
    """Even if client_id is valid, chat access must be approved.

    The route queries AppProductAccess with status="approved" — a pending row
    won't match, so .first() returns None, triggering the 403.
    """
    mock_app = _make_app(allowed_origins=[])
    with patch("src.api.v1.intake.RegisteredApp") as MockApp, \
         patch("src.api.v1.intake.AppProductAccess") as MockAccess:
        MockApp.query.filter_by.return_value.first.return_value = mock_app
        # Pending access: status="approved" filter finds nothing
        MockAccess.query.filter_by.return_value.first.return_value = None
        resp = _post_chat(client, client_id="iq_test", origin="https://mysite.com")
    assert resp.status_code == 403
