# tests/finance/test_addons_api.py
import pytest
import json
from unittest.mock import patch


def test_get_addon_status_not_active(client, auth_headers):
    resp = client.get("/api/v1/addons/finance", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["addon_type"] == "finance"
    assert data["status"] == "inactive"


def test_activate_addon(client, auth_headers, app):
    payload = {
        "mode": "csv_export",
        "stripe_provider_id": "prov-123",
        "csv_email": "accounting@example.com",
    }
    resp = client.post(
        "/api/v1/addons/finance/activate",
        headers=auth_headers,
        data=json.dumps(payload),
        content_type="application/json",
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "active"
    assert data["config_json"]["mode"] == "csv_export"
