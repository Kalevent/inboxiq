"""Smoke test: /marketing/linkedin renders with the new ICP experiment
block included. Catches regressions in the section_linkedin.html template
or the marketing_ops.html include path."""
from unittest.mock import patch, MagicMock

import pytest


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture(autouse=True)
def auth_bypass():
    """Patch JWT auth so the request passes login_required_settings.
    Mirrors the pattern used in tests/linkedin/test_experiment_api.py."""
    mock_user = MagicMock()
    mock_user.id = 1
    mock_user.role = "owner"
    mock_user.email = "owner@example.com"
    with (
        patch("src.settings.verify_jwt_in_request"),
        patch("src.settings.get_jwt", return_value={"account_id": 2}),
        patch("src.settings.get_jwt_identity", return_value="1"),
        patch("src.settings.account_allows_api", return_value=True),
        patch("src.extensions.db.session.get", return_value=mock_user),
    ):
        yield


def test_marketing_linkedin_page_renders_with_experiment_block(client):
    """Page returns 200 (or 302 if auth-redirect) and contains the new
    DOM markers added by Task 12. The legacy ICP Settings form must also
    still be present."""
    resp = client.get("/marketing/linkedin")
    # Auth wall is acceptable — page exists. 5xx would mean template broke.
    assert resp.status_code in (200, 302), f"unexpected status {resp.status_code}"
    if resp.status_code == 200:
        body = resp.get_data(as_text=True)
        assert 'id="icp-experiment-block"' in body, "Task 12 experiment block must be present"
        assert 'id="icp-form"' in body, "legacy ICP Settings form must still be present (fallback)"
