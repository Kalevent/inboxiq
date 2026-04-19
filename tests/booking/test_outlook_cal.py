import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime


def test_create_meeting_raises_when_not_connected(app):
    from src.integrations.outlook_cal import create_meeting

    with app.app_context():
        with patch("src.integrations.outlook_cal.InboxConnection") as MockConn:
            MockConn.query.filter_by.return_value.first.return_value = None
            with pytest.raises(RuntimeError, match="not connected"):
                create_meeting(
                    account_id=1,
                    title="Demo",
                    start_dt=datetime(2026, 4, 21, 10, 0),
                    end_dt=datetime(2026, 4, 21, 10, 30),
                    attendee_email="r@a.com",
                    attendee_name="Rachel",
                )


def test_create_meeting_returns_event_id_and_meet_link(app):
    from src.integrations.outlook_cal import create_meeting

    mock_conn = MagicMock()
    mock_conn.metadata_json = {"access_token_enc": "encrypted"}

    mock_response = MagicMock()
    mock_response.status_code = 201
    mock_response.json.return_value = {
        "id": "AAMkABC123",
        "webLink": "https://outlook.office.com/calendar/item/AAMkABC123",
        "onlineMeeting": {"joinUrl": "https://teams.microsoft.com/l/meetup-join/abc"},
    }

    with app.app_context():
        with patch("src.integrations.outlook_cal.InboxConnection") as MockConn:
            MockConn.query.filter_by.return_value.first.return_value = mock_conn
            with patch("src.integrations.outlook_cal.decrypt_value", return_value="valid_token"):
                with patch("src.integrations.outlook_cal.http.post", return_value=mock_response):
                    result = create_meeting(
                        account_id=1,
                        title="Demo",
                        start_dt=datetime(2026, 4, 21, 10, 0),
                        end_dt=datetime(2026, 4, 21, 10, 30),
                        attendee_email="r@a.com",
                        attendee_name="Rachel",
                    )

    assert result["event_id"] == "AAMkABC123"
    assert result["meet_link"] == "https://teams.microsoft.com/l/meetup-join/abc"
    assert "html_link" in result


def test_create_meeting_raises_on_api_error(app):
    from src.integrations.outlook_cal import create_meeting

    mock_conn = MagicMock()
    mock_conn.metadata_json = {"access_token_enc": "enc"}

    mock_response = MagicMock()
    mock_response.status_code = 403
    mock_response.text = "Forbidden"

    with app.app_context():
        with patch("src.integrations.outlook_cal.InboxConnection") as MockConn:
            MockConn.query.filter_by.return_value.first.return_value = mock_conn
            with patch("src.integrations.outlook_cal.decrypt_value", return_value="tok"):
                with patch("src.integrations.outlook_cal.http.post", return_value=mock_response):
                    with pytest.raises(RuntimeError, match="403"):
                        create_meeting(
                            account_id=1, title="x",
                            start_dt=datetime(2026, 4, 21, 10, 0),
                            end_dt=datetime(2026, 4, 21, 10, 30),
                            attendee_email="a@b.com", attendee_name="A",
                        )
