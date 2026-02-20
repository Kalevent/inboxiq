# Platform App Registration (Developer Apps)

## The Pattern (Twitter-style)

When a developer wants to connect their system to InboxIQ:

1. Go to Settings → Developer tab → "Request Access"
2. Fill in what they are building, what scopes they need, their callback URL
3. Access approved (auto for low-risk, reviewed for higher-risk)
4. Click "Register New App" → enter a name
5. InboxIQ issues `client_id` + `client_secret` (shown once, copy now)
6. Developer uses those credentials to authenticate API calls
7. Done

That is the entire flow. Same as Twitter, GitHub, Stripe.

---

## The Developer Tab

A new tab in Settings alongside Team, Profile, Billing, Integrations.

Only visible when the account has `developer_access = True` — invisible to
non-technical users by default.

### Access Request — Required Before Credentials Are Issued

A developer cannot register an app until they have completed an access request.
The request collects the minimum information needed to understand and audit
how the API will be used. Same approach as Twitter, GitHub, and Stripe.

**Required fields:**

- Full name and company
- What they are building (free text, required)
- Which data they need access to (scopes — multi-select)
- Callback / webhook URL (where InboxIQ will post events)
- Agreement to API terms of service

Once submitted, access is either auto-approved (low-risk scopes: `intake:write`)
or reviewed by the account owner (higher-risk scopes: `tickets:read`, `decisions:read`).

Only after approval does the developer see the full Developer tab and can
register apps and receive credentials.

**What it contains (post-approval):**

- List of registered apps (name, status, last used)
- Register New App → issues `client_id` + `client_secret`
- Revoke button per app
- API reference and example payloads (docs, not forms)

---

## What Gets Replaced

| Current (messy) | Replaced by |
| --- | --- |
| `IntakeToken` — manually generated tokens, copy/pasted | `RegisteredApp` — `client_id` + `client_secret` |
| Voice: paste Twilio credentials into a form | RegisteredApp with `voice:write` scope |
| Chat: paste API key into a form | RegisteredApp with `chat:write` scope |
| Social: paste WhatsApp API key into a form | RegisteredApp with appropriate scope |
| Webhook/API intake page with example payloads in Settings | API reference moved to Developer tab docs section |

**Not changing:** `WebhookProvider` (Automation Studio outbound — different concern)

---

## New Model

```python
class RegisteredApp(db.Model):
    __tablename__ = "registered_apps"
    id                 = Column(String, primary_key=True)   # UUID
    account_id         = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    name               = Column(String, nullable=False)
    client_id          = Column(String, unique=True)        # public, auto-generated
    client_secret_enc  = Column(String)                     # encrypted, shown once
    webhook_url        = Column(String)                     # optional: InboxIQ posts events here
    webhook_secret_enc = Column(String)                     # HMAC signing key for outbound events
    scopes             = Column(JSON)                       # ["intake:write", "tickets:read"]
    allowed_ips        = Column(JSON)                       # optional
    status             = Column(String, default="active")   # active | suspended
    created_at         = Column(DateTime)
    last_used_at       = Column(DateTime)
```

---

## Files to Change

| File | Lines | Action |
| --- | --- | --- |
| `src/models.py` | 489–515 | Delete `IntakeToken`, add `RegisteredApp` |
| `src/api/v1/intake.py` | 34–89 | Replace `_require_intake_token()` with `_require_registered_app()` |
| `src/api/v1/search.py` | 45–48 | Replace IntakeToken auth with RegisteredApp auth |
| `src/settings/routes.py` | 562–635 | Delete `save_voice` handler |
| `src/settings/routes.py` | 636–699 | Delete `save_social` handler |
| `src/settings/routes.py` | 700–773 | Delete `save_chat` handler |
| `src/settings/routes.py` | 1075–1104 | Replace token generation with RegisteredApp key generation |
| `src/templates/settings/index.html` | 782–838 | Remove Voice credential form |
| `src/templates/settings/index.html` | `integrations_view == 'webhooks'` block | Remove — replaced by Developer tab |

## Files to Create

| File | What it is |
| --- | --- |
| `src/templates/settings/developer.html` | Developer tab: access request form, app list, register, revoke, API docs |
| Add `developer` tab to `src/settings/routes.py` | Same pattern as existing tabs |
| Add `developer_access` to `Account` model | Gates full tab visibility |
| Add `DeveloperAccessRequest` model | Stores submitted request + approval status |

## Files NOT Changing

- `src/api/v1/webhook_providers.py` — Automation Studio outbound, separate concern
- `src/automation/` — untouched
- `src/social_auth/routes.py` — OAuth outbound, already correct

---

## Implementation Phases

### Phase 1 — Additive only (safe to ship, no breaking changes)

- Add `RegisteredApp` model to `src/models.py`
- Add `DeveloperAccessRequest` model to `src/models.py`
- Add `developer_access` boolean to `Account` model
- Build Developer tab in settings: access request form + app registration UI
- Run `flask db migrate`

Nothing existing is touched. New system runs alongside the old one.

### Phase 2 — Auth migration (after Phase 1 is stable in production)

- Update `src/api/v1/intake.py` to accept both `IntakeToken` and `RegisteredApp` credentials
- Update `src/api/v1/search.py` to accept both
- Migrate existing `IntakeToken` rows → `RegisteredApp` with `intake:write` scope
- Notify any existing API users of the new credential format

### Phase 3 — Cleanup (after Phase 2 confirmed stable)

- Delete `IntakeToken` model (`src/models.py` lines 489–515)
- Delete `save_voice` handler (`src/settings/routes.py` lines 562–635)
- Delete `save_social` handler (`src/settings/routes.py` lines 636–699)
- Delete `save_chat` handler (`src/settings/routes.py` lines 700–773)
- Remove webhooks UI block from `src/templates/settings/index.html`
- Remove all `intake_token_set` / `tokens` template vars from settings routes

---

## Priority

**P2** — after multi-tenant OAuth is stable.

Replaces ~500 lines of ad-hoc credential handling with one consistent pattern.
