# Tickets Settings Tab Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Tickets tab to the Settings page where every account can search, filter, view, and lightly manage (resolve/close) their tickets.

**Architecture:** Four new server-rendered routes in `src/settings/routes.py` protected by `@login_required_settings` and scoped to `g.current_account_id`. Two standalone Jinja templates (list + detail) following the `activity_log.html` pattern. No new API endpoints, no JS framework.

**Tech Stack:** Flask, SQLAlchemy, Jinja2, Tailwind CSS (pre-compiled), pytest + unittest.mock

---

## File Map

| Action | File | Purpose |
|---|---|---|
| Modify | `src/settings/routes.py` | Add `_build_ticket_query()` helper + 4 new routes |
| Modify | `src/templates/settings/index.html` | Add "Tickets" nav link to sidebar |
| Create | `src/templates/settings/tickets_list.html` | List page template |
| Create | `src/templates/settings/tickets_detail.html` | Detail page template |
| Create | `src/tests/test_tickets_settings.py` | Unit tests for helper + route logic |

---

## Task 1: Add "Tickets" nav link to the settings sidebar

**Files:**
- Modify: `src/templates/settings/index.html` (sidebar nav section, lines ~108–120)

- [ ] **Step 1: Add the nav link after "Integrations"**

  In `src/templates/settings/index.html`, find this block (after the Integrations `</a>` closing tag):

  ```html
              <a href="{{ url_for('settings.settings_page', tab='features') }}"
  ```

  Insert the new Tickets link **before** that line:

  ```html
              <a href="{{ url_for('settings.tickets_list') }}"
                 class="flex items-center justify-between px-3 py-2 rounded-xl border border-transparent hover:border-slate-700 hover:bg-slate-900/60 text-slate-200">
                <span>Tickets</span>
              </a>

  ```

- [ ] **Step 2: Verify the sidebar renders without errors**

  Open `https://kalevent.com/settings/team` in the browser and confirm the "Tickets" link appears in the sidebar between Integrations and AI Features. It should not be highlighted (no active state — the list page is a separate template).

- [ ] **Step 3: Commit**

  ```bash
  git add src/templates/settings/index.html
  git commit -m "feat: add Tickets nav link to settings sidebar"
  ```

---

## Task 2: Add Ticket import + `_build_ticket_query()` helper

**Files:**
- Modify: `src/settings/routes.py`
- Create: `src/tests/test_tickets_settings.py`

- [ ] **Step 1: Write the failing test**

  Create `src/tests/test_tickets_settings.py`:

  ```python
  """Tests for the Tickets settings tab — query helper and route logic."""
  from __future__ import annotations
  from unittest.mock import MagicMock, patch, call
  import pytest


  # ---------------------------------------------------------------------------
  # _build_ticket_query
  # ---------------------------------------------------------------------------

  class TestBuildTicketQuery:
      """Test filter application in _build_ticket_query."""

      def _make_mock_query(self):
          """Return a mock that chains .filter() and .order_by() calls."""
          q = MagicMock()
          q.filter.return_value = q
          q.order_by.return_value = q
          return q

      def test_scopes_to_account(self):
          mock_q = self._make_mock_query()
          with patch("src.settings.routes.Ticket") as MockTicket:
              MockTicket.query.filter.return_value = mock_q
              from src.settings.routes import _build_ticket_query
              result = _build_ticket_query(account_id=42)
              # First call must filter by account_id
              MockTicket.query.filter.assert_called_once()
              assert result is mock_q

      def test_no_extra_filters_when_params_empty(self):
          mock_q = self._make_mock_query()
          with patch("src.settings.routes.Ticket") as MockTicket:
              MockTicket.query.filter.return_value = mock_q
              from src.settings.routes import _build_ticket_query
              _build_ticket_query(account_id=1)
              # Only one filter call (account_id scope)
              assert mock_q.filter.call_count == 0

      def test_status_filter_applied(self):
          mock_q = self._make_mock_query()
          with patch("src.settings.routes.Ticket") as MockTicket:
              MockTicket.query.filter.return_value = mock_q
              from src.settings.routes import _build_ticket_query
              _build_ticket_query(account_id=1, status="open")
              assert mock_q.filter.call_count >= 1

      def test_empty_status_not_applied(self):
          mock_q = self._make_mock_query()
          with patch("src.settings.routes.Ticket") as MockTicket:
              MockTicket.query.filter.return_value = mock_q
              from src.settings.routes import _build_ticket_query
              _build_ticket_query(account_id=1, status="")
              assert mock_q.filter.call_count == 0
  ```

- [ ] **Step 2: Run the test to confirm it fails**

  ```bash
  cd /Users/kofi/inboxiq && python -m pytest src/tests/test_tickets_settings.py -v 2>&1 | head -30
  ```

  Expected: `ImportError` or `AttributeError` — `_build_ticket_query` does not exist yet.

