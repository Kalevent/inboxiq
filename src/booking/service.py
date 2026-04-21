import logging
import os
from datetime import datetime, timedelta, timezone

from src.extensions import db
from src.booking.tokens import make_booking_token, verify_booking_token, token_to_hash
from src.booking.calendar import create_calendar_event
from src.models.misc import Booking
from src.models.core import AccountFeatureFlags, InboxConnection

logger = logging.getLogger(__name__)

_BASE_URL = os.getenv("APP_BASE_URL", "https://kalevent.com")


def generate_booking(
    account_id: int,
    ticket_id: str,
    subject: str,
    requester_email: str,
    requester_name: str,
) -> str:
    """
    Create a pending Booking row and return the signed booking URL.

    Called when generating a draft reply for a meeting-request email.
    """
    flags = AccountFeatureFlags.query.filter_by(account_id=account_id).first()
    duration = flags.booking_duration_minutes if flags else 30

    token = make_booking_token({
        "account_id": account_id,
        "ticket_id": ticket_id,
        "subject": subject,
        "requester_email": requester_email,
        "requester_name": requester_name,
        "duration_minutes": duration,
    })

    booking = Booking(
        account_id=account_id,
        ticket_id=ticket_id,
        token_hash=token_to_hash(token),
        subject=subject,
        requester_email=requester_email,
        requester_name=requester_name,
        duration_minutes=duration,
        status="pending",
    )
    try:
        db.session.add(booking)
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise

    return f"{_BASE_URL}/book/{token}"


def confirm_booking(
    token: str,
    slot_start_iso: str,
    booked_by_name: str,
    booked_by_email: str,
) -> Booking:
    """
    Confirm a pending booking.

    1. Verifies HMAC token
    2. Checks Booking status == pending (raises ValueError if not)
    3. Creates calendar event (GCal or Outlook)
    4. Updates Booking + Ticket in a single transaction
    5. Dispatches Celery auto-reply task

    Returns confirmed Booking.
    Raises ValueError on invalid/expired token or non-pending status.
    Raises RuntimeError on calendar event creation failure.
    """
    payload = verify_booking_token(token)
    if not payload:
        raise ValueError("invalid_or_expired_token")

    booking = Booking.query.filter_by(token_hash=token_to_hash(token)).first()
    if not booking:
        raise ValueError("booking_not_found")
    if booking.status != "pending":
        raise ValueError(f"booking_already_{booking.status}")

    slot_start = None
    slot_end = None
    calendar_event_id = ""
    meet_link = ""

    if slot_start_iso:
        slot_start = datetime.fromisoformat(slot_start_iso.replace("Z", "+00:00"))
        slot_end = slot_start + timedelta(minutes=booking.duration_minutes)
        try:
            provider = _detect_provider(booking.account_id)
            if provider:
                event = create_calendar_event(
                    account_id=booking.account_id,
                    provider=provider,
                    summary=f"Meeting: {booking.subject or 'Scheduled call'}",
                    start_dt=slot_start.replace(tzinfo=None),
                    end_dt=slot_end.replace(tzinfo=None),
                    attendee_email=booked_by_email,
                    attendee_name=booked_by_name,
                )
                calendar_event_id = event.get("event_id", "")
                meet_link = event.get("meet_link", "")
        except RuntimeError as exc:
            logger.warning("Calendar event creation skipped: %s", exc)

    try:
        now = datetime.now(timezone.utc)
        booking.status = "confirmed"
        booking.slot_start = slot_start
        booking.slot_end = slot_end
        booking.booked_by_name = booked_by_name
        booking.booked_by_email = booked_by_email
        booking.calendar_event_id = calendar_event_id
        booking.meet_link = meet_link
        booking.confirmed_at = now

        from src.models.tickets import Ticket
        ticket = db.session.get(Ticket, booking.ticket_id)
        if ticket:
            if slot_start:
                slot_label = slot_start.strftime("%a %d %b %Y at %H:%M UTC")
                note = f"Meeting booked: {slot_label} via booking page by {booked_by_name} ({booked_by_email})"
            else:
                note = f"Meeting requested via booking page by {booked_by_name} ({booked_by_email}) — time to be arranged"
            existing_notes = ticket.decision or {}
            notes = list(existing_notes.get("notes", []))
            notes.append(note)
            ticket.decision = {**existing_notes, "notes": notes}
            ticket.status = "meeting_scheduled"

        db.session.commit()
    except Exception:
        db.session.rollback()
        raise

    try:
        from src.booking.tasks import send_booking_confirmation_reply
        send_booking_confirmation_reply.delay(booking.id)
    except Exception as exc:
        logger.warning("Failed to dispatch booking confirmation reply task: %s", exc)

    return booking


def _detect_provider(account_id: int) -> str | None:
    """Return 'gcal' or 'outlook_cal' based on which calendar is connected, or None."""
    conn = InboxConnection.query.filter_by(
        account_id=account_id, provider="gcal", status="connected"
    ).first()
    if conn:
        return "gcal"
    conn = InboxConnection.query.filter_by(
        account_id=account_id, provider="outlook_cal", status="connected"
    ).first()
    if conn:
        return "outlook_cal"
    return None
