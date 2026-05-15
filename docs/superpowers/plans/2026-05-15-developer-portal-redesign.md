# Developer Portal Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the linear "request access → wait → register app" developer flow with a LinkedIn-style portal where apps are self-service and per-product access requests are made within each app, with per-product webhook URLs and full light/dark mode support.

**Architecture:** New `AppProductAccess` model (per app+product access record) replaces the monolithic `DeveloperAccessRequest` gate. A static `PRODUCT_CATALOG` in `src/developer/products.py` defines available products. The developer section in `settings/index.html` is extracted to `src/templates/settings/developer_portal.html` and included — this avoids the Edit-on-Tailwind-classes constraint that causes trailing whitespace bugs in the large settings file.

**Tech Stack:** Flask/SQLAlchemy, Jinja2, Tailwind CSS (dual light/dark `dark:` variants), Python 3.11.

---

## File Map

| File | Action | Responsibility |
| --- | --- | --- |
| `src/models/developer.py` | Modify | Add `AppProductAccess` model |
| `src/models/__init__.py` | Modify | Export `AppProductAccess` |
| `src/developer/__init__.py` | Create | Package marker |
| `src/developer/products.py` | Create | `PRODUCT_CATALOG` list + `get_product_by_slug()` helper |
| `src/settings/routes.py` | Modify | Remove approval gate; add `request_product`, `update_webhook` actions; update GET to pass new vars |
| `src/api/v1/admin.py` | Modify | Add `GET /admin/developer/product-requests` and `POST .../review` |
| `src/templates/admin/section_developer.html` | Modify | Add product access requests panel |
| `src/templates/settings/developer_portal.html` | Create | Full two-panel developer portal UI (light/dark) |
| `src/templates/settings/index.html` | Modify | Replace developer section body with `{% include %}` |
| `tests/developer/` | Create | Unit tests for model, product catalog, routes |

---

## Task 1: AppProductAccess model

**Files:**
- Modify: `src/models/developer.py`
- Modify: `src/models/__init__.py`
- Create: `tests/developer/__init__.py`
- Create: `tests/developer/test_model.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/developer/test_model.py
from src.developer.products import PRODUCT_CATALOG, get_product_by_slug


def test_app_product_access_has_expected_columns():
    from src.models.developer import AppProductAccess
    cols = {c.key for c in AppProductAccess.__table__.columns}
    assert "app_id" in cols
    assert "account_id" in cols
    assert "product_slug" in cols
    assert "status" in cols
    assert "webhook_url" in cols
    assert "use_case" in cols
    assert "requested_at" in cols
    assert "approved_at" in cols


def test_app_product_access_unique_constraint_exists():
    from src.models.developer import AppProductAccess
    constraint_names = {c.name for c in AppProductAccess.__table__.constraints}
    assert "uq_app_product" in constraint_names


def test_app_product_access_default_status_is_pending():
    from src.models.developer import AppProductAccess
    status_col = AppProductAccess.__table__.columns["status"]
    assert status_col.default.arg == "pending"
```

- [ ] **Step 2: Run test to confirm it fails**

```bash
cd /Users/kofi/inboxiq
.venv/bin/pytest tests/developer/test_model.py -v
```

Expected: `ModuleNotFoundError` or `ImportError` — model doesn't exist yet.

- [ ] **Step 3: Add AppProductAccess to `src/models/developer.py`**

Add after the `RegisteredApp` class (end of file):

```python
class AppProductAccess(db.Model):
    """Per-product access request for a registered app."""
    __tablename__ = "app_product_access"
    __table_args__ = (
        db.UniqueConstraint("app_id", "product_slug", name="uq_app_product"),
    )

    id           = db.Column(db.String(64), primary_key=True, default=lambda: str(uuid4()))
    app_id       = db.Column(db.String(64), db.ForeignKey("registered_apps.id", ondelete="CASCADE"), nullable=False)
    account_id   = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=False)
    product_slug = db.Column(db.String(64), nullable=False)
    status       = db.Column(db.String(32), nullable=False, default="pending")  # pending | approved | rejected
    use_case     = db.Column(db.Text, nullable=True)
    webhook_url  = db.Column(db.String(2048), nullable=True)
    requested_at = db.Column(db.DateTime(timezone=True), server_default=func.now(), nullable=False)
    approved_at  = db.Column(db.DateTime(timezone=True), nullable=True)
    reviewed_by  = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
```

- [ ] **Step 4: Export from `src/models/__init__.py`**

Find the line that imports from `developer.py` (it imports `DeveloperAccessRequest` and `RegisteredApp`). Add `AppProductAccess` to that import:

```python
from src.models.developer import DeveloperAccessRequest, RegisteredApp, AppProductAccess
```

- [ ] **Step 5: Create test package marker**

Create `tests/developer/__init__.py` as an empty file.

- [ ] **Step 6: Run tests to confirm they pass**

```bash
.venv/bin/pytest tests/developer/test_model.py -v
```

Expected:
```
PASSED tests/developer/test_model.py::test_app_product_access_has_expected_columns
PASSED tests/developer/test_model.py::test_app_product_access_unique_constraint_exists
PASSED tests/developer/test_model.py::test_app_product_access_default_status_is_pending
```

- [ ] **Step 7: Commit**

```bash
git add src/models/developer.py src/models/__init__.py tests/developer/__init__.py tests/developer/test_model.py
git commit -m "feat: add AppProductAccess model for per-product developer access"
```

---

## Task 2: Product catalog module

**Files:**
- Create: `src/developer/__init__.py`
- Create: `src/developer/products.py`
- Add to: `tests/developer/test_model.py` (extend the existing file)

- [ ] **Step 1: Write failing tests** (append to `tests/developer/test_model.py`)

```python
# append to tests/developer/test_model.py

def test_product_catalog_has_chat_forms_intake():
    from src.developer.products import PRODUCT_CATALOG
    slugs = {p["slug"] for p in PRODUCT_CATALOG}
    assert "chat" in slugs
    assert "forms" in slugs
    assert "intake_api" in slugs


def test_get_product_by_slug_returns_correct_product():
    from src.developer.products import get_product_by_slug
    p = get_product_by_slug("chat")
    assert p is not None
    assert p["name"] == "Chat / Aria Widget"
    assert p["approval"] == "reviewed"


def test_get_product_by_slug_returns_none_for_unknown():
    from src.developer.products import get_product_by_slug
    assert get_product_by_slug("nonexistent") is None


def test_intake_api_is_auto_approved():
    from src.developer.products import get_product_by_slug
    p = get_product_by_slug("intake_api")
    assert p["approval"] == "auto"
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
.venv/bin/pytest tests/developer/test_model.py -v -k "catalog or product_by_slug or intake"
```

Expected: `ModuleNotFoundError: No module named 'src.developer'`

- [ ] **Step 3: Create `src/developer/__init__.py`** (empty file)

- [ ] **Step 4: Create `src/developer/products.py`**

```python
from __future__ import annotations
from typing import Optional

PRODUCT_CATALOG: list[dict] = [
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
        "approval": "auto",
    },
]

_CATALOG_BY_SLUG = {p["slug"]: p for p in PRODUCT_CATALOG}


def get_product_by_slug(slug: str) -> Optional[dict]:
    return _CATALOG_BY_SLUG.get(slug)
```

- [ ] **Step 5: Run tests to confirm they pass**

```bash
.venv/bin/pytest tests/developer/test_model.py -v
```

Expected: all 7 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add src/developer/__init__.py src/developer/products.py tests/developer/test_model.py
git commit -m "feat: add developer product catalog with chat, forms, intake_api"
```

---

## Task 3: Settings routes — GET update

**Files:**
- Modify: `src/settings/routes.py`
- Create: `tests/developer/test_routes.py`

The GET handler (`settings_page`) currently only loads `registered_apps` when `developer_access_request.status == "approved"`. Change it to always load apps, plus the new vars.

- [ ] **Step 1: Write failing tests**

```python
# tests/developer/test_routes.py
import pytest
from unittest.mock import patch, MagicMock