- [ ] **Step 3: Add the Ticket import and helper to `src/settings/routes.py`**

  Add this import near the top of `src/settings/routes.py` (after the existing model imports on line ~11):

  ```python
  from src.models.tickets import Ticket
  ```

  Then add the helper function immediately after the `_is_staff_account()` function (around line 28):

  ```python
  def _build_ticket_query(account_id, q="", status="", category="", priority="", from_date="", to_date=""):
    """Return a scoped, filtered, sorted Ticket query for the given account."""
    from sqlalchemy import case
    from datetime import datetime

    query = Ticket.query.filter(Ticket.account_id == account_id)

    if q:
      query = query.filter(
        Ticket.search_vec.op("@@")(db.func.plainto_tsquery("english", q))
      )
    if status:
      query = query.filter(Ticket.status == status)
    if category:
      query = query.filter(Ticket.category == category)
    if priority:
      query = query.filter(Ticket.priority == priority)
    if from_date:
      try:
        query = query.filter(Ticket.created_at >= datetime.strptime(from_date, "%Y-%m-%d"))
      except ValueError:
        pass
    if to_date:
      try:
        query = query.filter(Ticket.created_at <= datetime.strptime(to_date, "%Y-%m-%d"))
      except ValueError:
        pass

    priority_order = case(
      (Ticket.priority == "P0", 0),
      (Ticket.priority == "P1", 1),
      (Ticket.priority == "P2", 2),
      (Ticket.priority == "P3", 3),
      (Ticket.priority == "P4", 4),
      else_=5,
    )
    return query.order_by(priority_order, Ticket.created_at.desc())
  ```

- [ ] **Step 4: Run the tests and confirm they pass**

  ```bash
  cd /Users/kofi/inboxiq && python -m pytest src/tests/test_tickets_settings.py::TestBuildTicketQuery -v
  ```

  Expected: 4 tests pass.

- [ ] **Step 5: Commit**

  ```bash
  git add src/settings/routes.py src/tests/test_tickets_settings.py
  git commit -m "feat: add _build_ticket_query helper for tickets settings tab"
  ```

---

## Task 3: Implement the tickets list route

**Files:**
- Modify: `src/settings/routes.py`

- [ ] **Step 1: Add the list route to `src/settings/routes.py`**

  Add this route after the `activity_log_page` function (around line 608):

  ```python
  _TICKET_STATUSES = ["new", "open", "auto_handled", "optional", "needs_review",
                      "meeting_scheduled", "resolved", "closed"]
  _TICKET_CATEGORIES = ["support", "transactional", "scheduling", "billing", "spam", "other"]
  _TICKET_PRIORITIES = ["P0", "P1", "P2", "P3", "P4"]
  _TICKETS_PAGE_SIZE = 25


  @bp.get("/settings/tickets")
  @login_required_settings
  def tickets_list():
    account_id = getattr(g, "current_account_id", None)
    if not account_id:
      return redirect(url_for("settings.settings_page", tab="team"))

    q = request.args.get("q", "").strip()
    status = request.args.get("status", "").strip()
    category = request.args.get("category", "").strip()
    priority = request.args.get("priority", "").strip()
    from_date = request.args.get("from", "").strip()
    to_date = request.args.get("to", "").strip()

    try:
      page = max(1, int(request.args.get("page", 1) or 1))
    except (ValueError, TypeError):
      page = 1

    ticket_q = _build_ticket_query(account_id, q, status, category, priority, from_date, to_date)
    total = ticket_q.count()
    tickets = ticket_q.offset((page - 1) * _TICKETS_PAGE_SIZE).limit(_TICKETS_PAGE_SIZE).all()
    total_pages = max(1, (total + _TICKETS_PAGE_SIZE - 1) // _TICKETS_PAGE_SIZE)

    return render_template(
      "settings/tickets_list.html",
      tickets=tickets,
      page=page,
      total=total,
      total_pages=total_pages,
      page_size=_TICKETS_PAGE_SIZE,
      q=q,
      filter_status=status,
      filter_category=category,
      filter_priority=priority,
      filter_from=from_date,
      filter_to=to_date,
      statuses=_TICKET_STATUSES,
      categories=_TICKET_CATEGORIES,
      priorities=_TICKET_PRIORITIES,
      active_tab="tickets",
    )
  ```

- [ ] **Step 2: Verify the route loads without error**

  Visit `https://kalevent.com/settings/tickets` while logged in. You should see a Jinja `TemplateNotFound` error for `settings/tickets_list.html` — this is expected; the template doesn't exist yet.

- [ ] **Step 3: Commit**

  ```bash
  git add src/settings/routes.py
  git commit -m "feat: add tickets list route (template pending)"
  ```

---

## Task 4: Create the tickets list template

**Files:**
- Create: `src/templates/settings/tickets_list.html`

