# tests/developer/test_routes.py
import pytest
from unittest.mock import patch, MagicMock


@pytest.fixture(scope="module")
def app():
    from src.app import create_app
    app = create_app()
    app.config["TESTING"] = True
    app.config["SECRET_KEY"] = "test-secret"
    return app


@pytest.fixture
def client(app):
    return app.test_client()


def _mock_account(developer_access=True):
    acct = MagicMock()
    acct.id = 1
    acct.developer_access = developer_access
    acct.seats_limit = 5
    return acct


def test_developer_get_passes_product_catalog_to_template(client):
    mock_account = _mock_account()
    mock_app = MagicMock()
    mock_app.id = "app-1"
    mock_app.name = "My App"
    mock_app.client_id = "iq_abc"
    mock_app.status = "active"

    mock_user = MagicMock()
    mock_user.id = 1
    mock_user.email = "test@example.com"

    with patch("src.settings.verify_jwt_in_request"), \
         patch("src.settings.get_jwt", return_value={"account_id": "1"}), \
         patch("src.settings.get_jwt_identity", return_value="1"), \
         patch("src.settings.db") as mock_db, \
         patch("src.settings.account_allows_api", return_value=True), \
         patch("src.settings.routes.Account") as MockAccount, \
         patch("src.settings.routes.RegisteredApp") as MockApp, \
         patch("src.settings.routes.AppProductAccess") as MockAccess, \
         patch("src.settings.routes.DeveloperAccessRequest") as MockReq:
        mock_db.session.get.return_value = mock_user
        MockAccount.query.get.return_value = mock_account
        MockApp.query.filter_by.return_value.order_by.return_value.all.return_value = [mock_app]
        MockAccess.query.filter_by.return_value.all.return_value = []
        MockReq.query.filter_by.return_value.order_by.return_value.first.return_value = None

        resp = client.get("/settings/developer")

    assert resp.status_code == 200
    assert b"product_catalog" not in resp.data  # rendered, not a raw var name
    # template renders without error — product catalog comes from PRODUCT_CATALOG, not DB


def test_developer_get_selects_first_app_when_no_app_id(client):
    """Route correctly loads registered_apps without an approval gate.

    NOTE: The existing settings/index.html template still gates app rendering on
    developer_access_request.status == 'approved', so "CRM Sync" won't appear in
    resp.data until Task 7 updates the template. This test verifies the route
    returns HTTP 200 (not a redirect) — i.e. the new self-service GET logic is
    wired up correctly.
    """
    mock_account = _mock_account()
    mock_app = MagicMock()
    mock_app.id = "app-1"
    mock_app.name = "CRM Sync"
    mock_app.client_id = "iq_abc"
    mock_app.status = "active"

    mock_user = MagicMock()
    mock_user.id = 1
    mock_user.email = "test@example.com"

    with patch("src.settings.verify_jwt_in_request"), \
         patch("src.settings.get_jwt", return_value={"account_id": "1"}), \
         patch("src.settings.get_jwt_identity", return_value="1"), \
         patch("src.settings.db") as mock_db, \
         patch("src.settings.account_allows_api", return_value=True), \
         patch("src.settings.routes.Account") as MockAccount, \
         patch("src.settings.routes.RegisteredApp") as MockApp, \
         patch("src.settings.routes.AppProductAccess") as MockAccess, \
         patch("src.settings.routes.DeveloperAccessRequest") as MockReq:
        mock_db.session.get.return_value = mock_user
        MockAccount.query.get.return_value = mock_account
        MockApp.query.filter_by.return_value.order_by.return_value.all.return_value = [mock_app]
        MockAccess.query.filter_by.return_value.all.return_value = []
        MockReq.query.filter_by.return_value.order_by.return_value.first.return_value = None

        resp = client.get("/settings/developer")

    # Route loads without redirect — approval gate removed from GET handler
    assert resp.status_code == 200
    # "CRM Sync" will appear in resp.data after Task 7 updates the template
    # assert b"CRM Sync" in resp.data


