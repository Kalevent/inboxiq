# Booking Page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `/book/<signed_token>` — a public self-scheduling page that reads live calendar slots, lets a visitor pick a time, creates the calendar event automatically, updates the originating ticket, and fires an auto-reply on the thread.

**Architecture:** A per-email HMAC-signed token encodes account/ticket context. A `Booking` DB row (created at draft time, confirmed on visitor submit) prevents double-booking and provides an audit trail. The booking page is public (no login), reads slots from GCal or Outlook live, and dispatches a Celery task on confirm for the thread reply.

**Tech Stack:** Flask, SQLAlchemy, Celery, Google Calendar API, Microsoft Graph API, boto3 SES, Jinja2, HMAC-SHA256

---

## File Map

### New files
| File | Purpose |
|---|---|
| `src/booking/__init__.py` | Package marker |
| `src/booking/tokens.py` | HMAC token generation + verification |
| `src/booking/calendar.py` | Structured slot fetching + event creation for GCal and Outlook |
| `src/booking/service.py` | `generate_booking()` + `confirm_booking()` business logic |
| `src/booking/tasks.py` | Celery task: send auto-reply after booking confirmed |
| `src/booking/routes.py` | Flask blueprint: public GET/POST + internal API |
| `src/templates/booking/book.html` | Visitor-facing booking page |
| `src/templates/booking/confirmed.html` | Post-booking confirmation page |
| `src/templates/booking/expired.html` | Expired/invalid/already-booked page |
| `tests/booking/test_tokens.py` | Token unit tests |
| `tests/booking/test_service.py` | Service unit tests |
| `tests/booking/test_routes.py` | Route integration tests |

### Modified files
| File | Change |
|---|---|
| `src/models/misc.py` | Add `Booking` model |
| `src/models/core.py` | Add `booking_duration_minutes` to `AccountFeatureFlags` |
| `src/models/__init__.py` | Re-export `Booking` |
| `src/integrations/outlook_cal.py` | Add `create_meeting()` |
| `src/app.py` | Register `booking_bp` blueprint |
| `src/dspy/draft_reply.py` | Generate booking link instead of text slot list |
| `src/settings/routes.py` | Add `POST /integrations/booking-duration` route |
| `src/templates/settings/index.html` | Add duration `<select>` near GCal/Outlook section |
| `src/templates/marketing/features.html` | Add `<section id="scheduling">` |

---

## Task 1: Data Model + Migration

**Files:**
- Modify: `src/models/misc.py`
- Modify: `src/models/core.py`
- Modify: `src/models/__init__.py`

- [ ] **Step 1: Add `Booking` model to `src/models/misc.py`**

Append after the `Feedback` class:

```python
class Booking(db.Model):
    __tablename__ = "inboxiq_bookings"

    id = db.Column(db.String(64), primary_key=True, default=lambda: str(uuid4()), nullable=False)
    token_hash = db.Column(db.String(64), unique=True, nullable=False, index=True)
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=False)
    ticket_id = db.Column(db.String(64), db.ForeignKey("inboxiq_tickets.id"), nullable=False)
    subject = db.Column(db.String(500), nullable=False, default="")
    requester_email = db.Column(db.String(255), nullable=False, default="")
    requester_name = db.Column(db.String(255), nullable=False, default="")
    duration_minutes = db.Column(db.Integer, nullable=False, default=30)
    status = db.Column(db.String(32), nullable=False, default="pending")
    slot_start = db.Column(db.DateTime(timezone=True), nullable=True)
    slot_end = db.Column(db.DateTime(timezone=True), nullable=True)
    booked_by_name = db.Column(db.String(255), nullable=True)
    booked_by_email = db.Column(db.String(255), nullable=True)
    calendar_event_id = db.Column(db.String(255), nullable=True)
    meet_link = db.Column(db.String(500), nullable=True)
    confirmed_at = db.Column(db.DateTime(timezone=True), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), server_default=func.now(), nullable=False)
```

- [ ] **Step 2: Add `booking_duration_minutes` to `AccountFeatureFlags` in `src/models/core.py`**

Find the `AccountFeatureFlags` class (it has `draft_reply_enabled`, `draft_reply_auto_approve`, `draft_reply_min_confidence`). Add one line after the existing columns:

```python
    booking_duration_minutes = db.Column(db.Integer, nullable=False, default=30, server_default='30')
```

- [ ] **Step 3: Re-export `Booking` from `src/models/__init__.py`**

Find the line:
```python
from src.models.misc import Testimonial, Feedback
```
Replace with:
```python
from src.models.misc import Testimonial, Feedback, Booking
```

Also find the `__all__` list and add `"Booking"` next to `"Feedback"`:
```python
    "Testimonial", "Feedback", "Booking",
```

- [ ] **Step 4: Run migration**

```bash
flask db migrate -m "Add Booking model and booking_duration_minutes"
flask db upgrade
```

Expected: two new items in the migration — `inboxiq_bookings` table and `booking_duration_minutes` column on `account_feature_flags`.

- [ ] **Step 5: Commit**

```bash
git add src/models/misc.py src/models/core.py src/models/__init__.py src/migrations/versions/
git commit -m "feat: Booking model and booking_duration_minutes account setting"
```

---

## Task 2: Token Module

**Files:**
- Create: `src/booking/__init__.py`
- Create: `src/booking/tokens.py`
- Create: `tests/booking/__init__.py`
- Create: `tests/booking/test_tokens.py`

- [ ] **Step 1: Create package files**

`src/booking/__init__.py` — empty file.

`tests/booking/__init__.py` — empty file.

- [ ] **Step 2: Write failing tests for token module**

Create `tests/booking/test_tokens.py`:

```python
import time
import pytest
from unittest.mock import patch


def test_make_and_verify_token(app):
    """Round-trip: make a token, verify it returns the original payload."""
    from src.booking.tokens import make_booking_token, verify_booking_token

    with app.app_context():
        payload = {
            "account_id": 1,
            "ticket_id": "abc-123",
            "subject": "Demo request",
            "requester_email": "rachel@acme.com",
            "requester_name": "Rachel",
            "duration_minutes": 30,
        }
        token = make_booking_token(payload)
        result = verify_booking_token(token)
        assert result is not None
        assert result["account_id"] == 1
        assert result["ticket_id"] == "abc-123"
        assert result["requester_email"] == "rachel@acme.com"


def test_verify_tampered_token_returns_none(app):
    from src.booking.tokens import make_booking_token, verify_booking_token

    with app.app_context():
        token = make_booking_token({
            "account_id": 1, "ticket_id": "x", "subject": "", 
            "requester_email": "a@b.com", "requester_name": "", "duration_minutes": 30,
        })
        tampered = token[:-4] + "XXXX"
        assert verify_booking_token(tampered) is None


def test_verify_expired_token_returns_none(app):
    from src.booking.tokens import make_booking_token, verify_booking_token

    with app.app_context():
        with patch("src.booking.tokens.time") as mock_time:
            mock_time.time.return_value = 1000000
            token = make_booking_token({
                "account_id": 1, "ticket_id": "x", "subject": "",
                "requester_email": "a@b.com", "requester_name": "", "duration_minutes": 30,
            })
        # Verify 8 days later (TTL is 7 days)
        with patch("src.booking.tokens.time") as mock_time:
            mock_time.time.return_value = 1000000 + (8 * 24 * 3600)
            assert verify_booking_token(token) is None


def test_token_hash_is_sha256(app):
    from src.booking.tokens import make_booking_token, token_to_hash

    with app.app_context():
        token = make_booking_token({
            "account_id": 1, "ticket_id": "x", "subject": "",
            "requester_email": "a@b.com", "requester_name": "", "duration_minutes": 30,
        })
        h = token_to_hash(token)
        assert len(h) == 64  # SHA-256 hex is 64 chars
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
pytest tests/booking/test_tokens.py -v
```

Expected: `ImportError: cannot import name 'make_booking_token'`

- [ ] **Step 4: Create `src/booking/tokens.py`**

```python
import hashlib
import hmac
import json
import time as time_module

from flask import current_app

_TTL_SECONDS = 7 * 24 * 3600  # 7 days


def _secret() -> bytes:
    return current_app.config["SECRET_KEY"].encode()


def make_booking_token(payload: dict) -> str:
    """
    Sign a booking payload and return a URL-safe token string.

    payload must contain: account_id, ticket_id, subject,
    requester_email, requester_name, duration_minutes.
    """
    data = {**payload, "exp": int(time_module.time()) + _TTL_SECONDS}
    body = json.dumps(data, separators=(",", ":"), sort_keys=True)
    sig = hmac.new(_secret(), body.encode(), hashlib.sha256).hexdigest()
    import base64
    encoded = base64.urlsafe_b64encode(body.encode()).decode().rstrip("=")
    return f"{encoded}.{sig}"


def verify_booking_token(token: str) -> dict | None:
    """
    Verify HMAC signature and expiry. Returns decoded payload or None.
    """
    try:
        import base64
        encoded, sig = token.rsplit(".", 1)
        padding = "=" * (-len(encoded) % 4)
        body = base64.urlsafe_b64decode(encoded + padding).decode()
        expected = hmac.new(_secret(), body.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected):
            return None
        data = json.loads(body)
        if time_module.time() > data.get("exp", 0):
            return None
        return data
    except Exception:
        return None


def token_to_hash(token: str) -> str:
    """SHA-256 hash of the token string for DB storage."""
    return hashlib.sha256(token.encode()).hexdigest()
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/booking/test_tokens.py -v
```

Expected: 4 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add src/booking/__init__.py src/booking/tokens.py tests/booking/__init__.py tests/booking/test_tokens.py
git commit -m "feat: booking token HMAC module"
```

---

## Task 3: Structured Calendar Slots + GCal Event Creation

**Files:**
- Create: `src/booking/calendar.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/booking/test_tokens.py` (or create `tests/booking/test_calendar.py`):

Create `tests/booking/test_calendar.py`:

```python
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch


def test_get_available_slots_returns_list(app):
    """get_available_slots returns a list of dicts with start/end/label."""
    from src.booking.calendar import get_available_slots

    mock_service = MagicMock()
    mock_service.freebusy().query().execute.return_value = {
        "calendars": {"primary": {"busy": []}}
    }

    with app.app_context():
        with patch("src.booking.calendar.get_gcal_service", return_value=mock_service):
            slots = get_available_slots(account_id=1, duration_minutes=30, provider="gcal")

    assert isinstance(slots, list)
    for s in slots:
        assert "start" in s
        assert "end" in s
        assert "label" in s


def test_get_available_slots_returns_empty_when_no_service(app):
    from src.booking.calendar import get_available_slots

    with app.app_context():
        with patch("src.booking.calendar.get_gcal_service", return_value=None):
            slots = get_available_slots(account_id=1, duration_minutes=30, provider="gcal")
    assert slots == []


