"""Tests for src/marketing/experiment_metrics.py — derives an
ICPLeadAssignment.status from the lead's progress in existing tables."""
from unittest.mock import patch


def test_derive_status_returns_booked_when_booking_exists():
    from src.marketing.experiment_metrics import derive_status
    with patch("src.marketing.experiment_metrics._has_booking", return_value=True), \
         patch("src.marketing.experiment_metrics._has_reply", return_value=True), \
         patch("src.marketing.experiment_metrics._linkedin_status", return_value="connected"):
        assert derive_status("lead-1") == "booked"


def test_derive_status_returns_replied_when_reply_but_no_booking():
    from src.marketing.experiment_metrics import derive_status
    with patch("src.marketing.experiment_metrics._has_booking", return_value=False), \
         patch("src.marketing.experiment_metrics._has_reply", return_value=True), \
         patch("src.marketing.experiment_metrics._linkedin_status", return_value="connected"):
        assert derive_status("lead-1") == "replied"


def test_derive_status_returns_connected_when_only_linkedin_connected():
    from src.marketing.experiment_metrics import derive_status
    with patch("src.marketing.experiment_metrics._has_booking", return_value=False), \
         patch("src.marketing.experiment_metrics._has_reply", return_value=False), \
         patch("src.marketing.experiment_metrics._linkedin_status", return_value="connected"):
        assert derive_status("lead-1") == "connected"


def test_derive_status_returns_discovered_when_no_progress():
    from src.marketing.experiment_metrics import derive_status
    with patch("src.marketing.experiment_metrics._has_booking", return_value=False), \
         patch("src.marketing.experiment_metrics._has_reply", return_value=False), \
         patch("src.marketing.experiment_metrics._linkedin_status", return_value="pending"):
        assert derive_status("lead-1") == "discovered"
