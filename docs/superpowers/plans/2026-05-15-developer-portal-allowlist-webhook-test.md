# Developer Portal v1.1 — Domain Allowlist + Webhook Testing

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add per-app allowed-origins enforcement for the Chat widget (security) and a "Send test event" button per approved product (developer experience).

**Architecture:** `allowed_origins` is a JSON list on `RegisteredApp` (mirrors the existing `allowed_ips` pattern). Origin enforcement is opt-in: if the list is empty the chat endpoint allows all origins; once any origin is added, requests from unlisted origins get 403. Webhook testing is a synchronous JSON endpoint (`POST /settings/developer/test-webhook`) that fires a product-specific synthetic payload and returns the upstream status code + body for display inline in the portal.

**Tech Stack:** Flask, SQLAlchemy (PostgreSQL JSON column), `requests` (synchronous webhook test, 5-second timeout), Tailwind CSS (dual light/dark), Jinja2 template edit via Python splice (never Edit tool on index.html), vanilla JS in the portal template.

---

## Extra requirement

After each task that removes or replaces code, scan for and delete any resulting dead code.

---

## Context

- Existing developer portal spec: `docs/superpowers/specs/2026-05-15-developer-portal-redesign.md`
- **CRITICAL**: Never use the Edit tool on `src/templates/settings/index.html` — it breaks Tailwind CSS with trailing whitespace. Use Python splice scripts instead.
- After any template or static-JS change: run `cd src && npm run build:css`.
- SQLAlchemy: every `db.session.commit()` must be wrapped in `try/except` with `db.session.rollback()`.
- Do NOT create migration files. Tell the user to run `flask db migrate` themselves.
- `RegisteredApp` already has `allowed_ips` (JSON list, `default=list`) — `allowed_origins` follows the exact same pattern.
- The chat widget JS lives at `src/static/js/chat-widget.js`. It reads `window.InboxIQ.account` (account_id) and sends `context.account_id` to `/api/v1/chat/submit`. We will extend it to also read `window.InboxIQ.clientId` and include `context.client_id` in the payload.
- `AppProductAccess.webhook_url` stores the per-product webhook. Products: `chat`, `forms`, `intake_api`.
- Test pattern: mock-based unit tests in `tests/developer/`, see `tests/developer/test_routes.py` for the established fixture pattern.
- Import paths: `from src.models.developer import RegisteredApp, AppProductAccess`.
- Settings blueprint name: `settings` — `url_for("settings.developer_post")`, `url_for("settings.settings_page")`.
- `@login_required_settings` is the decorator for settings routes.

---

## File Map

| File | Action | What changes |
|---|---|---|
| `src/models/developer.py` | Modify | Add `allowed_origins` JSON column to `RegisteredApp` |
| `src/static/js/chat-widget.js` | Modify | Read `window.InboxIQ.clientId`; include `client_id` in context payload |
| `src/api/v1/intake.py` | Modify | Origin enforcement in `chat_submit` when `client_id` present and `allowed_origins` non-empty |
| `src/settings/routes.py` | Modify | Add `update_origins` POST action; add `test_webhook_endpoint` JSON route |
| `src/templates/settings/developer_portal.html` | Modify | Chat product approved card: embed snippet + origins editor; all approved products: test-webhook button + result div |
| `src/static/css/tailwind.min.css` | Rebuild | `npm run build:css` after template changes |
| `tests/developer/test_origin_check.py` | Create | Unit tests for origin enforcement logic in `chat_submit` |
| `tests/developer/test_routes.py` | Modify | Add tests for `update_origins` and `test_webhook_endpoint` |

---

### Task 1: Add `allowed_origins` to `RegisteredApp` model

**Files:**
- Modify: `src/models/developer.py` (line ~43 — after `allowed_ips`)
- Test: `tests/developer/test_model.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/developer/test_model.py`:

```python
def test_registered_app_has_allowed_origins_defaulting_to_empty_list():
    from src.models.developer import RegisteredApp
    app = RegisteredApp(
        account_id=1,
        name="Test",
        client_id="iq_test",
        client_secret_enc="enc",
        scopes=[],
        allowed_ips=[],
    )
    assert app.allowed_origins == []
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/developer/test_model.py::test_registered_app_has_allowed_origins_defaulting_to_empty_list -v
```

