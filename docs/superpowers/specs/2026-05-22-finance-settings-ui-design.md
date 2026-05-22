# Finance Add-on Settings UI — Design Spec

## Goal

Add a Finance Add-on sub-section to Settings → Integrations that lets every user discover and configure the Stripe → QuickBooks automation. Non-subscribers see an upgrade gate; subscribers complete a 3-step JS wizard to activate.

---

## Decisions Made

| Question | Decision |
| -------- | -------- |
| Where in settings? | Sub-section inside existing Integrations tab (`integrations_view='finance'`) |
| Who sees it? | Everyone — upgrade gate shown if add-on not active |
| Layout | JS show/hide step wizard (no page reloads) |
| Step 3 for CSV export | No extra input — weekly CSV sent to account owner's email as attachment |
| Google Drive / OneDrive? | Out of scope — user decides what to do with the emailed attachment |

---

## UI States

### State 0 — Upgrade gate (add-on not active)

Shown to all users whose `AccountAddOn` for `finance` does not exist or has `status != 'active'`.

Content:

- ⚡ Finance Add-on heading
- Short value prop: "Automate Stripe payments into QuickBooks — sync transactions in real time or receive weekly CSV exports."
- Three feature pills: "Stripe webhook", "QuickBooks sync", "Weekly CSV export"
- Primary CTA: **Upgrade to unlock →** — links to `/billing/upgrade`
- Sub-label: "Included in Pro and above"

### Step 1 — Connect Stripe

- Progress indicator: `1 — 2 — 3` (step 1 highlighted)
- Heading: "Connect your Stripe webhook"
- Subtext: "Select the Stripe provider that receives your payment events."
- `<select>` dropdown populated with all `WebhookProvider` rows where `provider_type='stripe'` and `account_id` matches
- Link below dropdown: "+ Add a new Stripe provider first →" — links to `integrations_view='webhooks'`
- **Next: Choose output →** button advances to step 2

### Step 2+3 — Choose mode (dynamic)

Step 2 and 3 are rendered together; step 3 content changes based on mode selection.

- Progress indicator: step 1 shown as ✓ (green), steps 2 and 3 highlighted amber
- **Mode toggle** (two cards, mutually exclusive):
  - ⚡ Direct sync — "Real-time QB API"
  - 📎 CSV export — "Weekly email"
- Selecting a mode swaps the step 3 content below:

**Direct sync selected (step 3):**

- Label: "QuickBooks provider"
- Subtext: "Select the QuickBooks provider to post transactions to."
- `<select>` dropdown populated with `WebhookProvider` rows where `provider_type='quickbooks'`
- Link: "+ Add a new QuickBooks provider first →"

**CSV export selected (step 3):**

- Label: "Ready to activate"
- Read-only confirmation box showing account owner's email address
- Sub-line: "Every Monday at 08:00 UTC · Intuit-compatible format"
- No user input required

- **← Back** link returns to step 1
- **Activate add-on ⚡** button submits

### State 4 — Already active (post-setup summary)

Shown when `AccountAddOn.status == 'active'`.

- Heading: "⚡ Finance Add-on · Active" (green)
- Transaction count: "N transactions processed this month" (from `AccountAddOn.transaction_count`)
- Two info cards side by side: Stripe provider name | Output mode
- **Reconfigure** button — hides the summary and shows the wizard at step 1 (client-side only; the add-on remains active until the user submits the wizard again, which upserts the config via `POST /api/v1/addons/finance/activate`)
- **Deactivate** button — calls `POST /api/v1/addons/finance/deactivate`, reloads page

---

## Backend

### Route change — `GET /settings/integrations` with `?finance` param

Extend the existing `integrations_webhooks()` route (or the general settings route) to recognise `integrations_view='finance'` and pass:

```python
finance_addon=AccountAddOn.query.filter_by(
    account_id=account_id, addon_type='finance'
).first(),
stripe_providers=WebhookProvider.query.filter_by(
    account_id=account_id, provider_type='stripe', enabled=True
).all(),
qb_providers=WebhookProvider.query.filter_by(
    account_id=account_id, provider_type='quickbooks', enabled=True
).all(),
```

No new POST handler needed — the wizard submits via `fetch` to the existing API endpoints.

### API calls (existing endpoints from Plan A)

| Action | Endpoint |
| ------ | -------- |
| Activate / reconfigure | `POST /api/v1/addons/finance/activate` |
| Deactivate | `POST /api/v1/addons/finance/deactivate` |
| Read status | `GET /api/v1/addons/finance` |

Activate payload:

```json
{
  "stripe_provider_id": "<uuid>",
  "mode": "direct_sync | csv_export",
  "quickbooks_provider_id": "<uuid>"
}
```

### Sidebar nav entry

Add to the Integrations sub-nav (left panel inside the Integrations tab):

```html
<a href="{{ url_for('settings.integrations_webhooks') }}?view=finance">
  ⚡ Finance Add-on
</a>
```

Highlight when `integrations_view == 'finance'`.

---

## JS Behaviour

All wizard logic lives in a `<script>` block at the bottom of the `{% elif integrations_view == 'finance' %}` section. No global state.

```text
financeStep = 1

showStep(n)        — hide all .finance-step divs, show #finance-step-{n}
selectMode(mode)   — toggle amber border on mode cards, show correct step-3 content
activateAddon()    — POST /api/v1/addons/finance/activate, on success reload page
deactivateAddon()  — POST /api/v1/addons/finance/deactivate, on success reload page
```

Back/Next buttons call `showStep()` directly. No routing, no state machine.

---

## Template structure

```jinja
{% elif integrations_view == 'finance' %}

  {# State 0: upgrade gate — shown if not active #}
  <div id="finance-gate" class="{{ 'hidden' if finance_addon_active }}">
    ...upgrade CTA...
  </div>

  {# Wizard — shown if active or after upgrade #}
  <div id="finance-wizard" class="{{ 'hidden' if not finance_addon_active }}">

    {# Step 1 #}
    <div class="finance-step" id="finance-step-1"> ... </div>

    {# Steps 2+3 combined #}
    <div class="finance-step hidden" id="finance-step-2"> ... </div>

    {# Already active summary #}
    <div id="finance-summary" class="{{ 'hidden' if not finance_addon_active }}"> ... </div>

  </div>

{% endif %}
```

`finance_addon_active` is a boolean passed from the route: `finance_addon and finance_addon.status == 'active'`.

---

## Upgrade gate logic

The gate is purely frontend-conditional on `finance_addon_active`. No separate middleware. If a user with no subscription somehow reaches the wizard and submits, `POST /api/v1/addons/finance/activate` returns `402` — the JS shows a toast and redirects to `/billing/upgrade`.

---

## Out of scope

- Email address customisation for CSV export (sends to account owner's email only)
- Google Drive / OneDrive integration
- Frequency selection (fixed: every Monday 08:00 UTC)
- In-page provider creation (links out to Webhooks sub-view)
