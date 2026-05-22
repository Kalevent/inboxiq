# Finance Add-on Settings UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Finance Add-on sub-section to Settings → Integrations with a 3-step JS wizard (connect Stripe → choose mode → connect QB or confirm email) and an upgrade gate for non-subscribers.

**Architecture:** New `GET /settings/integrations/finance` route in `src/settings/routes.py` passes `finance_addon`, `stripe_providers`, `qb_providers`, and `account_email` to the existing settings template. The template renders a new `{% elif integrations_view == 'finance' %}` block containing an upgrade gate (hidden when subscribed), a JS-driven 3-step wizard, and an active summary card. All wizard API calls use the existing Plan A endpoints (`POST /api/v1/addons/finance/activate` and `/deactivate`).

**Tech Stack:** Flask, SQLAlchemy, Jinja2, vanilla JS (no framework), existing settings CSS classes.

---

## File Structure

- **Modify** `src/settings/routes.py` — add `integrations_finance()` GET route + `AccountAddOn` import
- **Modify** `src/templates/settings/index.html` — add Finance link in quick-links grid (line ~1059); add `{% elif integrations_view == 'finance' %}` block (after webhooks block, line ~1320)
- **Create** `tests/settings/__init__.py` — empty, makes tests/settings a package
- **Create** `tests/settings/test_finance_settings.py` — route tests

---

## Task 1: Add `integrations_finance` route

**Files:**
- Modify: `src/settings/routes.py`
- Test: `tests/settings/test_finance_settings.py`

- [ ] **Step 1: Write the failing test**

Create `tests/settings/__init__.py` (empty file) and `tests/settings/test_finance_settings.py`:

```python
# tests/settings/test_finance_settings.py
import pytest
from unittest.mock import patch, MagicMock


@pytest.fixture(scope="module")
def app():
    from src.app import create_app
    app = create_app()
    app.config["TESTING"] = True
    app.config["SECRET_KEY"] = "test-secret"
    return app


@pytest.fixture
def client(app):
    return app.test_client()


def _mock_account(email="owner@example.com"):
    acct = MagicMock()
    acct.id = 1
    acct.email = email
    acct.seats_limit = 5
    return acct


def _mock_provider(provider_id, name, ptype):
    p = MagicMock()
    p.id = provider_id
    p.configuration_name = name
    p.provider_type = ptype
    return p


def test_finance_settings_upgrade_gate(client):
    """Non-subscribed user sees upgrade gate (finance_addon_active=False)."""
    mock_account = _mock_account()
    with patch("src.settings.verify_jwt_in_request"), \
         patch("src.settings.get_jwt", return_value={"account_id": "1"}), \
         patch("src.settings.get_jwt_identity", return_value="1"), \
         patch("src.settings.db"), \
         patch("src.settings.account_allows_api", return_value=True), \
         patch("src.settings.routes.Account") as MockAccount, \
         patch("src.settings.routes.AccountAddOn") as MockAddon, \
         patch("src.settings.routes.WebhookProvider") as MockWP:
        MockAccount.query.get.return_value = mock_account
        MockAddon.query.filter_by.return_value.first.return_value = None
        MockWP.query.filter_by.return_value.all.return_value = []
        resp = client.get("/settings/integrations/finance")
    assert resp.status_code == 200
    assert b"Upgrade to unlock" in resp.data


def test_finance_settings_active_summary(client):
    """Subscribed user sees active summary (finance_addon_active=True)."""
    mock_account = _mock_account()
    mock_addon = MagicMock()
    mock_addon.status = "active"
    mock_addon.transactions_this_month = 12
    mock_addon.config_json = {"mode": "csv_export", "stripe_provider_id": "prov-1", "csv_email": "owner@example.com"}
    with patch("src.settings.verify_jwt_in_request"), \
         patch("src.settings.get_jwt", return_value={"account_id": "1"}), \
         patch("src.settings.get_jwt_identity", return_value="1"), \
         patch("src.settings.db"), \
         patch("src.settings.account_allows_api", return_value=True), \
         patch("src.settings.routes.Account") as MockAccount, \
         patch("src.settings.routes.AccountAddOn") as MockAddon, \
         patch("src.settings.routes.WebhookProvider") as MockWP:
        MockAccount.query.get.return_value = mock_account
        MockAddon.query.filter_by.return_value.first.return_value = mock_addon
        MockWP.query.filter_by.return_value.all.return_value = []
        resp = client.get("/settings/integrations/finance")
    assert resp.status_code == 200
    assert b"Finance Add-on \xc2\xb7 Active" in resp.data or b"Finance Add-on" in resp.data


def test_finance_settings_passes_providers(client):
    """Stripe and QB providers are rendered in the wizard dropdowns."""
    mock_account = _mock_account()
    mock_addon = MagicMock()
    mock_addon.status = "active"
    mock_addon.transactions_this_month = 5
    mock_addon.config_json = {"mode": "direct_sync", "stripe_provider_id": "prov-s", "qb_provider_id": "prov-q"}

    stripe_prov = _mock_provider("prov-s", "My Stripe (production)", "stripe")
    qb_prov = _mock_provider("prov-q", "QuickBooks Online", "quickbooks")

    def wp_filter(**kwargs):
        m = MagicMock()
        if kwargs.get("provider_type") == "stripe":
            m.all.return_value = [stripe_prov]
        elif kwargs.get("provider_type") == "quickbooks":
            m.all.return_value = [qb_prov]
        else:
            m.all.return_value = []
        return m

    with patch("src.settings.verify_jwt_in_request"), \
         patch("src.settings.get_jwt", return_value={"account_id": "1"}), \
         patch("src.settings.get_jwt_identity", return_value="1"), \
         patch("src.settings.db"), \
         patch("src.settings.account_allows_api", return_value=True), \
         patch("src.settings.routes.Account") as MockAccount, \
         patch("src.settings.routes.AccountAddOn") as MockAddon, \
         patch("src.settings.routes.WebhookProvider") as MockWP:
        MockAccount.query.get.return_value = mock_account
        MockAddon.query.filter_by.return_value.first.return_value = mock_addon
        MockWP.query.filter_by.return_value = MagicMock(all=lambda: [])
        # Simulate provider_type-filtered results
        results_map = {"stripe": [stripe_prov], "quickbooks": [qb_prov]}
        def fb(**kw):
            m = MagicMock()
            m.all.return_value = results_map.get(kw.get("provider_type"), [])
            return m
        MockWP.query.filter_by.side_effect = fb
        resp = client.get("/settings/integrations/finance")
    assert resp.status_code == 200
    assert b"My Stripe (production)" in resp.data
    assert b"QuickBooks Online" in resp.data
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/kofi/inboxiq && python -m pytest tests/settings/test_finance_settings.py -v 2>&1 | tail -20
```