Expected: `AttributeError: allowed_origins` (column not yet defined).

- [ ] **Step 3: Add the column**

In `src/models/developer.py`, add after the `allowed_ips` line:

```python
    allowed_ips        = db.Column(db.JSON, nullable=False, default=list)
    allowed_origins    = db.Column(db.JSON, nullable=False, default=list)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/developer/test_model.py::test_registered_app_has_allowed_origins_defaulting_to_empty_list -v
```

Expected: PASS.

- [ ] **Step 5: Tell user to run migration**

> Run: `flask db migrate -m "add allowed_origins to registered_apps"` then `flask db upgrade`
> (Do NOT create the migration file yourself.)

- [ ] **Step 6: Commit**

```bash
git add src/models/developer.py tests/developer/test_model.py
git commit -m "feat(developer): add allowed_origins JSON column to RegisteredApp"
```

---

### Task 2: Extend chat-widget.js to forward `client_id`

**Files:**
- Modify: `src/static/js/chat-widget.js` (line ~4-5 config block; line ~143 context payload)

The widget reads `window.InboxIQ?.account` today. We add `window.InboxIQ?.clientId` — optional, used by registered apps. If absent the widget works exactly as before.

- [ ] **Step 1: Add `clientId` to the config block**

In `src/static/js/chat-widget.js`, the top of the IIFE currently reads:

```js
  const account = window.InboxIQ?.account || '2';
  const primaryColor = window.InboxIQ?.config?.primaryColor || '#6366f1';
```

Change to:

```js
  const account = window.InboxIQ?.account || '2';
  const clientId = window.InboxIQ?.clientId || null;
  const primaryColor = window.InboxIQ?.config?.primaryColor || '#6366f1';
```

- [ ] **Step 2: Include `client_id` in the chat submit payload**

The context object in `src/static/js/chat-widget.js` currently reads:

```js
      context: {
        account_id: account, name: state.name, email: state.email,
        branch: branch, page_url: window.location.href,
        history: state.messages.slice(-10),
      },
```

Change to:

```js
      context: {
        account_id: account, client_id: clientId,
        name: state.name, email: state.email,
        branch: branch, page_url: window.location.href,
        history: state.messages.slice(-10),
      },
```

- [ ] **Step 3: Verify no JS errors**

Open the browser console on any page that loads the widget. Confirm no errors. `clientId` will be `null` for unregistered embeds — that's correct.

- [ ] **Step 4: Commit**

```bash
git add src/static/js/chat-widget.js
git commit -m "feat(chat-widget): forward optional client_id in submit context"
```

---

### Task 3: Enforce allowed_origins in `chat/submit`

**Files:**
- Modify: `src/api/v1/intake.py` (function `chat_submit`, ~line 279)
- Create: `tests/developer/test_origin_check.py`

Origin enforcement is **opt-in**: only runs when ALL of:
1. `context.client_id` is present in the request payload
2. The `RegisteredApp` has a non-empty `allowed_origins` list
3. That app has an approved `AppProductAccess` for product `"chat"`

If any condition is false → skip enforcement (allow request). This preserves full backward compatibility with existing embeds.

- [ ] **Step 1: Write failing tests**

Create `tests/developer/test_origin_check.py`:

```python
# tests/developer/test_origin_check.py
import pytest
from unittest.mock import patch, MagicMock


def _make_app(allowed_origins=None, status="active"):
    app = MagicMock()
    app.id = "app-1"
    app.account_id = 1
    app.status = status
    app.allowed_origins = allowed_origins or []
    return app


def _make_access(product_slug="chat", status="approved"):
    acc = MagicMock()
    acc.product_slug = product_slug
    acc.status = status
    return acc


@pytest.fixture(scope="module")
def flask_app():
    from src.app import create_app
    a = create_app()
    a.config["TESTING"] = True
    return a


@pytest.fixture
def client(flask_app):
    return flask_app.test_client()


def _post_chat(client, client_id=None, origin=None):
    headers = {"Content-Type": "application/json"}
    if origin:
        headers["Origin"] = origin
    payload = {"body": "hello", "context": {"account_id": "1"}}
    if client_id:
        payload["context"]["client_id"] = client_id
    return client.post("/api/v1/chat/submit", json=payload, headers=headers)


def test_no_client_id_skips_origin_check(client):
    """Requests without client_id are never blocked (legacy behaviour)."""
    with patch("src.api.v1.intake.RegisteredApp") as MockApp, \
         patch("src.api.v1.intake.AppProductAccess"):
        MockApp.query.filter_by.return_value.first.return_value = None
        resp = _post_chat(client, client_id=None, origin="https://evil.com")
    # May 200 or 400 (account not found) but NOT 403
    assert resp.status_code != 403


def test_allowed_origins_empty_permits_any_origin(client):
    """When allowed_origins is [], any Origin is permitted."""
    mock_app = _make_app(allowed_origins=[])
    mock_access = _make_access()
    with patch("src.api.v1.intake.RegisteredApp") as MockApp, \
         patch("src.api.v1.intake.AppProductAccess") as MockAccess:
        MockApp.query.filter_by.return_value.first.return_value = mock_app
        MockAccess.query.filter_by.return_value.first.return_value = mock_access
        resp = _post_chat(client, client_id="iq_test", origin="https://anyone.com")
    assert resp.status_code != 403


def test_origin_not_in_allowlist_returns_403(client):
    """When allowed_origins is set, an unlisted Origin gets 403."""
    mock_app = _make_app(allowed_origins=["https://mysite.com"])
    mock_access = _make_access()
    with patch("src.api.v1.intake.RegisteredApp") as MockApp, \
         patch("src.api.v1.intake.AppProductAccess") as MockAccess:
        MockApp.query.filter_by.return_value.first.return_value = mock_app
        MockAccess.query.filter_by.return_value.first.return_value = mock_access
        resp = _post_chat(client, client_id="iq_test", origin="https://evil.com")
    assert resp.status_code == 403


def test_origin_in_allowlist_is_permitted(client):
    """When allowed_origins is set, a listed Origin is permitted."""
    mock_app = _make_app(allowed_origins=["https://mysite.com"])
    mock_access = _make_access()
    with patch("src.api.v1.intake.RegisteredApp") as MockApp, \
         patch("src.api.v1.intake.AppProductAccess") as MockAccess:
        MockApp.query.filter_by.return_value.first.return_value = mock_app
        MockAccess.query.filter_by.return_value.first.return_value = mock_access
        resp = _post_chat(client, client_id="iq_test", origin="https://mysite.com")
    assert resp.status_code != 403


def test_suspended_app_returns_403(client):
    """A suspended app cannot use the chat endpoint regardless of origin."""
    mock_app = _make_app(allowed_origins=[], status="suspended")
    with patch("src.api.v1.intake.RegisteredApp") as MockApp:
        MockApp.query.filter_by.return_value.first.return_value = mock_app
        resp = _post_chat(client, client_id="iq_test", origin="https://mysite.com")
    assert resp.status_code == 403


def test_chat_product_not_approved_returns_403(client):
    """Even if client_id is valid, chat access must be approved."""
    mock_app = _make_app(allowed_origins=[])
    mock_access = _make_access(status="pending")
    with patch("src.api.v1.intake.RegisteredApp") as MockApp, \
         patch("src.api.v1.intake.AppProductAccess") as MockAccess:
        MockApp.query.filter_by.return_value.first.return_value = mock_app
        MockAccess.query.filter_by.return_value.first.return_value = mock_access
        resp = _post_chat(client, client_id="iq_test", origin="https://mysite.com")
    assert resp.status_code == 403
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/developer/test_origin_check.py -v
```

Expected: Several assertions fail because origin enforcement doesn't exist yet.

- [ ] **Step 3: Add origin enforcement to `chat_submit`**

In `src/api/v1/intake.py`, add these imports near the top (after existing imports):

```python
from src.models.developer import RegisteredApp, AppProductAccess
```

Then in `chat_submit`, after the line that sets `account_id_int` and before the feature gate block (around line 330), add:

```python
    # ── Registered app origin check ────────────────────────────────────────
    req_client_id = str(context.get("client_id", "") or "").strip()[:64]
    if req_client_id:
        reg_app = RegisteredApp.query.filter_by(
            client_id=req_client_id, status="active"
        ).first()
        if not reg_app:
            return jsonify({"error": "forbidden", "message": "invalid client_id"}), 403
        # Require approved chat product access
        chat_access = AppProductAccess.query.filter_by(
            app_id=reg_app.id, product_slug="chat", status="approved"
        ).first()
        if not chat_access:
            return jsonify({"error": "forbidden", "message": "chat access not approved"}), 403
        # Enforce allowed_origins when the list is non-empty
        if reg_app.allowed_origins:
            request_origin = (request.headers.get("Origin") or "").rstrip("/")
            if request_origin not in [o.rstrip("/") for o in reg_app.allowed_origins]:
                return jsonify({"error": "forbidden", "message": "origin_not_allowed"}), 403
        # Use account_id from the app record (more trustworthy than caller-supplied value)
        account_id_int = reg_app.account_id
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/developer/test_origin_check.py -v
```

Expected: all 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/api/v1/intake.py tests/developer/test_origin_check.py
git commit -m "feat(chat): enforce allowed_origins per RegisteredApp when client_id supplied"
```

---

### Task 4: `update_origins` POST action in settings routes

**Files:**
- Modify: `src/settings/routes.py` (add after `update_webhook` block, ~line 2170)
- Modify: `tests/developer/test_routes.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/developer/test_routes.py`:

```python
def test_update_origins_saves_valid_origins(client):
    mock_account = _mock_account()
    mock_app = MagicMock()
    mock_app.id = "app-1"
    mock_app.name = "My App"
    mock_app.client_id = "iq_abc"
    mock_app.status = "active"
    mock_app.allowed_origins = []

    mock_user = MagicMock()
    mock_user.id = 1
    mock_user.email = "test@example.com"

    with patch("src.settings.verify_jwt_in_request"), \
         patch("src.settings.get_jwt", return_value={"account_id": "1"}), \
         patch("src.settings.get_jwt_identity", return_value="1"), \
         patch("src.settings.db") as mock_db, \
         patch("src.settings.account_allows_api", return_value=True), \
         patch("src.settings.routes.Account") as MockAccount, \
         patch("src.settings.routes.RegisteredApp") as MockApp:
        mock_db.session.get.return_value = mock_user
        mock_db.session.commit.return_value = None
        MockAccount.query.get.return_value = mock_account
        MockApp.query.filter_by.return_value.first.return_value = mock_app

        resp = client.post("/settings/developer", data={
            "action": "update_origins",
            "app_id": "app-1",
            "origins": "https://mysite.com\nhttps://staging.mysite.com",
        }, follow_redirects=False)

    assert resp.status_code in (302, 200)
    assert mock_app.allowed_origins == ["https://mysite.com", "https://staging.mysite.com"]


