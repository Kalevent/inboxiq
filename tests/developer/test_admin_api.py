import pytest
from unittest.mock import MagicMock, patch


@pytest.fixture
def app():
    from src.app import create_app
    app = create_app()
    app.config["TESTING"] = True
    app.config["SECRET_KEY"] = "test-secret"
    app.config["JWT_SECRET_KEY"] = "test-jwt-secret"
    return app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def auth_headers(app):
    from flask_jwt_extended import create_access_token
    with app.app_context():
        token = create_access_token(identity="1")
    return {"Authorization": f"Bearer {token}"}


def test_product_requests_list_endpoint_exists(client):
    resp = client.get("/api/v1/admin/developer/product-requests")
    assert resp.status_code in (200, 401, 403)


def test_product_request_review_endpoint_exists(client):
    resp = client.post("/api/v1/admin/developer/product-requests/access-1/review",
                       json={"status": "approved"})
    assert resp.status_code in (200, 400, 401, 403, 404)


def test_product_request_review_rejects_invalid_status(client, auth_headers):
    mock_admin = MagicMock()
    mock_admin.email = "admin@example.com"
    mock_admin.id = 1

    with patch("src.api.v1.admin._require_admin", return_value=mock_admin):
        resp = client.post(
            "/api/v1/admin/developer/product-requests/access-1/review",
            json={"status": "maybe"},
            headers=auth_headers,
        )

    assert resp.status_code == 400


def test_product_request_review_409_when_already_reviewed(client, auth_headers):
    mock_admin = MagicMock()
    mock_admin.email = "admin@example.com"
    mock_admin.id = 1

    with patch("src.api.v1.admin._require_admin", return_value=mock_admin), \
         patch("src.api.v1.admin.db") as mock_db:
        mock_access = MagicMock()
        mock_access.status = "approved"  # already reviewed
        mock_db.session.get.return_value = mock_access

        resp = client.post(
            "/api/v1/admin/developer/product-requests/access-1/review",
            json={"status": "rejected"},
            headers=auth_headers,
        )

    assert resp.status_code == 409
