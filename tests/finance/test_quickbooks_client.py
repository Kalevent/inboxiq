import pytest
from unittest.mock import patch, Mock
from src.integrations.quickbooks import QuickBooksClient


def _make_client(sandbox=True):
    return QuickBooksClient(
        realm_id="123456",
        access_token="tok_access",
        refresh_token="tok_refresh",
        client_id="client_id_xxx",
        client_secret="client_secret_xxx",
        sandbox=sandbox,
    )


def test_base_url_sandbox():
    client = _make_client(sandbox=True)
    assert "sandbox" in client.base_url


def test_base_url_production():
    client = _make_client(sandbox=False)
    assert "sandbox" not in client.base_url


def test_find_customer_found():
    client = _make_client()
    mock_resp = Mock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "QueryResponse": {
            "Customer": [{"Id": "42", "DisplayName": "John Doe"}]
        }
    }
    with patch("requests.get", return_value=mock_resp):
        customer_id = client.find_customer_by_email("john@example.com")
    assert customer_id == "42"


def test_find_customer_not_found():
    client = _make_client()
    mock_resp = Mock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"QueryResponse": {}}
    with patch("requests.get", return_value=mock_resp):
        customer_id = client.find_customer_by_email("nobody@example.com")
    assert customer_id is None


def test_create_customer():
    client = _make_client()
    mock_resp = Mock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"Customer": {"Id": "99", "DisplayName": "Jane"}}
    with patch("requests.post", return_value=mock_resp):
        customer_id = client.create_customer(name="Jane", email="jane@example.com")
    assert customer_id == "99"


def test_create_sales_receipt():
    client = _make_client()
    mock_resp = Mock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "SalesReceipt": {"Id": "SR-1", "TotalAmt": 50.00}
    }
    with patch("requests.post", return_value=mock_resp):
        result = client.create_sales_receipt(
            customer_id="42",
            amount_cents=5000,
            currency="GBP",
            description="Stripe payment",
        )
    assert result["SalesReceipt"]["Id"] == "SR-1"


def test_refresh_token():
    client = _make_client()
    mock_resp = Mock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "access_token": "new_access",
        "refresh_token": "new_refresh",
    }
    with patch("requests.post", return_value=mock_resp):
        new_access, new_refresh = client.refresh_access_token()
    assert new_access == "new_access"
    assert new_refresh == "new_refresh"