def test_update_origins_rejects_http_origins(client):
    mock_account = _mock_account()
    mock_app = MagicMock()
    mock_app.id = "app-1"
    mock_app.allowed_origins = []

    mock_user = MagicMock()
    mock_user.id = 1
    mock_user.email = "test@example.com"

    with patch("src.settings.verify_jwt_in_request"), \
         patch("src.settings.get_jwt", return_value={"account_id": "1"}), \
         patch("src.settings.get_jwt_identity", return_value="1"), \
         patch("src.settings.db") as mock_db, \
         patch("src.settings.account_allows_api", return_value=True), \
         patch("src.settings.routes.Account") as MockAccount, \
         patch("src.settings.routes.RegisteredApp") as MockApp:
        mock_db.session.get.return_value = mock_user
        MockAccount.query.get.return_value = mock_account
        MockApp.query.filter_by.return_value.first.return_value = mock_app

        client.post("/settings/developer", data={
            "action": "update_origins",
            "app_id": "app-1",
            "origins": "http://insecure.com",
        })

    # http:// origin must be silently dropped
    assert mock_app.allowed_origins == []
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/developer/test_routes.py::test_update_origins_saves_valid_origins tests/developer/test_routes.py::test_update_origins_rejects_http_origins -v
```

Expected: FAIL — action not handled.

- [ ] **Step 3: Add `update_origins` action to settings routes**

In `src/settings/routes.py`, after the `update_webhook` block (just before the final `return redirect(...)` at the end of the `developer_post` function), add:

```python
  if action == "update_origins":
    app_id = (request.form.get("app_id") or "").strip()
    raw_origins = (request.form.get("origins") or "")

    app = RegisteredApp.query.filter_by(id=app_id, account_id=account_id).first()
    if app:
      origins = []
      for line in raw_origins.splitlines():
        origin = line.strip().rstrip("/")[:255]
        if origin.startswith("https://") and len(origin) > 8:
          origins.append(origin)
      app.allowed_origins = origins[:20]  # cap at 20 entries
      try:
        db.session.commit()
      except Exception:
        db.session.rollback()
        raise
      current_app.logger.info(
        f"RegisteredApp allowed_origins updated account={account_id} app={app_id} count={len(app.allowed_origins)}"
      )
    return redirect(url_for("settings.settings_page", tab="developer", app_id=app_id))
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/developer/test_routes.py::test_update_origins_saves_valid_origins tests/developer/test_routes.py::test_update_origins_rejects_http_origins -v
```

Expected: both PASS.

- [ ] **Step 5: Commit**

```bash
git add src/settings/routes.py tests/developer/test_routes.py
git commit -m "feat(developer): update_origins POST action — save allowed_origins per app"
```

---

### Task 5: Webhook test endpoint

**Files:**
- Modify: `src/settings/routes.py` (add new JSON route after `_developer_page`)
- Modify: `tests/developer/test_routes.py`

This is a separate route (not a redirect action) because it must return JSON for the AJAX call from the portal UI.

- [ ] **Step 1: Write failing tests**

Add to `tests/developer/test_routes.py`:

```python
def test_test_webhook_returns_json_with_status(client):
    mock_account = _mock_account()
    mock_app = MagicMock()
    mock_app.id = "app-1"
    mock_app.account_id = 1

    mock_access = MagicMock()
    mock_access.status = "approved"
    mock_access.webhook_url = "https://example.com/hook"

    mock_user = MagicMock()
    mock_user.id = 1
    mock_user.email = "test@example.com"

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = '{"ok": true}'

    with patch("src.settings.verify_jwt_in_request"), \
         patch("src.settings.get_jwt", return_value={"account_id": "1"}), \
         patch("src.settings.get_jwt_identity", return_value="1"), \
         patch("src.settings.db") as mock_db, \
         patch("src.settings.account_allows_api", return_value=True), \
         patch("src.settings.routes.Account") as MockAccount, \
         patch("src.settings.routes.RegisteredApp") as MockApp, \
         patch("src.settings.routes.AppProductAccess") as MockAccess, \
         patch("src.settings.routes.requests") as mock_requests:
        mock_db.session.get.return_value = mock_user
        MockAccount.query.get.return_value = mock_account
        MockApp.query.filter_by.return_value.first.return_value = mock_app
        MockAccess.query.filter_by.return_value.first.return_value = mock_access
        mock_requests.post.return_value = mock_response

        resp = client.post("/settings/developer/test-webhook",
                           json={"app_id": "app-1", "product_slug": "chat"})

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert data["status_code"] == 200


def test_test_webhook_returns_error_when_no_webhook_url(client):
    mock_account = _mock_account()
    mock_app = MagicMock()
    mock_app.id = "app-1"
    mock_app.account_id = 1

    mock_access = MagicMock()
    mock_access.status = "approved"
    mock_access.webhook_url = None

    mock_user = MagicMock()
    mock_user.id = 1
    mock_user.email = "test@example.com"

    with patch("src.settings.verify_jwt_in_request"), \
         patch("src.settings.get_jwt", return_value={"account_id": "1"}), \
         patch("src.settings.get_jwt_identity", return_value="1"), \
         patch("src.settings.db") as mock_db, \
         patch("src.settings.account_allows_api", return_value=True), \
         patch("src.settings.routes.Account") as MockAccount, \
         patch("src.settings.routes.RegisteredApp") as MockApp, \
         patch("src.settings.routes.AppProductAccess") as MockAccess:
        mock_db.session.get.return_value = mock_user
        MockAccount.query.get.return_value = mock_account
        MockApp.query.filter_by.return_value.first.return_value = mock_app
        MockAccess.query.filter_by.return_value.first.return_value = mock_access

        resp = client.post("/settings/developer/test-webhook",
                           json={"app_id": "app-1", "product_slug": "chat"})

    assert resp.status_code == 400
    assert resp.get_json()["ok"] is False
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/developer/test_routes.py::test_test_webhook_returns_json_with_status tests/developer/test_routes.py::test_test_webhook_returns_error_when_no_webhook_url -v
```

Expected: 404 — route doesn't exist yet.

- [ ] **Step 3: Add `import requests` to settings/routes.py**

Near the top of `src/settings/routes.py`, find the existing imports and add:

```python
import requests as requests_lib
```

(Using alias to avoid collision with Flask's `request`.)

- [ ] **Step 4: Add the test-webhook route**

In `src/settings/routes.py`, add after the `_developer_page` function (at end of file or after the last developer helper):

```python
_WEBHOOK_TEST_PAYLOADS = {
    "chat": {
        "event": "chat.message",
        "data": {
            "message": "Hello, this is a test message from a visitor.",
            "session_id": "test_session_001",
        },
    },
    "forms": {
        "event": "form.submitted",
        "data": {
            "form_id": "contact_form",
            "fields": {
                "name": "Test User",
                "email": "test@example.com",
                "message": "This is a test form submission.",
            },
        },
    },
    "intake_api": {
        "event": "intake.ticket",
        "data": {
            "ticket_id": "test_ticket_001",
            "subject": "Test webhook delivery",
            "body": "This is a test event from InboxIQ. Your webhook is working correctly.",
            "priority": "normal",
        },
    },
}


