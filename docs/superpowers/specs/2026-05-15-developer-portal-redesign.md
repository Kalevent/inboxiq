# Developer Portal Redesign — Settings → Developer

**Date:** 2026-05-15
**Scope:** Frontend redesign of `Settings → Developer` tab + new `AppProductAccess` model + admin updates. Backend authentication (`app_auth.py`, `RegisteredApp` credentials, intake API) is unchanged.

---

## Goal

Replace the current linear "request access → wait → register app" flow with a LinkedIn-style developer portal where users:

1. Create apps immediately (self-service, no prior approval gate)
2. Browse a product catalog inside each app
3. Request access per-product — each product has its own approval and its own webhook URL
4. One product request per app per product (duplicate requests blocked)

---

## Architecture

### New model — `AppProductAccess` (`src/models/developer.py`)

```python
class AppProductAccess(db.Model):
    __tablename__ = "app_product_access"
    __table_args__ = (
        db.UniqueConstraint("app_id", "product_slug", name="uq_app_product"),
    )

    id           = db.Column(db.String(64), primary_key=True, default=lambda: str(uuid4()))
    app_id       = db.Column(db.String(64), db.ForeignKey("registered_apps.id", ondelete="CASCADE"), nullable=False)
    account_id   = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=False)
    product_slug = db.Column(db.String(64), nullable=False)   # "chat" | "forms" | "intake_api"
    status       = db.Column(db.String(32), nullable=False, default="pending")  # pending | approved | rejected
    use_case     = db.Column(db.Text, nullable=True)
    webhook_url  = db.Column(db.String(2048), nullable=True)
    requested_at = db.Column(db.DateTime(timezone=True), server_default=func.now(), nullable=False)
    approved_at  = db.Column(db.DateTime(timezone=True), nullable=True)
    reviewed_by  = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
```

### Static product catalog — `src/developer/products.py` (new file)

Defines the 3 launch products. `approval` controls whether admin review is required.

```python
PRODUCT_CATALOG = [
    {
        "slug": "chat",
        "name": "Chat / Aria Widget",
        "icon": "💬",
        "description": "Embed an AI-powered chat widget on your site or app.",
        "approval": "reviewed",
    },
    {
        "slug": "forms",
        "name": "External Forms",
        "icon": "📋",
        "description": "Route external form submissions into InboxIQ triage.",
        "approval": "reviewed",
    },
    {
        "slug": "intake_api",
        "name": "Intake API",
        "icon": "📥",
        "description": "Submit tickets and messages directly into InboxIQ.",
        "approval": "auto",   # auto-approved on request
    },
]
```

### Existing models (unchanged)

- `RegisteredApp` — credentials (`client_id`, `client_secret_enc`) unchanged; `webhook_url` field on the model is superseded by per-product webhooks but left in place for backward compatibility
- `DeveloperAccessRequest` — kept in DB; the settings UI no longer gates app creation on it, but existing approved records are left intact
- `app_auth.py` — HTTP Basic Auth logic unchanged

---

## Settings Routes (`src/settings/routes.py`)

### Gate change

Remove the `developer_access_request.status == 'approved'` check that currently gates `register_app`. Any account with `account.developer_access = True` can now register apps directly.

### New/changed POST actions on `POST /settings/developer`

| `action` | Params | Behaviour |
| --- | --- | --- |
| `register_app` | `app_name` | Existing — keep, remove approval gate |
| `revoke_app` | `app_id` | Existing — keep |
| `request_product` | `app_id`, `product_slug`, `use_case` | New — creates `AppProductAccess(status="pending")`. If `approval=="auto"` set `status="approved"` immediately. Enforce unique constraint: 409 if already exists. |
| `update_webhook` | `app_id`, `product_slug`, `webhook_url` | New — only succeeds if `AppProductAccess.status == "approved"`. Validates URL format. |

### GET `/settings?tab=developer`

Passes to template:

