"""Compute experiment-level metrics from existing tables.

derive_status(lead_id) inspects the existing Booking / LeadEngagementEvent /
LinkedInProspect tables to figure out the most progressed state for one
lead. Used by Task 8's periodic refresh task.

The helper is split into small private functions (_has_booking / _has_reply
/ _linkedin_status) so unit tests can patch the table lookups without
needing a full DB fixture.
"""
from __future__ import annotations


def _has_booking(lead_id: str) -> bool:
    """True if a Booking is recorded for this lead."""
    try:
        from src.models.bookings import Booking
    except ImportError:
        # Booking model may not yet exist in this codebase. Treat as False
        # rather than fail; revisit once Booking lands.
        return False
    return Booking.query.filter_by(lead_id=lead_id).first() is not None


def _has_reply(lead_id: str) -> bool:
    """True if any LeadEngagementEvent of type 'reply' exists for this lead."""
    from src.models.leads import LeadEngagementEvent
    return (
        LeadEngagementEvent.query
        .filter_by(lead_id=lead_id, event_type="reply")
        .first() is not None
    )


def _linkedin_status(lead_id: str) -> str | None:
    """Return the LinkedInProspect.status for this lead, or None."""
    from src.models.campaigns import LinkedInProspect
    p = LinkedInProspect.query.filter_by(lead_id=lead_id).first()
    return p.status if p else None


def derive_status(lead_id: str) -> str:
    """Most-progressed wins. Booking > replied > connected > discovered."""
    if _has_booking(lead_id):
        return "booked"
    if _has_reply(lead_id):
        return "replied"
    if _linkedin_status(lead_id) == "connected":
        return "connected"
    return "discovered"


from typing import Any, Dict


def _latest_metric_snapshots(experiment_id: str) -> Dict[str, Any]:
    """Return {label: ICPMetric} for the most recent snapshot per variant for
    this experiment, or {} if none exist. Reads in O(2 * N_variants)."""
    from sqlalchemy import desc
    from src.models.marketing import ICPMetric, ICPVariant

    out: Dict[str, Any] = {}
    variants = ICPVariant.query.filter_by(experiment_id=experiment_id).all()
    for v in variants:
        latest = (
            ICPMetric.query
            .filter_by(experiment_id=experiment_id, variant_id=v.id)
            .order_by(desc(ICPMetric.snapshot_at))
            .first()
        )
        if latest:
            out[v.label] = latest
    return out


def _assignment_status_counts(experiment_id: str) -> Dict[str, Dict[str, int]]:
    """Return per-variant raw status counts. Statuses are mutually exclusive
    in storage. Rolling up to dashboard 'connected/replied/booked' is the
    caller's job."""
    from sqlalchemy import func as sqlfunc
    from src.extensions import db
    from src.models.marketing import ICPLeadAssignment, ICPVariant

    rows = (
        db.session.query(
            ICPVariant.label,
            ICPLeadAssignment.status,
            sqlfunc.count(ICPLeadAssignment.id),
        )
        .join(ICPVariant, ICPLeadAssignment.variant_id == ICPVariant.id)
        .filter(ICPLeadAssignment.experiment_id == experiment_id)
        .group_by(ICPVariant.label, ICPLeadAssignment.status)
        .all()
    )
    out: Dict[str, Dict[str, int]] = {"A": {}, "B": {}}
    for label, status, count in rows:
        out.setdefault(label, {})[status] = int(count)
    return out


def compute_experiment_metrics(experiment) -> Dict[str, Any]:
    """Build the live metrics block returned by GET /experiments/:id.

    Read priority:
      1. Latest ICPMetric snapshot per variant (when both A and B have one) —
         O(2) read; reflects the last 15-min refresh tick.
      2. Live aggregation over ICPLeadAssignment — used until the first
         snapshot lands, or if a partial snapshot would mislead.
    """
    snapshots = _latest_metric_snapshots(experiment.id)

    if "A" in snapshots and "B" in snapshots:
        a = _block_from_snapshot(snapshots["A"])
        b = _block_from_snapshot(snapshots["B"])
    else:
        counts = _assignment_status_counts(experiment.id)
        a = _block_from_counts(counts.get("A", {}))
        b = _block_from_counts(counts.get("B", {}))

    return _assemble(a, b)


def _block_from_snapshot(m) -> Dict[str, Any]:
    return {
        "discovered": int(m.discovered or 0),
        "connected": int(m.connected or 0),
        "replied": int(m.replied or 0),
        "booked": int(m.booked or 0),
        "conversion_pct": round(float(m.conversion_pct or 0.0), 2),
    }


def _block_from_counts(c: Dict[str, int]) -> Dict[str, Any]:
    """Roll up mutually-exclusive status counts into dashboard cumulative shape."""
    discovered = sum(c.values())
    connected = c.get("connected", 0) + c.get("replied", 0) + c.get("booked", 0)
    replied = c.get("replied", 0) + c.get("booked", 0)
    booked = c.get("booked", 0)
    conv = (booked / discovered * 100.0) if discovered > 0 else 0.0
    return {
        "discovered": discovered,
        "connected": connected,
        "replied": replied,
        "booked": booked,
        "conversion_pct": round(conv, 2),
    }


def _assemble(a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
    if a["conversion_pct"] > b["conversion_pct"]:
        leader, margin = "A", a["conversion_pct"] - b["conversion_pct"]
    elif b["conversion_pct"] > a["conversion_pct"]:
        leader, margin = "B", b["conversion_pct"] - a["conversion_pct"]
    else:
        leader, margin = None, 0.0
    return {"A": a, "B": b, "current_leader": leader, "lead_margin_pct": round(margin, 2)}