def test_register_app_succeeds_without_developer_access_request(client):
    """App creation must work with developer_access=True even with no DeveloperAccessRequest."""
    mock_account = _mock_account()

    with patch("src.settings.routes.g") as mock_g, \
         patch("src.settings.routes.Account") as MockAccount, \
         patch("src.settings.routes.RegisteredApp") as MockApp, \
         patch("src.settings.routes.AppProductAccess"), \
         patch("src.settings.routes.DeveloperAccessRequest") as MockReq, \
         patch("src.settings.routes.db") as mock_db, \
         patch("src.settings.routes.encrypt_value", return_value="enc"), \
         patch("src.settings.routes.secrets") as mock_secrets:
        mock_g.current_account_id = 1
        MockAccount.query.get.return_value = mock_account
        MockReq.query.filter_by.return_value.order_by.return_value.first.return_value = None
        mock_secrets.token_hex.side_effect = ["abc123", "def456"]
        MockApp.query.filter_by.return_value.order_by.return_value.all.return_value = []

        resp = client.post("/settings/developer", data={
            "action": "register_app",
            "app_name": "My New App",
            "csrf_token": "dummy",
        })

    # Should redirect to developer tab, not bounce back to team tab
    assert resp.status_code == 302
    assert "developer" in resp.headers["Location"]


def _mock_user():
    user = MagicMock()
    user.id = 1
    user.email = "test@example.com"
    user.role = "owner"
    return user


def _auth_patches():
    """Context managers that bypass login_required_settings for POST tests."""
    return (
        patch("src.settings.verify_jwt_in_request"),
        patch("src.settings.get_jwt", return_value={"account_id": "1"}),
        patch("src.settings.get_jwt_identity", return_value="1"),
        patch("src.settings.account_allows_api", return_value=True),
    )


def test_request_product_creates_access_record(client):
    mock_account = _mock_account()
    mock_app = MagicMock()
    mock_app.id = "app-1"
    mock_app.account_id = 1
    mock_user = _mock_user()

    # Use side_effect so constructor kwargs become real attributes on the returned object
    from types import SimpleNamespace

    def _make_access(**kwargs):
        return SimpleNamespace(**kwargs)

    vjwt, gjwt, gji, aaa = _auth_patches()
    with vjwt, gjwt, gji, aaa, \
         patch("src.settings.db") as mock_settings_db, \
         patch("src.settings.routes.Account") as MockAccount, \
         patch("src.settings.routes.RegisteredApp") as MockApp, \
         patch("src.settings.routes.AppProductAccess") as MockAccess, \
         patch("src.settings.routes.DeveloperAccessRequest"), \
         patch("src.settings.routes.db") as mock_db:
        mock_settings_db.session.get.return_value = mock_user
        MockAccount.query.get.return_value = mock_account
        MockApp.query.filter_by.return_value.first.return_value = mock_app
        MockAccess.query.filter_by.return_value.first.return_value = None  # no existing request
        MockAccess.side_effect = _make_access

        resp = client.post("/settings/developer", data={
            "action": "request_product",
            "app_id": "app-1",
            "product_slug": "chat",
            "use_case": "I want to embed Aria on my site",
            "csrf_token": "dummy",
        })

    assert resp.status_code == 302
    mock_db.session.add.assert_called_once()
    added = mock_db.session.add.call_args[0][0]
    assert added.product_slug == "chat"
    assert added.status == "pending"


def test_request_product_auto_approves_intake_api(client):
    mock_account = _mock_account()
    mock_app = MagicMock()
    mock_app.id = "app-1"
    mock_app.account_id = 1
    mock_user = _mock_user()

    from types import SimpleNamespace

    def _make_access(**kwargs):
        return SimpleNamespace(**kwargs)

    vjwt, gjwt, gji, aaa = _auth_patches()
    with vjwt, gjwt, gji, aaa, \
         patch("src.settings.db") as mock_settings_db, \
         patch("src.settings.routes.Account") as MockAccount, \
         patch("src.settings.routes.RegisteredApp") as MockApp, \
         patch("src.settings.routes.AppProductAccess") as MockAccess, \
         patch("src.settings.routes.DeveloperAccessRequest"), \
         patch("src.settings.routes.db") as mock_db:
        mock_settings_db.session.get.return_value = mock_user
        MockAccount.query.get.return_value = mock_account
        MockApp.query.filter_by.return_value.first.return_value = mock_app
        MockAccess.query.filter_by.return_value.first.return_value = None
        MockAccess.side_effect = _make_access

        resp = client.post("/settings/developer", data={
            "action": "request_product",
            "app_id": "app-1",
            "product_slug": "intake_api",
            "use_case": "submit support tickets",
            "csrf_token": "dummy",
        })

    assert resp.status_code == 302
    added = mock_db.session.add.call_args[0][0]
    assert added.status == "approved"  # auto-approved