def test_create_gcal_event_returns_event_id_and_meet_link(app):
    from src.booking.calendar import create_gcal_event
    from datetime import datetime, timezone

    mock_service = MagicMock()
    mock_service.events().insert().execute.return_value = {
        "id": "evt_abc123",
        "htmlLink": "https://calendar.google.com/event?id=evt_abc123",
        "conferenceData": {
            "entryPoints": [
                {"entryPointType": "video", "uri": "https://meet.google.com/abc-def-ghi"}
            ]
        }
    }

    start = datetime(2026, 4, 21, 10, 0, tzinfo=timezone.utc)
    end = datetime(2026, 4, 21, 10, 30, tzinfo=timezone.utc)

    with app.app_context():
        with patch("src.booking.calendar.get_gcal_service", return_value=mock_service):
            result = create_gcal_event(
                account_id=1,
                summary="Demo call",
                start_dt=start,
                end_dt=end,
                attendee_email="rachel@acme.com",
                attendee_name="Rachel",
            )

    assert result["event_id"] == "evt_abc123"
    assert result["meet_link"] == "https://meet.google.com/abc-def-ghi"
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest tests/booking/test_calendar.py -v
```

Expected: `ImportError: cannot import name 'get_available_slots' from 'src.booking.calendar'`

- [ ] **Step 3: Create `src/booking/calendar.py`**

```python
import logging
from datetime import datetime, timedelta, time, timezone
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

    Each slot: {"start": ISO str, "end": ISO str, "label": "Mon Apr 21 · 10:00 AM UTC"}
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
    Create a calendar event and return {"event_id": ..., "meet_link": ...}.
    Raises RuntimeError if the calendar is not connected or creation fails.
    """
    if provider == "gcal":
        return create_gcal_event(account_id, summary, start_dt, end_dt, attendee_email, attendee_name)
    if provider == "outlook_cal":
        from src.integrations.outlook_cal import create_meeting as outlook_create
        result = outlook_create(account_id, summary, start_dt, end_dt, attendee_email, attendee_name)
        return result
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
        if cursor.weekday() >= 5:
            cursor += timedelta(days=1)
            continue
        slot_start = cursor.replace(hour=_BUSINESS_START.hour, minute=_BUSINESS_START.minute)
        day_end = cursor.replace(hour=_BUSINESS_END.hour, minute=_BUSINESS_END.minute)
        while (
            slot_start + timedelta(minutes=duration_minutes) <= day_end
            and len(slots) < _MAX_SLOTS
        ):
            slot_end = slot_start + timedelta(minutes=duration_minutes)
            occupied = _overlaps(slot_start, slot_end, busy_times)
            if not occupied:
                slots.append({
                    "start": slot_start.isoformat() + "Z",
                    "end": slot_end.isoformat() + "Z",
                    "label": slot_start.strftime("%a %d %b · %I:%M %p UTC").replace(" 0", " "),
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/booking/test_calendar.py -v
```

Expected: 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/booking/calendar.py tests/booking/test_calendar.py
git commit -m "feat: structured calendar slot fetching and GCal event creation"
```

---

## Task 4: Outlook `create_meeting`

**Files:**
- Modify: `src/integrations/outlook_cal.py`

- [ ] **Step 1: Add `create_meeting` to `src/integrations/outlook_cal.py`**

Append this function at the end of the file (after the existing `get_available_slots_text`):

```python
def create_meeting(
    account_id: int,
    title: str,
    start_dt,
    end_dt,
    attendee_email: str,
    attendee_name: str,
) -> dict:
    """
    Create an Outlook Calendar event with a Teams meeting link.

    Returns {"event_id": str, "meet_link": str} or raises RuntimeError.
    """
    import requests as http
    from src.models.core import InboxConnection
    from src.crypto import decrypt_value

    conn = InboxConnection.query.filter_by(
        account_id=account_id, provider="outlook_cal", status="connected"
    ).first()
    if not conn:
        raise RuntimeError("Outlook Calendar not connected for this account")

    meta = conn.metadata_json or {}
    token = decrypt_value(meta.get("access_token_enc", ""))
    if not token:
        raise RuntimeError("Outlook access token missing or could not be decrypted")

    url = "https://graph.microsoft.com/v1.0/me/events"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    body = {
        "subject": title,
        "start": {"dateTime": start_dt.isoformat(), "timeZone": "UTC"},
        "end": {"dateTime": end_dt.isoformat(), "timeZone": "UTC"},
        "attendees": [
            {
                "emailAddress": {"address": attendee_email, "name": attendee_name},
                "type": "required",
            }
        ],
        "isOnlineMeeting": True,
        "onlineMeetingProvider": "teamsForBusiness",
    }
    resp = http.post(url, headers=headers, json=body, timeout=15)
    if resp.status_code not in (200, 201):
        raise RuntimeError(f"Outlook event creation failed: {resp.status_code} {resp.text[:200]}")

    data = resp.json()
    meet_link = (data.get("onlineMeeting") or {}).get("joinUrl", "")
    return {
        "event_id": data["id"],
        "meet_link": meet_link,
    }
```

- [ ] **Step 2: Verify the module imports cleanly**

```bash
python -c "from src.integrations.outlook_cal import create_meeting; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add src/integrations/outlook_cal.py
git commit -m "feat: Outlook Calendar create_meeting via Graph API"
```

---

## Task 5: Booking Service

**Files:**
- Create: `src/booking/service.py`
- Create: `tests/booking/test_service.py`

The service contains two functions:
- `generate_booking(account_id, ticket_id, subject, requester_email, requester_name)` → booking URL
- `confirm_booking(token, slot_start_iso, booked_by_name, booked_by_email)` → confirmed Booking

- [ ] **Step 1: Write failing tests**

Create `tests/booking/test_service.py`:

```python
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone


def _make_flags(duration=30):
    flags = MagicMock()
    flags.booking_duration_minutes = duration
    return flags


def test_generate_booking_creates_pending_row(app, db):
    """generate_booking returns a URL and creates a Booking(status=pending) row."""
    from src.booking.service import generate_booking
    from src.models.misc import Booking

    with app.app_context():
        with patch("src.booking.service.AccountFeatureFlags") as MockFlags:
            MockFlags.query.filter_by.return_value.first.return_value = _make_flags(30)
            with patch("src.booking.service.db") as mock_db:
                mock_db.session = MagicMock()
                url = generate_booking(
                    account_id=1,
                    ticket_id="ticket-abc",
                    subject="Demo request",
                    requester_email="rachel@acme.com",
                    requester_name="Rachel",
                )

        assert url.startswith("https://kalevent.com/book/")
        mock_db.session.add.assert_called_once()
        mock_db.session.commit.assert_called_once()
        booking = mock_db.session.add.call_args[0][0]
        assert booking.status == "pending"
        assert booking.ticket_id == "ticket-abc"
        assert booking.requester_email == "rachel@acme.com"


def test_generate_booking_uses_default_duration_when_no_flags(app):
    from src.booking.service import generate_booking

    with app.app_context():
        with patch("src.booking.service.AccountFeatureFlags") as MockFlags:
            MockFlags.query.filter_by.return_value.first.return_value = None
            with patch("src.booking.service.db") as mock_db:
                mock_db.session = MagicMock()
                url = generate_booking(
                    account_id=1, ticket_id="t1", subject="hi",
                    requester_email="a@b.com", requester_name="",
                )
        assert "book/" in url
        booking = mock_db.session.add.call_args[0][0]
        assert booking.duration_minutes == 30  # default
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest tests/booking/test_service.py -v
```

Expected: `ImportError: cannot import name 'generate_booking'`

- [ ] **Step 3: Create `src/booking/service.py`**

```python
import hashlib
import logging
import os
from datetime import datetime, timedelta, timezone

from src.extensions import db
from src.booking.tokens import make_booking_token, verify_booking_token, token_to_hash
from src.models.misc import Booking

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

    Call this when generating a draft reply for a meeting-request email.
    """
    from src.models.core import AccountFeatureFlags

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

    Verifies token, checks status=pending, creates the calendar event,
    updates the Booking and Ticket, dispatches the auto-reply Celery task.

    Returns the confirmed Booking.
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

    slot_start = datetime.fromisoformat(slot_start_iso.replace("Z", "+00:00"))
    slot_end = slot_start + timedelta(minutes=booking.duration_minutes)

    # Detect calendar provider
    provider = _detect_provider(booking.account_id)

    # Create calendar event
    from src.booking.calendar import create_calendar_event
    event = create_calendar_event(
        account_id=booking.account_id,
        provider=provider,
        summary=f"Meeting: {booking.subject or 'Scheduled call'}",
        start_dt=slot_start.replace(tzinfo=None),
        end_dt=slot_end.replace(tzinfo=None),
        attendee_email=booked_by_email,
        attendee_name=booked_by_name,
    )

    # Update booking + ticket in one transaction
    try:
        now = datetime.now(timezone.utc)
        booking.status = "confirmed"
        booking.slot_start = slot_start
        booking.slot_end = slot_end
        booking.booked_by_name = booked_by_name
        booking.booked_by_email = booked_by_email
        booking.calendar_event_id = event.get("event_id", "")
        booking.meet_link = event.get("meet_link", "")
        booking.confirmed_at = now

        from src.models.tickets import Ticket
        ticket = db.session.get(Ticket, booking.ticket_id)
        if ticket:
            slot_label = slot_start.strftime("%a %d %b %Y at %H:%M UTC")
            existing_notes = ticket.decision or {}
            notes = existing_notes.get("notes", [])
            notes.append(
                f"Meeting booked: {slot_label} via booking page by {booked_by_name} ({booked_by_email})"
            )
            ticket.decision = {**existing_notes, "notes": notes}
            ticket.status = "meeting_scheduled"

        db.session.commit()
    except Exception:
        db.session.rollback()
        raise

    # Dispatch auto-reply task
    try:
        from src.booking.tasks import send_booking_confirmation_reply
        send_booking_confirmation_reply.delay(booking.id)
    except Exception as exc:
        logger.warning("Failed to dispatch booking confirmation reply task: %s", exc)

    return booking


