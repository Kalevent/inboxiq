"""Tests for linkedin.refresh_experiment_metrics — periodic Celery task that
reconciles ICPLeadAssignment.status against existing tables AND inserts one
ICPMetric snapshot per (running experiment, variant) per tick."""
from unittest.mock import patch, MagicMock


def test_refresh_skips_disqualified_assignments():
    """Disqualified assignments are MANUALLY set; never overwrite them."""
    from src.tasks.linkedin import refresh_experiment_metrics

    asg_disq = MagicMock(status="disqualified", lead_id="L1")
    asg_live = MagicMock(status="discovered", lead_id="L2")

    with patch("src.tasks.linkedin._all_assignments_for_refresh", return_value=[asg_disq, asg_live]), \
         patch("src.tasks.linkedin._running_experiments_with_variants", return_value=[]), \
         patch("src.tasks.linkedin.derive_status", return_value="connected"), \
         patch("src.tasks.linkedin.db.session.commit"):
        refresh_experiment_metrics.run()

    assert asg_disq.status == "disqualified", "must not overwrite disqualified"
    assert asg_live.status == "connected", "must update live assignment to derived status"


def test_refresh_no_change_when_status_already_correct():
    """If derive_status returns the same value, don't churn."""
    from src.tasks.linkedin import refresh_experiment_metrics

    asg = MagicMock(status="connected", lead_id="L1")
    with patch("src.tasks.linkedin._all_assignments_for_refresh", return_value=[asg]), \
         patch("src.tasks.linkedin._running_experiments_with_variants", return_value=[]), \
         patch("src.tasks.linkedin.derive_status", return_value="connected"), \
         patch("src.tasks.linkedin.db.session.commit"):
        refresh_experiment_metrics.run()

    assert asg.status == "connected"


def test_refresh_inserts_one_snapshot_per_variant_per_running_experiment():
    """Every running experiment gets one ICPMetric row per variant per tick."""
    from src.tasks.linkedin import refresh_experiment_metrics

    fake_exp = MagicMock(id="exp-1")
    fake_va = MagicMock(id="var-A", label="A")
    fake_vb = MagicMock(id="var-B", label="B")

    inserted = []

    class FakeICPMetric:
        def __init__(self, **kwargs):
            inserted.append(kwargs)

    with patch("src.tasks.linkedin._all_assignments_for_refresh", return_value=[]), \
         patch("src.tasks.linkedin._running_experiments_with_variants", return_value=[(fake_exp, [fake_va, fake_vb])]), \
         patch("src.tasks.linkedin._count_assignments_by_status", side_effect=[
             {"discovered": 30, "connected": 10, "replied": 4, "booked": 1},  # variant A
             {"discovered": 30, "connected": 18, "replied": 8, "booked": 4},  # variant B
         ]), \
         patch("src.tasks.linkedin.ICPMetric", FakeICPMetric), \
         patch("src.tasks.linkedin.db.session.add") as add, \
         patch("src.tasks.linkedin.db.session.commit"):
        refresh_experiment_metrics.run()

    assert len(inserted) == 2, f"expected 2 ICPMetric rows (one per variant), got {len(inserted)}"
    a_row = next(r for r in inserted if r["variant_id"] == "var-A")
    assert a_row["discovered"] == 45  # 30+10+4+1 cumulative
    assert a_row["connected"] == 15
    assert a_row["replied"] == 5
    assert a_row["booked"] == 1


def test_refresh_runs_twice_inserts_two_sets_of_snapshots():
    """The task is INSERT-only; each tick adds new ICPMetric rows."""
    from src.tasks.linkedin import refresh_experiment_metrics

    fake_exp = MagicMock(id="exp-1")
    fake_va = MagicMock(id="var-A", label="A")

    inserted = []

    class FakeICPMetric:
        def __init__(self, **kwargs):
            inserted.append(kwargs)

    counts_iter = [
        {"discovered": 10},  # tick 1, variant A
        {"discovered": 20},  # tick 2, variant A
    ]

    with patch("src.tasks.linkedin._all_assignments_for_refresh", return_value=[]), \
         patch("src.tasks.linkedin._running_experiments_with_variants",
               return_value=[(fake_exp, [fake_va])]), \
         patch("src.tasks.linkedin._count_assignments_by_status",
               side_effect=lambda *a, **kw: counts_iter.pop(0)), \
         patch("src.tasks.linkedin.ICPMetric", FakeICPMetric), \
         patch("src.tasks.linkedin.db.session.add"), \
         patch("src.tasks.linkedin.db.session.commit"):
        refresh_experiment_metrics.run()
        refresh_experiment_metrics.run()

    assert len(inserted) == 2
    assert inserted[0]["discovered"] == 10
    assert inserted[1]["discovered"] == 20
