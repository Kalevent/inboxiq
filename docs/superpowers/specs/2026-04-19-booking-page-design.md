# Booking Page Design — `/book/<signed_token>`

**Date:** 2026-04-19  
**Status:** Approved  
**Scope:** Self-service calendar booking page embedded in AI draft replies for meeting-request emails.

---

## Overview

When InboxIQ detects a meeting-request email and generates a draft reply, it also generates a per-email booking link (`https://kalevent.com/book/<token>`). The visitor (e.g. Rachel from AcmeCorp) clicks the link, sees available slots pulled live from the account's connected Google Calendar or Outlook Calendar, picks a time, and confirms. The calendar event is created automatically; the originating ticket is updated and an auto-reply fires on the thread.

This is a public page — no InboxIQ login required for the visitor.

---

## Data Model

### `Booking` model — `src/models/misc.py`

| Field | Type | Notes |
|---|---|---|
| `id` | UUID string PK | |
| `token_hash` | string, unique, indexed | SHA-256 of signed token — lookup key |
| `account_id` | FK → Account | |
| `ticket_id` | FK → Ticket | |
| `subject` | string | Email subject, shown on booking page |
| `requester_email` | string | Original sender email, pre-fills form |
| `requester_name` | string | Extracted from ticket/email |
| `duration_minutes` | integer | Snapshot of account setting at generation time |
| `status` | string | `pending` → `confirmed` \| `cancelled` \| `expired` |
| `slot_start` | datetime UTC | Set on confirm |
| `slot_end` | datetime UTC | Set on confirm |
| `booked_by_name` | string | Visitor-entered name |
| `booked_by_email` | string | Visitor-entered email |
| `calendar_event_id` | string | External event ID (for future cancellation) |
| `meet_link` | string | Google Meet or Teams URL |
| `confirmed_at` | datetime UTC | |
| `created_at` | datetime UTC | When draft link was generated |

### `AccountFeatureFlags` — new column

- `booking_duration_minutes` (integer, default 30) — configurable per account via settings UI.

**Migration:** `flask db migrate -m "Add Booking model and booking_duration_minutes"`

---

## Token

HMAC-SHA256 signed, 7-day TTL. Payload:

```json
{
  "account_id": 42,
  "ticket_id": "uuid",
  "subject": "Re: Demo request — InboxIQ pricing",
  "requester_email": "rachel@acmecorp.com",
  "requester_name": "Rachel",
  "duration_minutes": 30,
  "exp": 1713600000
}
```

Uses same HMAC pattern as `_make_connect_state` / `_parse_connect_state` in `src/api/v1/auth.py`. Secret from `SECRET_KEY` env var. Stored as SHA-256 hash in `Booking.token_hash`.

---

## Routes

### Public blueprint — `src/booking/routes.py`

#### `GET /book/<token>`

1. Verify HMAC signature — 400 if invalid.
2. Check expiry — 410 Gone if expired.
3. Look up `Booking` by `token_hash`:
   - `confirmed` → show "already booked" page with meet link.
   - `cancelled` → show "this link has been cancelled" page.
4. Fetch live calendar slots:
   - GCal: `src/integrations/gcal.py` → `get_available_slots()`
   - Outlook: `src/integrations/outlook_cal.py` → `get_available_slots()`
5. Render `src/templates/booking/book.html` with subject, requester_email, slots.

#### `POST /book/<token>/confirm`

1. Verify token (same as GET).
2. Load `Booking`, assert `status == "pending"` — 409 if already confirmed (race condition guard).
3. Parse `slot_start` (ISO 8601) from POST body.
4. Detect calendar provider from `InboxConnection` for `account_id`.
5. Create calendar event:
   - GCal: `src/mcp/gcal_mcp.py` → `create_meeting()`
   - Outlook: `src/integrations/outlook_cal.py` → `create_meeting()` *(new function — see below)*