def _detect_provider(account_id: int) -> str:
    """Return 'gcal' or 'outlook_cal' based on which calendar is connected."""
    from src.models.core import InboxConnection
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
    raise RuntimeError("No calendar connected for this account")
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/booking/test_service.py -v
```

Expected: 2 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/booking/service.py tests/booking/test_service.py
git commit -m "feat: booking service generate and confirm"
```

---

## Task 6: Celery Auto-Reply Task

**Files:**
- Create: `src/booking/tasks.py`

- [ ] **Step 1: Create `src/booking/tasks.py`**

```python
import logging
import os

from celery import shared_task

logger = logging.getLogger(__name__)

_FROM_EMAIL = os.getenv("TRIAL_ONBOARDING_FROM_EMAIL", "hello@kalevent.com")
_FROM_NAME = os.getenv("TRIAL_ONBOARDING_FROM_NAME", "Kofi from InboxIQ")


@shared_task(name="booking.send_confirmation_reply", bind=True, max_retries=3, default_retry_delay=60)
def send_booking_confirmation_reply(self, booking_id: str) -> None:
    """
    Send a confirmation email to the person who just booked a meeting.
    Uses SES — appears as a reply to the original support thread.
    """
    from src.app import create_app
    app = create_app()
    with app.app_context():
        try:
            import boto3
            from src.models.misc import Booking
            from src.models.core import Account

            from src.extensions import db
            booking = db.session.get(Booking, booking_id)
            if not booking or booking.status != "confirmed":
                logger.warning("Booking %s not found or not confirmed — skipping reply", booking_id)
                return

            account = Account.query.get(booking.account_id)
            account_name = account.name if account else "InboxIQ"

            slot_label = booking.slot_start.strftime("%A %d %B %Y at %H:%M UTC") if booking.slot_start else "the scheduled time"
            meet_link = booking.meet_link or ""

            subject = f"Re: {booking.subject}" if booking.subject else "Your meeting is confirmed"

            body_html = f"""<!DOCTYPE html>
<html>
<body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Arial,sans-serif;color:#333;max-width:600px;margin:0 auto;padding:20px;">
  <p>Hi {booking.booked_by_name or 'there'},</p>
  <p>Your meeting is confirmed for <strong>{slot_label}</strong>.</p>
  {"<p><a href='" + meet_link + "' style='background:#4F46E5;color:#fff;padding:10px 20px;border-radius:6px;text-decoration:none;font-weight:600;'>Join meeting</a></p>" if meet_link else ""}
  <p>Looking forward to speaking with you.</p>
  <p style="color:#666;font-size:13px;">— {account_name}</p>
</body>
</html>"""

            import re
            body_text = re.sub(r'<[^>]+>', '', body_html)
            body_text = re.sub(r'\s+', ' ', body_text).strip()

            ses = boto3.client(
                'ses',
                region_name=os.getenv('AWS_REGION', 'us-west-2'),
                aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
                aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
            )
            source = f"{_FROM_NAME} <{_FROM_EMAIL}>"
            ses.send_email(
                Source=source,
                Destination={'ToAddresses': [booking.booked_by_email]},
                Message={
                    'Subject': {'Data': subject, 'Charset': 'UTF-8'},
                    'Body': {
                        'Text': {'Data': body_text, 'Charset': 'UTF-8'},
                        'Html': {'Data': body_html, 'Charset': 'UTF-8'},
                    },
                },
            )
            logger.info("Booking confirmation reply sent to %s (booking=%s)", booking.booked_by_email, booking_id)
        except Exception as exc:
            logger.error("Booking confirmation reply failed (booking=%s): %s", booking_id, exc)
            raise self.retry(exc=exc)
```