@bp.route("/developer/test-webhook", methods=["POST"])
@login_required_settings
def developer_test_webhook():
    """Return JSON result of firing a synthetic event at the product webhook URL."""
    import time
    from datetime import timezone

    account_id = _get_account_id_from_jwt()
    if not account_id:
        return jsonify({"ok": False, "error": "unauthorized"}), 401

    body = request.get_json(silent=True) or {}
    app_id = (body.get("app_id") or "").strip()
    product_slug = (body.get("product_slug") or "").strip()

    if not app_id or not product_slug:
        return jsonify({"ok": False, "error": "app_id and product_slug required"}), 400

    app = RegisteredApp.query.filter_by(id=app_id, account_id=account_id).first()
    if not app:
        return jsonify({"ok": False, "error": "app not found"}), 404

    access = AppProductAccess.query.filter_by(
        app_id=app_id, product_slug=product_slug, status="approved"
    ).first()
    if not access:
        return jsonify({"ok": False, "error": "product not approved"}), 400

    if not access.webhook_url:
        return jsonify({"ok": False, "error": "no webhook URL configured"}), 400

    template = _WEBHOOK_TEST_PAYLOADS.get(product_slug, {
        "event": f"{product_slug}.test",
        "data": {},
    })
    payload = {
        **template,
        "app_id": app.client_id,
        "account_id": account_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "test": True,
    }

    start = time.monotonic()
    try:
        resp = requests_lib.post(
            access.webhook_url,
            json=payload,
            timeout=5,
            allow_redirects=False,
            headers={"User-Agent": "InboxIQ-Webhook/1.0"},
        )
        latency_ms = int((time.monotonic() - start) * 1000)
        return jsonify({
            "ok": True,
            "status_code": resp.status_code,
            "body": resp.text[:500],
            "latency_ms": latency_ms,
        })
    except requests_lib.exceptions.Timeout:
        return jsonify({"ok": False, "error": "timeout", "latency_ms": 5000})
    except requests_lib.exceptions.ConnectionError as e:
        return jsonify({"ok": False, "error": f"connection_error: {str(e)[:120]}"})
    except Exception as e:
        current_app.logger.error(f"test_webhook error account={account_id} app={app_id}: {e}")
        return jsonify({"ok": False, "error": "internal_error"}), 500
```

Also ensure `datetime` is imported at the top of `src/settings/routes.py`. Search for an existing `from datetime import datetime` — if absent add it.

**Note:** `_get_account_id_from_jwt()` — search `src/settings/routes.py` for the helper used by other routes that extracts `account_id` from JWT (likely named something similar). Use whatever pattern the file already uses. Do NOT invent a new helper.

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/developer/test_routes.py::test_test_webhook_returns_json_with_status tests/developer/test_routes.py::test_test_webhook_returns_error_when_no_webhook_url -v
```

Expected: both PASS.

- [ ] **Step 6: Commit**

```bash
git add src/settings/routes.py tests/developer/test_routes.py
git commit -m "feat(developer): synchronous test-webhook endpoint for approved products"
```

---

### Task 6: Portal UI — embed snippet, origins editor, test-webhook button

**Files:**
- Modify: `src/templates/settings/developer_portal.html`
- Rebuild: `src/static/css/tailwind.min.css`

