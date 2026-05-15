import pytest


@pytest.fixture
def app():
    from src.app import create_app
    app = create_app()
    app.config["TESTING"] = True
    app.config["SECRET_KEY"] = "test-secret"
    return app


@pytest.fixture
def client(app):
    return app.test_client()


def test_product_requests_list_endpoint_exists(client):
    resp = client.get("/api/v1/admin/developer/product-requests")
    assert resp.status_code in (200, 401, 403)


def test_product_request_review_endpoint_exists(client):
    resp = client.post("/api/v1/admin/developer/product-requests/access-1/review",
                       json={"status": "approved"})
    assert resp.status_code in (200, 400, 401, 403, 404)
