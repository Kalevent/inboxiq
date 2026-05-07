import pytest
from unittest.mock import patch, MagicMock


@pytest.fixture
def client(app):
    return app.test_client()


def test_get_book_invalid_token_returns_410(client):
    resp = client.get("/book/not-a-valid-token")
    assert resp.status_code == 410


def test_get_book_valid_token_returns_200(client, app):
    from src.booking.tokens import make_booking_token

    with app.app_context():
        token = make_booking_token({
            "account_id": 1, "ticket_id": "t1", "subject": "Demo",
            "requester_email": "r@a.com", "requester_name": "Rachel", "duration_minutes": 30,
        })

    with patch("src.booking.routes.Booking") as MockBooking, \
         patch("src.booking.routes.get_available_slots", return_value=[]), \
         patch("src.booking.routes.Account") as MockAccount, \
         patch("src.booking.routes._detect_provider", return_value=None):
        MockBooking.query.filter_by.return_value.first.return_value = None
        MockAccount.query.get.return_value = MagicMock(name="Acme")
        resp = client.get(f"/book/{token}")
    assert resp.status_code == 200


def test_get_book_confirmed_booking_returns_200(client, app):
    from src.booking.tokens import make_booking_token

    with app.app_context():
        token = make_booking_token({
            "account_id": 1, "ticket_id": "t1", "subject": "Demo",
            "requester_email": "r@a.com", "requester_name": "Rachel", "duration_minutes": 30,
        })

    mock_booking = MagicMock()
    mock_booking.status = "confirmed"
    mock_booking.booked_by_email = "r@a.com"
    mock_booking.meet_link = "https://meet.google.com/abc"

    with patch("src.booking.routes.Booking") as MockBooking, \
         patch("src.booking.routes.Account") as MockAccount:
        MockBooking.query.filter_by.return_value.first.return_value = mock_booking
        MockAccount.query.get.return_value = MagicMock(name="Acme")
        resp = client.get(f"/book/{token}")
    assert resp.status_code == 200
    assert b"Already booked" in resp.data


def test_book_confirm_missing_fields_returns_400(client):
    resp = client.post("/book/sometoken/confirm", data={})
    assert resp.status_code == 400


def test_ics_not_found_returns_404(client, app):
    with patch("src.extensions.db") as mock_db:
        mock_db.session.get.return_value = None
        resp = client.get("/book/nonexistent/ics")
    assert resp.status_code == 404
