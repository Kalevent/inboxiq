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