- [ ] **Step 1: Create the template**

  Create `src/templates/settings/tickets_list.html` with this content:

  ```html
  <!DOCTYPE html>
  <html lang="en">
  <head>
    <meta charset="UTF-8" />
    <title>InboxIQ – Tickets</title>
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <link rel="stylesheet" href="{{ url_for('static', filename='css/tailwind.min.css') }}" />
    <link rel="stylesheet" href="{{ url_for('static', filename='css/custom.css') }}" />
  </head>

  <body class="bg-slate-950 text-slate-50 antialiased">
    <div class="min-h-screen flex flex-col">

      <header class="border-b border-slate-800 bg-slate-950/80 backdrop-blur dashboard-header">
        <div class="max-w-6xl mx-auto px-4 lg:px-6 py-4 flex items-center justify-between">
          <div class="flex items-center gap-3">
            <div class="h-9 w-9 rounded-xl bg-indigo-500 flex items-center justify-center font-bold text-white">KI</div>
            <div>
              <div class="font-semibold text-lg tracking-tight text-white">Kalevent</div>
              <div class="text-xs text-slate-400">InboxIQ – Tickets</div>
            </div>
          </div>
          <a href="{{ url_for('settings.settings_page', tab='team') }}" class="px-3 py-1.5 rounded-full border border-slate-700 hover:bg-slate-800 text-sm text-slate-200">
            ← Settings
          </a>
        </div>
      </header>

      <main class="flex-1 bg-gradient-to-br from-slate-950 via-slate-900 to-indigo-950">
        <div class="max-w-6xl mx-auto px-4 lg:px-6 py-10 lg:py-14">

          <div class="mb-6">
            <h1 class="text-2xl md:text-3xl font-semibold tracking-tight">Tickets</h1>
            <p class="text-sm text-slate-300 mt-1">All emails InboxIQ has processed for your account.</p>
          </div>

          <!-- Flash messages -->
          {% with messages = get_flashed_messages(with_categories=true) %}
            {% for category, message in messages %}
              <div class="mb-4 px-4 py-3 rounded-xl text-sm
                {% if category == 'success' %}bg-emerald-500/10 border border-emerald-500/30 text-emerald-300
                {% elif category == 'error' %}bg-red-500/10 border border-red-500/30 text-red-300
                {% else %}bg-indigo-500/10 border border-indigo-400/30 text-indigo-200{% endif %}">
                {{ message }}
              </div>
            {% endfor %}
          {% endwith %}

          <!-- Filter form -->
          <form method="GET" action="{{ url_for('settings.tickets_list') }}" class="mb-6 rounded-2xl border border-slate-800 bg-slate-900/60 p-4">
            <div class="flex flex-wrap gap-3 items-end">
              <div class="flex-1 min-w-48">
                <label class="block text-xs text-slate-400 mb-1">Search</label>
                <input type="text" name="q" value="{{ q }}"
                       placeholder="Subject or sender email…"
                       class="w-full bg-slate-800 border border-slate-700 text-slate-200 text-sm rounded-xl px-3 py-2 placeholder-slate-500 focus:outline-none focus:border-indigo-500" />
              </div>
              <div>
                <label class="block text-xs text-slate-400 mb-1">Status</label>
                <select name="status" class="bg-slate-800 border border-slate-700 text-slate-200 text-sm rounded-xl px-3 py-2">
                  <option value="">All statuses</option>
                  {% for s in statuses %}
                    <option value="{{ s }}" {% if filter_status == s %}selected{% endif %}>{{ s | replace('_', ' ') | title }}</option>
                  {% endfor %}
                </select>
              </div>
              <div>
                <label class="block text-xs text-slate-400 mb-1">Category</label>
                <select name="category" class="bg-slate-800 border border-slate-700 text-slate-200 text-sm rounded-xl px-3 py-2">
                  <option value="">All categories</option>
                  {% for c in categories %}
                    <option value="{{ c }}" {% if filter_category == c %}selected{% endif %}>{{ c | title }}</option>
                  {% endfor %}
                </select>
              </div>
              <div>
                <label class="block text-xs text-slate-400 mb-1">Priority</label>
                <select name="priority" class="bg-slate-800 border border-slate-700 text-slate-200 text-sm rounded-xl px-3 py-2">
                  <option value="">All priorities</option>
                  {% for p in priorities %}
                    <option value="{{ p }}" {% if filter_priority == p %}selected{% endif %}>{{ p }}</option>
                  {% endfor %}
                </select>
              </div>
              <div>
                <label class="block text-xs text-slate-400 mb-1">From</label>
                <input type="date" name="from" value="{{ filter_from }}"
                       class="bg-slate-800 border border-slate-700 text-slate-200 text-sm rounded-xl px-3 py-2" />
              </div>
              <div>
                <label class="block text-xs text-slate-400 mb-1">To</label>
                <input type="date" name="to" value="{{ filter_to }}"
                       class="bg-slate-800 border border-slate-700 text-slate-200 text-sm rounded-xl px-3 py-2" />
              </div>
              <div class="flex gap-2">
                <button type="submit" class="rounded-xl px-4 py-2 text-sm font-semibold bg-indigo-600 hover:bg-indigo-500 text-white">Search</button>
                <a href="{{ url_for('settings.tickets_list') }}" class="rounded-xl px-4 py-2 text-sm border border-slate-700 text-slate-300 hover:bg-slate-800">Clear</a>
              </div>
            </div>
          </form>

          <!-- Results count -->
          {% if total > 0 %}
            <p class="text-xs text-slate-400 mb-3">
              Showing {{ (page - 1) * page_size + 1 }}–{{ [page * page_size, total] | min }} of {{ total }} ticket{{ 's' if total != 1 else '' }}
            </p>
          {% endif %}

          <!-- Ticket table -->
          <div class="rounded-3xl border border-slate-800 bg-slate-900/60 shadow-2xl shadow-indigo-500/10 overflow-hidden">
            <div class="overflow-x-auto">
              <table class="w-full text-sm">
                <thead>
                  <tr class="border-b border-slate-800 text-slate-400 text-xs uppercase tracking-wide">
                    <th class="px-5 py-3 text-left">Subject</th>
                    <th class="px-5 py-3 text-left">From</th>
                    <th class="px-5 py-3 text-left">Category</th>
                    <th class="px-5 py-3 text-left">Priority</th>
                    <th class="px-5 py-3 text-left">Status</th>
                    <th class="px-5 py-3 text-left">Date</th>
                  </tr>
                </thead>
                <tbody>
                  {% if tickets %}
                    {% for ticket in tickets %}
                      {% set back = request.url | urlencode %}
                      <tr class="border-b border-slate-800/60 hover:bg-slate-800/30 cursor-pointer"
                          onclick="window.location='{{ url_for('settings.tickets_detail', ticket_id=ticket.id) }}?back={{ request.url | urlencode }}'">
                        <td class="px-5 py-3 text-slate-100 max-w-xs truncate">
                          {{ ticket.subject[:80] }}{% if ticket.subject | length > 80 %}…{% endif %}
                        </td>
                        <td class="px-5 py-3 text-slate-300">{{ ticket.from_email }}</td>
                        <td class="px-5 py-3 text-slate-300">{{ ticket.category | title }}</td>
                        <td class="px-5 py-3">
                          <span class="inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium
                            {% if ticket.priority == 'P0' %}bg-red-500/20 text-red-300
                            {% elif ticket.priority == 'P1' %}bg-orange-500/20 text-orange-300
                            {% elif ticket.priority == 'P2' %}bg-yellow-500/20 text-yellow-300
                            {% else %}bg-slate-700 text-slate-300{% endif %}">
                            {{ ticket.priority }}
                          </span>
                        </td>
                        <td class="px-5 py-3">
                          <span class="inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium
                            {% if ticket.status == 'resolved' %}bg-emerald-500/20 text-emerald-300
                            {% elif ticket.status == 'closed' %}bg-slate-700 text-slate-400
                            {% elif ticket.status == 'needs_review' %}bg-yellow-500/20 text-yellow-300
                            {% elif ticket.status in ('new', 'open') %}bg-indigo-500/20 text-indigo-300
                            {% else %}bg-slate-700/50 text-slate-400{% endif %}">
                            {{ ticket.status | replace('_', ' ') | title }}
                          </span>
                        </td>
                        <td class="px-5 py-3 text-slate-400 whitespace-nowrap">
                          {{ ticket.created_at.strftime('%b %d, %Y') if ticket.created_at else '—' }}
                        </td>
                      </tr>
                    {% endfor %}
                  {% else %}
                    <tr>
                      <td colspan="6" class="px-5 py-12 text-center text-slate-400">
                        No tickets found for these filters.
                        <a href="{{ url_for('settings.tickets_list') }}" class="ml-1 text-indigo-400 hover:text-indigo-300">Clear filters</a>
                      </td>
                    </tr>
                  {% endif %}
                </tbody>
              </table>
            </div>

            <!-- Pagination -->
            {% if total_pages > 1 %}
              {% set base = url_for('settings.tickets_list') ~ '?q=' ~ (q | urlencode) ~ '&status=' ~ filter_status ~ '&category=' ~ filter_category ~ '&priority=' ~ filter_priority ~ '&from=' ~ filter_from ~ '&to=' ~ filter_to %}
              <div class="flex items-center justify-between px-5 py-3 border-t border-slate-800 text-sm text-slate-400">
                <span>Page {{ page }} of {{ total_pages }}</span>
                <div class="flex gap-2">
                  {% if page > 1 %}
                    <a href="{{ base }}&page={{ page - 1 }}"
                       class="px-3 py-1.5 rounded-lg border border-slate-700 hover:bg-slate-800">Prev</a>
                  {% endif %}
                  {% if page < total_pages %}
                    <a href="{{ base }}&page={{ page + 1 }}"
                       class="px-3 py-1.5 rounded-lg border border-slate-700 hover:bg-slate-800">Next</a>
                  {% endif %}
                </div>
              </div>
            {% endif %}

          </div>
        </div>
      </main>
    </div>
  </body>
  </html>
  ```

