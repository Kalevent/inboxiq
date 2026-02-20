# Multi-Tenant OAuth Integration Plan

## Problem

All current OAuth integrations (LinkedIn, Twitter, and future ones) are single-tenant:
- One token per provider, shared across the whole system
- Stored against a hardcoded `DEFAULT_ACCOUNT_ID`
- No mechanism for individual users/accounts to connect their own social accounts

This needs to change before InboxIQ can serve multiple customers each with their own LinkedIn, Twitter, Gmail, etc.

## Goal

Each account (and optionally each user within an account) can independently connect their own social/app credentials. InboxIQ acts as the OAuth broker — no Composio or third-party token storage needed.

---

## What Needs to Change

### 1. OAuth Start Routes — Carry `account_id` in State

Currently: state token only contains `nonce | timestamp | pkce_verifier`

New: state token carries `account_id` (and optionally `user_id`)

```
state = nonce | timestamp | account_id | pkce_verifier
```

- `account_id` is injected at the start of the flow (from JWT, session, or signed link)
- The callback reads it back from the verified state — no DB lookup needed mid-flow
- Still HMAC-signed, still stateless, still works behind ALB

### 2. OAuth Callback Routes — Save Per-Account

Currently: hardcoded `DEFAULT_ACCOUNT_ID` lookup

New: use `account_id` extracted from state token to scope the save

```python
existing = InboxConnection.query.filter_by(
    account_id=account_id, provider=provider
).first()
```

### 3. Settings UI — Per-Account Connect Buttons

Each account's settings page shows:
- "Connect LinkedIn" → `/social_auth/linkedin?account_id=...` (signed)
- "Connect Twitter" → `/social_auth/twitter?account_id=...` (signed)
- Connected status pulled from `InboxConnection` scoped to their `account_id`

The `account_id` in the URL must be HMAC-signed (same mechanism as state token) to prevent users connecting to another account's slot.

### 4. Token Retrieval — Scoped by Account

Any code that uses the LinkedIn/Twitter token must scope by `account_id`:

```python
conn = InboxConnection.query.filter_by(
    account_id=current_account_id, provider="linkedin_social", status="connected"
).first()
token = decrypt_value(conn.metadata_json["access_token_enc"])
```

### 5. Token Refresh — Per-Account Background Task

Twitter tokens expire. A Celery task should refresh per-account:

```python
@celery.task
def refresh_twitter_tokens():
    conns = InboxConnection.query.filter_by(provider="twitter_social", status="connected").all()
    for conn in conns:
        # refresh using conn.metadata_json["refresh_token_enc"]
```

---

## InboxConnection Model — Already Supports This

The model already has:
- `account_id` (FK to Account)
- `user_id` (FK to User)
- `provider` (string)
- `metadata_json` (encrypted tokens)
- `status`

No schema changes needed. The multi-tenant work is purely in the routing and retrieval logic.

---

## Migration Path from Current Single-Tenant Setup

1. Existing connections (stored under `DEFAULT_ACCOUNT_ID=2`) remain valid
2. New connections go through the updated flow carrying `account_id` in state
3. `DEFAULT_ACCOUNT_ID` env var becomes unnecessary once all flows are updated
4. Remove `DEFAULT_ACCOUNT_ID` references from `social_auth/routes.py` last

---

## Integrations This Applies To

| Integration | Provider String | Status |
|---|---|---|
| LinkedIn | `linkedin_social` | Connected (single-tenant) → needs multi-tenant |
| Twitter/X | `twitter_social` | Not yet connected → build multi-tenant from the start |
| Gmail / Google | `google_oauth` | Future |
| HubSpot | `hubspot_oauth` | Future |
| Any future OAuth app | `{name}_oauth` | Follow same pattern |

---

## Priority

**P1** — Before InboxIQ onboards a second customer that needs social publishing.

The single-tenant setup works for the current single-account deployment but will block growth.