This task modifies `developer_portal.html` (safe to use Edit tool — NOT `settings/index.html`). Three UI additions:
1. **Chat product approved card** — embed snippet with `client_id` + allowed_origins textarea + save button
2. **All approved product cards** — "Send test event" button (only visible when `webhook_url` is set)
3. **JS** — `testWebhook(appId, slug)` + `saveOrigins(form)` functions

Find the approved state block in the portal template. It currently looks like:

```html
{% if access and access.status == 'approved' %}
{# ── Approved ─────────────────────────────────────────────── #}
```

- [ ] **Step 1: Identify exact lines for the approved Chat card**

Run:

```bash
grep -n "Approved\|webhook_url\|approved\|product.slug\|access.status" src/templates/settings/developer_portal.html | head -30
```

Use the output to identify the lines that render the approved product card, specifically where `webhook_url` input is shown.

- [ ] **Step 2: Add embed snippet + origins editor to Chat product approved card**

In `src/templates/settings/developer_portal.html`, inside the `{% if access and access.status == 'approved' %}` block, add a conditional section that shows ONLY for the `chat` product. Insert it after the webhook URL form and before the closing `</div>` of the approved card:

```html
{% if product.slug == 'chat' %}
{# ── Embed snippet ──────────────────────────────────────── #}
<div class="mt-4 pt-4 border-t border-gray-100 dark:border-slate-700">
  <div class="text-xs font-semibold text-gray-500 dark:text-slate-400 mb-2">Embed snippet</div>
  <pre class="rounded-lg bg-gray-950 text-green-300 text-xs p-3 overflow-x-auto select-all whitespace-pre-wrap break-all leading-5"><code id="embedSnippet-{{ product.slug }}">&lt;script&gt;
window.InboxIQ = {
  account: '{{ account.id }}',
  clientId: '{{ selected_app.client_id }}',
  config: { primaryColor: '#6366f1' }
};
&lt;/script&gt;
&lt;script src="{{ request.host_url }}static/js/chat-widget.js"&gt;&lt;/script&gt;</code></pre>
  <button type="button" onclick="copyEmbedSnippet('{{ product.slug }}')"
          class="mt-1.5 text-xs text-indigo-600 dark:text-indigo-400 hover:underline">Copy snippet</button>
</div>
{# ── Allowed origins ───────────────────────────────────── #}
<div class="mt-4 pt-4 border-t border-gray-100 dark:border-slate-700">
  <div class="text-xs font-semibold text-gray-500 dark:text-slate-400 mb-1">Allowed origins</div>
  <p class="text-xs text-gray-400 dark:text-slate-500 mb-2">One HTTPS origin per line (e.g. <code class="text-xs">https://mysite.com</code>). Leave empty to allow all origins.</p>
  <form method="POST" action="{{ url_for('settings.developer_post') }}">
    <input type="hidden" name="csrf_token" value="{{ csrf_token() }}" />
    <input type="hidden" name="action" value="update_origins" />
    <input type="hidden" name="app_id" value="{{ selected_app.id }}" />
    <textarea name="origins" rows="3"
              class="w-full rounded-lg border border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-900 px-3 py-2 text-xs text-gray-900 dark:text-slate-100 font-mono focus:outline-none focus:border-indigo-500 resize-none"
              placeholder="https://mysite.com&#10;https://staging.mysite.com">{{ (selected_app.allowed_origins or []) | join('\n') }}</textarea>
    <button type="submit"
            class="mt-2 rounded-lg bg-indigo-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-indigo-500 transition-colors">
      Save origins
    </button>
  </form>
</div>
{% endif %}{# chat #}
```

- [ ] **Step 3: Add "Send test event" button to all approved product cards**

In the same approved card block, add the test webhook button after the webhook URL form (visible only when `access.webhook_url` is set):

```html
{% if access.webhook_url %}
<div class="mt-3 flex items-center gap-3">
  <button type="button"
          onclick="testWebhook('{{ selected_app.id | e }}', '{{ product.slug | e }}')"
          class="inline-flex items-center gap-1.5 rounded-lg border border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-800 px-3 py-1.5 text-xs font-medium text-gray-700 dark:text-slate-200 hover:border-indigo-400 dark:hover:border-indigo-400 transition-colors">
    <svg class="w-3.5 h-3.5 opacity-60" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z"/>
    </svg>
    Send test event
  </button>
  <span id="webhookTestResult-{{ product.slug }}" class="text-xs text-gray-500 dark:text-slate-400 hidden"></span>
</div>
{% endif %}
```