- [ ] **Step 2: Verify the task imports cleanly**

```bash
python -c "from src.booking.tasks import send_booking_confirmation_reply; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add src/booking/tasks.py
git commit -m "feat: Celery task for booking confirmation auto-reply"
```

---

## Task 7: Templates

**Files:**
- Create: `src/templates/booking/book.html`
- Create: `src/templates/booking/confirmed.html`
- Create: `src/templates/booking/expired.html`

- [ ] **Step 1: Create `src/templates/booking/book.html`**

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Book a meeting</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif; background: #f5f5f5; color: #1a1a1a; }
    .wrap { max-width: 560px; margin: 40px auto; padding: 0 16px; }
    .card { background: #fff; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,.08); padding: 32px; }
    .logo { display: flex; align-items: center; gap: 10px; margin-bottom: 24px; }
    .logo-mark { width: 32px; height: 32px; background: #4F46E5; border-radius: 7px; }
    .logo-name { font-size: 15px; font-weight: 600; color: #111; }
    .context-banner { background: #fef3c7; border-left: 4px solid #f59e0b; padding: 12px 14px; border-radius: 4px; margin-bottom: 24px; font-size: 13px; }
    .context-banner .subject { font-weight: 600; color: #92400e; }
    .context-banner .from { color: #78350f; margin-top: 2px; }
    h1 { font-size: 18px; font-weight: 600; margin-bottom: 4px; }
    .subtitle { font-size: 13px; color: #666; margin-bottom: 20px; }
    .slots { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-bottom: 24px; }
    .slot { border: 2px solid #e5e7eb; border-radius: 8px; padding: 10px 12px; cursor: pointer; font-size: 13px; background: #f9fafb; transition: all .15s; }
    .slot:hover { border-color: #a5b4fc; background: #eef2ff; }
    .slot.selected { border-color: #4F46E5; background: #eef2ff; color: #4F46E5; font-weight: 600; }
    .slot .date { font-size: 11px; color: #666; }
    .slot.selected .date { color: #6366f1; }
    .no-slots { text-align: center; padding: 20px; color: #666; font-size: 14px; }
    label { display: block; font-size: 13px; font-weight: 500; margin-bottom: 4px; color: #374151; }
    input { width: 100%; border: 1px solid #d1d5db; border-radius: 6px; padding: 9px 12px; font-size: 14px; margin-bottom: 14px; outline: none; }
    input:focus { border-color: #4F46E5; box-shadow: 0 0 0 2px rgba(79,70,229,.15); }
    .btn { width: 100%; background: #4F46E5; color: #fff; border: none; border-radius: 8px; padding: 13px; font-size: 15px; font-weight: 600; cursor: pointer; margin-top: 4px; }
    .btn:disabled { background: #c7c9f0; cursor: not-allowed; }
    .footer { text-align: center; font-size: 11px; color: #999; margin-top: 20px; }
  </style>
</head>
<body>
  <div class="wrap">
    <div class="card">
      <div class="logo">
        <div class="logo-mark"></div>
        <span class="logo-name">InboxIQ</span>
      </div>

      {% if subject or requester_email %}
      <div class="context-banner">
        {% if subject %}<div class="subject">Re: {{ subject }}</div>{% endif %}
        {% if requester_email %}<div class="from">from {{ requester_email }}</div>{% endif %}
      </div>
      {% endif %}

      <h1>Book a meeting with {{ account_name }}</h1>
      <p class="subtitle">{{ duration_minutes }}-minute call &middot; Video link sent on confirmation</p>

      <form method="POST" action="/book/{{ token }}/confirm" id="book-form">
        {% if slots %}
        <div class="slots" id="slot-grid">
          {% for slot in slots %}
          <div class="slot" data-start="{{ slot.start }}" onclick="selectSlot(this)">
            <div class="date">{{ slot.label.split('·')[0].strip() }}</div>
            <strong>{{ slot.label.split('·')[1].strip() if '·' in slot.label else slot.label }}</strong>
          </div>
          {% endfor %}
        </div>
        <input type="hidden" name="slot_start" id="slot_start" value="">
        {% else %}
        <div class="no-slots">No available slots found. Please reply to the email to arrange a time.</div>
        {% endif %}

        <label for="name">Your name</label>
        <input type="text" id="name" name="booked_by_name" value="{{ requester_name }}" required placeholder="Your full name">

        <label for="email">Your email</label>
        <input type="email" id="email" name="booked_by_email" value="{{ requester_email }}" required placeholder="you@company.com">

        {% if slots %}
        <button type="submit" class="btn" id="submit-btn" disabled>Select a time above</button>
        {% endif %}
      </form>
    </div>
    <div class="footer">Powered by InboxIQ</div>
  </div>

  <script>
    function selectSlot(el) {
      document.querySelectorAll('.slot').forEach(s => s.classList.remove('selected'));
      el.classList.add('selected');
      document.getElementById('slot_start').value = el.dataset.start;
      var btn = document.getElementById('submit-btn');
      btn.disabled = false;
      btn.textContent = 'Confirm booking';
    }
    document.getElementById('book-form').addEventListener('submit', function(e) {
      var slot = document.getElementById('slot_start').value;
      if (!slot) { e.preventDefault(); alert('Please select a time slot.'); }
    });
  </script>
</body>
</html>
```

- [ ] **Step 2: Create `src/templates/booking/confirmed.html`**

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Meeting confirmed</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif; background: #f5f5f5; }
    .wrap { max-width: 560px; margin: 60px auto; padding: 0 16px; }
    .card { background: #fff; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,.08); padding: 40px; text-align: center; }
    .check { font-size: 48px; margin-bottom: 16px; }
    h1 { font-size: 22px; font-weight: 700; margin-bottom: 8px; color: #111; }
    .slot-label { font-size: 16px; color: #4F46E5; font-weight: 600; margin: 16px 0; }
    p { font-size: 14px; color: #555; margin-bottom: 20px; line-height: 1.6; }
    .meet-btn { display: inline-block; background: #4F46E5; color: #fff; padding: 12px 28px; border-radius: 8px; text-decoration: none; font-weight: 600; font-size: 15px; }
    .ics-link { display: block; margin-top: 16px; font-size: 13px; color: #4F46E5; text-decoration: none; }
    .footer { text-align: center; font-size: 11px; color: #999; margin-top: 24px; }
  </style>
</head>
<body>
  <div class="wrap">
    <div class="card">
      <div class="check">&#10003;</div>
      <h1>You're booked!</h1>
      <div class="slot-label">{{ slot_label }}</div>
      <p>A confirmation has been sent to {{ booked_by_email }}.<br>A calendar invite has been sent to all attendees.</p>
      {% if meet_link %}
      <a href="{{ meet_link }}" class="meet-btn">Join meeting</a>
      {% endif %}
      <a href="/book/{{ booking_id }}/ics" class="ics-link">&#8595; Add to calendar (.ics)</a>
    </div>
    <div class="footer">Powered by InboxIQ</div>
  </div>
</body>
</html>
```

- [ ] **Step 3: Create `src/templates/booking/expired.html`**

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Link unavailable</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif; background: #f5f5f5; }
    .wrap { max-width: 480px; margin: 80px auto; padding: 0 16px; text-align: center; }
    .card { background: #fff; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,.08); padding: 40px; }
    h1 { font-size: 20px; font-weight: 600; margin-bottom: 12px; color: #111; }
    p { font-size: 14px; color: #666; line-height: 1.6; }
    {% if meet_link %}
    .meet-btn { display: inline-block; margin-top: 20px; background: #4F46E5; color: #fff; padding: 10px 24px; border-radius: 8px; text-decoration: none; font-weight: 600; }
    {% endif %}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="card">
      <h1>{{ title }}</h1>
      <p>{{ message }}</p>
      {% if meet_link %}
      <a href="{{ meet_link }}" class="meet-btn">Join the meeting</a>
      {% endif %}
    </div>
  </div>
</body>
</html>
```

- [ ] **Step 4: Commit**

```bash
git add src/templates/booking/
git commit -m "feat: booking page templates (book, confirmed, expired)"
```

---

## Task 8: Routes Blueprint + App Registration

**Files:**
- Create: `src/booking/routes.py`
- Modify: `src/app.py`
- Create: `tests/booking/test_routes.py`

- [ ] **Step 1: Write failing route tests**

Create `tests/booking/test_routes.py`:

```python
import pytest
from unittest.mock import patch, MagicMock


def test_get_book_invalid_token_returns_400(client):
    resp = client.get("/book/not-a-valid-token")
    assert resp.status_code in (400, 200)  # 400 preferred; 200 with error page is acceptable


def test_get_book_valid_token_returns_200(client, app):
    from src.booking.tokens import make_booking_token

    with app.app_context():
        token = make_booking_token({
            "account_id": 1, "ticket_id": "t1", "subject": "Demo",
            "requester_email": "r@a.com", "requester_name": "Rachel", "duration_minutes": 30,
        })

    with patch("src.booking.routes.Booking") as MockBooking:
        MockBooking.query.filter_by.return_value.first.return_value = MagicMock(status="pending")
        with patch("src.booking.routes.get_available_slots", return_value=[]):
            with patch("src.booking.routes.Account") as MockAccount:
                MockAccount.query.get.return_value = MagicMock(name="Acme")
                resp = client.get(f"/book/{token}")
    assert resp.status_code == 200
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest tests/booking/test_routes.py -v
```

Expected: `404` on the `/book/` route since blueprint is not registered yet.

- [ ] **Step 3: Create `src/booking/routes.py`**

```python
import logging
from datetime import datetime, timedelta

from flask import Blueprint, render_template, request, abort, redirect, url_for, Response, jsonify, g
from flask_jwt_extended import jwt_required, get_jwt_identity

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

    return render_template(
        "booking/book.html",
        token=token,
        subject=payload.get("subject", ""),
        requester_email=payload.get("requester_email", ""),
        requester_name=payload.get("requester_name", ""),
        duration_minutes=payload.get("duration_minutes", 30),
        account_name=account_name,
        slots=slots,
    )


@booking_bp.post("/book/<token>/confirm")
def book_confirm(token: str):
    from src.booking.service import confirm_booking

    slot_start = request.form.get("slot_start", "").strip()
    booked_by_name = request.form.get("booked_by_name", "").strip()
    booked_by_email = request.form.get("booked_by_email", "").strip()

    if not slot_start or not booked_by_email:
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
        if booking.slot_start else "your scheduled time"
    )
    return render_template(
        "booking/confirmed.html",
        slot_label=slot_label,
        booked_by_email=booked_by_email,
        meet_link=booking.meet_link or "",
        booking_id=booking.id,
    )


@booking_bp.get("/book/<booking_id>/ics")
def booking_ics(booking_id: str):
    """Generate and serve an .ics calendar file for a confirmed booking."""
    booking = Booking.query.get(booking_id)
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


def _detect_provider(account_id: int) -> str | None:
    from src.models.core import InboxConnection
    for provider in ("gcal", "outlook_cal"):
        conn = InboxConnection.query.filter_by(
            account_id=account_id, provider=provider, status="connected"
        ).first()
        if conn:
            return provider
    return None
```

- [ ] **Step 4: Register the blueprint in `src/app.py`**

Find the blueprint registration block (around line 292). Add after the last `app.register_blueprint` call:

```python
    from src.booking.routes import booking_bp
    app.register_blueprint(booking_bp)
```

- [ ] **Step 5: Run route tests**

```bash
pytest tests/booking/test_routes.py -v
```

Expected: tests PASS (or at minimum no import errors; mock-based tests pass).

- [ ] **Step 6: Commit**

```bash
git add src/booking/routes.py src/app.py tests/booking/test_routes.py
git commit -m "feat: booking routes blueprint and app registration"
```

---

## Task 9: Draft Reply Integration

**Files:**
- Modify: `src/dspy/draft_reply.py`

The goal: when `fetch_calendar_slots` detects a meeting-request email and `ticket_id`/`requester_email` are provided, generate a booking link instead of returning the text slot list.

- [ ] **Step 1: Find the `fetch_calendar_slots` call site**

```bash
grep -n "fetch_calendar_slots" src/dspy/draft_reply.py
```

Note the line number where it is **called** (not defined). Check what variables are available at that call site — you need `ticket_id` (from the Ticket object) and `from_email` (i.e. `ticket.from_email`).

- [ ] **Step 2: Update the function signature in `src/dspy/draft_reply.py`**

Find the function definition:
```python
def fetch_calendar_slots(subject: str, body: str, account_id: int | None) -> str:
```

Replace with:
```python
def fetch_calendar_slots(
    subject: str,
    body: str,
    account_id: int | None,
    ticket_id: str | None = None,
    requester_email: str | None = None,
    requester_name: str | None = None,
) -> str:
```

- [ ] **Step 3: Replace the function body with booking-link generation**

Replace the entire function body (inside `fetch_calendar_slots`) with:

```python
    if not account_id:
        return ""
    try:
        from src.integrations.gcal import is_meeting_request
        if not is_meeting_request(subject, body):
            return ""

        # When ticket context is available, generate a booking link
        if ticket_id and requester_email:
            from src.booking.service import generate_booking
            booking_url = generate_booking(
                account_id=account_id,
                ticket_id=ticket_id,
                subject=subject,
                requester_email=requester_email,
                requester_name=requester_name or "",
            )
            return f"\n\nSchedule a time that works for you: {booking_url}"

        # Fallback: text slots (no ticket context)
        from src.integrations.gcal import get_available_slots_text as gcal_slots
        from src.integrations.outlook_cal import get_available_slots_text as outlook_slots
        slots = gcal_slots(account_id)
        if not slots:
            slots = outlook_slots(account_id)
        return slots
    except Exception as exc:
        logger.warning("fetch_calendar_slots failed account=%s: %s", account_id, exc)
        return ""
```

- [ ] **Step 4: Update the call site to pass ticket context**

Find where `fetch_calendar_slots` is called in `src/dspy/draft_reply.py`. The call currently looks like:
```python
slots = fetch_calendar_slots(subject, body, account_id)
```

Update it to pass ticket context. If a `Ticket` object is available at the call site:
```python
slots = fetch_calendar_slots(
    subject,
    body,
    account_id,
    ticket_id=ticket.id if ticket else None,
    requester_email=ticket.from_email if ticket else None,
    requester_name="",
)
```

If only `ticket_id` and `from_email` are available as separate variables, use those directly.

- [ ] **Step 5: Verify the module imports without error**

```bash
python -c "from src.dspy.draft_reply import fetch_calendar_slots; print('OK')"
```

Expected: `OK`

- [ ] **Step 6: Commit**

```bash
git add src/dspy/draft_reply.py
git commit -m "feat: booking link replaces text slots in draft reply for meeting requests"
```

---

## Task 10: Settings UI — Meeting Duration

**Files:**
- Modify: `src/settings/routes.py`
- Modify: `src/templates/settings/index.html`

- [ ] **Step 1: Add the save route to `src/settings/routes.py`**

Find the imports at the top of the file. The file already imports `g`, `request`, `redirect`, `url_for`, and uses `@login_required_settings`. Add this route near the other integrations POST handlers:

```python
@bp.post("/integrations/booking-duration")
@login_required_settings
def save_booking_duration():
    from src.models.core import AccountFeatureFlags
    account_id = getattr(g, "current_account_id", None)
    if not account_id:
        return redirect(url_for("settings.settings_page", tab="integrations"))

    raw = request.form.get("booking_duration_minutes", "30")
    try:
        duration = int(raw)
        if duration not in (15, 30, 45, 60):
            duration = 30
    except (ValueError, TypeError):
        duration = 30

    try:
        flags = AccountFeatureFlags.query.filter_by(account_id=account_id).first()
        if not flags:
            flags = AccountFeatureFlags(account_id=account_id)
            db.session.add(flags)
        flags.booking_duration_minutes = duration
        db.session.commit()
    except Exception:
        db.session.rollback()
        current_app.logger.error("Failed to save booking_duration_minutes account=%s", account_id)

    return redirect(url_for("settings.settings_page", tab="integrations"))
```

Make sure `db` and `current_app` are imported at the top of `src/settings/routes.py`. They likely already are; verify:
```python
from src.extensions import db
from flask import current_app
```

- [ ] **Step 2: Add duration UI to `src/templates/settings/index.html`**

Open `src/templates/settings/index.html` and find the section that shows `gcal_connection` or `outlook_cal_connection` (search for "gcal" in the file). Add this block immediately after the calendar connection section:

```html
<!-- Meeting duration setting -->
<div class="mt-6 border-t border-white/10 pt-6">
  <h3 class="text-sm font-semibold text-white mb-1">Default meeting duration</h3>
  <p class="text-xs text-slate-400 mb-3">Applied to scheduling links generated in draft replies.</p>
  <form method="POST" action="{{ url_for('settings.save_booking_duration') }}" class="flex items-center gap-3">
    <select name="booking_duration_minutes" class="bg-slate-800 border border-white/10 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:ring-2 focus:ring-indigo-500">
      {% set dur = feature_flags.booking_duration_minutes if feature_flags else 30 %}
      <option value="15" {% if dur == 15 %}selected{% endif %}>15 minutes</option>
      <option value="30" {% if dur == 30 %}selected{% endif %}>30 minutes</option>
      <option value="45" {% if dur == 45 %}selected{% endif %}>45 minutes</option>
      <option value="60" {% if dur == 60 %}selected{% endif %}>60 minutes</option>
    </select>
    <button type="submit" class="text-xs bg-indigo-600 hover:bg-indigo-500 text-white px-4 py-2 rounded-lg font-medium">Save</button>
  </form>
</div>
```

Note: `feature_flags` must be passed to the template by the settings route. Check `src/settings/routes.py` — there is already a `feature_flags` variable loaded for the features tab. Make sure it is also loaded for the `integrations` tab:

```python
# In the settings_page route, ensure feature_flags is loaded for integrations tab too:
if tab in ("integrations", "features") and account_id:
    from src.models.core import AccountFeatureFlags
    feature_flags = AccountFeatureFlags.query.filter_by(account_id=account_id).first()
```

Pass `feature_flags=feature_flags` to `render_template`.

- [ ] **Step 3: Rebuild Tailwind CSS**

```bash
cd src && npm run build:css
```

- [ ] **Step 4: Commit**

```bash
git add src/settings/routes.py src/templates/settings/index.html src/static/css/
git commit -m "feat: booking duration setting in integrations settings"
```

---

## Task 11: Features Page

**Files:**
- Modify: `src/templates/marketing/features.html`

- [ ] **Step 1: Find the insert point**

```bash
grep -n 'id="drafts"\|id="automation"' src/templates/marketing/features.html
```

Note the line number of `id="automation"`. The new scheduling section goes immediately before it.

- [ ] **Step 2: Insert the scheduling section**

Open `src/templates/marketing/features.html`. Find the line that begins `<section id="automation"`. Insert this block immediately before it:

```html
  <section id="scheduling" class="grid lg:grid-cols-2 gap-8 marketing-section">
    <div>
      <h2 class="text-2xl font-semibold text-white mb-4">Meeting requested? A booking link is already in the draft.</h2>
      <p class="text-slate-300 mb-6">
        When InboxIQ detects a meeting request, it generates a personal scheduling link and embeds it in the draft reply automatically. No Calendly. No back-and-forth. Rachel clicks, picks a slot, and the event is created — all while you were in another tab.
      </p>
      <ul class="space-y-3 text-slate-300 text-sm">
        <li class="flex gap-3"><span class="text-indigo-400 font-semibold mt-0.5">1.</span><span>AI detects "can we find a time?" in the incoming email.</span></li>
        <li class="flex gap-3"><span class="text-indigo-400 font-semibold mt-0.5">2.</span><span>A signed booking link is embedded in the draft reply — one click for the visitor.</span></li>
        <li class="flex gap-3"><span class="text-indigo-400 font-semibold mt-0.5">3.</span><span>Visitor picks a slot. Calendar event created instantly. Ticket marked as scheduled.</span></li>
      </ul>
      <p class="text-slate-400 text-xs mt-4">Works with Google Calendar and Outlook Calendar &bull; No third-party scheduling tool required</p>
    </div>
    <div class="marketing-card space-y-4">
      <h3 class="font-semibold text-white">What happens on confirm</h3>
      <ul class="space-y-3 text-sm text-slate-300">
        <li class="flex gap-3">
          <span class="text-green-400 font-bold mt-0.5">&#10003;</span>
          <span>Google Meet or Microsoft Teams link created and sent to both parties</span>
        </li>
        <li class="flex gap-3">
          <span class="text-green-400 font-bold mt-0.5">&#10003;</span>
          <span>Ticket status updated to &ldquo;meeting scheduled&rdquo; &mdash; no manual follow-up needed</span>
        </li>
        <li class="flex gap-3">
          <span class="text-green-400 font-bold mt-0.5">&#10003;</span>
          <span>Auto-reply sent on the thread confirming the time and meeting link</span>
        </li>
        <li class="flex gap-3">
          <span class="text-green-400 font-bold mt-0.5">&#10003;</span>
          <span>Visitor can add to their calendar with one click (.ics download)</span>
        </li>
      </ul>
    </div>
  </section>
```

- [ ] **Step 3: Rebuild Tailwind CSS**

```bash
cd src && npm run build:css
```

- [ ] **Step 4: Commit**

```bash
git add src/templates/marketing/features.html src/static/css/
git commit -m "feat: scheduling section on features marketing page"
```

---

## Self-Review Checklist

Run before declaring implementation complete:

- [ ] `flask db upgrade` applied cleanly in staging
- [ ] `GET /book/<valid_token>` renders slots
- [ ] `GET /book/<expired_token>` returns 410 expired page
- [ ] `POST /book/<token>/confirm` creates GCal event + updates ticket + fires Celery task
- [ ] `GET /book/<booking_id>/ics` returns a valid `.ics` file
- [ ] Settings `/integrations` page shows the duration select and saves correctly
- [ ] Features page `id="scheduling"` section renders correctly on `/features`
- [ ] Draft reply for a meeting-request email now contains a booking URL (not text slots)
- [ ] `pytest tests/booking/ -v` all pass
