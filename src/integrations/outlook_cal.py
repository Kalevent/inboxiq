"""
Microsoft Outlook Calendar integration — per-account OAuth token management.

Uses Microsoft Graph API with the access token stored in
InboxConnection(provider='outlook_cal').

Provides:
- get_available_slots_text(account_id) → human-readable slots string or ""
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, time

import requests as http

logger = logging.getLogger(__name__)

_GRAPH_CALENDAR_VIEW = "https://graph.microsoft.com/v1.0/me/calendarView"

_BUSINESS_START = time(9, 0)
_BUSINESS_END = time(17, 0)
_SLOT_MINUTES = 30
_BUFFER_MINUTES = 15
_MAX_SLOTS = 6


def _get_access_token(account_id: int) -> str | None:
    """
    Return the decrypted access token for the account's Outlook Calendar
    connection, or None if not connected.
    """
    try:
        from src.models.core import InboxConnection
        from src.crypto import decrypt_value

        conn = InboxConnection.query.filter_by(
            account_id=account_id, provider="outlook_cal", status="connected"
        ).first()
        if not conn:
            return None

        meta = conn.metadata_json or {}
        return decrypt_value(meta.get("access_token_enc", ""))
    except Exception as exc:
        logger.warning("outlook_cal _get_access_token failed account=%s: %s", account_id, exc)
        return None


def get_available_slots_text(account_id: int, days_ahead: int = 5) -> str:
    """
    Query the account's Outlook Calendar for free slots over the next
    `days_ahead` business days via Microsoft Graph API.

    Returns empty string if the calendar is not connected or the query fails.
    """
    access_token = _get_access_token(account_id)
    if not access_token:
        return ""

    try:
        now = datetime.utcnow()
        end = now + timedelta(days=days_ahead)

        # Fetch calendar events in the window
        resp = http.get(
            _GRAPH_CALENDAR_VIEW,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
                "Prefer": 'outlook.timezone="UTC"',
            },
            params={
                "startDateTime": now.strftime("%Y-%m-%dT%H:%M:%S"),
                "endDateTime": end.strftime("%Y-%m-%dT%H:%M:%S"),
                "$select": "start,end,showAs",
                "$top": "100",
                "$orderby": "start/dateTime",
            },
            timeout=10,
        )

        if resp.status_code == 401:
            logger.warning("outlook_cal: token expired for account=%s", account_id)
            return ""

        resp.raise_for_status()
        events = resp.json().get("value", [])

        # Build list of busy intervals
        busy_times = []
        for ev in events:
            if ev.get("showAs") in ("free", "workingElsewhere"):
                continue
            try:
                bs = datetime.fromisoformat(ev["start"]["dateTime"].replace("Z", ""))
                be = datetime.fromisoformat(ev["end"]["dateTime"].replace("Z", ""))
                busy_times.append((bs, be))
            except Exception:
                continue

        # Find free slots
        slots = []
        cursor = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)

        while cursor.date() <= end.date() and len(slots) < _MAX_SLOTS:
            if cursor.weekday() >= 5:  # skip Saturday/Sunday
                cursor += timedelta(days=1)
                continue

            slot_start = cursor.replace(
                hour=_BUSINESS_START.hour, minute=_BUSINESS_START.minute
            )
            day_end = cursor.replace(
                hour=_BUSINESS_END.hour, minute=_BUSINESS_END.minute
            )

            while (
                slot_start + timedelta(minutes=_SLOT_MINUTES) <= day_end
                and len(slots) < _MAX_SLOTS
            ):
                slot_end = slot_start + timedelta(minutes=_SLOT_MINUTES)
                occupied = any(
                    slot_start < be and slot_end > bs for bs, be in busy_times
                )
                if not occupied:
                    slots.append(slot_start.strftime("%A %d %b, %H:%M UTC"))
                slot_start += timedelta(minutes=_SLOT_MINUTES + _BUFFER_MINUTES)

            cursor += timedelta(days=1)

        if not slots:
            return ""

        lines = ["Here are some available times to connect:"]
        lines.extend(f"- {s}" for s in slots)
        lines.append("Please let me know which works best for you.")
        return "\n".join(lines)

    except Exception as exc:
        logger.warning(
            "outlook_cal get_available_slots_text failed account=%s: %s", account_id, exc
        )
        return ""
