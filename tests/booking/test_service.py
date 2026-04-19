import sys
import types
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone


def _make_token(app, account_id=1, ticket_id="t1"):
    from src.booking.tokens import make_booking_token
    with app.app_context():
        return make_booking_token({
            "account_id": account_id, "ticket_id": ticket_id,
            "subject": "Demo request", "requester_email": "r@acme.com",
            "requester_name": "Rachel", "duration_minutes": 30,
        })


def test_generate_booking_creates_pending_row_and_returns_url(app):
    from src.booking.service import generate_booking

    mock_flags = MagicMock()
    mock_flags.booking_duration_minutes = 30

    with app.app_context():
        with patch("src.booking.service.AccountFeatureFlags") as MockFlags, \
             patch("src.booking.service.db") as mock_db:
            MockFlags.query.filter_by.return_value.first.return_value = mock_flags
            mock_db.session = MagicMock()
            url = generate_booking(
                account_id=1, ticket_id="ticket-abc",
                subject="Demo request", requester_email="rachel@acme.com",
                requester_name="Rachel",
            )

    assert url.startswith("https://kalevent.com/book/")
    booking_arg = mock_db.session.add.call_args[0][0]
    assert booking_arg.status == "pending"
    assert booking_arg.ticket_id == "ticket-abc"
    assert booking_arg.requester_email == "rachel@acme.com"
    assert booking_arg.duration_minutes == 30
    mock_db.session.commit.assert_called_once()


def test_generate_booking_uses_default_duration_when_no_flags(app):
    from src.booking.service import generate_booking

    with app.app_context():
        with patch("src.booking.service.AccountFeatureFlags") as MockFlags, \
             patch("src.booking.service.db") as mock_db:
            MockFlags.query.filter_by.return_value.first.return_value = None
            mock_db.session = MagicMock()
            url = generate_booking(
                account_id=1, ticket_id="t1", subject="hi",
                requester_email="a@b.com", requester_name="",
            )
    booking_arg = mock_db.session.add.call_args[0][0]
    assert booking_arg.duration_minutes == 30


def test_confirm_booking_invalid_token_raises(app):
    from src.booking.service import confirm_booking

    with app.app_context():
        with pytest.raises(ValueError, match="invalid_or_expired_token"):
            confirm_booking(
                token="not.a.valid.token",
                slot_start_iso="2026-04-21T10:00:00Z",
                booked_by_name="Rachel",
                booked_by_email="r@acme.com",
            )


def test_confirm_booking_already_confirmed_raises(app):
    from src.booking.service import confirm_booking
    from src.booking.tokens import token_to_hash

    token = _make_token(app)
    mock_booking = MagicMock()
    mock_booking.status = "confirmed"

    with app.app_context():
        with patch("src.booking.service.Booking") as MockBooking:
            MockBooking.query.filter_by.return_value.first.return_value = mock_booking
            with pytest.raises(ValueError, match="booking_already_confirmed"):
                confirm_booking(
                    token=token,
                    slot_start_iso="2026-04-21T10:00:00Z",
                    booked_by_name="Rachel",
                    booked_by_email="r@acme.com",
                )


def test_confirm_booking_success(app):
    from src.booking.service import confirm_booking

    token = _make_token(app)

    mock_booking = MagicMock()
    mock_booking.status = "pending"
    mock_booking.duration_minutes = 30
    mock_booking.account_id = 1
    mock_booking.ticket_id = "t1"
    mock_booking.subject = "Demo"

    mock_event = {"event_id": "evt123", "meet_link": "https://meet.google.com/x", "html_link": ""}

    # Inject a stub tasks module so the lazy import in confirm_booking resolves
    mock_task = MagicMock()
    fake_tasks = types.ModuleType("src.booking.tasks")
    fake_tasks.send_booking_confirmation_reply = mock_task
    sys.modules["src.booking.tasks"] = fake_tasks

    try:
        with app.app_context():
            with patch("src.booking.service.Booking") as MockBooking:
                MockBooking.query.filter_by.return_value.first.return_value = mock_booking
                with patch("src.booking.service._detect_provider", return_value="gcal"):
                    with patch("src.booking.service.create_calendar_event", return_value=mock_event):
                        with patch("src.booking.service.db") as mock_db:
                            mock_db.session = MagicMock()
                            mock_db.session.get.return_value = None  # no ticket
                            result = confirm_booking(
                                token=token,
                                slot_start_iso="2026-04-21T10:00:00Z",
                                booked_by_name="Rachel",
                                booked_by_email="r@acme.com",
                            )
    finally:
        sys.modules.pop("src.booking.tasks", None)

    assert mock_booking.status == "confirmed"
    assert mock_booking.meet_link == "https://meet.google.com/x"
    assert mock_booking.booked_by_name == "Rachel"
    mock_db.session.commit.assert_called_once()
    mock_task.delay.assert_called_once()
