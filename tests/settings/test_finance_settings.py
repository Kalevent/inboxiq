# tests/settings/test_finance_settings.py
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


def _mock_user(email="owner@example.com"):
    u = MagicMock()
    u.id = 1
    u.email = email
    return u


def _mock_account(email="owner@example.com"):
    acct = MagicMock()
    acct.id = 1
    acct.email = email
    acct.seats_limit = 5
    return acct


def _mock_provider(provider_id, name, ptype):
    p = MagicMock()
    p.id = provider_id
    p.configuration_name = name
    p.provider_type = ptype
    return p


def test_finance_settings_upgrade_gate(client):
    """Non-subscribed user sees upgrade gate (finance_addon_active=False)."""
    mock_account = _mock_account()
    mock_user = _mock_user()
    with patch("src.settings.verify_jwt_in_request"), \
         patch("src.settings.get_jwt", return_value={"account_id": "1"}), \
         patch("src.settings.get_jwt_identity", return_value="1"), \
         patch("src.settings.db") as mock_db, \
         patch("src.settings.account_allows_api", return_value=True), \
         patch("src.settings.routes.account_allows_api", return_value=True), \
         patch("src.settings.routes.Account") as MockAccount, \
         patch("src.settings.routes.User") as MockUser, \
         patch("src.settings.routes.AccountAddOn") as MockAddon, \
         patch("src.settings.routes.WebhookProvider") as MockWP:
        mock_db.session.get.return_value = mock_user
        MockAccount.query.get.return_value = mock_account
        MockUser.query.filter_by.return_value.first.return_value = mock_user
        MockAddon.query.filter_by.return_value.first.return_value = None
        MockWP.query.filter_by.return_value.all.return_value = []
        resp = client.get("/integrations/finance")
    assert resp.status_code == 200
    assert b"Upgrade to unlock" in resp.data


def test_finance_settings_active_summary(client):
    """Subscribed user sees active summary (finance_addon_active=True)."""
    mock_account = _mock_account()
    mock_user = _mock_user()
    mock_addon = MagicMock()
    mock_addon.status = "active"
    mock_addon.transactions_this_month = 12
    mock_addon.config_json = {"mode": "csv_export", "stripe_provider_id": "prov-1", "csv_email": "owner@example.com"}
    with patch("src.settings.verify_jwt_in_request"), \
         patch("src.settings.get_jwt", return_value={"account_id": "1"}), \
         patch("src.settings.get_jwt_identity", return_value="1"), \
         patch("src.settings.db") as mock_db, \
         patch("src.settings.account_allows_api", return_value=True), \
         patch("src.settings.routes.account_allows_api", return_value=True), \
         patch("src.settings.routes.Account") as MockAccount, \
         patch("src.settings.routes.User") as MockUser, \
         patch("src.settings.routes.AccountAddOn") as MockAddon, \
         patch("src.settings.routes.WebhookProvider") as MockWP:
        mock_db.session.get.return_value = mock_user
        MockAccount.query.get.return_value = mock_account
        MockUser.query.filter_by.return_value.first.return_value = mock_user
        MockAddon.query.filter_by.return_value.first.return_value = mock_addon
        MockWP.query.filter_by.return_value.all.return_value = []
        resp = client.get("/integrations/finance")
    assert resp.status_code == 200
    assert b"Finance Add-on \xc2\xb7 Active" in resp.data or b"Finance Add-on" in resp.data


def test_finance_settings_passes_providers(client):
    """Stripe and QB providers are rendered in the wizard dropdowns."""
    mock_account = _mock_account()
    mock_user = _mock_user()
    mock_addon = MagicMock()
    mock_addon.status = "active"
    mock_addon.transactions_this_month = 5
    mock_addon.config_json = {"mode": "direct_sync", "stripe_provider_id": "prov-s", "qb_provider_id": "prov-q"}

    stripe_prov = _mock_provider("prov-s", "My Stripe (production)", "stripe")
    qb_prov = _mock_provider("prov-q", "QuickBooks Online", "quickbooks")

    with patch("src.settings.verify_jwt_in_request"), \
         patch("src.settings.get_jwt", return_value={"account_id": "1"}), \
         patch("src.settings.get_jwt_identity", return_value="1"), \
         patch("src.settings.db") as mock_db, \
         patch("src.settings.account_allows_api", return_value=True), \
         patch("src.settings.routes.account_allows_api", return_value=True), \
         patch("src.settings.routes.Account") as MockAccount, \
         patch("src.settings.routes.User") as MockUser, \
         patch("src.settings.routes.AccountAddOn") as MockAddon, \
         patch("src.settings.routes.WebhookProvider") as MockWP:
        mock_db.session.get.return_value = mock_user
        MockAccount.query.get.return_value = mock_account
        MockUser.query.filter_by.return_value.first.return_value = mock_user
        MockAddon.query.filter_by.return_value.first.return_value = mock_addon
        results_map = {"stripe": [stripe_prov], "quickbooks": [qb_prov]}
        def fb(**kw):
            m = MagicMock()
            m.all.return_value = results_map.get(kw.get("provider_type"), [])
            return m
        MockWP.query.filter_by.side_effect = fb
        resp = client.get("/integrations/finance")
    assert resp.status_code == 200
    assert b"My Stripe (production)" in resp.data
    assert b"QuickBooks Online" in resp.data