- `registered_apps` — all apps for account
- `selected_app` — `RegisteredApp` matching `?app_id=` query param (or first app if omitted; `None` if account has no apps yet → show empty state with "Register your first app" prompt)
- `product_accesses` — `AppProductAccess` records for `selected_app`, keyed by `product_slug`
- `product_catalog` — from `PRODUCT_CATALOG`

---

## Template (`src/templates/settings/index.html` — developer section)

The developer section is **completely rewritten**. The rest of `settings/index.html` is untouched.

### Layout — two-panel

```text
┌─────────────────────────────────────────────────────────────┐
│  [sidebar: app list]  │  [main: selected app detail]         │
│                       │                                      │
│  ● CRM Sync           │  CRM Sync                            │
│    Support Bot        │  client_id: app_7f3a... [Copy]       │
│                       │  secret: ●●●●●●  [Reveal / Rotate]   │
│  [+ New App]          │                                      │
│                       │  PRODUCTS                            │
│                       │  💬 Chat / Aria Widget  [Approved ✓]  │
│                       │     Webhook: https://...  [Edit]     │
│                       │                                      │
│                       │  📋 External Forms  [Under review]   │
│                       │     Webhook locked until approved    │
│                       │                                      │
│                       │  📥 Intake API  [Request Access]     │
└─────────────────────────────────────────────────────────────┘
```

On mobile: sidebar collapses to a `<select>` dropdown above the main panel.

### Light / dark mode

All new code uses dual Tailwind classes. Pattern:

```html
<!-- background -->
bg-white dark:bg-slate-900

<!-- border -->
border-slate-200 dark:border-slate-700

<!-- primary text -->
text-slate-900 dark:text-slate-100

<!-- secondary text -->
text-slate-500 dark:text-slate-400

<!-- card -->
bg-slate-50 dark:bg-slate-900/70 border border-slate-200 dark:border-slate-800

<!-- active sidebar item -->
bg-indigo-50 dark:bg-indigo-500/10 text-indigo-700 dark:text-indigo-300 border-indigo-300 dark:border-indigo-400/40
```

### Product access states (per-product within an app)

- **Not requested** — dashed border card, "Request Access" button opens inline form (use_case textarea + submit)
- **Pending** — amber badge "Under review", webhook field locked with greyed hint text
- **Approved** — green badge "Approved", webhook URL input editable inline, Edit/Save buttons
- **Rejected** — red badge "Not approved", contact support link

### New App flow

"+ New App" in sidebar opens an inline form (not a modal): name input + Register button. On success, page reloads with `?tab=developer&app_id=<new_id>` and credential modal fires.

### Credentials display (inside selected app)

Shows `client_id` with a Copy button. No secret display — the secret was shown once in the credential modal at creation time and cannot be retrieved. A small note reads: "Secret was shown once at creation. Revoke and re-register the app if you've lost it."

### Credential modal (fires immediately after app creation)

Unchanged from current implementation — amber warning, one-time secret display, checkbox confirm before dismiss.

---

## Admin (`src/templates/admin/section_developer.html` + `src/api/v1/admin.py`)

### New admin section: Product Access Requests

Add below the existing "Access Requests" panel. Lists all `AppProductAccess` records with `status="pending"`, grouped by account. Each row shows:

- Account name / ID
- App name
- Product slug
- Use case text
- Approve / Reject buttons

### New admin API endpoints (`src/api/v1/admin.py`)

```text
GET  /api/v1/admin/developer/product-requests     → list pending AppProductAccess
POST /api/v1/admin/developer/product-requests/<id>/review  → { "status": "approved"|"rejected" }
```

On approve: set `status="approved"`, `approved_at=now()`, `reviewed_by=admin_user_id`.

---

## Migration

One new table. Tell user to run:

```bash
flask db migrate -m "add app_product_access table"
flask db upgrade
```

---

## Out of scope

- Pricing / billing per product (product tier prices will be added later)
- Converting the rest of `settings/index.html` to light mode (developer section only gets dual-mode now; full settings page light-mode conversion is a separate task)
- Webhook delivery / retry logic (existing webhook plumbing unchanged)
- `decisions:read` and `tickets:read` scopes from `DeveloperAccessRequest` — not surfaced in product catalog yet
