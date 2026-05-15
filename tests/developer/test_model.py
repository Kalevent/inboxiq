# tests/developer/test_model.py


def test_app_product_access_has_expected_columns():
    from src.models.developer import AppProductAccess
    cols = {c.key for c in AppProductAccess.__table__.columns}
    assert "app_id" in cols
    assert "account_id" in cols
    assert "product_slug" in cols
    assert "status" in cols
    assert "webhook_url" in cols
    assert "use_case" in cols
    assert "requested_at" in cols
    assert "approved_at" in cols


def test_app_product_access_unique_constraint_exists():
    from src.models.developer import AppProductAccess
    constraint_names = {c.name for c in AppProductAccess.__table__.constraints}
    assert "uq_app_product" in constraint_names


def test_app_product_access_default_status_is_pending():
    from src.models.developer import AppProductAccess
    status_col = AppProductAccess.__table__.columns["status"]
    assert status_col.default.arg == "pending"


def test_product_catalog_has_chat_forms_intake():
    from src.developer.products import PRODUCT_CATALOG
    slugs = {p["slug"] for p in PRODUCT_CATALOG}
    assert "chat" in slugs
    assert "forms" in slugs
    assert "intake_api" in slugs


def test_get_product_by_slug_returns_correct_product():
    from src.developer.products import get_product_by_slug
    p = get_product_by_slug("chat")
    assert p is not None
    assert p["name"] == "Chat / Aria Widget"
    assert p["approval"] == "reviewed"


def test_get_product_by_slug_returns_none_for_unknown():
    from src.developer.products import get_product_by_slug
    assert get_product_by_slug("nonexistent") is None


def test_intake_api_is_auto_approved():
    from src.developer.products import get_product_by_slug
    p = get_product_by_slug("intake_api")
    assert p["approval"] == "auto"


def test_registered_app_has_allowed_origins_column():
    from src.models.developer import RegisteredApp
    app = RegisteredApp(
        account_id=1,
        name="Test",
        client_id="iq_test",
        client_secret_enc="enc",
        scopes=[],
        allowed_ips=[],
        allowed_origins=[],
    )
    assert app.allowed_origins == []
    app.allowed_origins = ["https://example.com"]
    assert app.allowed_origins == ["https://example.com"]