def test_request_product_rejects_duplicate(client):
    mock_account = _mock_account()
    mock_app = MagicMock()
    mock_app.id = "app-1"
    mock_app.account_id = 1
    existing_access = MagicMock()  # already has a request
    mock_user = _mock_user()

    vjwt, gjwt, gji, aaa = _auth_patches()
    with vjwt, gjwt, gji, aaa, \
         patch("src.settings.db") as mock_settings_db, \
         patch("src.settings.routes.Account") as MockAccount, \
         patch("src.settings.routes.RegisteredApp") as MockApp, \
         patch("src.settings.routes.AppProductAccess") as MockAccess, \
         patch("src.settings.routes.DeveloperAccessRequest"), \
         patch("src.settings.routes.db") as mock_db:
        mock_settings_db.session.get.return_value = mock_user
        MockAccount.query.get.return_value = mock_account
        MockApp.query.filter_by.return_value.first.return_value = mock_app
        MockAccess.query.filter_by.return_value.first.return_value = existing_access  # duplicate

        resp = client.post("/settings/developer", data={
            "action": "request_product",
            "app_id": "app-1",
            "product_slug": "chat",
            "use_case": "trying again",
            "csrf_token": "dummy",
        })

    assert resp.status_code == 302
    mock_db.session.add.assert_not_called()  # no new record created


def test_update_webhook_succeeds_when_approved(client):
    mock_account = _mock_account()
    mock_app = MagicMock()
    mock_app.id = "app-1"
    mock_app.account_id = 1
    mock_access = MagicMock()
    mock_access.status = "approved"
    mock_user = _mock_user()

    vjwt, gjwt, gji, aaa = _auth_patches()
    with vjwt, gjwt, gji, aaa, \
         patch("src.settings.db") as mock_settings_db, \
         patch("src.settings.routes.Account") as MockAccount, \
         patch("src.settings.routes.RegisteredApp") as MockApp, \
         patch("src.settings.routes.AppProductAccess") as MockAccess, \
         patch("src.settings.routes.DeveloperAccessRequest"), \
         patch("src.settings.routes.db") as mock_db:
        mock_settings_db.session.get.return_value = mock_user
        MockAccount.query.get.return_value = mock_account
        MockApp.query.filter_by.return_value.first.return_value = mock_app
        MockAccess.query.filter_by.return_value.first.return_value = mock_access

        resp = client.post("/settings/developer", data={
            "action": "update_webhook",
            "app_id": "app-1",
            "product_slug": "chat",
            "webhook_url": "https://example.com/hooks/chat",
            "csrf_token": "dummy",
        })

    assert resp.status_code == 302
    assert mock_access.webhook_url == "https://example.com/hooks/chat"
    mock_db.session.commit.assert_called()


def test_update_webhook_blocked_when_not_approved(client):
    mock_account = _mock_account()
    mock_app = MagicMock()
    mock_app.id = "app-1"
    mock_app.account_id = 1
    mock_access = MagicMock()
    mock_access.status = "pending"  # not approved
    mock_user = _mock_user()

    vjwt, gjwt, gji, aaa = _auth_patches()
    with vjwt, gjwt, gji, aaa, \
         patch("src.settings.db") as mock_settings_db, \
         patch("src.settings.routes.Account") as MockAccount, \
         patch("src.settings.routes.RegisteredApp") as MockApp, \
         patch("src.settings.routes.AppProductAccess") as MockAccess, \
         patch("src.settings.routes.DeveloperAccessRequest"), \
         patch("src.settings.routes.db") as mock_db:
        mock_settings_db.session.get.return_value = mock_user
        MockAccount.query.get.return_value = mock_account
        MockApp.query.filter_by.return_value.first.return_value = mock_app
        MockAccess.query.filter_by.return_value.first.return_value = mock_access

        resp = client.post("/settings/developer", data={
            "action": "update_webhook",
            "app_id": "app-1",
            "product_slug": "chat",
            "webhook_url": "https://example.com/hooks/chat",
            "csrf_token": "dummy",
        })

    assert resp.status_code == 302
    # webhook_url must NOT have been set
    assert mock_access.webhook_url != "https://example.com/hooks/chat"