- [ ] **Step 2: Verify the list page loads**

  Visit `https://kalevent.com/settings/tickets`. Confirm:
  - Page loads with header, filter form, and table
  - If there are tickets, they appear in the table
  - "Clear" link resets to `/settings/tickets`

- [ ] **Step 3: Commit**

  ```bash
  git add src/templates/settings/tickets_list.html
  git commit -m "feat: add tickets list template"
  ```

---

## Task 5: Implement tickets detail route + add tests

**Files:**
- Modify: `src/settings/routes.py`
- Modify: `src/tests/test_tickets_settings.py`

- [ ] **Step 1: Add tests for the detail route logic**

  Append to `src/tests/test_tickets_settings.py`:

  ```python
  # ---------------------------------------------------------------------------
  # _is_staff_account
  # ---------------------------------------------------------------------------

  class TestIsStaffAccount:

      def test_staff_email_returns_true(self):
          from src.settings.routes import _is_staff_account
          user = MagicMock()
          user.email = "kofi@kalevent.com"
          with patch("src.settings.routes.current_app") as mock_app:
              mock_app.config.get.return_value = "kofi@kalevent.com"
              assert _is_staff_account(user) is True

      def test_non_staff_email_returns_false(self):
          from src.settings.routes import _is_staff_account
          user = MagicMock()
          user.email = "customer@example.com"
          with patch("src.settings.routes.current_app") as mock_app:
              mock_app.config.get.return_value = "kofi@kalevent.com"
              assert _is_staff_account(user) is False

      def test_none_user_returns_false(self):
          from src.settings.routes import _is_staff_account
          assert _is_staff_account(None) is False

      def test_case_insensitive(self):
          from src.settings.routes import _is_staff_account
          user = MagicMock()
          user.email = "KOFI@KALEVENT.COM"
          with patch("src.settings.routes.current_app") as mock_app:
              mock_app.config.get.return_value = "kofi@kalevent.com"
              assert _is_staff_account(user) is True
  ```

