"""Tests for src/marketing/experiment_metrics.py — derives an
ICPLeadAssignment.status from the lead's progress in existing tables."""
from unittest.mock import MagicMock, patch


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


def test_compute_experiment_metrics_zero_assignments_no_snapshot():
    """Brand-new experiment: no ICPMetric snapshot yet, no assignments yet.
    Returns zeros, no DivisionByZero."""
    from src.marketing.experiment_metrics import compute_experiment_metrics

    fake_exp = MagicMock(id="exp-1")
    with patch("src.marketing.experiment_metrics._latest_metric_snapshots", return_value={}), \
         patch("src.marketing.experiment_metrics._assignment_status_counts",
               return_value={"A": {}, "B": {}}):
        result = compute_experiment_metrics(fake_exp)

    assert result["A"]["discovered"] == 0
    assert result["A"]["conversion_pct"] == 0.0
    assert result["B"]["discovered"] == 0
    assert result["B"]["conversion_pct"] == 0.0
    assert result["current_leader"] is None
    assert result["lead_margin_pct"] == 0.0


def test_compute_experiment_metrics_uses_latest_snapshot_when_present():
    """When ICPMetric snapshots exist for both variants, prefer them
    (O(2) read) over aggregating ICPLeadAssignment live."""
    from src.marketing.experiment_metrics import compute_experiment_metrics

    fake_exp = MagicMock(id="exp-1")
    snapshots = {
        "A": MagicMock(discovered=50, connected=20, replied=8, booked=3, conversion_pct=6.0),
        "B": MagicMock(discovered=50, connected=32, replied=14, booked=7, conversion_pct=14.0),
    }
    with patch("src.marketing.experiment_metrics._latest_metric_snapshots", return_value=snapshots), \
         patch("src.marketing.experiment_metrics._assignment_status_counts") as live_aggr:
        result = compute_experiment_metrics(fake_exp)

    live_aggr.assert_not_called()
    assert result["A"]["discovered"] == 50
    assert result["A"]["booked"] == 3
    assert result["A"]["conversion_pct"] == 6.0
    assert result["B"]["conversion_pct"] == 14.0
    assert result["current_leader"] == "B"
    assert abs(result["lead_margin_pct"] - 8.0) < 0.01


def test_compute_experiment_metrics_falls_back_to_live_when_no_snapshot():
    """When ICPMetric is empty (refresh hasn't run yet), aggregate live
    over ICPLeadAssignment so the dashboard isn't blank."""
    from src.marketing.experiment_metrics import compute_experiment_metrics

    fake_exp = MagicMock(id="exp-1")
    counts = {
        "A": {"discovered": 30, "connected": 10, "replied": 4, "booked": 1},
        "B": {"discovered": 30, "connected": 18, "replied": 8, "booked": 4},
    }
    with patch("src.marketing.experiment_metrics._latest_metric_snapshots", return_value={}), \
         patch("src.marketing.experiment_metrics._assignment_status_counts", return_value=counts):
        result = compute_experiment_metrics(fake_exp)

    # Recall: status values are mutually exclusive in storage; rolled-up
    # counts in metrics are inclusive of more-progressed states.
    # discovered = total assignments = sum of all status counts
    # connected = c.get("connected") + c.get("replied") + c.get("booked")
    # replied = c.get("replied") + c.get("booked")
    # booked = c.get("booked")
    a = result["A"]
    assert a["discovered"] == 45  # 30+10+4+1
    assert a["connected"] == 15   # 10+4+1
    assert a["replied"] == 5      # 4+1
    assert a["booked"] == 1
    # conversion_pct = booked / discovered * 100
    assert a["conversion_pct"] == round(1 / 45 * 100, 2)


def test_compute_experiment_metrics_partial_snapshot_falls_back_to_live():
    """If only one variant has a snapshot but not the other, fall back to
    live aggregation for both — don't mix sources, that would be misleading."""
    from src.marketing.experiment_metrics import compute_experiment_metrics

    fake_exp = MagicMock(id="exp-1")
    snapshots = {  # only variant A has a snapshot
        "A": MagicMock(discovered=50, connected=20, replied=8, booked=3, conversion_pct=6.0),
    }
    counts = {  # live counts available for both
        "A": {"discovered": 30, "connected": 10, "replied": 4, "booked": 1},
        "B": {"discovered": 30, "connected": 18, "replied": 8, "booked": 4},
    }
    with patch("src.marketing.experiment_metrics._latest_metric_snapshots", return_value=snapshots), \
         patch("src.marketing.experiment_metrics._assignment_status_counts", return_value=counts):
        result = compute_experiment_metrics(fake_exp)

    # Should reflect LIVE counts (rolled-up), not snapshot
    assert result["A"]["discovered"] == 45
    assert result["B"]["discovered"] == 60  # 30+18+8+4
