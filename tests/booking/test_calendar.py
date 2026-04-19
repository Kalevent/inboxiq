from datetime import datetime, timezone
from unittest.mock import MagicMock, patch


def test_get_available_slots_gcal_returns_list(app):
    from src.booking.calendar import get_available_slots

    mock_service = MagicMock()
    mock_service.freebusy().query().execute.return_value = {
        "calendars": {"primary": {"busy": []}}
    }
    with app.app_context():
        with patch("src.booking.calendar.get_gcal_service",return_value=mock_service):
            slots = get_available_slots(account_id=1, duration_minutes=30, provider="gcal")

    assert isinstance(slots, list)
    assert len(slots) > 0
    for s in slots:
        assert "start" in s
        assert "end" in s
        assert "label" in s
        assert s["start"].endswith("Z")


def test_get_available_slots_returns_empty_when_no_service(app):
    from src.booking.calendar import get_available_slots

    with app.app_context():
        with patch("src.booking.calendar.get_gcal_service",return_value=None):
            slots = get_available_slots(account_id=1, duration_minutes=30, provider="gcal")
    assert slots == []


def test_get_available_slots_unknown_provider_returns_empty(app):
    from src.booking.calendar import get_available_slots

    with app.app_context():
        slots = get_available_slots(account_id=1, duration_minutes=30, provider="unknown")
    assert slots == []


def test_create_gcal_event_returns_event_id_and_meet_link(app):
    from src.booking.calendar import create_gcal_event

    mock_service = MagicMock()
    mock_service.events().insert().execute.return_value = {
        "id": "evt_abc123",
        "htmlLink": "https://calendar.google.com/event?id=evt_abc123",
        "conferenceData": {
            "entryPoints": [
                {"entryPointType": "video", "uri": "https://meet.google.com/abc-def-ghi"}
            ]
        }
    }
    start = datetime(2026, 4, 21, 10, 0)
    end = datetime(2026, 4, 21, 10, 30)

    with app.app_context():
        with patch("src.booking.calendar.get_gcal_service",return_value=mock_service):
            result = create_gcal_event(
                account_id=1,
                summary="Demo call",
                start_dt=start,
                end_dt=end,
                attendee_email="rachel@acme.com",
                attendee_name="Rachel",
            )

    assert result["event_id"] == "evt_abc123"
    assert result["meet_link"] == "https://meet.google.com/abc-def-ghi"
    assert "html_link" in result


def test_create_gcal_event_raises_when_no_service(app):
    from src.booking.calendar import create_gcal_event
    import pytest

    with app.app_context():
        with patch("src.booking.calendar.get_gcal_service",return_value=None):
            with pytest.raises(RuntimeError, match="not connected"):
                create_gcal_event(
                    account_id=1, summary="x",
                    start_dt=datetime(2026, 4, 21, 10, 0),
                    end_dt=datetime(2026, 4, 21, 10, 30),
                    attendee_email="a@b.com", attendee_name="A",
                )


def test_slots_respect_busy_times(app):
    from src.booking.calendar import _compute_slots
    from datetime import timedelta

    now_day = datetime(2026, 4, 21, 9, 0)  # a weekday
    # Mark 9:00-17:00 as busy on day 1
    busy = [{"start": "2026-04-22T09:00:00Z", "end": "2026-04-22T17:00:00Z"}]
    slots = _compute_slots(busy, duration_minutes=30, days_ahead=2)
    # All returned slots should not overlap the busy range
    busy_start = datetime(2026, 4, 22, 9, 0)
    busy_end = datetime(2026, 4, 22, 17, 0)
    for s in slots:
        slot_dt = datetime.fromisoformat(s["start"].replace("Z", ""))
        assert not (slot_dt >= busy_start and slot_dt < busy_end)