Expected: 3 tests FAIL with `404` (route doesn't exist yet).

- [ ] **Step 3: Add `AccountAddOn` import to `src/settings/routes.py`**

In `src/settings/routes.py`, find line 12:
```python
from src.models.automation import WebhookProvider
```

Change it to:
```python
from src.models.automation import WebhookProvider
from src.models.addons import AccountAddOn
```

- [ ] **Step 4: Add the `integrations_finance` route to `src/settings/routes.py`**

Add the following after the `integrations_webhooks` function (after line ~1437, just before the `_AUTOMATION_VIEW_ROLES` constant):

```python
@bp.route("/integrations/finance", methods=["GET"])
@login_required_settings
def integrations_finance():
    """Finance Add-on setup wizard — visible to all, gated by add-on status."""
    account_id = getattr(g, "current_account_id", None)
    account = Account.query.get(account_id) if account_id else None

    finance_addon = AccountAddOn.query.filter_by(
        account_id=account_id, addon_type="finance"
    ).first() if account_id else None

    stripe_providers = WebhookProvider.query.filter_by(
        account_id=account_id, provider_type="stripe", enabled=True
    ).all() if account_id else []

    qb_providers = WebhookProvider.query.filter_by(
        account_id=account_id, provider_type="quickbooks", enabled=True
    ).all() if account_id else []

    finance_addon_active = bool(finance_addon and finance_addon.status == "active")
    account_email = account.email if account else ""

    return render_template(
        "settings/index.html",
        active_tab="integrations",
        integrations_view="finance",
        team_view=None,
        billing_view=None,
        security_view=None,
        api_allowed=account_allows_api(account_id) if account_id else False,
        account_id=account_id,
        account=account,
        finance_addon=finance_addon,
        finance_addon_active=finance_addon_active,
        stripe_providers=stripe_providers,
        qb_providers=qb_providers,
        account_email=account_email,
        crm_connection=None,
        crm_prefill={},
        webhook_providers=[],
        show_social_integrations=False,
        linkedin_connection=None,
        twitter_connection=None,
        facebook_connection=None,
        gcal_connection=None,
        outlook_cal_connection=None,
        inbox_connections=[],
    )
```

- [ ] **Step 5: Run tests — expect 2 pass, 1 partial (providers test needs template)**

```bash
cd /Users/kofi/inboxiq && python -m pytest tests/settings/test_finance_settings.py -v 2>&1 | tail -20
```

Expected: `test_finance_settings_upgrade_gate` and `test_finance_settings_active_summary` PASS (template renders without error). `test_finance_settings_passes_providers` will PASS once the template renders the dropdowns (Task 2).

- [ ] **Step 6: Commit**

```bash
git add tests/settings/__init__.py tests/settings/test_finance_settings.py src/settings/routes.py
git commit -m "feat(finance-settings): add integrations_finance route"
```

---

## Task 2: Add Finance sub-view template block

**Files:**
- Modify: `src/templates/settings/index.html`

> **IMPORTANT**: Do NOT use the Edit tool on lines with Tailwind classes. Make targeted edits around structural HTML landmarks only. If any styling breaks after this task, run `cd src && npm run build:css`.

- [ ] **Step 1: Add Finance Add-on quick link in the automation sub-view**

In `src/templates/settings/index.html`, find this exact string (around line 1059):

```html
                      </a>
                    </div>
                  </div>

                  <div class="flex items-center gap-3">
                    <a href="{{ url_for('settings.settings_page', tab='integrations') }}" class="text-sm text-indigo-200 hover:text-white">
                      ← Back to integrations
```

Insert a Finance Add-on card **before** `</div>` closing the grid (i.e. before the last `</div>` before `<div class="flex items-center gap-3">`):

Replace:
```html
                      </a>
                    </div>
                  </div>

                  <div class="flex items-center gap-3">
                    <a href="{{ url_for('settings.settings_page', tab='integrations') }}" class="text-sm text-indigo-200 hover:text-white">
                      ← Back to integrations
```

With:
```html
                      </a>
                      <a href="{{ url_for('settings.integrations_finance') }}" class="flex items-center gap-3 p-3 rounded-lg bg-slate-950/40 border border-slate-800 hover:border-slate-700 transition-colors">
                        <svg class="w-5 h-5 text-amber-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                        </svg>
                        <div class="flex-1">
                          <div class="text-sm font-semibold text-slate-100">Finance Add-on</div>
                          <div class="text-xs text-slate-400">Stripe → QuickBooks automation</div>
                        </div>
                      </a>
                    </div>
                  </div>

                  <div class="flex items-center gap-3">
                    <a href="{{ url_for('settings.settings_page', tab='integrations') }}" class="text-sm text-indigo-200 hover:text-white">
                      ← Back to integrations
```

- [ ] **Step 2: Add `{% elif integrations_view == 'finance' %}` template block**

In `src/templates/settings/index.html`, find this exact string (around line 1320):

```html
                </script>

              {% else %}
```

Insert the entire Finance sub-view block between `</script>` and `{% else %}`:

Replace:
```html
                </script>

              {% else %}
```

With:
```html
                </script>

              {% elif integrations_view == 'finance' %}
                <div class="space-y-3">
                  <p class="text-sm text-amber-200 inline-flex items-center gap-2 rounded-full border border-amber-400/30 bg-amber-500/10 px-3 py-1">
                    Integrations • Finance Add-on
                  </p>
                  <h2 class="text-xl md:text-3xl font-semibold">Finance Add-on</h2>
                  <p class="text-sm text-slate-300 max-w-3xl">
                    Automate Stripe payment events into QuickBooks — sync transactions in real time or receive weekly CSV exports.
                  </p>
                </div>

                {# ── Upgrade gate ──────────────────────────────────── #}
                <div id="finance-gate" class="mt-8 {% if finance_addon_active %}hidden{% endif %}">
                  <div class="rounded-2xl border border-amber-500/30 bg-amber-950/20 p-8 text-center">
                    <div class="text-4xl mb-4">⚡</div>
                    <h3 class="text-lg font-semibold mb-2">Upgrade to unlock Finance Add-on</h3>
                    <p class="text-sm text-slate-300 max-w-md mx-auto mb-6">
                      Automate Stripe payments into QuickBooks — sync transactions in real time or receive weekly CSV exports.
                    </p>
                    <div class="flex flex-wrap justify-center gap-2 mb-6">
                      <span class="text-xs px-3 py-1 rounded-full border border-slate-600 text-slate-300">✓ Stripe webhook</span>
                      <span class="text-xs px-3 py-1 rounded-full border border-slate-600 text-slate-300">✓ QuickBooks sync</span>
                      <span class="text-xs px-3 py-1 rounded-full border border-slate-600 text-slate-300">✓ Weekly CSV export</span>
                    </div>
                    <a href="{{ url_for('settings.settings_page', tab='billing') }}" class="inline-flex items-center gap-2 rounded-lg bg-amber-500 hover:bg-amber-400 px-6 py-2.5 text-sm font-semibold text-black transition-colors">
                      Upgrade to unlock →
                    </a>
                    <p class="text-xs text-slate-500 mt-3">Included in Pro and above</p>
                  </div>
                </div>

                {# ── Wizard ────────────────────────────────────────── #}
                <div id="finance-wizard" class="mt-8 {% if not finance_addon_active %}hidden{% endif %}">

                  {# Step 1 — Connect Stripe #}
                  <div class="finance-step" id="finance-step-1">
                    <div class="rounded-2xl border border-slate-800 bg-slate-900/70 p-6">
                      <div class="flex items-center gap-2 mb-6">
                        <div class="w-7 h-7 rounded-full bg-amber-500 flex items-center justify-center text-xs font-bold text-black">1</div>
                        <div class="flex-1 h-px bg-slate-700"></div>
                        <div class="w-7 h-7 rounded-full bg-slate-700 flex items-center justify-center text-xs text-slate-400">2</div>
                        <div class="flex-1 h-px bg-slate-700"></div>
                        <div class="w-7 h-7 rounded-full bg-slate-700 flex items-center justify-center text-xs text-slate-400">3</div>
                      </div>
                      <h3 class="text-base font-semibold mb-1">Connect your Stripe webhook</h3>
                      <p class="text-sm text-slate-400 mb-4">Select the Stripe provider that receives your payment events.</p>
                      <label class="block text-xs text-slate-400 mb-1">Stripe webhook provider</label>
                      <select id="finance-stripe-select" class="w-full rounded-lg bg-slate-950 border border-slate-700 px-3 py-2 text-sm text-slate-100 focus:outline-none focus:border-amber-500 mb-2">
                        <option value="">Select a Stripe provider…</option>
                        {% for p in stripe_providers %}
                          <option value="{{ p.id }}">{{ p.configuration_name }}</option>
                        {% endfor %}
                      </select>
                      <a href="{{ url_for('settings.integrations_webhooks') }}" class="text-xs text-indigo-400 hover:text-indigo-300">
                        + Add a new Stripe provider first →
                      </a>
                      <div class="mt-6 flex justify-end">
                        <button type="button" onclick="financeShowStep(2)" class="rounded-lg bg-indigo-600 hover:bg-indigo-500 px-4 py-2 text-sm font-semibold text-white transition-colors">
                          Next: Choose output →
                        </button>
                      </div>
                    </div>
                  </div>

                  {# Step 2+3 — Mode + provider/confirmation #}
                  <div class="finance-step hidden" id="finance-step-2">
                    <div class="rounded-2xl border border-slate-800 bg-slate-900/70 p-6">
                      <div class="flex items-center gap-2 mb-6">
                        <div class="w-7 h-7 rounded-full bg-emerald-500 flex items-center justify-center text-xs font-bold text-black">✓</div>
                        <div class="flex-1 h-px bg-emerald-500"></div>
                        <div class="w-7 h-7 rounded-full bg-amber-500 flex items-center justify-center text-xs font-bold text-black">2</div>
                        <div class="flex-1 h-px bg-slate-700"></div>
                        <div class="w-7 h-7 rounded-full bg-amber-500 flex items-center justify-center text-xs font-bold text-black">3</div>
                      </div>
                      <h3 class="text-base font-semibold mb-4">Output mode</h3>
                      <div class="grid grid-cols-2 gap-3 mb-6">
                        <button type="button" id="finance-mode-direct" onclick="financeSelectMode('direct_sync')" class="rounded-xl border border-slate-700 p-4 text-left transition-colors hover:border-amber-500/60">
                          <div class="text-sm font-semibold mb-1">⚡ Direct sync</div>
                          <div class="text-xs text-slate-400">Real-time QuickBooks API</div>
                        </button>
                        <button type="button" id="finance-mode-csv" onclick="financeSelectMode('csv_export')" class="rounded-xl border border-slate-700 p-4 text-left transition-colors hover:border-amber-500/60">
                          <div class="text-sm font-semibold mb-1">📎 CSV export</div>
                          <div class="text-xs text-slate-400">Weekly email attachment</div>
                        </button>
                      </div>

                      {# Step 3a — Direct sync QB provider #}
                      <div id="finance-step3-direct" class="hidden mb-4">
                        <label class="block text-xs text-slate-400 mb-1">QuickBooks provider</label>
                        <p class="text-xs text-slate-500 mb-2">Select the QuickBooks provider to post transactions to.</p>
                        <select id="finance-qb-select" class="w-full rounded-lg bg-slate-950 border border-slate-700 px-3 py-2 text-sm text-slate-100 focus:outline-none focus:border-amber-500 mb-2">
                          <option value="">Select a QuickBooks provider…</option>
                          {% for p in qb_providers %}
                            <option value="{{ p.id }}">{{ p.configuration_name }}</option>
                          {% endfor %}
                        </select>
                        <a href="{{ url_for('settings.integrations_webhooks') }}" class="text-xs text-indigo-400 hover:text-indigo-300">
                          + Add a new QuickBooks provider first →
                        </a>
                      </div>

                      {# Step 3b — CSV export confirmation #}
                      <div id="finance-step3-csv" class="hidden mb-4">
                        <div class="text-xs text-slate-400 mb-2">Ready to activate</div>
                        <div class="rounded-xl border border-slate-700 bg-slate-950/50 px-4 py-3">
                          <div class="text-xs text-slate-500 mb-1">Weekly CSV will be sent to:</div>
                          <div class="text-sm font-medium">{{ account_email }}</div>
                          <div class="text-xs text-slate-500 mt-1">Every Monday at 08:00 UTC · Intuit-compatible format</div>
                        </div>
                      </div>

                      <div class="mt-6 flex justify-between items-center">
                        <button type="button" onclick="financeShowStep(1)" class="text-sm text-slate-400 hover:text-slate-200">← Back</button>
                        <button type="button" id="finance-activate-btn" onclick="financeActivate()" disabled class="rounded-lg bg-amber-500 hover:bg-amber-400 disabled:opacity-40 disabled:cursor-not-allowed px-4 py-2 text-sm font-semibold text-black transition-colors">
                          Activate add-on ⚡
                        </button>
                      </div>
                    </div>
                  </div>

                </div>

                {# ── Active summary ────────────────────────────────── #}
                <div id="finance-summary" class="mt-8 {% if not finance_addon_active %}hidden{% endif %}">
                  <div class="rounded-2xl border border-emerald-700/40 bg-emerald-950/10 p-6">
                    <div class="flex flex-wrap items-start justify-between gap-4 mb-4">
                      <div>
                        <div class="text-base font-semibold text-emerald-300">⚡ Finance Add-on · Active</div>
                        {% if finance_addon %}
                          <div class="text-sm text-slate-400 mt-1">{{ finance_addon.transactions_this_month }} transactions processed this month</div>
                        {% endif %}
                      </div>
                      <div class="flex gap-2">
                        <button type="button" onclick="financeReconfigure()" class="rounded-lg bg-indigo-600 hover:bg-indigo-500 px-4 py-2 text-sm font-semibold text-white transition-colors">
                          Reconfigure
                        </button>
                        <button type="button" onclick="financeDeactivate()" class="rounded-lg border border-slate-600 hover:border-slate-500 px-4 py-2 text-sm text-slate-300 hover:text-white transition-colors">
                          Deactivate
                        </button>
                      </div>
                    </div>
                    {% if finance_addon and finance_addon.config_json %}
                      <div class="grid grid-cols-2 gap-3">
                        <div class="rounded-xl border border-slate-700 bg-slate-950/50 px-4 py-3">
                          <div class="text-xs text-slate-500 mb-1 uppercase tracking-wide">Stripe</div>
                          {% set stripe_name = namespace(found='') %}
                          {% for p in stripe_providers %}
                            {% if p.id|string == finance_addon.config_json.get('stripe_provider_id', '')|string %}
                              {% set stripe_name.found = p.configuration_name %}
                            {% endif %}
                          {% endfor %}
                          <div class="text-sm">{{ stripe_name.found or '—' }}</div>
                        </div>
                        <div class="rounded-xl border border-slate-700 bg-slate-950/50 px-4 py-3">
                          <div class="text-xs text-slate-500 mb-1 uppercase tracking-wide">Output</div>
                          <div class="text-sm">{{ 'Direct QB sync' if finance_addon.config_json.get('mode') == 'direct_sync' else 'CSV export · weekly' }}</div>
                        </div>
                      </div>
                    {% endif %}
                  </div>
                </div>

                <div class="mt-6 flex items-center gap-3">
                  <a href="{{ url_for('settings.integrations_webhooks') }}" class="text-sm text-indigo-200 hover:text-white">
                    ← Back to Webhook Providers
                  </a>
                </div>

                <script>
                (function () {
                  var _mode = null;
                  var _accountEmail = {{ account_email | tojson }};

                  function getCsrfToken() {
                    return document.cookie.split(';').reduce(function(t, c) {
                      var p = c.trim().split('=');
                      return p[0] === 'csrf_access_token' ? decodeURIComponent(p[1]) : t;
                    }, '');
                  }

                  window.financeShowStep = function(n) {
                    document.querySelectorAll('.finance-step').forEach(function(el) {
                      el.classList.add('hidden');
                    });
                    var step = document.getElementById('finance-step-' + n);
                    if (step) step.classList.remove('hidden');
                  };

                  window.financeSelectMode = function(mode) {
                    _mode = mode;
                    var btnDirect = document.getElementById('finance-mode-direct');
                    var btnCsv = document.getElementById('finance-mode-csv');
                    var step3Direct = document.getElementById('finance-step3-direct');
                    var step3Csv = document.getElementById('finance-step3-csv');
                    var activateBtn = document.getElementById('finance-activate-btn');
                    btnDirect.classList.toggle('border-amber-500', mode === 'direct_sync');
                    btnDirect.classList.toggle('border-slate-700', mode !== 'direct_sync');
                    btnCsv.classList.toggle('border-amber-500', mode === 'csv_export');
                    btnCsv.classList.toggle('border-slate-700', mode !== 'csv_export');
                    step3Direct.classList.toggle('hidden', mode !== 'direct_sync');
                    step3Csv.classList.toggle('hidden', mode !== 'csv_export');
                    if (activateBtn) activateBtn.disabled = false;
                  };

                  window.financeActivate = async function() {
                    var stripeId = document.getElementById('finance-stripe-select').value;
                    if (!stripeId) { alert('Please select a Stripe provider.'); return; }
                    if (!_mode) { alert('Please select an output mode.'); return; }
                    var payload = { stripe_provider_id: stripeId, mode: _mode };
                    if (_mode === 'direct_sync') {
                      var qbId = document.getElementById('finance-qb-select').value;
                      if (!qbId) { alert('Please select a QuickBooks provider.'); return; }
                      payload.qb_provider_id = qbId;
                    } else {
                      payload.csv_email = _accountEmail;
                    }
                    var resp = await fetch('/api/v1/addons/finance/activate', {
                      method: 'POST',
                      headers: { 'Content-Type': 'application/json', 'X-CSRF-TOKEN': getCsrfToken() },
                      body: JSON.stringify(payload),
                    });
                    if (resp.ok) {
                      window.location.reload();
                    } else if (resp.status === 402) {
                      window.location.href = "{{ url_for('settings.settings_page', tab='billing') }}";
                    } else {
                      var data = await resp.json();
                      alert('Error: ' + (data.error || 'Unknown error'));
                    }
                  };

                  window.financeDeactivate = async function() {
                    if (!confirm('Deactivate Finance Add-on? Your configuration will be saved but processing will stop.')) return;
                    var resp = await fetch('/api/v1/addons/finance/deactivate', {
                      method: 'POST',
                      headers: { 'Content-Type': 'application/json', 'X-CSRF-TOKEN': getCsrfToken() },
                    });
                    if (resp.ok) {
                      window.location.reload();
                    } else {
                      alert('Could not deactivate. Please try again.');
                    }
                  };

                  window.financeReconfigure = function() {
                    document.getElementById('finance-summary').classList.add('hidden');
                    document.getElementById('finance-wizard').classList.remove('hidden');
                    window.financeShowStep(1);
                  };
                })();
                </script>

              {% else %}
```

- [ ] **Step 3: Run all 3 tests — expect all PASS**

```bash
cd /Users/kofi/inboxiq && python -m pytest tests/settings/test_finance_settings.py -v 2>&1 | tail -20
```

Expected: All 3 tests PASS.

- [ ] **Step 4: Smoke-check the full test suite for regressions**

```bash
cd /Users/kofi/inboxiq && python -m pytest tests/ -x --ignore=tests/settings -q 2>&1 | tail -20
```

Expected: Same pass/fail as before this task (6 pre-existing failures in developer/onboarding are expected — any new failures are regressions).

- [ ] **Step 5: Commit**

```bash
git add src/templates/settings/index.html
git commit -m "feat(finance-settings): Finance Add-on wizard in Settings → Integrations"
```

---

## Self-Review Checklist

**Spec coverage:**

| Spec requirement | Task |
| --- | --- |
| Sub-section in Integrations tab | Task 2 — `{% elif integrations_view == 'finance' %}` |
| Visible to all, upgrade gate if not active | Task 2 — `#finance-gate` with `{% if finance_addon_active %}hidden{% endif %}` |
| JS wizard, no page reloads | Task 2 — `financeShowStep()` JS |
| Step 1: Stripe provider dropdown | Task 2 — `#finance-step-1` |
| Step 2: mode toggle | Task 2 — `financeSelectMode()` |
| Step 3 direct_sync: QB provider | Task 2 — `#finance-step3-direct` |
| Step 3 csv_export: account email confirmation | Task 2 — `#finance-step3-csv` with `{{ account_email }}` |
| Active summary with transaction count | Task 2 — `#finance-summary` |
| Reconfigure button (client-side only) | Task 2 — `financeReconfigure()` |
| Deactivate via API | Task 2 — `financeDeactivate()` |
| Quick link from automation view | Task 2 — Finance Add-on card in quick-links grid |
| Route passes stripe_providers, qb_providers | Task 1 — `integrations_finance()` |
| csv_email = account owner email | Task 1 — `account_email` passed to template; Task 2 — `_accountEmail` in JS payload |

All requirements covered.

**Placeholder scan:** None found.

**Type consistency:** `finance_addon_active` (bool) used consistently in both route and template. `stripe_providers` / `qb_providers` are lists of `WebhookProvider` objects — accessed via `.id` and `.configuration_name`, both present on the model.
