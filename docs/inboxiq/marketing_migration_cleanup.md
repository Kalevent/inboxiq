Before you start add the marking link to the drop don even # Marketing Ops Migration — Admin Cleanup Reference

Items to remove from `admin.html` and the admin blueprint **after** `/marketing` is live and verified.
Do not remove anything until the new `marketing_ops.html` is deployed and tested.

---

## 1. Template `{% include %}` Statements to Remove

File: `src/templates/admin.html`

| Line | Statement | Reason |
|------|-----------|--------|
| 179  | `{% include 'admin/section_funnel.html' %}` | Moves to `/marketing/funnel` |
| 182  | `{% include 'admin/section_content.html' %}` | Moves to `/marketing/content` |
| 191  | `{% include 'admin/section_marketing.html' %}` | Moves to `/marketing/marketing` |
| 194  | `{% include 'admin/section_campaigns.html' %}` | Moves to `/marketing/campaigns` |

**Retained includes (do not touch):**
- Line 176 — `section_overview.html`
- Line 185 — `section_trial.html`
- Line 188 — `section_saas.html`
- Line 197 — `section_ai.html`
- Line 200 — `section_developer.html`
- Line 202 — `section_system.html`
- Line 211 — `partials/feedback_footer.html`

---

## 2. Sidebar Nav Items to Remove

File: `src/templates/admin.html` (sidebar `<nav>` block, lines ~119–170)

| Line | `data-section` | Label |
|------|----------------|-------|
| 124  | `funnel`       | Funnel v2.0 |
| 130  | `content`      | Content |
| 146  | `marketing`    | Marketing |
| 151  | `campaigns`    | Email Outreach |

**Replace with:** A single crosslink entry, e.g.:
```html
<li>
  <a href="/marketing" class="...">
    ↗ Marketing Ops
  </a>
</li>
```

**Retained sidebar items (do not touch):** Overview, Trial Onboarding, SaaS Metrics, AI & Training, Developer, System.

---

## 3. Inline JavaScript to Remove

All JS lives in one `<script>` block starting at line 217. Remove these ranges:

| Approx. Lines | Functions / Block | Section |
|---------------|-------------------|---------|
| 299–550       | `loadFunnelMetrics()`, `qualifyLead()`, `updateInterestScore()`, `moveLeadStage()`, `runOrchestration()`, `checkProgression()`, `discoverLeads()`, `refreshLeads()`, lead picker helpers (`leadPickerSearch`, `leadPickerSelect`) | Funnel v2.0 |
| 651–800       | `loadMarketingData()`, A/B test rendering, nurture stats helpers | Marketing (nurture) |
| 1527–1867     | `_campHeaders()`, `_statusBadge()`, `_campNote()`, `_campActions()`, `loadCampaignsData()`, `campaignAction()`, `openExtendModal()`, `saveExtendLimit()`, `createCampaign()`, `toggleCampPanel()`, `loadCampaignStats()`, `loadCampaignOutreaches()` | Email Campaigns |

> **Note:** Content section JS (blog/KB generation) is also in this block. Identify its range when reading the file; it will also move to `/marketing/content`.

**Retained JS (do not touch):**
- Lines 218–297 — Sidebar navigation click handlers + CSRF utility
- Lines 551–650 — Trial section (`loadTrialMetrics()`, etc.)
- Lines 801–950 — SaaS Metrics (`loadSaasMetrics()`, `loadSpendEntries()`)
- Lines 951–1525 — Developer section (`loadDevRequests()`, `reviewDevRequest()`)

---

## 4. Partial Template Files — Status After Migration

These files move **wholesale** into `marketing_ops.html` via the same `{% include %}` pattern.
They are **not deleted** — they are reused by the new template unchanged.

| File | Migrates To | Delete After? |
|------|-------------|---------------|
| `src/templates/admin/section_funnel.html` | `marketing_ops.html` | **No** — keep, just re-included from new template |
| `src/templates/admin/section_content.html` | `marketing_ops.html` | **No** |
| `src/templates/admin/section_marketing.html` | `marketing_ops.html` | **No** |
| `src/templates/admin/section_campaigns.html` | `marketing_ops.html` | **No** |

> Consider moving them to `src/templates/marketing/` in a future cleanup pass, but this is optional — the includes work regardless of location.

---

## 5. API Endpoints — Dual-Mode Auth Changes Required

These endpoints currently gate on `_require_admin()`. After migration, non-admin users
accessing `/marketing` need to reach them scoped to their `account_id`.

### `src/api/v1/outreach.py`

| Method | Path | Change |
|--------|------|--------|
| GET    | `/api/v1/outreach/campaigns` | Dual-mode: admin sees all, JWT user sees own account |
| POST   | `/api/v1/outreach/campaigns` | Dual-mode |
| PATCH  | `/api/v1/outreach/campaigns/<id>` | Dual-mode |
| POST   | `/api/v1/outreach/campaigns/<id>/send` | Dual-mode |

### `src/api/v1/admin_funnel.py`

| Method | Path | Change |
|--------|------|--------|
| POST   | `/api/v1/admin/funnel/qualify-lead` | Dual-mode |
| POST   | `/api/v1/admin/funnel/move-stage` | Dual-mode |
| POST   | `/api/v1/admin/funnel/update-interest` | Dual-mode |
| POST   | `/api/v1/admin/funnel/discover-leads` | Dual-mode |
| GET    | `/api/v1/admin/funnel/leads` | Already has `?q=` search; add account_id filter for non-admin |

### `src/api/v1/admin_marketing.py` — New per-tenant endpoints to add

| Method | Path | Description |
|--------|------|-------------|
| GET    | `/api/v1/marketing/ab-results` | Same as admin version, scoped to JWT `account_id` |
| GET    | `/api/v1/marketing/nurture-stats` | Same, scoped to JWT `account_id` |

---

## 6. New Blueprint / Route to Create

| File | Status |
|------|--------|
| `src/marketing_ops/__init__.py` | **Done** (empty) |
| `src/marketing_ops/routes.py` | **Pending** — `GET /marketing` + `GET /marketing/<section>` with `@login_required_settings` |
| `src/templates/marketing_ops.html` | **Pending** — standalone dark-theme SPA |
| Register in `src/app.py` | **Pending** |

---

## 7. Header Nav Change

File: wherever the logged-in user header dropdown is rendered (check `src/templates/base.html` or `src/templates/dashboard.html`).

Add a **Marketing** dropdown with these links:
- Funnel → `/marketing/funnel`
- Email Outreach → `/marketing/campaigns`
- Nurture & A/B → `/marketing/marketing`
- Content → `/marketing/content`

---

## 8. Summary Count

After migration is complete and verified:
- **4 `{% include %}` lines** removed from `admin.html`
- **4 sidebar `<li>` / `<button>` elements** removed from `admin.html`
- **~800 lines of inline JS** removed from `admin.html` (funnel + marketing + campaigns + content blocks)
- **0 partial files deleted** (reused by new template)
- **admin.html shrinks from ~1870 → ~900 lines**
