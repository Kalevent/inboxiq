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