- [ ] **Step 4: Add JS functions**

In the `<script>` block at the bottom of `developer_portal.html`, add:

```javascript
async function testWebhook(appId, slug) {
  const resultEl = document.getElementById('webhookTestResult-' + slug);
  if (!resultEl) return;
  resultEl.textContent = 'Sending…';
  resultEl.className = 'text-xs text-gray-500 dark:text-slate-400';
  resultEl.classList.remove('hidden');
  try {
    const resp = await fetch('/settings/developer/test-webhook', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ app_id: appId, product_slug: slug }),
    });
    const data = await resp.json();
    if (data.ok) {
      resultEl.textContent = `✓ ${data.status_code} · ${data.latency_ms}ms`;
      resultEl.className = 'text-xs text-green-600 dark:text-green-400';
    } else {
      resultEl.textContent = `✗ ${data.error || 'error'}`;
      resultEl.className = 'text-xs text-red-600 dark:text-red-400';
    }
  } catch (_) {
    resultEl.textContent = '✗ network error';
    resultEl.className = 'text-xs text-red-600 dark:text-red-400';
  }
  setTimeout(() => resultEl.classList.add('hidden'), 8000);
}

function copyEmbedSnippet(slug) {
  const el = document.getElementById('embedSnippet-' + slug);
  if (!el) return;
  navigator.clipboard.writeText(el.textContent.trim()).then(() => {
    const btn = el.closest('.mt-4').querySelector('button');
    const orig = btn.textContent;
    btn.textContent = 'Copied!';
    setTimeout(() => btn.textContent = orig, 2000);
  });
}
```

- [ ] **Step 5: Rebuild Tailwind**

```bash
cd src && npm run build:css
```

Expected output: `Done in Xms`.

- [ ] **Step 6: Run the full developer test suite**

```bash
pytest tests/developer/ -v
```

Expected: all tests PASS.

- [ ] **Step 7: Commit**

```bash
git add src/templates/settings/developer_portal.html src/static/css/tailwind.min.css
git commit -m "feat(developer): embed snippet, allowed-origins editor, send-test-event button per product"
```

---

### Task 7: Push and smoke-test in browser

- [ ] **Step 1: Push**

```bash
git push origin main
```

- [ ] **Step 2: After deploy, verify in browser**

1. Go to `kalevent.com/settings/developer`
2. Select an app — confirm "Allowed origins" textarea appears under the Chat product (once approved)
3. Add `https://kalevent.com`, click Save — page reloads, textarea shows the saved origin
4. Set a webhook URL for any approved product, click "Send test event" — result shows `✓ 200 · Xms` or an error
5. Go to `kalevent.com/docs` — confirm header shows "Developer Portal" link (not "Log in")
6. Copy embed snippet — confirm `clientId` matches the app's `client_id`

---

## Self-review

### Spec coverage check

| Requirement | Task |
|---|---|
| `allowed_origins` column on `RegisteredApp` | Task 1 |
| Widget forwards `client_id` | Task 2 |
| `chat/submit` enforces origin when `client_id` + non-empty allowlist | Task 3 |
| Backward compat — no `client_id` skips enforcement | Task 3 (conditional) |
| `update_origins` POST action with `https://` validation | Task 4 |
| Chat embed snippet with `clientId` baked in | Task 6 |
| Origins editor UI | Task 6 |
| Webhook test endpoint returning JSON | Task 5 |
| "Send test event" UI + inline result | Task 6 |
| Migration instruction | Task 1 |

### Type/name consistency check

- `allowed_origins` used consistently across model, route action, JS, and template
- `requests_lib` alias avoids collision with Flask `request`
- `_WEBHOOK_TEST_PAYLOADS` dict keyed by product slug — matches `PRODUCT_CATALOG` slugs: `chat`, `forms`, `intake_api`
- `testWebhook(appId, slug)` ↔ endpoint reads `app_id`, `product_slug` — ✓
- `copyEmbedSnippet(slug)` uses `embedSnippet-{{ product.slug }}` id — ✓
- `webhookTestResult-{{ product.slug }}` id ↔ `document.getElementById('webhookTestResult-' + slug)` — ✓