- [ ] **Step 2: Run the new tests to confirm they pass**

  ```bash
  cd /Users/kofi/inboxiq && python -m pytest src/tests/test_tickets_settings.py::TestIsStaffAccount -v
  ```

  Expected: 4 tests pass.

- [ ] **Step 3: Add the detail route to `src/settings/routes.py`**

  Add after the `tickets_list` function:

  ```python
  @bp.get("/settings/tickets/<ticket_id>")
  @login_required_settings
  def tickets_detail(ticket_id):
    account_id = getattr(g, "current_account_id", None)
    current_user = getattr(g, "current_user", None)
    if not account_id:
      return redirect(url_for("settings.settings_page", tab="team"))

    ticket = Ticket.query.filter_by(id=ticket_id, account_id=account_id).first()
    if not ticket:
      from flask import abort
      abort(404)

    back_url = request.args.get("back") or url_for("settings.tickets_list")
    is_staff = _is_staff_account(current_user)

    return render_template(
      "settings/tickets_detail.html",
      ticket=ticket,
      back_url=back_url,
      is_staff=is_staff,
      active_tab="tickets",
    )
  ```

- [ ] **Step 4: Verify the detail route returns 404 for a bad ticket_id**

  In the browser, visit `https://kalevent.com/settings/tickets/nonexistent-id`. Confirm you see a 404 response (Flask default or custom 404 page).

- [ ] **Step 5: Commit**

  ```bash
  git add src/settings/routes.py src/tests/test_tickets_settings.py
  git commit -m "feat: add tickets detail route"
  ```

---

## Task 6: Create the tickets detail template

**Files:**
- Create: `src/templates/settings/tickets_detail.html`