@pytest.fixture
def app():
    from src.app import create_app
    app = create_app()
    app.config["TESTING"] = True
    app.config["SECRET_KEY"] = "test-secret"
    return app


@pytest.fixture
def client(app):
    return app.test_client()


def _mock_account(developer_access=True):
    acct = MagicMock()
    acct.id = 1
    acct.developer_access = developer_access
    acct.seats_limit = 5
    return acct


def test_developer_get_passes_product_catalog_to_template(client):
    mock_account = _mock_account()
    mock_app = MagicMock()
    mock_app.id = "app-1"
    mock_app.name = "My App"
    mock_app.client_id = "iq_abc"
    mock_app.status = "active"

    with patch("src.settings.routes.g") as mock_g, \
         patch("src.settings.routes.Account") as MockAccount, \
         patch("src.settings.routes.RegisteredApp") as MockApp, \
         patch("src.settings.routes.AppProductAccess") as MockAccess, \
         patch("src.settings.routes.DeveloperAccessRequest") as MockReq:
        mock_g.current_account_id = 1
        mock_g.current_user = MagicMock(id=1)
        MockAccount.query.get.return_value = mock_account
        MockApp.query.filter_by.return_value.order_by.return_value.all.return_value = [mock_app]
        MockAccess.query.filter_by.return_value.all.return_value = []
        MockReq.query.filter_by.return_value.order_by.return_value.first.return_value = None

        resp = client.get("/settings?tab=developer")

    assert resp.status_code == 200
    assert b"product_catalog" not in resp.data  # rendered, not a raw var name
    # template renders without error — product catalog comes from PRODUCT_CATALOG, not DB


def test_developer_get_selects_first_app_when_no_app_id(client):
    mock_account = _mock_account()
    mock_app = MagicMock()
    mock_app.id = "app-1"
    mock_app.name = "CRM Sync"
    mock_app.client_id = "iq_abc"
    mock_app.status = "active"

    with patch("src.settings.routes.g") as mock_g, \
         patch("src.settings.routes.Account") as MockAccount, \
         patch("src.settings.routes.RegisteredApp") as MockApp, \
         patch("src.settings.routes.AppProductAccess") as MockAccess, \
         patch("src.settings.routes.DeveloperAccessRequest") as MockReq:
        mock_g.current_account_id = 1
        mock_g.current_user = MagicMock(id=1)
        MockAccount.query.get.return_value = mock_account
        MockApp.query.filter_by.return_value.order_by.return_value.all.return_value = [mock_app]
        MockAccess.query.filter_by.return_value.all.return_value = []
        MockReq.query.filter_by.return_value.order_by.return_value.first.return_value = None

        resp = client.get("/settings?tab=developer")

    assert resp.status_code == 200
    assert b"CRM Sync" in resp.data
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
.venv/bin/pytest tests/developer/test_routes.py -v
```

Expected: failures because `AppProductAccess` isn't imported in routes yet and the template doesn't exist yet.

- [ ] **Step 3: Update imports in `src/settings/routes.py`**

Find the existing developer imports near the top of the file (around line 13):
```python
from src.models.developer import RegisteredApp, DeveloperAccessRequest
```

Replace with:
```python
from src.models.developer import RegisteredApp, DeveloperAccessRequest, AppProductAccess
from src.developer.products import PRODUCT_CATALOG
```

- [ ] **Step 4: Update the GET handler's developer block in `src/settings/routes.py`**

Find the block starting at approximately line 247:
```python
  # Developer tab — only accessible if account has developer_access
  developer_access_request = None
  registered_apps = []
  if tab == "developer" and account_id:
    if not (account and account.developer_access):
      tab = "team"  # silently redirect if not enabled
    else:
      developer_access_request = DeveloperAccessRequest.query.filter_by(
        account_id=account_id
      ).order_by(DeveloperAccessRequest.created_at.desc()).first()
      if developer_access_request and developer_access_request.status == "approved":
        registered_apps = RegisteredApp.query.filter_by(
          account_id=account_id
        ).order_by(RegisteredApp.created_at.desc()).all()
```

Replace with:
```python
  # Developer tab — only accessible if account has developer_access
  developer_access_request = None
  registered_apps = []
  selected_app = None
  product_accesses = {}
  if tab == "developer" and account_id:
    if not (account and account.developer_access):
      tab = "team"  # silently redirect if not enabled
    else:
      developer_access_request = DeveloperAccessRequest.query.filter_by(
        account_id=account_id
      ).order_by(DeveloperAccessRequest.created_at.desc()).first()
      registered_apps = RegisteredApp.query.filter_by(
        account_id=account_id
      ).order_by(RegisteredApp.created_at.desc()).all()
      # Select app from query param or fall back to first
      app_id_param = request.args.get("app_id", "").strip()
      if app_id_param:
        selected_app = next((a for a in registered_apps if a.id == app_id_param), None)
      if selected_app is None and registered_apps:
        selected_app = registered_apps[0]
      # Load product accesses for the selected app
      if selected_app:
        accesses = AppProductAccess.query.filter_by(app_id=selected_app.id).all()
        product_accesses = {a.product_slug: a for a in accesses}
```

- [ ] **Step 5: Pass new vars to `render_template` in the GET handler**

Find the `return render_template("settings/index.html", ...)` call (around line 270). Add these keyword args alongside the existing `registered_apps` and `developer_access_request`:

```python
    selected_app=selected_app,
    product_accesses=product_accesses,
    product_catalog=PRODUCT_CATALOG,
```

- [ ] **Step 6: Run tests**

```bash
.venv/bin/pytest tests/developer/test_routes.py -v
```

Expected: the import tests now work but template tests may still fail because `developer_portal.html` doesn't exist yet. That's fine — the GET handler changes are tested in Task 7 when the template is in place.

- [ ] **Step 7: Commit**

```bash
git add src/settings/routes.py tests/developer/test_routes.py
git commit -m "feat: update settings GET to load apps self-service with product accesses"
```

---

## Task 4: Settings routes — POST new actions

**Files:**
- Modify: `src/settings/routes.py`
- Modify: `tests/developer/test_routes.py`

- [ ] **Step 1: Write failing tests** (append to `tests/developer/test_routes.py`)

```python
# append to tests/developer/test_routes.py

def test_register_app_succeeds_without_developer_access_request(client):
    """App creation must work with developer_access=True even with no DeveloperAccessRequest."""
    mock_account = _mock_account()

    with patch("src.settings.routes.g") as mock_g, \
         patch("src.settings.routes.Account") as MockAccount, \
         patch("src.settings.routes.RegisteredApp") as MockApp, \
         patch("src.settings.routes.AppProductAccess"), \
         patch("src.settings.routes.DeveloperAccessRequest") as MockReq, \
         patch("src.settings.routes.db") as mock_db, \
         patch("src.settings.routes.encrypt_value", return_value="enc"), \
         patch("src.settings.routes.secrets") as mock_secrets:
        mock_g.current_account_id = 1
        MockAccount.query.get.return_value = mock_account
        MockReq.query.filter_by.return_value.order_by.return_value.first.return_value = None
        mock_secrets.token_hex.side_effect = ["abc123", "def456"]
        MockApp.query.filter_by.return_value.order_by.return_value.all.return_value = []

        resp = client.post("/settings/developer", data={
            "action": "register_app",
            "app_name": "My New App",
            "csrf_token": "dummy",
        })

    # Should redirect to developer tab, not bounce back to team tab
    assert resp.status_code == 302
    assert "developer" in resp.headers["Location"]


