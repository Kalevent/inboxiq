import logging
from datetime import timedelta

from flask import Blueprint, render_template, request, abort, Response, jsonify, g
from flask_jwt_extended import jwt_required

from src.booking.tokens import verify_booking_token, token_to_hash
from src.booking.calendar import get_available_slots
from src.models.misc import Booking
from src.models.core import Account

logger = logging.getLogger(__name__)

booking_bp = Blueprint("booking", __name__)


@booking_bp.get("/book/<token>")
def book_page(token: str):
    payload = verify_booking_token(token)
    if not payload:
        return render_template(
            "booking/expired.html",
            title="This link has expired",
            message="Booking links are valid for 7 days. Please reply to the original email to request a new one.",
            meet_link=None,
        ), 410

    booking = Booking.query.filter_by(token_hash=token_to_hash(token)).first()
    if booking and booking.status == "confirmed":
        return render_template(
            "booking/expired.html",
            title="Already booked",
            message=f"This meeting has already been scheduled. A confirmation was sent to {booking.booked_by_email}.",
            meet_link=booking.meet_link,
        ), 200
    if booking and booking.status == "cancelled":
        return render_template(
            "booking/expired.html",
            title="This link has been cancelled",
            message="Please reply to the original email to arrange a new time.",
            meet_link=None,
        ), 410

    account = Account.query.get(payload["account_id"])
    account_name = account.name if account else "InboxIQ"

    provider = _detect_provider(payload["account_id"])
    slots = []
    if provider:
        try:
            slots = get_available_slots(
                account_id=payload["account_id"],
                duration_minutes=payload.get("duration_minutes", 30),
                provider=provider,
            )
        except Exception as exc:
            logger.warning("Slot fetch failed for booking page account=%s: %s", payload["account_id"], exc)

    from email.utils import parseaddr
    _, requester_email = parseaddr(payload.get("requester_email", ""))
    requester_email = requester_email or payload.get("requester_email", "")

    return render_template(
        "booking/book.html",
        token=token,
        subject=payload.get("subject", ""),
        requester_email=requester_email,
        requester_name=payload.get("requester_name", ""),
        duration_minutes=payload.get("duration_minutes", 30),
        account_name=account_name,
        slots=slots,
        has_calendar=bool(provider),
    )


@booking_bp.post("/book/<token>/confirm")
def book_confirm(token: str):
    from src.booking.service import confirm_booking

    slot_start = request.form.get("slot_start", "").strip()
    booked_by_name = request.form.get("booked_by_name", "").strip()
    booked_by_email = request.form.get("booked_by_email", "").strip()

    if not booked_by_email:
        abort(400)

    try:
        booking = confirm_booking(
            token=token,
            slot_start_iso=slot_start,
            booked_by_name=booked_by_name,
            booked_by_email=booked_by_email,
        )
    except ValueError as e:
        err = str(e)
        if "expired" in err or "not_found" in err:
            return render_template(
                "booking/expired.html",
                title="This link has expired",
                message="Please reply to the original email to request a new one.",
                meet_link=None,
            ), 410
        if "already_confirmed" in err:
            b = Booking.query.filter_by(token_hash=token_to_hash(token)).first()
            return render_template(
                "booking/expired.html",
                title="Already booked",
                message="This slot has already been confirmed.",
                meet_link=b.meet_link if b else None,
            ), 409
        abort(400)
    except RuntimeError as exc:
        logger.error("Booking confirm failed: %s", exc)
        abort(500)

    slot_label = (
        booking.slot_start.strftime("%A %d %B %Y at %H:%M UTC")
        if booking.slot_start else ""
    )
    return render_template(
        "booking/confirmed.html",
        slot_label=slot_label,
        booked_by_email=booked_by_email,
        meet_link=booking.meet_link or "",
        booking_id=booking.id,
        has_slot=bool(booking.slot_start),
    )


@booking_bp.get("/book/<booking_id>/ics")
def booking_ics(booking_id: str):
    from src.extensions import db
    booking = db.session.get(Booking, booking_id)
    if not booking or booking.status != "confirmed" or not booking.slot_start:
        abort(404)

    dtstart = booking.slot_start.strftime("%Y%m%dT%H%M%SZ")
    dtend = booking.slot_end.strftime("%Y%m%dT%H%M%SZ") if booking.slot_end else (
        booking.slot_start + timedelta(minutes=booking.duration_minutes)
    ).strftime("%Y%m%dT%H%M%SZ")

    description = f"Join: {booking.meet_link}" if booking.meet_link else ""
    ics = (
        "BEGIN:VCALENDAR\r\n"
        "VERSION:2.0\r\n"
        "PRODID:-//InboxIQ//NONSGML v1.0//EN\r\n"
        "BEGIN:VEVENT\r\n"
        f"DTSTART:{dtstart}\r\n"
        f"DTEND:{dtend}\r\n"
        f"SUMMARY:{booking.subject or 'Scheduled meeting'}\r\n"
        f"DESCRIPTION:{description}\r\n"
        f"URL:{booking.meet_link or ''}\r\n"
        "END:VEVENT\r\n"
        "END:VCALENDAR\r\n"
    )
    return Response(
        ics,
        mimetype="text/calendar",
        headers={"Content-Disposition": "attachment; filename=meeting.ics"},
    )


@booking_bp.post("/api/v1/bookings/generate")
@jwt_required()
def api_generate_booking():
    from src.booking.service import generate_booking

    account_id = getattr(g, "current_account_id", None)
    if not account_id:
        return jsonify({"error": "account required"}), 400

    data = request.get_json(silent=True) or {}
    ticket_id = data.get("ticket_id", "")
    subject = data.get("subject", "")
    requester_email = data.get("requester_email", "")
    requester_name = data.get("requester_name", "")

    if not ticket_id or not requester_email:
        return jsonify({"error": "ticket_id and requester_email required"}), 400

    try:
        url = generate_booking(
            account_id=account_id,
            ticket_id=ticket_id,
            subject=subject,
            requester_email=requester_email,
            requester_name=requester_name,
        )
        return jsonify({"booking_url": url})
    except Exception as exc:
        logger.error("API generate booking failed account=%s: %s", account_id, exc)
        return jsonify({"error": "Failed to generate booking link"}), 500


@booking_bp.get("/api/v1/bookings/feature-status")
@jwt_required()
def api_booking_feature_status():
    """
    Returns booking feature flags for the current account.

    Frontend uses this to:
    - Show an upgrade prompt when dynamic_booking_enabled=false and the
      email is a meeting request (draft reply has no booking link).
    - Insert static_booking_url when composing a proactive outbound email.
    """
    from src.models.core import AccountFeatureFlags
    account_id = getattr(g, "current_account_id", None)
    if not account_id:
        return jsonify({"error": "account required"}), 400

    flags = AccountFeatureFlags.query.filter_by(account_id=account_id).first()
    return jsonify({
        "dynamic_booking_enabled": flags.dynamic_booking_enabled if flags else True,
        "static_booking_url": flags.static_booking_url if flags else None,
    })


def _detect_provider(account_id: int):
    from src.models.core import InboxConnection
    for provider in ("gcal", "outlook_cal"):
        conn = InboxConnection.query.filter_by(
            account_id=account_id, provider=provider, status="connected"
        ).first()
        if conn:
            return provider
    return None