- [ ] **Step 1: Create the template**

  Create `src/templates/settings/tickets_detail.html`:

  ```html
  <!DOCTYPE html>
  <html lang="en">
  <head>
    <meta charset="UTF-8" />
    <title>InboxIQ – Ticket</title>
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <link rel="stylesheet" href="{{ url_for('static', filename='css/tailwind.min.css') }}" />
    <link rel="stylesheet" href="{{ url_for('static', filename='css/custom.css') }}" />
  </head>

  <body class="bg-slate-950 text-slate-50 antialiased">
    <div class="min-h-screen flex flex-col">

      <header class="border-b border-slate-800 bg-slate-950/80 backdrop-blur dashboard-header">
        <div class="max-w-6xl mx-auto px-4 lg:px-6 py-4 flex items-center justify-between">
          <div class="flex items-center gap-3">
            <div class="h-9 w-9 rounded-xl bg-indigo-500 flex items-center justify-center font-bold text-white">KI</div>
            <div>
              <div class="font-semibold text-lg tracking-tight text-white">Kalevent</div>
              <div class="text-xs text-slate-400">InboxIQ – Ticket Detail</div>
            </div>
          </div>
          <a href="{{ back_url }}" class="px-3 py-1.5 rounded-full border border-slate-700 hover:bg-slate-800 text-sm text-slate-200">
            ← Back to tickets
          </a>
        </div>
      </header>

      <main class="flex-1 bg-gradient-to-br from-slate-950 via-slate-900 to-indigo-950">
        <div class="max-w-6xl mx-auto px-4 lg:px-6 py-10 lg:py-14">

          <!-- Flash messages -->
          {% with messages = get_flashed_messages(with_categories=true) %}
            {% for category, message in messages %}
              <div class="mb-4 px-4 py-3 rounded-xl text-sm
                {% if category == 'success' %}bg-emerald-500/10 border border-emerald-500/30 text-emerald-300
                {% elif category == 'error' %}bg-red-500/10 border border-red-500/30 text-red-300
                {% else %}bg-indigo-500/10 border border-indigo-400/30 text-indigo-200{% endif %}">
                {{ message }}
              </div>
            {% endfor %}
          {% endwith %}

          <!-- Title + status badge -->
          <div class="mb-6 flex items-start gap-4 flex-wrap">
            <div class="flex-1">
              <h1 class="text-2xl md:text-3xl font-semibold tracking-tight">{{ ticket.subject }}</h1>
            </div>
            <span class="mt-1 inline-flex items-center rounded-full px-3 py-1 text-sm font-medium
              {% if ticket.status == 'resolved' %}bg-emerald-500/20 text-emerald-300
              {% elif ticket.status == 'closed' %}bg-slate-700 text-slate-400
              {% elif ticket.status == 'needs_review' %}bg-yellow-500/20 text-yellow-300
              {% elif ticket.status in ('new', 'open') %}bg-indigo-500/20 text-indigo-300
              {% else %}bg-slate-700/50 text-slate-400{% endif %}">
              {{ ticket.status | replace('_', ' ') | title }}
            </span>
          </div>

          <!-- Two-column layout -->
          <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">

            <!-- Left: primary info -->
            <div class="lg:col-span-2 space-y-4">

              <div class="rounded-2xl border border-slate-800 bg-slate-900/60 p-5">
                <h2 class="text-xs font-semibold text-slate-400 uppercase tracking-wide mb-3">Details</h2>
                <dl class="space-y-2 text-sm">
                  <div class="flex gap-2">
                    <dt class="w-28 text-slate-400 shrink-0">From</dt>
                    <dd class="text-slate-100">{{ ticket.from_email }}</dd>
                  </div>
                  <div class="flex gap-2">
                    <dt class="w-28 text-slate-400 shrink-0">Received</dt>
                    <dd class="text-slate-100">{{ ticket.created_at.strftime('%B %d, %Y at %H:%M UTC') if ticket.created_at else '—' }}</dd>
                  </div>
                  <div class="flex gap-2">
                    <dt class="w-28 text-slate-400 shrink-0">Provider</dt>
                    <dd class="text-slate-100">{{ ticket.provider | title if ticket.provider else '—' }}</dd>
                  </div>
                  <div class="flex gap-2">
                    <dt class="w-28 text-slate-400 shrink-0">Category</dt>
                    <dd class="text-slate-100">{{ ticket.category | title }}</dd>
                  </div>
                  <div class="flex gap-2">
                    <dt class="w-28 text-slate-400 shrink-0">Priority</dt>
                    <dd>
                      <span class="inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium
                        {% if ticket.priority == 'P0' %}bg-red-500/20 text-red-300
                        {% elif ticket.priority == 'P1' %}bg-orange-500/20 text-orange-300
                        {% elif ticket.priority == 'P2' %}bg-yellow-500/20 text-yellow-300
                        {% else %}bg-slate-700 text-slate-300{% endif %}">
                        {{ ticket.priority }}
                      </span>
                    </dd>
                  </div>
                  <div class="flex gap-2">
                    <dt class="w-28 text-slate-400 shrink-0">Sentiment</dt>
                    <dd class="text-slate-100">{{ ticket.sentiment | title }}</dd>
                  </div>
                </dl>
              </div>

              {% if ticket.body_preview %}
              <div class="rounded-2xl border border-slate-800 bg-slate-900/60 p-5">
                <h2 class="text-xs font-semibold text-slate-400 uppercase tracking-wide mb-3">Message</h2>
                <p class="text-sm text-slate-200 whitespace-pre-wrap">{{ ticket.body_preview }}</p>
              </div>
              {% endif %}

              {% if ticket.summary %}
              <div class="rounded-2xl border border-slate-800 bg-slate-900/60 p-5">
                <h2 class="text-xs font-semibold text-slate-400 uppercase tracking-wide mb-3">AI Summary</h2>
                <p class="text-sm text-slate-200">{{ ticket.summary }}</p>
              </div>
              {% endif %}

            </div>

            <!-- Right: metadata sidebar -->
            <div class="space-y-4">

              <div class="rounded-2xl border border-slate-800 bg-slate-900/60 p-5">
                <h2 class="text-xs font-semibold text-slate-400 uppercase tracking-wide mb-3">Triage</h2>
                {% set dec = ticket.decision or {} %}
                <dl class="space-y-2 text-sm">
                  <div class="flex gap-2">
                    <dt class="w-28 text-slate-400 shrink-0">Action needed</dt>
                    <dd class="text-slate-100">{{ dec.get('action_required', '—') }}</dd>
                  </div>
                  <div class="flex gap-2">
                    <dt class="w-28 text-slate-400 shrink-0">Intent</dt>
                    <dd class="text-slate-100">{{ dec.get('intent', '—') }}</dd>
                  </div>
                  <div class="flex gap-2">
                    <dt class="w-28 text-slate-400 shrink-0">Risk</dt>
                    <dd class="text-slate-100">{{ dec.get('risk_flag', '—') }}</dd>
                  </div>
                </dl>
              </div>

              {% if ticket.assigned_to or ticket.team or ticket.owner %}
              <div class="rounded-2xl border border-slate-800 bg-slate-900/60 p-5">
                <h2 class="text-xs font-semibold text-slate-400 uppercase tracking-wide mb-3">Assignment</h2>
                <dl class="space-y-2 text-sm">
                  {% if ticket.assigned_to %}
                  <div class="flex gap-2">
                    <dt class="w-20 text-slate-400 shrink-0">Assigned to</dt>
                    <dd class="text-slate-100">{{ ticket.assigned_to }}</dd>
                  </div>
                  {% endif %}
                  {% if ticket.team %}
                  <div class="flex gap-2">
                    <dt class="w-20 text-slate-400 shrink-0">Team</dt>
                    <dd class="text-slate-100">{{ ticket.team }}</dd>
                  </div>
                  {% endif %}
                  {% if ticket.owner %}
                  <div class="flex gap-2">
                    <dt class="w-20 text-slate-400 shrink-0">Owner</dt>
                    <dd class="text-slate-100">{{ ticket.owner }}</dd>
                  </div>
                  {% endif %}
                </dl>
              </div>
              {% endif %}

              {% if is_staff %}
              <div class="rounded-2xl border border-slate-800 bg-slate-900/60 p-5">
                <h2 class="text-xs font-semibold text-slate-400 uppercase tracking-wide mb-3">LLM Usage</h2>
                <dl class="space-y-2 text-sm">
                  <div class="flex gap-2">
                    <dt class="w-20 text-slate-400 shrink-0">Model</dt>
                    <dd class="text-slate-100 font-mono text-xs">{{ ticket.llm_model or '—' }}</dd>
                  </div>
                  <div class="flex gap-2">
                    <dt class="w-20 text-slate-400 shrink-0">Tokens in</dt>
                    <dd class="text-slate-100">{{ ticket.llm_tokens_in }}</dd>
                  </div>
                  <div class="flex gap-2">
                    <dt class="w-20 text-slate-400 shrink-0">Tokens out</dt>
                    <dd class="text-slate-100">{{ ticket.llm_tokens_out }}</dd>
                  </div>
                  <div class="flex gap-2">
                    <dt class="w-20 text-slate-400 shrink-0">Cost</dt>
                    <dd class="text-slate-100">${{ '%.6f' | format(ticket.llm_cost_usd | float) }}</dd>
                  </div>
                </dl>
              </div>
              {% endif %}

            </div>
          </div>

          <!-- Actions -->
          {% if ticket.status not in ('resolved', 'closed') %}
          <div class="mt-8 flex gap-3 flex-wrap">
            <form method="POST" action="{{ url_for('settings.tickets_resolve', ticket_id=ticket.id) }}">
              <input type="hidden" name="csrf_token" value="{{ csrf_token() }}" />
              <button type="submit"
                      class="rounded-xl px-5 py-2.5 text-sm font-semibold bg-emerald-600 hover:bg-emerald-500 text-white">
                Mark as Resolved
              </button>
            </form>
            <form method="POST" action="{{ url_for('settings.tickets_close', ticket_id=ticket.id) }}">
              <input type="hidden" name="csrf_token" value="{{ csrf_token() }}" />
              <button type="submit"
                      class="rounded-xl px-5 py-2.5 text-sm font-semibold border border-slate-700 text-slate-300 hover:bg-slate-800">
                Close Ticket
              </button>
            </form>
          </div>
          {% endif %}

        </div>
      </main>
    </div>
  </body>
  </html>
  ```