def test_request_product_creates_access_record(client):
    mock_account = _mock_account()
    mock_app = MagicMock()
    mock_app.id = "app-1"
    mock_app.account_id = 1

    with patch("src.settings.routes.g") as mock_g, \
         patch("src.settings.routes.Account") as MockAccount, \
         patch("src.settings.routes.RegisteredApp") as MockApp, \
         patch("src.settings.routes.AppProductAccess") as MockAccess, \
         patch("src.settings.routes.DeveloperAccessRequest"), \
         patch("src.settings.routes.db") as mock_db:
        mock_g.current_account_id = 1
        MockAccount.query.get.return_value = mock_account
        MockApp.query.filter_by.return_value.first.return_value = mock_app
        MockAccess.query.filter_by.return_value.first.return_value = None  # no existing request

        resp = client.post("/settings/developer", data={
            "action": "request_product",
            "app_id": "app-1",
            "product_slug": "chat",
            "use_case": "I want to embed Aria on my site",
            "csrf_token": "dummy",
        })

    assert resp.status_code == 302
    mock_db.session.add.assert_called_once()
    added = mock_db.session.add.call_args[0][0]
    assert added.product_slug == "chat"
    assert added.status == "pending"


def test_request_product_auto_approves_intake_api(client):
    mock_account = _mock_account()
    mock_app = MagicMock()
    mock_app.id = "app-1"
    mock_app.account_id = 1

    with patch("src.settings.routes.g") as mock_g, \
         patch("src.settings.routes.Account") as MockAccount, \
         patch("src.settings.routes.RegisteredApp") as MockApp, \
         patch("src.settings.routes.AppProductAccess") as MockAccess, \
         patch("src.settings.routes.DeveloperAccessRequest"), \
         patch("src.settings.routes.db") as mock_db:
        mock_g.current_account_id = 1
        MockAccount.query.get.return_value = mock_account
        MockApp.query.filter_by.return_value.first.return_value = mock_app
        MockAccess.query.filter_by.return_value.first.return_value = None

        resp = client.post("/settings/developer", data={
            "action": "request_product",
            "app_id": "app-1",
            "product_slug": "intake_api",
            "use_case": "submit support tickets",
            "csrf_token": "dummy",
        })

    assert resp.status_code == 302
    added = mock_db.session.add.call_args[0][0]
    assert added.status == "approved"  # auto-approved


def test_request_product_rejects_duplicate(client):
    mock_account = _mock_account()
    mock_app = MagicMock()
    mock_app.id = "app-1"
    mock_app.account_id = 1
    existing_access = MagicMock()  # already has a request

    with patch("src.settings.routes.g") as mock_g, \
         patch("src.settings.routes.Account") as MockAccount, \
         patch("src.settings.routes.RegisteredApp") as MockApp, \
         patch("src.settings.routes.AppProductAccess") as MockAccess, \
         patch("src.settings.routes.DeveloperAccessRequest"), \
         patch("src.settings.routes.db") as mock_db:
        mock_g.current_account_id = 1
        MockAccount.query.get.return_value = mock_account
        MockApp.query.filter_by.return_value.first.return_value = mock_app
        MockAccess.query.filter_by.return_value.first.return_value = existing_access  # duplicate

        resp = client.post("/settings/developer", data={
            "action": "request_product",
            "app_id": "app-1",
            "product_slug": "chat",
            "use_case": "trying again",
            "csrf_token": "dummy",
        })

    assert resp.status_code == 302
    mock_db.session.add.assert_not_called()  # no new record created


def test_update_webhook_succeeds_when_approved(client):
    mock_account = _mock_account()
    mock_app = MagicMock()
    mock_app.id = "app-1"
    mock_app.account_id = 1
    mock_access = MagicMock()
    mock_access.status = "approved"

    with patch("src.settings.routes.g") as mock_g, \
         patch("src.settings.routes.Account") as MockAccount, \
         patch("src.settings.routes.RegisteredApp") as MockApp, \
         patch("src.settings.routes.AppProductAccess") as MockAccess, \
         patch("src.settings.routes.DeveloperAccessRequest"), \
         patch("src.settings.routes.db") as mock_db:
        mock_g.current_account_id = 1
        MockAccount.query.get.return_value = mock_account
        MockApp.query.filter_by.return_value.first.return_value = mock_app
        MockAccess.query.filter_by.return_value.first.return_value = mock_access

        resp = client.post("/settings/developer", data={
            "action": "update_webhook",
            "app_id": "app-1",
            "product_slug": "chat",
            "webhook_url": "https://example.com/hooks/chat",
            "csrf_token": "dummy",
        })

    assert resp.status_code == 302
    assert mock_access.webhook_url == "https://example.com/hooks/chat"
    mock_db.session.commit.assert_called()


def test_update_webhook_blocked_when_not_approved(client):
    mock_account = _mock_account()
    mock_app = MagicMock()
    mock_app.id = "app-1"
    mock_app.account_id = 1
    mock_access = MagicMock()
    mock_access.status = "pending"  # not approved

    with patch("src.settings.routes.g") as mock_g, \
         patch("src.settings.routes.Account") as MockAccount, \
         patch("src.settings.routes.RegisteredApp") as MockApp, \
         patch("src.settings.routes.AppProductAccess") as MockAccess, \
         patch("src.settings.routes.DeveloperAccessRequest"), \
         patch("src.settings.routes.db") as mock_db:
        mock_g.current_account_id = 1
        MockAccount.query.get.return_value = mock_account
        MockApp.query.filter_by.return_value.first.return_value = mock_app
        MockAccess.query.filter_by.return_value.first.return_value = mock_access

        resp = client.post("/settings/developer", data={
            "action": "update_webhook",
            "app_id": "app-1",
            "product_slug": "chat",
            "webhook_url": "https://example.com/hooks/chat",
            "csrf_token": "dummy",
        })

    assert resp.status_code == 302
    # webhook_url must NOT have been set
    assert mock_access.webhook_url != "https://example.com/hooks/chat"
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
.venv/bin/pytest tests/developer/test_routes.py -v -k "register_app or request_product or update_webhook"
```

Expected: `test_register_app` fails (still gated), others fail with 405 or missing action.

- [ ] **Step 3: Update the `register_app` action in `src/settings/routes.py`**

Find the `register_app` block (around line 2026). Remove the approval gate entirely:

```python
  # ── Register new app ───────────────────────────────────────────────────────
  if action == "register_app":
    app_name = (request.form.get("app_name") or "").strip()
    if not app_name:
      registered_apps = RegisteredApp.query.filter_by(account_id=account_id).order_by(RegisteredApp.created_at.desc()).all()
      return _developer_page(
        account_id=account_id,
        account=account,
        developer_access_request=None,
        registered_apps=registered_apps,
        selected_app=registered_apps[0] if registered_apps else None,
        product_accesses={},
        error="App name is required.",
        new_app=None,
      )

    client_id = "iq_" + secrets.token_hex(16)
    client_secret_plain = secrets.token_hex(32)

    new_registered_app = RegisteredApp(
      account_id=account_id,
      name=app_name,
      client_id=client_id,
      client_secret_enc=encrypt_value(client_secret_plain),
      scopes=[],
    )
    try:
      db.session.add(new_registered_app)
      db.session.commit()
    except Exception:
      db.session.rollback()
      raise
    current_app.logger.info(
      f"RegisteredApp created account={account_id} client_id={client_id}"
    )

    registered_apps = RegisteredApp.query.filter_by(account_id=account_id).order_by(RegisteredApp.created_at.desc()).all()
    return _developer_page(
      account_id=account_id,
      account=account,
      developer_access_request=None,
      registered_apps=registered_apps,
      selected_app=new_registered_app,
      product_accesses={},
      error=None,
      new_app={"name": app_name, "client_id": client_id, "client_secret": client_secret_plain},
    )
