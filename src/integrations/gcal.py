"""
Google Calendar integration — per-account OAuth token management.

Provides:
- get_gcal_service(account_id)       → googleapiclient service or None
- get_available_slots_text(account_id) → human-readable slots string or ""
- is_meeting_request(subject, body)   → bool keyword detection
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, time
from typing import Optional

logger = logging.getLogger(__name__)

_MEETING_KEYWORDS = (
    "schedule", "meeting", "call", "demo", "webinar", "available",
    "book", "appointment", "calendar", "time slot", "availability",
    "catch up", "chat", "discussion", "zoom", "google meet", "teams call",
    "can we meet", "would you be available", "find a time",
)

_BUSINESS_START = time(9, 0)
_BUSINESS_END = time(17, 0)
_SLOT_MINUTES = 30
_BUFFER_MINUTES = 15
_MAX_SLOTS = 6


def is_meeting_request(subject: str, body: str) -> bool:
    """Return True if the email text contains meeting-request signals."""
    text = f"{subject} {body}".lower()
    return any(kw in text for kw in _MEETING_KEYWORDS)


def get_gcal_service(account_id: int):
    """
    Build an authorised Google Calendar API service for the given account
    using the OAuth token stored in InboxConnection(provider='gcal').

    Returns None if:
    - No gcal connection exists for this account
    - google-api-python-client is not installed
    - Token decryption or service build fails
    """
    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
    except ImportError:
        logger.debug("google-api-python-client not installed — gcal unavailable")
        return None

    try:
        from src.models.core import InboxConnection
        from src.crypto import decrypt_value

        conn = InboxConnection.query.filter_by(
            account_id=account_id, provider="gcal", status="connected"
        ).first()
        if not conn:
            return None

        meta = conn.metadata_json or {}
        access_token = decrypt_value(meta.get("access_token_enc", ""))
        refresh_token = decrypt_value(meta.get("refresh_token_enc", "") or "")

        if not access_token:
            logger.warning("gcal: no access_token for account=%s", account_id)
            return None

        creds = Credentials(
            token=access_token,
            refresh_token=refresh_token or None,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=os.getenv("GOOGLE_CLIENT_ID"),
            client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
            scopes=["https://www.googleapis.com/auth/calendar"],
        )
        return build("calendar", "v3", credentials=creds, cache_discovery=False)
    except Exception as exc:
        logger.warning("get_gcal_service failed account=%s: %s", account_id, exc)
        return None


def get_available_slots_text(account_id: int, days_ahead: int = 5) -> str:
    """
    Query the account's Google Calendar for free slots over the next
    `days_ahead` business days and return a short human-readable string.

    Returns empty string if calendar is not connected or the query fails.
    """
    service = get_gcal_service(account_id)
    if not service:
        return ""

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

        slots = []
        # Start checking from tomorrow
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
                occupied = False
                for b in busy_times:
                    bs = datetime.fromisoformat(
                        b["start"].replace("Z", "+00:00")
                    ).replace(tzinfo=None)
                    be = datetime.fromisoformat(
                        b["end"].replace("Z", "+00:00")
                    ).replace(tzinfo=None)
                    if slot_start < be and slot_end > bs:
                        occupied = True
                        break
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
            "get_available_slots_text failed account=%s: %s", account_id, exc
        )
        return ""