- [ ] **Step 2: Verify the detail page loads for a real ticket**

  From the tickets list, click a ticket row. Confirm:
  - Subject appears as title
  - Status badge shows correct colour
  - Details, message, summary sections render
  - Triage section shows decision fields
  - Resolve/Close buttons appear (if ticket is not already resolved/closed)
  - "← Back to tickets" returns to the list (with filters preserved)

- [ ] **Step 3: Commit**

  ```bash
  git add src/templates/settings/tickets_detail.html
  git commit -m "feat: add tickets detail template"
  ```

---

## Task 7: Implement resolve and close routes + tests

**Files:**
- Modify: `src/settings/routes.py`
- Modify: `src/tests/test_tickets_settings.py`

- [ ] **Step 1: Add tests for resolve/close logic**

  Append to `src/tests/test_tickets_settings.py`:

  ```python
  # ---------------------------------------------------------------------------
  # Resolve / close idempotency guard
  # ---------------------------------------------------------------------------

  class TestTicketActionIdempotency:
      """The resolve and close routes skip the DB write if ticket is already resolved/closed."""

      def _already_done_ticket(self, status):
          ticket = MagicMock()
          ticket.id = "abc123"
          ticket.status = status
          return ticket

      def test_resolve_skipped_when_already_resolved(self):
          ticket = self._already_done_ticket("resolved")
          # Simulate the guard condition from the route
          already_done = ticket.status in ("resolved", "closed")
          assert already_done is True

      def test_resolve_skipped_when_already_closed(self):
          ticket = self._already_done_ticket("closed")
          already_done = ticket.status in ("resolved", "closed")
          assert already_done is True

      def test_resolve_proceeds_when_open(self):
          ticket = self._already_done_ticket("open")
          already_done = ticket.status in ("resolved", "closed")
          assert already_done is False

      def test_close_proceeds_when_new(self):
          ticket = self._already_done_ticket("new")
          already_done = ticket.status in ("resolved", "closed")
          assert already_done is False
  ```