```

- [ ] **Step 4: Add `request_product` action** (insert after the `revoke_app` block, before `return redirect(...)`):

```python
  # ── Request product access ─────────────────────────────────────────────────
  if action == "request_product":
    app_id = (request.form.get("app_id") or "").strip()
    product_slug = (request.form.get("product_slug") or "").strip()
    use_case = (request.form.get("use_case") or "").strip()

    app = RegisteredApp.query.filter_by(id=app_id, account_id=account_id).first()
    if not app or not product_slug:
      return redirect(url_for("settings.settings_page", tab="developer"))

    # Block duplicate requests
    existing = AppProductAccess.query.filter_by(app_id=app_id, product_slug=product_slug).first()
    if existing:
      return redirect(url_for("settings.settings_page", tab="developer", app_id=app_id))

    # Auto-approve if product approval == "auto"
    from src.developer.products import get_product_by_slug
    product = get_product_by_slug(product_slug)
    status = "approved" if (product and product.get("approval") == "auto") else "pending"

    access = AppProductAccess(
      app_id=app_id,
      account_id=account_id,
      product_slug=product_slug,
      status=status,
      use_case=use_case or None,
    )
    try:
      db.session.add(access)
      db.session.commit()
    except Exception:
      db.session.rollback()
      raise
    current_app.logger.info(
      f"AppProductAccess created account={account_id} app={app_id} product={product_slug} status={status}"
    )
    return redirect(url_for("settings.settings_page", tab="developer", app_id=app_id))

  # ── Update product webhook ─────────────────────────────────────────────────
  if action == "update_webhook":
    app_id = (request.form.get("app_id") or "").strip()
    product_slug = (request.form.get("product_slug") or "").strip()
    webhook_url = (request.form.get("webhook_url") or "").strip() or None

    app = RegisteredApp.query.filter_by(id=app_id, account_id=account_id).first()
    if not app:
      return redirect(url_for("settings.settings_page", tab="developer"))

    access = AppProductAccess.query.filter_by(app_id=app_id, product_slug=product_slug).first()
    if not access or access.status != "approved":
      return redirect(url_for("settings.settings_page", tab="developer", app_id=app_id))

    # Basic URL validation
    if webhook_url and not webhook_url.startswith(("https://", "http://")):
      return redirect(url_for("settings.settings_page", tab="developer", app_id=app_id))

    access.webhook_url = webhook_url
    try:
      db.session.commit()
    except Exception:
      db.session.rollback()
      raise
    current_app.logger.info(
      f"AppProductAccess webhook updated account={account_id} app={app_id} product={product_slug}"
    )
    return redirect(url_for("settings.settings_page", tab="developer", app_id=app_id))
