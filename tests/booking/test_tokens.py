import time
import pytest
from unittest.mock import patch


def test_make_and_verify_roundtrip(app):
    from src.booking.tokens import make_booking_token, verify_booking_token
    with app.app_context():
        payload = {
            "account_id": 1, "ticket_id": "abc-123", "subject": "Demo request",
            "requester_email": "rachel@acme.com", "requester_name": "Rachel",
            "duration_minutes": 30,
        }
        token = make_booking_token(payload)
        result = verify_booking_token(token)
    assert result is not None
    assert result["account_id"] == 1
    assert result["ticket_id"] == "abc-123"
    assert result["requester_email"] == "rachel@acme.com"


def test_tampered_token_returns_none(app):
    from src.booking.tokens import make_booking_token, verify_booking_token
    with app.app_context():
        token = make_booking_token({
            "account_id": 1, "ticket_id": "x", "subject": "",
            "requester_email": "a@b.com", "requester_name": "", "duration_minutes": 30,
        })
    tampered = token[:-4] + "XXXX"
    with app.app_context():
        assert verify_booking_token(tampered) is None


def test_expired_token_returns_none(app):
    from src.booking.tokens import make_booking_token, verify_booking_token
    with app.app_context():
        with patch("src.booking.tokens.time_module") as mock_time:
            mock_time.time.return_value = 1_000_000
            token = make_booking_token({
                "account_id": 1, "ticket_id": "x", "subject": "",
                "requester_email": "a@b.com", "requester_name": "", "duration_minutes": 30,
            })
    with app.app_context():
        with patch("src.booking.tokens.time_module") as mock_time:
            mock_time.time.return_value = 1_000_000 + (8 * 24 * 3600)  # 8 days later
            assert verify_booking_token(token) is None


def test_token_hash_is_64_hex_chars(app):
    from src.booking.tokens import make_booking_token, token_to_hash
    with app.app_context():
        token = make_booking_token({
            "account_id": 1, "ticket_id": "x", "subject": "",
            "requester_email": "a@b.com", "requester_name": "", "duration_minutes": 30,
        })
        h = token_to_hash(token)
    assert len(h) == 64
    assert all(c in "0123456789abcdef" for c in h)