6. In a single `db.session` transaction:
   - Update `Booking`: `status=confirmed`, `slot_start`, `slot_end`, `booked_by_name`, `booked_by_email`, `calendar_event_id`, `meet_link`, `confirmed_at`.
   - Add note to `Ticket`: *"Meeting booked: {slot_start_formatted} via booking page by {booked_by_name}"*
   - Update `Ticket.status` to `"meeting_scheduled"` — this is a new status value; existing values are `new`, `open`, `needs_review`, `auto_handled`, `optional`.
7. Dispatch Celery task: send auto-reply on the original thread — *"Looking forward to our call on {date}. Here's the link: {meet_link}"*
8. Render `src/templates/booking/confirmed.html` with slot details and meet link.

### Internal API — `src/api/v1/booking.py`

#### `POST /api/v1/bookings/generate`

- JWT-authenticated.
- Accepts `ticket_id`, `requester_email`, `requester_name`, `subject`.
- Reads `booking_duration_minutes` from `AccountFeatureFlags`.
- Generates HMAC token, creates `Booking(status=pending)`.
- Returns `{ "booking_url": "https://kalevent.com/book/<token>" }`.

---

## Booking Page UI — `src/templates/booking/book.html`

Public template. No base template inheritance that requires login.

Layout (Option B — Contextual):
- InboxIQ logo + "Book a meeting with {account_name}"
- Amber context banner: **Re: {subject}** / from {requester_email}
- Slot grid: 2-column, each slot shows date + time, selected slot highlighted indigo
- Name field (pre-filled with `requester_name`, editable)
- Email field (pre-filled with `requester_email`, editable)
- "Confirm booking" button → POST to `/book/<token>/confirm`

Confirmation page (`src/templates/booking/confirmed.html`):
- "You're booked!" header
- Slot date/time + meet link button
- "Add to calendar" link (.ics download, generated server-side)

---

## Draft Reply Integration

In the draft reply pipeline (where `get_available_slots_text` is called for meeting-request emails):

1. Call the booking service function directly (same logic as `POST /api/v1/bookings/generate`) to generate a booking URL.
2. Append to draft body:

   > *Schedule a time that works for you: **https://kalevent.com/book/{token}***

The existing `get_available_slots_text` plain-text slot list is removed from the draft body — the booking link replaces it.

---

## Outlook Event Creation — `src/integrations/outlook_cal.py`

New function `create_meeting(account_id, title, start_dt, end_dt, attendee_email, attendee_name)`:

- Uses Microsoft Graph API: `POST /me/events`
- Sets `isOnlineMeeting: true`, `onlineMeetingProvider: "teamsForBusiness"`
- Returns `{ "event_id": "...", "meet_link": "https://teams.microsoft.com/..." }`

---

## Settings UI

In the calendar integrations settings page (`src/templates/settings/integrations.html` or equivalent):

- Add "Default meeting duration" row with a `<select>` — options: 15, 30, 45, 60 minutes.
- Saves via existing settings update endpoint to `AccountFeatureFlags.booking_duration_minutes`.
- Default: 30 minutes.

---

## Features Page — `src/templates/marketing/features.html`

New `<section id="scheduling">` inserted between the drafts section and the automation section.

Content:
- Headline: *"Meeting requested? A booking link is already in the draft."*
- 3-step flow diagram: **AI detects meeting request** → **Booking link embedded in draft reply** → **Visitor picks slot, event created automatically**
- Sub-copy: works with Google Calendar and Outlook Calendar; no Calendly required.

---

## Security

- Token is HMAC-signed — cannot be forged without `SECRET_KEY`.
- `token_hash` stored in DB — token itself never persisted.
- 7-day TTL — expired links return 410.
- Booking page is public but scoped: only shows slots for the account that generated the link.
- POST confirm is idempotent-safe: status check prevents double-booking on concurrent requests.
- No account-level data exposed on the booking page beyond account name and available slots.

---

## Out of Scope (this iteration)

- Booking cancellation / rescheduling UI (calendar_event_id is stored for later).
- Timezone detection / conversion UI (slots shown in account owner's timezone).
- Custom booking page branding.
- Per-link duration override (per-account setting is sufficient).
