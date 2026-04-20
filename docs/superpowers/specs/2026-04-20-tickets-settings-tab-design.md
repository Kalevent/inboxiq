# Tickets Settings Tab — Design Spec

**Date:** 2026-04-20  
**Status:** Approved  
**Scope:** Add a Tickets tab to the Settings page where customers can search, filter, view, and lightly manage their tickets.

---

## Overview

Customers currently have no self-service way to browse or manage the tickets InboxIQ has processed on their account. This feature adds a "Tickets" tab to the existing Settings page, giving every account a searchable, filterable ticket list with a detail view and lightweight actions (resolve / close).

Webhook delivery of tickets is explicitly out of scope — deferred to a later phase based on user demand.

---

## Approach

Pure server-rendered, session-authenticated routes added to `src/settings/routes.py`. Follows the existing settings pattern: `@login_required_settings`, scoped by `g.current_account_id`, Jinja templates extending the settings layout. No new API endpoints. No JS framework.

---

## Routes

```
GET  /settings/tickets                       → list view
GET  /settings/tickets/<ticket_id>           → detail view
POST /settings/tickets/<ticket_id>/resolve   → mark resolved
POST /settings/tickets/<ticket_id>/close     → close ticket
```

All routes are protected by `@login_required_settings` and scope every query to `g.current_account_id`.

The string `"tickets"` is added to the allowed tab set in the existing `settings_page()` route so the sidebar nav link highlights correctly when the user is on any tickets route.

Filters persist in the URL as GET query params so the browser back button from a detail page returns to the same filtered list:  
`?q=&status=&category=&priority=&from=&to=&page=`

---

## List Page (`/settings/tickets`)

### Filter Bar

Rendered as a `<form method="GET">` above the table. Fields:

| Field | Type | Backend column |
|---|---|---|
| Search | Text input | `search_vec` tsvector (existing) |
| Status | Dropdown | `Ticket.status` |
| Category | Dropdown | `Ticket.category` |
| Priority | Dropdown | `Ticket.priority` |
| From date | Date input | `Ticket.created_at >=` |
| To date | Date input | `Ticket.created_at <=` |

Status options: All / New / Open / Auto-handled / Needs review / Resolved / Closed  
Priority options: All / P0 / P1 / P2 / P3 / P4  
Category options: All / Support / Transactional / Scheduling / Billing / Spam / Other (static list matching known triage label categories)

Submit button: "Search". Clear link resets all params.

### Ticket Table

Columns: Subject (truncated to 80 chars) | From email | Category | Priority (badge) | Status (badge) | Date (relative, e.g. "2h ago")

- Each row links to `/settings/tickets/<id>?back=<encoded_filter_url>`
- Sort: priority ascending (P0 first), then `created_at DESC`

### Pagination

- Page size: 25 tickets per page
- Previous / Next links carry all active filter params
- Count display: "Showing 26–50 of 143 tickets"

### Empty State

Message: "No tickets found for these filters." with a "Clear filters" link.

---

## Detail Page (`/settings/tickets/<ticket_id>`)

### Header

- Page title: ticket subject
- "← Back to tickets" link — uses `back` query param if present, otherwise `/settings/tickets`
- Status badge (colour-coded: green=resolved, yellow=needs_review, blue=new/open, grey=auto_handled/closed)

### Layout — Two Columns

**Left (primary):**
- From email
- Received date/time (full timestamp)
- Provider (Gmail / Outlook / Webhook)
- Category, priority, sentiment
- Body preview (full text, not truncated)
- AI-generated summary (if present)

**Right (sidebar):**
- Triage decision: action_required, intent, risk_flag (from `decision` JSON)
- Assigned to / team (if set)
- LLM model + token cost — **staff accounts only** (uses `_is_staff_account()` from settings/routes.py)

### Actions

Two POST forms at the bottom of the page:

- **"Mark as Resolved"** → `POST /settings/tickets/<id>/resolve` → sets `status = "resolved"`
- **"Close ticket"** → `POST /settings/tickets/<id>/close` → sets `status = "closed"`

Both forms include a CSRF token. Both buttons are hidden when ticket status is already `resolved` or `closed`. On success, redirect back to detail page with a flash message. On failure, rollback and flash an error.

> **Note:** `resolved` and `closed` are two new status values introduced by this feature. The existing Ticket model statuses are `new`, `open`, `auto_handled`, `optional`, `needs_review`, `meeting_scheduled`. No migration is needed — `status` is a free-form `String(32)` column — but the list page filter dropdown and any existing status-based logic must account for these two new values.

---

## Templates

| File | Purpose |
|---|---|
| `src/templates/settings/tickets_list.html` | List page — extends settings layout |
| `src/templates/settings/tickets_detail.html` | Detail page — extends settings layout |

Both use existing badge/pill CSS classes for status and priority colours. No new CSS required.

---

## Security

- Every query filters by `account_id = g.current_account_id` — cross-account access is impossible even by guessing a UUID
- Resolve/close routes look up the ticket with `account_id` filter before updating; return 404 if not found or wrong account
- All `db.session.commit()` calls wrapped in try/except with rollback
- CSRF token on all POST forms
- LLM cost data shown to staff accounts only

---

## Error Handling

| Scenario | Behaviour |
|---|---|
| Invalid ticket_id on detail route | 404 |
| Ticket already resolved/closed on action submit | Redirect to detail, flash "Ticket is already {status}" |
| DB failure on resolve/close | Rollback, flash error, redirect back to detail |
| No tickets match filters | Empty state message with clear link |

---

## Out of Scope (Deferred)

- Outbound webhook delivery of tickets to customer systems
- Inbound API polling via registered app key (partially covered by Developer tab)
- Bulk actions (resolve all, export)
- Ticket reply / draft management from this view
