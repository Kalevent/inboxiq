import logging
from datetime import datetime, timedelta, time
from typing import Any
from uuid import uuid4

logger = logging.getLogger(__name__)

_BUSINESS_START = time(9, 0)
_BUSINESS_END = time(17, 0)
_BUFFER_MINUTES = 15
_MAX_SLOTS = 8


def get_available_slots(
    account_id: int,
    duration_minutes: int = 30,
    provider: str = "gcal",
    days_ahead: int = 5,
) -> list[dict[str, str]]:
    """
    Return structured free slots for the account's calendar.

    Each slot: {"start": ISO str (Z suffix), "end": ISO str (Z suffix), "label": "Mon 21 Apr · 10:00 AM UTC"}
    Returns [] if calendar not connected or query fails.
    """
    if provider == "gcal":
        return _gcal_slots(account_id, duration_minutes, days_ahead)
    if provider == "outlook_cal":
        return _outlook_slots(account_id, duration_minutes, days_ahead)
    return []


def create_calendar_event(
    account_id: int,
    provider: str,
    summary: str,
    start_dt: datetime,
    end_dt: datetime,
    attendee_email: str,
    attendee_name: str,
) -> dict[str, str]:
    """
    Create a calendar event and return {"event_id": ..., "meet_link": ..., "html_link": ...}.
    Raises RuntimeError if the calendar is not connected or creation fails.
    """
    if provider == "gcal":
        return create_gcal_event(account_id, summary, start_dt, end_dt, attendee_email, attendee_name)
    if provider == "outlook_cal":
        from src.integrations.outlook_cal import create_meeting as outlook_create
        return outlook_create(account_id, summary, start_dt, end_dt, attendee_email, attendee_name)
    raise RuntimeError(f"Unknown calendar provider: {provider}")


def _gcal_slots(account_id: int, duration_minutes: int, days_ahead: int) -> list[dict]:
    from src.integrations.gcal import get_gcal_service
    service = get_gcal_service(account_id)
    if not service:
        return []
    try:
        now = datetime.utcnow()
        end = now + timedelta(days=days_ahead)
        freebusy_body = {
            "timeMin": now.isoformat() + "Z",
            "timeMax": end.isoformat() + "Z",
            "timeZone": "UTC",
            "items": [{"id": "primary"}],
        }
        result = service.freebusy().query(body=freebusy_body).execute()
        busy_times = result.get("calendars", {}).get("primary", {}).get("busy", [])
        return _compute_slots(busy_times, duration_minutes, days_ahead)
    except Exception as exc:
        logger.warning("gcal slot fetch failed account=%s: %s", account_id, exc)
        return []


def _outlook_slots(account_id: int, duration_minutes: int, days_ahead: int) -> list[dict]:
    import requests as http
    from src.models.core import InboxConnection
    from src.crypto import decrypt_value
    try:
        conn = InboxConnection.query.filter_by(
            account_id=account_id, provider="outlook_cal", status="connected"
        ).first()
        if not conn:
            return []
        meta = conn.metadata_json or {}
        token = decrypt_value(meta.get("access_token_enc", ""))
        if not token:
            return []
        now = datetime.utcnow()
        end = now + timedelta(days=days_ahead)
        url = "https://graph.microsoft.com/v1.0/me/calendarView"
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        params = {
            "startDateTime": now.isoformat() + "Z",
            "endDateTime": end.isoformat() + "Z",
            "$select": "start,end",
        }
        resp = http.get(url, headers=headers, params=params, timeout=10)
        if resp.status_code != 200:
            return []
        busy_times = [
            {"start": e["start"]["dateTime"], "end": e["end"]["dateTime"]}
            for e in resp.json().get("value", [])
        ]
        return _compute_slots(busy_times, duration_minutes, days_ahead)
    except Exception as exc:
        logger.warning("outlook slot fetch failed account=%s: %s", account_id, exc)
        return []


def _compute_slots(busy_times: list, duration_minutes: int, days_ahead: int) -> list[dict]:
    slots = []
    now = datetime.utcnow()
    cursor = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    end_date = now + timedelta(days=days_ahead)

    while cursor.date() <= end_date.date() and len(slots) < _MAX_SLOTS:
        if cursor.weekday() >= 5:  # skip weekends
            cursor += timedelta(days=1)
            continue
        slot_start = cursor.replace(hour=_BUSINESS_START.hour, minute=_BUSINESS_START.minute)
        day_end = cursor.replace(hour=_BUSINESS_END.hour, minute=_BUSINESS_END.minute)
        while (
            slot_start + timedelta(minutes=duration_minutes) <= day_end
            and len(slots) < _MAX_SLOTS
        ):
            slot_end = slot_start + timedelta(minutes=duration_minutes)
            if not _overlaps(slot_start, slot_end, busy_times):
                slots.append({
                    "start": slot_start.isoformat() + "Z",
                    "end": slot_end.isoformat() + "Z",
                    "label": slot_start.strftime("%a %d %b · %I:%M %p UTC").lstrip("0").replace(" 0", " "),
                })
            slot_start += timedelta(minutes=duration_minutes + _BUFFER_MINUTES)
        cursor += timedelta(days=1)
    return slots


def _overlaps(slot_start: datetime, slot_end: datetime, busy_times: list) -> bool:
    for b in busy_times:
        try:
            bs = datetime.fromisoformat(b["start"].replace("Z", "+00:00")).replace(tzinfo=None)
            be = datetime.fromisoformat(b["end"].replace("Z", "+00:00")).replace(tzinfo=None)
            if slot_start < be and slot_end > bs:
                return True
        except Exception:
            continue
    return False


def create_gcal_event(
    account_id: int,
    summary: str,
    start_dt: datetime,
    end_dt: datetime,
    attendee_email: str,
    attendee_name: str,
) -> dict[str, str]:
    """Create a Google Calendar event with Meet link. Returns {event_id, meet_link, html_link}."""
    from src.integrations.gcal import get_gcal_service
    service = get_gcal_service(account_id)
    if not service:
        raise RuntimeError("Google Calendar not connected for this account")

    event_body = {
        "summary": summary,
        "start": {"dateTime": start_dt.isoformat(), "timeZone": "UTC"},
        "end": {"dateTime": end_dt.isoformat(), "timeZone": "UTC"},
        "attendees": [{"email": attendee_email, "displayName": attendee_name}],
        "conferenceData": {
            "createRequest": {
                "requestId": str(uuid4()),
                "conferenceSolutionKey": {"type": "hangoutsMeet"},
            }
        },
        "reminders": {
            "useDefault": False,
            "overrides": [
                {"method": "email", "minutes": 24 * 60},
                {"method": "popup", "minutes": 30},
            ],
        },
    }
    result = service.events().insert(
        calendarId="primary",
        body=event_body,
        conferenceDataVersion=1,
        sendUpdates="all",
    ).execute()

    meet_link = ""
    for ep in result.get("conferenceData", {}).get("entryPoints", []):
        if ep.get("entryPointType") == "video":
            meet_link = ep.get("uri", "")
            break

    return {
        "event_id": result["id"],
        "meet_link": meet_link,
        "html_link": result.get("htmlLink", ""),
    }