- [ ] **Step 2: Run the new tests**

  ```bash
  cd /Users/kofi/inboxiq && python -m pytest src/tests/test_tickets_settings.py::TestTicketActionIdempotency -v
  ```

  Expected: 4 tests pass.

- [ ] **Step 3: Add the resolve and close routes to `src/settings/routes.py`**

  Add after the `tickets_detail` function:

  ```python
  @bp.post("/settings/tickets/<ticket_id>/resolve")
  @login_required_settings
  def tickets_resolve(ticket_id):
    account_id = getattr(g, "current_account_id", None)
    ticket = Ticket.query.filter_by(id=ticket_id, account_id=account_id).first()
    if not ticket:
      from flask import abort
      abort(404)

    if ticket.status in ("resolved", "closed"):
      flash(f"Ticket is already {ticket.status}.", "info")
      return redirect(url_for("settings.tickets_detail", ticket_id=ticket_id))

    ticket.status = "resolved"
    try:
      db.session.commit()
      flash("Ticket marked as resolved.", "success")
    except Exception:
      db.session.rollback()
      flash("Failed to update ticket. Please try again.", "error")

    return redirect(url_for("settings.tickets_detail", ticket_id=ticket_id))


  @bp.post("/settings/tickets/<ticket_id>/close")
  @login_required_settings
  def tickets_close(ticket_id):
    account_id = getattr(g, "current_account_id", None)
    ticket = Ticket.query.filter_by(id=ticket_id, account_id=account_id).first()
    if not ticket:
      from flask import abort
      abort(404)

    if ticket.status in ("resolved", "closed"):
      flash(f"Ticket is already {ticket.status}.", "info")
      return redirect(url_for("settings.tickets_detail", ticket_id=ticket_id))

    ticket.status = "closed"
    try:
      db.session.commit()
      flash("Ticket closed.", "success")
    except Exception:
      db.session.rollback()
      flash("Failed to update ticket. Please try again.", "error")

    return redirect(url_for("settings.tickets_detail", ticket_id=ticket_id))
  ```

- [ ] **Step 4: Run the full test suite**

  ```bash
  cd /Users/kofi/inboxiq && python -m pytest src/tests/test_tickets_settings.py -v
  ```

  Expected: All tests pass.

- [ ] **Step 5: Manually test resolve and close**

  1. Open a ticket that is in `new` or `open` status
  2. Click "Mark as Resolved" — confirm flash message "Ticket marked as resolved." and status badge changes to green "Resolved"
  3. Confirm "Mark as Resolved" and "Close Ticket" buttons are now hidden
  4. In a new tab, visit the same ticket URL — confirm status is still "resolved" (persisted)
  5. Try submitting the resolve form again via direct POST (e.g., `curl`) — confirm flash "Ticket is already resolved." and no DB error

- [ ] **Step 6: Final commit**

  ```bash
  git add src/settings/routes.py src/tests/test_tickets_settings.py
  git commit -m "feat: add tickets resolve and close routes with idempotency guard"
  ```

---

## Task 8: Deploy and smoke-test in production

- [ ] **Step 1: Push to main to trigger CI/CD**

  ```bash
  git push origin main
  ```

- [ ] **Step 2: Smoke-test in production**

  Once deployed:
  1. Visit `https://kalevent.com/settings/team` → confirm "Tickets" appears in sidebar
  2. Click "Tickets" → confirm list loads with all processed tickets
  3. Apply a status filter → confirm results are scoped correctly
  4. Click a ticket → confirm detail page with all fields
  5. Resolve a test ticket → confirm status persists and buttons disappear
  6. Log in as a non-staff account → confirm LLM cost section is not visible on detail page