```

- [ ] **Step 5: Update `_developer_page` signature** to accept and pass the new vars.

Find the existing `_developer_page` function signature (around line 2085):

```python
def _developer_page(*, account_id, account, developer_access_request, registered_apps, error, new_app):
  """Render the developer settings tab directly (used after form submission)."""
  from src.models.ai import MCPServerCatalog
  mcp_servers = MCPServerCatalog.query.filter_by(enabled=True).order_by(MCPServerCatalog.label.asc()).all()
  return render_template(
    "settings/index.html",
    active_tab="developer",
    account_id=account_id,
    account=account,
    developer_access_request=developer_access_request,
    registered_apps=registered_apps,
    mcp_servers=mcp_servers,
    developer_error=error,
    new_app=new_app,
```

Replace with:

```python
def _developer_page(*, account_id, account, developer_access_request, registered_apps,
                    selected_app=None, product_accesses=None, error, new_app):
  """Render the developer settings tab directly (used after form submission)."""
  from src.models.ai import MCPServerCatalog
  mcp_servers = MCPServerCatalog.query.filter_by(enabled=True).order_by(MCPServerCatalog.label.asc()).all()
  return render_template(
    "settings/index.html",
    active_tab="developer",
    account_id=account_id,
    account=account,
    developer_access_request=developer_access_request,
    registered_apps=registered_apps,
    selected_app=selected_app,
    product_accesses=product_accesses or {},
    product_catalog=PRODUCT_CATALOG,
    mcp_servers=mcp_servers,
    developer_error=error,
    new_app=new_app,
```

- [ ] **Step 6: Run tests**

```bash
.venv/bin/pytest tests/developer/test_routes.py -v
```

Expected: all route tests PASS (GET tests may still fail because template not created yet — that's fine).

- [ ] **Step 7: Commit**

```bash
git add src/settings/routes.py tests/developer/test_routes.py
git commit -m "feat: add request_product and update_webhook actions; remove register_app approval gate"
```

---

## Task 5: Admin API — product-request endpoints

**Files:**
- Modify: `src/api/v1/admin.py`
- Create: `tests/developer/test_admin_api.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/developer/test_admin_api.py
import pytest
from unittest.mock import patch, MagicMock


@pytest.fixture
def app():
    from src.app import create_app
    app = create_app()
    app.config["TESTING"] = True
    app.config["SECRET_KEY"] = "test-secret"
    return app


@pytest.fixture
def client(app):
    return app.test_client()


def _auth_headers():
    # Admin routes check JWT — patch the decorator instead
    return {}


def test_product_requests_list_endpoint_exists(client):
    with patch("src.api.v1.admin.admin_required", lambda f: f), \
         patch("src.api.v1.admin.AppProductAccess") as MockAccess, \
         patch("src.api.v1.admin.RegisteredApp") as MockApp, \
         patch("src.api.v1.admin.Account") as MockAccount:
        mock_access = MagicMock()
        mock_access.id = "access-1"
        mock_access.product_slug = "chat"
        mock_access.status = "pending"
        mock_access.use_case = "embed on site"
        mock_access.requested_at.isoformat.return_value = "2026-05-15T10:00:00"
        mock_access.app_id = "app-1"
        mock_access.account_id = 1

        MockAccess.query.filter_by.return_value.order_by.return_value.all.return_value = [mock_access]
        MockApp.query.get.return_value = MagicMock(name="CRM Sync")
        MockAccount.query.get.return_value = MagicMock(email="user@example.com")

        resp = client.get("/api/v1/admin/developer/product-requests")

    assert resp.status_code == 200
    data = resp.get_json()
    assert isinstance(data, list)
    assert data[0]["product_slug"] == "chat"


def test_product_request_review_approve(client):
    with patch("src.api.v1.admin.admin_required", lambda f: f), \
         patch("src.api.v1.admin.AppProductAccess") as MockAccess, \
         patch("src.api.v1.admin.db") as mock_db, \
         patch("src.api.v1.admin.g") as mock_g:
        mock_access = MagicMock()
        mock_access.status = "pending"
        mock_g.current_user = MagicMock(id=99)
        MockAccess.query.get.return_value = mock_access

        resp = client.post("/api/v1/admin/developer/product-requests/access-1/review",
                           json={"status": "approved"})

    assert resp.status_code == 200
    assert mock_access.status == "approved"
    assert mock_access.reviewed_by == 99
    mock_db.session.commit.assert_called_once()


def test_product_request_review_rejects_invalid_status(client):
    with patch("src.api.v1.admin.admin_required", lambda f: f), \
         patch("src.api.v1.admin.AppProductAccess") as MockAccess:
        MockAccess.query.get.return_value = MagicMock(status="pending")

        resp = client.post("/api/v1/admin/developer/product-requests/access-1/review",
                           json={"status": "maybe"})

    assert resp.status_code == 400
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
.venv/bin/pytest tests/developer/test_admin_api.py -v
```

Expected: 404 — endpoints don't exist yet.

- [ ] **Step 3: Add import to `src/api/v1/admin.py`**

Find the imports at the top of `src/api/v1/admin.py`. Add `AppProductAccess`:

```python
from src.models.developer import DeveloperAccessRequest, RegisteredApp, AppProductAccess
```

(If those models are currently imported inside individual functions, add the import at the top instead.)

- [ ] **Step 4: Add the two endpoints to `src/api/v1/admin.py`**

Add after the existing `admin_developer_review` function:

```python
@v1.route("/admin/developer/product-requests", methods=["GET"])
@admin_required
def admin_developer_product_requests():
    """List all pending product access requests."""
    from src.models.core import Account
    requests_all = AppProductAccess.query.filter_by(status="pending").order_by(
        AppProductAccess.requested_at.desc()
    ).all()
    result = []
    for req in requests_all:
        app = RegisteredApp.query.get(req.app_id)
        account = Account.query.get(req.account_id)
        result.append({
            "id": req.id,
            "product_slug": req.product_slug,
            "status": req.status,
            "use_case": req.use_case,
            "requested_at": req.requested_at.isoformat() if req.requested_at else None,
            "app_name": app.name if app else None,
            "app_client_id": app.client_id if app else None,
            "account_email": account.email if account else None,
            "account_id": req.account_id,
        })
    return jsonify(result)


@v1.route("/admin/developer/product-requests/<request_id>/review", methods=["POST"])
@admin_required
def admin_developer_product_request_review(request_id):
    """Approve or reject a product access request."""
    from datetime import datetime, timezone
    data = request.get_json(force=True) or {}
    status = data.get("status", "").strip()
    if status not in ("approved", "rejected"):
        return jsonify({"error": "status must be 'approved' or 'rejected'"}), 400

    req = AppProductAccess.query.get(request_id)
    if not req:
        return jsonify({"error": "not found"}), 404

    req.status = status
    req.reviewed_by = g.current_user.id if g.current_user else None
    if status == "approved":
        req.approved_at = datetime.now(timezone.utc)
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    current_app.logger.info(
        f"admin: product access {request_id} {status} by {g.current_user.id if g.current_user else 'unknown'}"
    )
    return jsonify({"status": status})
```

- [ ] **Step 5: Run tests**

```bash
.venv/bin/pytest tests/developer/test_admin_api.py -v
```

Expected: all 3 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add src/api/v1/admin.py tests/developer/test_admin_api.py
git commit -m "feat: add admin API endpoints for product access request review"
```

---

## Task 6: Admin template — product requests panel

**Files:**
- Modify: `src/templates/admin/section_developer.html`

- [ ] **Step 1: Replace `src/templates/admin/section_developer.html`** with the updated version adding the product requests panel below the existing "Access Requests" panel:

```html
<section id="section-developer" class="admin-section">
  <div class="content-container space-y-6">
    <div>
      <h1 class="text-2xl font-semibold tracking-tight">Developer Access</h1>
      <p class="text-sm text-slate-300 mt-1">Manage API access and product approvals per account.</p>
    </div>

    <!-- Enable developer access for an account -->
    <div class="rounded-2xl border border-slate-800 bg-slate-900/70 p-5">
      <h2 class="text-base font-semibold text-slate-100 mb-3">Enable Developer Portal</h2>
      <p class="text-sm text-slate-400 mb-4">Grant an account access to the Developer tab in Settings.</p>
      <div class="flex items-end gap-3">
        <div class="flex-1">
          <label class="block text-xs text-slate-400 mb-1">Account ID</label>
          <input type="number" id="devAccessAccountId" placeholder="e.g. 2"
                 class="w-full rounded-lg bg-slate-950 border border-slate-700 px-3 py-2 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-indigo-500" />
        </div>
        <button onclick="enableDeveloperAccess()" class="flex-shrink-0 rounded-xl bg-indigo-600 px-4 py-2 text-sm font-semibold text-white hover:bg-indigo-500 transition-colors">Enable</button>
      </div>
      <div id="devAccessResult" class="hidden mt-3 text-xs px-3 py-2 rounded-xl border"></div>
    </div>

    <!-- Product access requests (new) -->
    <div class="rounded-2xl border border-slate-800 bg-slate-900/70 p-5">
      <div class="flex items-center justify-between mb-4">
        <h2 class="text-base font-semibold text-slate-100">Product Access Requests</h2>
        <button onclick="loadProductRequests()" class="text-xs text-indigo-400 hover:text-indigo-300">Refresh</button>
      </div>
      <div id="productRequestsList">
        <p class="text-sm text-slate-500">Loading...</p>
      </div>
    </div>

    <!-- Legacy account-level access requests -->
    <div class="rounded-2xl border border-slate-800 bg-slate-900/70 p-5">
      <div class="flex items-center justify-between mb-4">
        <h2 class="text-base font-semibold text-slate-100">Account Access Requests (legacy)</h2>
        <button onclick="loadDevRequests()" class="text-xs text-indigo-400 hover:text-indigo-300">Refresh</button>
      </div>
      <div id="devRequestsList">
        <p class="text-sm text-slate-500">Loading...</p>
      </div>
    </div>
  </div>
</section>

<script>
async function loadProductRequests() {
  const el = document.getElementById('productRequestsList');
  try {
    const token = localStorage.getItem('access_token') || sessionStorage.getItem('access_token') || '';
    const resp = await fetch('/api/v1/admin/developer/product-requests', {
      headers: { Authorization: `Bearer ${token}` }
    });
    const items = await resp.json();
    if (!items.length) {
      el.innerHTML = '<p class="text-sm text-slate-500">No pending product requests.</p>';
      return;
    }
    el.innerHTML = items.map(r => `
      <div class="flex items-start justify-between gap-4 py-3 border-b border-slate-800 last:border-0">
        <div class="min-w-0">
          <div class="text-sm text-slate-100 font-medium">${r.account_email || r.account_id} — ${r.app_name || r.app_id}</div>
          <div class="text-xs text-indigo-300 mt-0.5">${r.product_slug}</div>
          ${r.use_case ? `<p class="text-xs text-slate-400 mt-1">"${r.use_case}"</p>` : ''}
          <div class="text-xs text-slate-500 mt-0.5">${r.requested_at || ''}</div>
        </div>
        <div class="flex gap-2 flex-shrink-0">
          <button onclick="reviewProductRequest('${r.id}','approved')"
                  class="rounded-lg bg-emerald-600/20 border border-emerald-500/30 px-3 py-1 text-xs text-emerald-300 hover:bg-emerald-600/30 transition-colors">Approve</button>
          <button onclick="reviewProductRequest('${r.id}','rejected')"
                  class="rounded-lg bg-red-600/10 border border-red-500/30 px-3 py-1 text-xs text-red-300 hover:bg-red-600/20 transition-colors">Reject</button>
        </div>
      </div>`).join('');
  } catch (e) {
    el.innerHTML = `<p class="text-sm text-red-400">Error loading requests: ${e.message}</p>`;
  }
}

async function reviewProductRequest(id, status) {
  const token = localStorage.getItem('access_token') || sessionStorage.getItem('access_token') || '';
  const resp = await fetch(`/api/v1/admin/developer/product-requests/${id}/review`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
    body: JSON.stringify({ status })
  });
  if (resp.ok) loadProductRequests();
}

document.addEventListener('DOMContentLoaded', () => {
  if (document.getElementById('section-developer')?.classList.contains('active')) {
    loadProductRequests();
    loadDevRequests();
  }
});
</script>
```

- [ ] **Step 2: Verify the admin page renders without error** (the new JS functions `loadProductRequests` and `reviewProductRequest` are defined, and `loadDevRequests` still exists in `admin.html`).

```bash
grep -n "loadDevRequests\|enableDeveloperAccess" /Users/kofi/inboxiq/src/templates/admin.html | head -5
```

Expected: at least one match confirming those functions exist in the parent admin.html.

- [ ] **Step 3: Commit**

```bash
git add src/templates/admin/section_developer.html
git commit -m "feat: add product access requests panel to admin developer section"
```

---

## Task 7: Developer portal template (new file)

**Files:**
- Create: `src/templates/settings/developer_portal.html`

This template is included inside the `{% elif active_tab == 'developer' %}` block. It has access to all template vars passed from the route: `registered_apps`, `selected_app`, `product_accesses`, `product_catalog`, `new_app`, `developer_error`, `csrf_token()`.

- [ ] **Step 1: Create `src/templates/settings/developer_portal.html`**

```html
{# Developer portal — included by settings/index.html when active_tab == 'developer' #}

{# ── Credential modal (shown once after app creation) ──────────────────────── #}
{% if new_app %}
<div id="credentialModal" class="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/90 backdrop-blur-sm">
  <div class="relative w-full max-w-lg mx-4 rounded-2xl border border-amber-500/50 bg-slate-900 shadow-2xl p-6">
    <div class="flex items-start gap-3 mb-4">
      <div class="flex-shrink-0 w-9 h-9 rounded-full bg-amber-500/20 flex items-center justify-center">
        <svg class="w-5 h-5 text-amber-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/>
        </svg>
      </div>
      <div>
        <div class="text-base font-semibold text-amber-300">Copy your credentials now</div>
        <p class="text-xs text-slate-400 mt-1">The client secret is shown <strong class="text-slate-200">once only</strong> and cannot be retrieved after you dismiss this.</p>
      </div>
    </div>
    <div class="space-y-3 mb-5">
      <div>
        <label class="block text-xs text-slate-400 mb-1">App</label>
        <code class="block rounded-lg bg-slate-950 border border-slate-700 px-3 py-2 text-sm text-slate-100 font-mono">{{ new_app.name }}</code>
      </div>
      <div>
        <label class="block text-xs text-slate-400 mb-1">Client ID</label>
        <div class="flex items-center gap-2">
          <code id="modalClientId" class="flex-1 rounded-lg bg-slate-950 border border-slate-700 px-3 py-2 text-sm text-slate-100 font-mono select-all break-all">{{ new_app.client_id }}</code>
          <button type="button" onclick="copyModal('modalClientId',this)" class="flex-shrink-0 rounded-lg border border-slate-700 px-2 py-2 text-xs text-slate-400 hover:text-white hover:border-slate-500 transition-colors">Copy</button>
        </div>
      </div>
      <div>
        <label class="block text-xs text-amber-400 mb-1 font-medium">Client Secret — copy this now</label>
        <div class="flex items-center gap-2">
          <code id="modalClientSecret" class="flex-1 rounded-lg bg-slate-950 border border-amber-500/50 px-3 py-2 text-sm text-amber-100 font-mono select-all break-all">{{ new_app.client_secret }}</code>
          <button type="button" onclick="copyModal('modalClientSecret',this)" class="flex-shrink-0 rounded-lg border border-amber-500/40 px-2 py-2 text-xs text-amber-300 hover:bg-amber-500/10 transition-colors">Copy</button>
        </div>
      </div>
    </div>
    <label class="flex items-start gap-2 cursor-pointer mb-4">
      <input type="checkbox" id="copiedConfirm" onchange="document.getElementById('dismissCredentials').disabled=!this.checked"
             class="mt-0.5 rounded border-slate-600 bg-slate-800 text-amber-500 focus:ring-amber-500" />
      <span class="text-sm text-slate-300">I have copied and stored both the Client ID and Client Secret securely.</span>
    </label>
    <button id="dismissCredentials" disabled onclick="document.getElementById('credentialModal').remove()"
            class="w-full rounded-xl bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-indigo-500 transition-colors disabled:opacity-40 disabled:cursor-not-allowed">
      I've saved my credentials — close
    </button>
  </div>
</div>
<script>
function copyModal(id, btn) {
  navigator.clipboard.writeText(document.getElementById(id).textContent.trim()).then(() => {
    const orig = btn.textContent; btn.textContent = 'Copied!';
    setTimeout(() => btn.textContent = orig, 2000);
  });
}
</script>
{% endif %}

{# ── Page header ─────────────────────────────────────────────────────────── #}
<div class="space-y-2">
  <h2 class="text-xl font-semibold text-gray-900 dark:text-slate-100">Developer</h2>
  <p class="text-sm text-gray-600 dark:text-slate-300">Register apps and request access to InboxIQ products. Each product gets its own credentials and webhook URL.</p>
</div>

{% if developer_error %}
<div class="mt-4 rounded-xl border border-red-400/40 bg-red-50 dark:bg-red-500/10 px-4 py-3 text-sm text-red-700 dark:text-red-200">
  {{ developer_error }}
</div>
{% endif %}

{# ── Two-panel layout ─────────────────────────────────────────────────────── #}
<div class="mt-6 lg:grid lg:grid-cols-[220px_1fr] lg:rounded-2xl lg:border lg:border-gray-200 lg:dark:border-slate-800 lg:overflow-hidden">

  {# ── Sidebar ──────────────────────────────────────────────────────────── #}
  <div class="lg:border-r lg:border-gray-200 lg:dark:border-slate-800 lg:bg-gray-50 lg:dark:bg-slate-900/50">

    {# Mobile: select dropdown #}
    {% if registered_apps %}
    <div class="lg:hidden px-4 py-3">
      <select onchange="location.href='{{ url_for('settings.settings_page', tab='developer') }}&app_id='+this.value"
              class="w-full rounded-lg border border-gray-300 dark:border-slate-700 bg-white dark:bg-slate-900 px-3 py-2 text-sm text-gray-900 dark:text-slate-100 focus:outline-none focus:border-indigo-500">
        {% for app in registered_apps %}
          <option value="{{ app.id }}"{% if selected_app and selected_app.id == app.id %} selected{% endif %}>{{ app.name }}</option>
        {% endfor %}
      </select>
    </div>
    {% endif %}

    {# Desktop: app list #}
    <div class="hidden lg:flex lg:flex-col p-3 gap-0.5 min-h-[200px]">
      <div class="px-2 py-1.5 text-xs font-semibold uppercase tracking-wider text-gray-400 dark:text-slate-500 mb-1">My Apps</div>

      {% for app in registered_apps %}
      <a href="{{ url_for('settings.settings_page', tab='developer', app_id=app.id) }}"
         class="flex items-center gap-2 px-2.5 py-2 rounded-lg text-sm transition-colors
                {% if selected_app and selected_app.id == app.id %}bg-indigo-50 dark:bg-indigo-500/10 text-indigo-700 dark:text-indigo-300 font-medium border border-indigo-200 dark:border-indigo-400/30{% else %}text-gray-700 dark:text-slate-300 hover:bg-gray-100 dark:hover:bg-slate-800/60 border border-transparent{% endif %}">
        <span class="flex-shrink-0 w-5 h-5 rounded bg-indigo-100 dark:bg-indigo-500/20 text-indigo-600 dark:text-indigo-300 flex items-center justify-center text-xs font-bold">{{ app.name[0].upper() }}</span>
        <span class="truncate">{{ app.name }}</span>
      </a>
      {% endfor %}

      {# New app inline form #}
      <div class="mt-2 pt-2 border-t border-gray-200 dark:border-slate-700">
        <form method="POST" action="{{ url_for('settings.developer_post') }}">
          <input type="hidden" name="csrf_token" value="{{ csrf_token() }}" />
          <input type="hidden" name="action" value="register_app" />
          <div class="flex items-center gap-1">
            <input type="text" name="app_name" placeholder="New app name"
                   class="flex-1 min-w-0 rounded-lg border border-gray-300 dark:border-slate-700 bg-white dark:bg-slate-900 px-2 py-1.5 text-xs text-gray-900 dark:text-slate-100 placeholder-gray-400 dark:placeholder-slate-500 focus:outline-none focus:border-indigo-500" />
            <button type="submit" title="Register app"
                    class="flex-shrink-0 w-7 h-7 rounded-lg bg-indigo-600 text-white text-sm font-bold hover:bg-indigo-500 transition-colors flex items-center justify-center">+</button>
          </div>
          <p class="text-xs text-gray-400 dark:text-slate-600 mt-1">Secret shown once at creation.</p>
        </form>
      </div>
    </div>
  </div>

  {# ── Main panel ───────────────────────────────────────────────────────── #}
  <div class="mt-4 lg:mt-0 lg:p-6 p-0">

    {% if not registered_apps %}
    {# Empty state #}
    <div class="flex flex-col items-center justify-center py-16 text-center px-4">
      <div class="w-12 h-12 rounded-xl bg-indigo-100 dark:bg-indigo-500/20 flex items-center justify-center mb-4">
        <svg class="w-6 h-6 text-indigo-600 dark:text-indigo-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4"/>
        </svg>
      </div>
      <h3 class="text-sm font-semibold text-gray-900 dark:text-slate-100 mb-1">No apps yet</h3>
      <p class="text-sm text-gray-500 dark:text-slate-400 max-w-xs">Use the form on the left to register your first app and get credentials.</p>
    </div>

    {% elif selected_app %}

    {# App header #}
    <div class="flex items-center gap-3 mb-5">
      <div class="flex-shrink-0 w-9 h-9 rounded-xl bg-indigo-600 flex items-center justify-center text-white text-sm font-bold">
        {{ selected_app.name[0].upper() }}
      </div>
      <div class="min-w-0 flex-1">
        <div class="text-base font-semibold text-gray-900 dark:text-slate-100">{{ selected_app.name }}</div>
        <div class="flex items-center gap-2 mt-0.5">
          <code class="text-xs text-gray-500 dark:text-slate-400 font-mono" id="clientIdVal">{{ selected_app.client_id }}</code>
          <button type="button" onclick="copyClientId()" id="copyClientIdBtn"
                  class="text-xs text-indigo-600 dark:text-indigo-400 hover:text-indigo-500 transition-colors">Copy</button>
        </div>
      </div>
      {% if selected_app.status == 'active' %}
        <span class="flex-shrink-0 text-xs px-2 py-0.5 rounded-full bg-green-100 dark:bg-emerald-500/15 text-green-700 dark:text-emerald-300 font-medium">Active</span>
      {% else %}
        <span class="flex-shrink-0 text-xs px-2 py-0.5 rounded-full bg-gray-100 dark:bg-slate-700 text-gray-500 dark:text-slate-400 font-medium">Suspended</span>
      {% endif %}
    </div>

    {# Secret note + revoke #}
    <div class="mb-5 rounded-lg bg-gray-50 dark:bg-slate-800/50 border border-gray-200 dark:border-slate-700 px-3.5 py-2.5 flex items-center justify-between gap-3">
      <p class="text-xs text-gray-500 dark:text-slate-400">Client secret was shown once at creation and cannot be retrieved. If lost, revoke and re-register.</p>
      {% if selected_app.status == 'active' %}
      <form method="POST" action="{{ url_for('settings.developer_post') }}" class="flex-shrink-0"
            onsubmit="return confirm('Revoke {{ selected_app.name }}? Integrations using these credentials will stop working immediately.')">
        <input type="hidden" name="csrf_token" value="{{ csrf_token() }}" />
        <input type="hidden" name="action" value="revoke_app" />
        <input type="hidden" name="app_id" value="{{ selected_app.id }}" />
        <button type="submit" class="text-xs text-red-600 dark:text-red-400 hover:underline whitespace-nowrap">Revoke</button>
      </form>
      {% endif %}
    </div>

    {# Products #}
    <div class="text-xs font-semibold uppercase tracking-wider text-gray-400 dark:text-slate-500 mb-3">Products</div>
    <div class="space-y-3">

      {% for product in product_catalog %}
        {% set access = product_accesses.get(product.slug) %}

        {% if access and access.status == 'approved' %}
        {# ── Approved ─────────────────────────────────────────────── #}
        <div class="rounded-xl border border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-900/70 p-4">
          <div class="flex items-start gap-3">
            <span class="text-base leading-none mt-0.5">{{ product.icon }}</span>
            <div class="flex-1 min-w-0">
              <div class="flex items-center gap-2 flex-wrap">
                <span class="text-sm font-semibold text-gray-900 dark:text-slate-100">{{ product.name }}</span>
                <span class="text-xs px-1.5 py-0.5 rounded-full bg-green-100 dark:bg-emerald-500/15 text-green-700 dark:text-emerald-300 font-medium">Approved</span>
              </div>
              <p class="text-xs text-gray-500 dark:text-slate-400 mt-0.5">{{ product.description }}</p>
            </div>
          </div>
          <form method="POST" action="{{ url_for('settings.developer_post') }}" class="mt-3 flex items-center gap-2">
            <input type="hidden" name="csrf_token" value="{{ csrf_token() }}" />
            <input type="hidden" name="action" value="update_webhook" />
            <input type="hidden" name="app_id" value="{{ selected_app.id }}" />
            <input type="hidden" name="product_slug" value="{{ product.slug }}" />
            <span class="text-xs text-gray-400 dark:text-slate-500 flex-shrink-0">Webhook</span>
            <input type="url" name="webhook_url" value="{{ access.webhook_url or '' }}"
                   placeholder="https://yourapp.com/webhooks/inboxiq"
                   class="flex-1 min-w-0 rounded-lg border border-gray-300 dark:border-slate-700 bg-gray-50 dark:bg-slate-950 px-2.5 py-1.5 text-xs text-gray-900 dark:text-slate-200 font-mono placeholder-gray-400 dark:placeholder-slate-600 focus:outline-none focus:border-indigo-500" />
            <button type="submit"
                    class="flex-shrink-0 rounded-lg border border-gray-300 dark:border-slate-700 bg-white dark:bg-transparent px-2.5 py-1.5 text-xs text-gray-600 dark:text-slate-400 hover:border-indigo-400 hover:text-indigo-600 dark:hover:text-indigo-300 transition-colors">Save</button>
          </form>
        </div>

        {% elif access and access.status == 'pending' %}
        {# ── Under review ─────────────────────────────────────────── #}
        <div class="rounded-xl border border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-900/70 p-4">
          <div class="flex items-start gap-3">
            <span class="text-base leading-none mt-0.5">{{ product.icon }}</span>
            <div class="flex-1 min-w-0">
              <div class="flex items-center gap-2 flex-wrap">
                <span class="text-sm font-semibold text-gray-900 dark:text-slate-100">{{ product.name }}</span>
                <span class="text-xs px-1.5 py-0.5 rounded-full bg-amber-100 dark:bg-amber-500/15 text-amber-700 dark:text-amber-300 font-medium">Under review</span>
              </div>
              <p class="text-xs text-gray-500 dark:text-slate-400 mt-0.5">{{ product.description }}</p>
            </div>
          </div>
          <p class="mt-2 text-xs text-gray-400 dark:text-slate-500 italic">Webhook URL can be configured once access is approved.</p>
        </div>

        {% elif access and access.status == 'rejected' %}
        {# ── Rejected ─────────────────────────────────────────────── #}
        <div class="rounded-xl border border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-900/70 p-4 opacity-75">
          <div class="flex items-start gap-3">
            <span class="text-base leading-none mt-0.5">{{ product.icon }}</span>
            <div class="flex-1 min-w-0">
              <div class="flex items-center gap-2 flex-wrap">
                <span class="text-sm font-semibold text-gray-500 dark:text-slate-400">{{ product.name }}</span>
                <span class="text-xs px-1.5 py-0.5 rounded-full bg-red-100 dark:bg-red-500/15 text-red-700 dark:text-red-300 font-medium">Not approved</span>
              </div>
              <p class="text-xs text-gray-400 dark:text-slate-500 mt-0.5">{{ product.description }}</p>
            </div>
          </div>
          <p class="mt-2 text-xs text-gray-400 dark:text-slate-500">
            Contact <a href="mailto:support@kalevent.com" class="text-indigo-500 dark:text-indigo-400 hover:underline">support</a> if you believe this is a mistake.
          </p>
        </div>

        {% else %}
        {# ── Not yet requested ────────────────────────────────────── #}
        <div class="rounded-xl border border-dashed border-gray-300 dark:border-slate-700 bg-gray-50 dark:bg-transparent p-4" id="pcard-{{ product.slug }}">
          <div class="flex items-start gap-3">
            <span class="text-base leading-none mt-0.5">{{ product.icon }}</span>
            <div class="flex-1 min-w-0">
              <div class="text-sm font-semibold text-gray-500 dark:text-slate-400">{{ product.name }}</div>
              <p class="text-xs text-gray-400 dark:text-slate-500 mt-0.5">{{ product.description }}</p>
            </div>
            <button type="button" onclick="showProductReq('{{ product.slug }}')"
                    class="flex-shrink-0 rounded-lg bg-indigo-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-indigo-500 transition-colors">
              Request Access
            </button>
          </div>
          <form method="POST" action="{{ url_for('settings.developer_post') }}"
                id="preqform-{{ product.slug }}" class="hidden mt-3 space-y-2">
            <input type="hidden" name="csrf_token" value="{{ csrf_token() }}" />
            <input type="hidden" name="action" value="request_product" />
            <input type="hidden" name="app_id" value="{{ selected_app.id }}" />
            <input type="hidden" name="product_slug" value="{{ product.slug }}" />
            <textarea name="use_case" rows="2" required
                      placeholder="Briefly describe how you'll use {{ product.name }}…"
                      class="w-full rounded-lg border border-gray-300 dark:border-slate-700 bg-white dark:bg-slate-900 px-3 py-2 text-xs text-gray-900 dark:text-slate-100 placeholder-gray-400 dark:placeholder-slate-500 focus:outline-none focus:border-indigo-500 resize-none"></textarea>
            <div class="flex items-center gap-2">
              <button type="submit"
                      class="rounded-lg bg-indigo-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-indigo-500 transition-colors">
                Submit Request
              </button>
              <button type="button" onclick="hideProductReq('{{ product.slug }}')"
                      class="text-xs text-gray-400 dark:text-slate-500 hover:text-gray-600 dark:hover:text-slate-300 transition-colors">
                Cancel
              </button>
            </div>
          </form>
        </div>
        {% endif %}

      {% endfor %}
    </div>

    {% endif %}{# selected_app #}
  </div>{# main panel #}
</div>{# two-panel grid #}

<script>
function copyClientId() {
  const text = document.getElementById('clientIdVal').textContent.trim();
  navigator.clipboard.writeText(text).then(() => {
    const btn = document.getElementById('copyClientIdBtn');
    const orig = btn.textContent;
    btn.textContent = 'Copied!';
    setTimeout(() => btn.textContent = orig, 2000);
  });
}
function showProductReq(slug) {
  document.getElementById('pcard-' + slug).querySelector('button[onclick]').classList.add('hidden');
  document.getElementById('preqform-' + slug).classList.remove('hidden');
}
function hideProductReq(slug) {
  document.getElementById('preqform-' + slug).classList.add('hidden');
  document.getElementById('pcard-' + slug).querySelector('button[onclick]').classList.remove('hidden');
}
</script>
```

- [ ] **Step 2: Verify the file was created**

```bash
ls -la /Users/kofi/inboxiq/src/templates/settings/developer_portal.html
```

Expected: file exists, non-zero size.

- [ ] **Step 3: Commit**

```bash
git add src/templates/settings/developer_portal.html
git commit -m "feat: add developer portal template with dual light/dark mode"
```

---

## Task 8: Wire include into settings/index.html

**Files:**
- Modify: `src/templates/settings/index.html` (lines 1920–2261)

The current developer block spans from `{% elif active_tab == 'developer' %}` (line 1920) to the closing `{% endif %}` at line 2261. **Do NOT use the Edit tool here** — the section contains hundreds of Tailwind class lines and the Edit tool introduces trailing whitespace that breaks CSS rendering. Use a Python script to splice the file at exact line numbers instead.

- [ ] **Step 1: Confirm current line boundaries**

```bash
sed -n '1920p;2261p;2263p' /Users/kofi/inboxiq/src/templates/settings/index.html
```

Expected:
```
            {% elif active_tab == 'developer' %}
              {% endif %}
            {% else %}
```

If the line numbers differ (file may have changed), adjust `START` and `END` in Step 2 accordingly.

- [ ] **Step 2: Run Python splice script**

```bash
python3 - <<'PYEOF'
import pathlib

path = pathlib.Path("src/templates/settings/index.html")
lines = path.read_text(encoding="utf-8").splitlines(keepends=True)

# Lines are 1-indexed; Python list is 0-indexed
START = 1920  # {% elif active_tab == 'developer' %}
END   = 2261  # closing {% endif %} of the developer block (inclusive)

replacement = (
    "            {% elif active_tab == 'developer' %}\n"
    "              {% include 'settings/developer_portal.html' %}\n"
)

new_lines = lines[:START - 1] + [replacement] + lines[END:]
path.write_text("".join(new_lines), encoding="utf-8")
print(f"Done. Replaced lines {START}–{END} with include.")
PYEOF
```

Expected: `Done. Replaced lines 1920–2261 with include.`

- [ ] **Step 3: Confirm the new block looks correct**

```bash
sed -n '1918,1925p' /Users/kofi/inboxiq/src/templates/settings/index.html
```

Expected:
```
            {% elif active_tab == 'ai_provider' %}
              ...
            {% elif active_tab == 'developer' %}
              {% include 'settings/developer_portal.html' %}
            {% else %}
              <div class="space-y-2">
```

- [ ] **Step 4: Commit**

```bash
git add src/templates/settings/index.html
git commit -m "feat: replace developer section body with include of developer_portal.html"
```

---

## Task 9: Rebuild Tailwind CSS

**Files:**
- Modify: `src/static/css/output.css` (generated)

The new template uses `dark:` variants and new light mode classes. Tailwind must scan the template to include them.

- [ ] **Step 1: Rebuild CSS**

```bash
cd /Users/kofi/inboxiq/src && npm run build:css
```

Expected: `Done in Xs.` with no errors.

- [ ] **Step 2: Confirm new classes are present in output**

```bash
grep -c "dark:bg-indigo-500" /Users/kofi/inboxiq/src/static/css/output.css
```

Expected: number greater than 0.

- [ ] **Step 3: Commit**

```bash
cd /Users/kofi/inboxiq
git add src/static/css/output.css
git commit -m "build: rebuild Tailwind CSS with developer portal light/dark classes"
```

---

## Task 10: Database migration

- [ ] **Step 1: Run migration autogenerate**

```bash
cd /Users/kofi/inboxiq
flask db migrate -m "add app_product_access table"
```

Expected: new file created in `src/migrations/versions/`. Inspect it and confirm it contains `create_table('app_product_access', ...)` and the `uq_app_product` unique constraint.

- [ ] **Step 2: Apply migration**

```bash
flask db upgrade
```

Expected: `Running upgrade ... -> <revision>` with no errors.

- [ ] **Step 3: Verify table exists**

```bash
kubectl exec -n kaley deploy/inboxiq -- python -c "
from src.extensions import db
from src.app import create_app
app = create_app()
with app.app_context():
    result = db.engine.execute(\"SELECT COUNT(*) FROM app_product_access\")
    print('table ok, rows:', list(result)[0][0])
"
```

Expected: `table ok, rows: 0`

- [ ] **Step 4: Commit migration file**

```bash
git add src/migrations/versions/
git commit -m "chore: migration — add app_product_access table"
```

---

## Task 11: Smoke test in browser

- [ ] **Step 1: Open the settings developer tab** at `https://your-app/settings?tab=developer`

Confirm:
- Page renders without 500 error
- "No apps yet" empty state shows for an account with no apps
- "New app name" + `+` button visible in sidebar

- [ ] **Step 2: Register a new app**

Enter a name, click `+`. Confirm:
- Credential modal fires with amber warning
- client_id and client_secret are shown
- Checkbox must be checked before "I've saved my credentials" button enables
- After dismiss: the new app appears in the sidebar as the active app
- Product catalog shows all 3 products in "Request Access" state

- [ ] **Step 3: Request Chat access**

Click "Request Access" on Chat / Aria Widget, fill in use_case, submit. Confirm:
- Card switches to "Under review" amber badge
- Webhook field is locked with hint text

- [ ] **Step 4: Request Intake API access**

Submit a request for Intake API (approval=auto). Confirm:
- Card immediately shows "Approved" green badge
- Webhook URL input is active and editable

- [ ] **Step 5: Set a webhook URL**

Enter `https://example.com/test` in the webhook field for Intake API, click Save. Confirm:
- Page reloads to same app
- Webhook URL is pre-filled with the saved value

- [ ] **Step 6: Test light mode**

Toggle the page to light mode (if toggle is available) or check via browser DevTools → Emulate `prefers-color-scheme: light`. Confirm the portal renders in the light theme with readable contrast.

- [ ] **Step 7: Approve Chat via admin**

In the admin panel (`/admin` → Developer), confirm:
- "Product Access Requests" panel shows the pending Chat request
- Click Approve — card refreshes and shows empty (approved, no longer pending)

- [ ] **Step 8: Verify Chat is now approved in settings**

Reload the developer settings tab. Confirm Chat card now shows "Approved" with an editable webhook URL field.
```
