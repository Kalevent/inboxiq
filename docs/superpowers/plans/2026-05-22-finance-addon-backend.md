# Finance Add-on Backend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the backend for the Finance Add-on — a paid add-on that receives Stripe payment events via webhook and either syncs them to QuickBooks in real-time or generates a weekly Intuit-compatible CSV export.

**Architecture:** An `AccountAddOn` model gates the feature per-account. A per-account Stripe webhook endpoint (`POST /api/v1/finance/webhook/stripe/<provider_id>`) receives events, verifies the signing secret stored in the existing `WebhookProvider` model, and dispatches a Celery task. Mode 1 (direct sync) calls the QuickBooks API using a second `WebhookProvider` record for QB credentials. Mode 2 (CSV export) accumulates transactions and a Celery Beat task emails a weekly CSV. No new OAuth flows are needed — credentials are configured via the existing `WebhookProvider` settings UI.

**Tech Stack:** Flask, SQLAlchemy, Celery, `stripe` SDK (already installed), `requests` (already installed), existing `src/crypto.py` for credential encryption/decryption. CSV email uses Python stdlib `smtplib` + `email.mime` directly — `src/notifications/emails.py` does not support attachments.

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `src/models/addons.py` | Create | `AccountAddOn` model — per-account add-on status, mode config, transaction metering |
| `src/models/__init__.py` | Modify | Re-export `AccountAddOn` |
| `src/features.py` | Modify | Add `finance_addon_active(account_id)` check |
| `src/integrations/finance_stripe.py` | Create | Pure functions: normalise `checkout.session.completed` and `payment_intent.succeeded` into a common `FinanceTransaction` dict |
| `src/integrations/quickbooks.py` | Create | QB API client — find/create customer, create SalesReceipt, refresh OAuth token |
| `src/tasks/finance_addon.py` | Create | Two Celery tasks: `process_stripe_event` (Mode 1 + buffers for Mode 2) and `generate_weekly_csv_export` (Mode 2 scheduled) |
| `src/celery_inboxiq.py` | Modify | Add `generate_weekly_csv_export` beat schedule (Fridays 08:00 UTC) + explicit import |
| `src/api/v1/addons.py` | Create | `GET /api/v1/addons/finance` and `POST /api/v1/addons/finance/activate` |
| `src/api/v1/finance_webhook.py` | Create | `POST /api/v1/finance/webhook/stripe/<provider_id>` — inbound Stripe events, unauthenticated |
| `src/api/v1/__init__.py` | Modify | Import `addons` and `finance_webhook` modules |
| `tests/finance/__init__.py` | Create | Empty package init |
| `tests/finance/test_stripe_normalizer.py` | Create | Unit tests for normaliser functions |
| `tests/finance/test_quickbooks_client.py` | Create | Unit tests for QB client (mocked HTTP) |
| `tests/finance/test_finance_tasks.py` | Create | Unit tests for Celery tasks (mocked QB + Stripe calls) |
| `tests/finance/test_addons_api.py` | Create | Integration tests for add-on management API |
| `tests/finance/test_finance_webhook.py` | Create | Integration tests for inbound webhook endpoint |

---

## Task 1: AccountAddOn Model

**Files:**
- Create: `src/models/addons.py`
- Modify: `src/models/__init__.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/finance/__init__.py  — empty file, create first
```

```python
# tests/finance/test_addons_model.py
import pytest
from src.models.addons import AccountAddOn


def test_addon_defaults(app):
    with app.app_context():
        addon = AccountAddOn(account_id=1, addon_type="finance")
        assert addon.status == "inactive"
        assert addon.transactions_this_month == 0
        assert addon.config_json == {}
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/finance/test_addons_model.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'src.models.addons'`

- [ ] **Step 3: Create the model**

```python
# src/models/addons.py
from uuid import uuid4
from sqlalchemy.sql import func
from src.extensions import db


class AccountAddOn(db.Model):
    __tablename__ = "account_addons"
    __table_args__ = (
        db.UniqueConstraint("account_id", "addon_type", name="uq_account_addon_type"),
        db.Index("ix_account_addons_account_type", "account_id", "addon_type"),
    )

    id = db.Column(db.String(64), primary_key=True, default=lambda: str(uuid4()))
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=False, index=True)
    addon_type = db.Column(db.String(64), nullable=False)  # "finance"
    status = db.Column(db.String(32), nullable=False, default="inactive")  # active|inactive|cancelled

    # Stripe subscription tracking for this add-on
    stripe_subscription_id = db.Column(db.String(128), nullable=True)

    # Volume metering — reset monthly
    transactions_this_month = db.Column(db.Integer, nullable=False, default=0)
    billing_month = db.Column(db.String(7), nullable=True)  # "2026-05"

    # Add-on configuration:
    # {
    #   "mode": "direct_sync" | "csv_export",
    #   "stripe_provider_id": "<WebhookProvider id>",
    #   "qb_provider_id": "<WebhookProvider id>",   # Mode 1 only
    #   "csv_email": "accounting@company.com",       # Mode 2 only
    # }
    config_json = db.Column(db.JSON, nullable=False, default=dict)

    created_at = db.Column(db.DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    account = db.relationship("Account", backref="addons")

    def is_active(self) -> bool:
        return self.status == "active"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "account_id": self.account_id,
            "addon_type": self.addon_type,
            "status": self.status,
            "transactions_this_month": self.transactions_this_month,
            "billing_month": self.billing_month,
            "config_json": self.config_json,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
```

- [ ] **Step 4: Add to `src/models/__init__.py`**

Add to the imports section:
```python
from src.models.addons import AccountAddOn
```

Add `"AccountAddOn"` to `__all__`.

- [ ] **Step 5: Run test to verify it passes**

```bash
pytest tests/finance/test_addons_model.py -v
```
Expected: PASS

- [ ] **Step 6: Tell user to run migration**

```
flask db migrate -m "add account_addons table"
```
User reviews generated migration and runs `flask db upgrade`.

- [ ] **Step 7: Commit**

```bash
git add src/models/addons.py src/models/__init__.py tests/finance/__init__.py tests/finance/test_addons_model.py
git commit -m "feat(finance-addon): add AccountAddOn model"
```

---

## Task 2: Finance Add-on Feature Gate + Management API

**Files:**
- Modify: `src/features.py`
- Create: `src/api/v1/addons.py`
- Modify: `src/api/v1/__init__.py`
- Test: `tests/finance/test_addons_api.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/finance/test_addons_api.py
import pytest
import json
from unittest.mock import patch


def test_get_addon_status_not_active(client, auth_headers):
    resp = client.get("/api/v1/addons/finance", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["addon_type"] == "finance"
    assert data["status"] == "inactive"


def test_activate_addon(client, auth_headers, app):
    payload = {
        "mode": "csv_export",
        "stripe_provider_id": "prov-123",
        "csv_email": "accounting@example.com",
    }
    resp = client.post(
        "/api/v1/addons/finance/activate",
        headers=auth_headers,
        data=json.dumps(payload),
        content_type="application/json",
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "active"
    assert data["config_json"]["mode"] == "csv_export"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/finance/test_addons_api.py -v
```
Expected: FAIL — `404 NOT FOUND`

- [ ] **Step 3: Add `finance_addon_active` to features.py**

Add after the `feature_enabled` function:

```python
def finance_addon_active(account_id: int) -> bool:
    """Return True if the Finance add-on is active for this account."""
    from src.models.addons import AccountAddOn
    addon = AccountAddOn.query.filter_by(
        account_id=account_id,
        addon_type="finance",
        status="active",
    ).first()
    return addon is not None
```

- [ ] **Step 4: Create the add-on management API**

```python
# src/api/v1/addons.py
from flask import request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity

from src.api.v1 import v1
from src.models.addons import AccountAddOn
from src.extensions import db


@v1.route("/addons/finance", methods=["GET"])
@jwt_required()
def get_finance_addon():
    account_id = get_jwt_identity()
    addon = AccountAddOn.query.filter_by(
        account_id=account_id,
        addon_type="finance",
    ).first()
    if not addon:
        return jsonify({
            "addon_type": "finance",
            "status": "inactive",
            "transactions_this_month": 0,
            "config_json": {},
        }), 200
    return jsonify(addon.to_dict()), 200


@v1.route("/addons/finance/activate", methods=["POST"])
@jwt_required()
def activate_finance_addon():
    """
    Activate or reconfigure the Finance add-on.

    Body:
        {
            "mode": "direct_sync" | "csv_export",
            "stripe_provider_id": "<WebhookProvider id>",
            "qb_provider_id": "<WebhookProvider id>",   // required for direct_sync
            "csv_email": "accounting@company.com"        // required for csv_export
        }
    """
    account_id = get_jwt_identity()
    data = request.get_json() or {}

    mode = data.get("mode")
    if mode not in ("direct_sync", "csv_export"):
        return jsonify({"error": "mode must be 'direct_sync' or 'csv_export'"}), 400

    stripe_provider_id = data.get("stripe_provider_id")
    if not stripe_provider_id:
        return jsonify({"error": "stripe_provider_id is required"}), 400

    if mode == "direct_sync" and not data.get("qb_provider_id"):
        return jsonify({"error": "qb_provider_id is required for direct_sync mode"}), 400

    if mode == "csv_export" and not data.get("csv_email"):
        return jsonify({"error": "csv_email is required for csv_export mode"}), 400

    config = {
        "mode": mode,
        "stripe_provider_id": stripe_provider_id,
    }
    if mode == "direct_sync":
        config["qb_provider_id"] = data["qb_provider_id"]
    else:
        config["csv_email"] = data["csv_email"]

    addon = AccountAddOn.query.filter_by(
        account_id=account_id,
        addon_type="finance",
    ).first()

    if not addon:
        addon = AccountAddOn(account_id=account_id, addon_type="finance")
        db.session.add(addon)

    addon.status = "active"
    addon.config_json = config

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise

    return jsonify(addon.to_dict()), 200


@v1.route("/addons/finance/deactivate", methods=["POST"])
@jwt_required()
def deactivate_finance_addon():
    account_id = get_jwt_identity()
    addon = AccountAddOn.query.filter_by(
        account_id=account_id,
        addon_type="finance",
    ).first()
    if not addon:
        return jsonify({"error": "not_found"}), 404

    addon.status = "inactive"
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise

    return jsonify(addon.to_dict()), 200
```

- [ ] **Step 5: Register the module in `src/api/v1/__init__.py`**

Add `from src.api.v1 import addons as _addons  # noqa: F401` to the imports block at the bottom of `__init__.py` (follow the existing pattern for other v1 modules).

- [ ] **Step 6: Run tests to verify they pass**

```bash
pytest tests/finance/test_addons_api.py -v
```
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add src/features.py src/api/v1/addons.py src/api/v1/__init__.py tests/finance/test_addons_api.py
git commit -m "feat(finance-addon): add-on feature gate and management API"
```

---

## Task 3: Stripe Event Normaliser

**Files:**
- Create: `src/integrations/finance_stripe.py`
- Test: `tests/finance/test_stripe_normalizer.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/finance/test_stripe_normalizer.py
import pytest
from src.integrations.finance_stripe import (
    normalize_stripe_event,
    SUPPORTED_EVENTS,
)


CHECKOUT_EVENT = {
    "id": "evt_abc123",
    "type": "checkout.session.completed",
    "data": {
        "object": {
            "id": "cs_test_xxx",
            "payment_intent": "pi_abc",
            "customer": "cus_xyz",
            "amount_total": 4999,
            "currency": "gbp",
            "customer_details": {
                "email": "john@example.com",
                "name": "John Doe",
            },
            "metadata": {"order_id": "1234"},
        }
    },
}

PAYMENT_INTENT_EVENT = {
    "id": "evt_def456",
    "type": "payment_intent.succeeded",
    "data": {
        "object": {
            "id": "pi_def",
            "customer": "cus_abc",
            "amount": 2000,
            "currency": "usd",
            "description": "Subscription renewal",
            "metadata": {},
        }
    },
}


def test_normalize_checkout_session():
    tx = normalize_stripe_event(CHECKOUT_EVENT)
    assert tx["stripe_event_id"] == "evt_abc123"
    assert tx["stripe_payment_intent_id"] == "pi_abc"
    assert tx["stripe_customer_id"] == "cus_xyz"
    assert tx["amount_cents"] == 4999
    assert tx["currency"] == "GBP"
    assert tx["customer_email"] == "john@example.com"
    assert tx["customer_name"] == "John Doe"
    assert tx["event_type"] == "checkout.session.completed"


def test_normalize_payment_intent():
    tx = normalize_stripe_event(PAYMENT_INTENT_EVENT)
    assert tx["stripe_event_id"] == "evt_def456"
    assert tx["stripe_payment_intent_id"] == "pi_def"
    assert tx["amount_cents"] == 2000
    assert tx["currency"] == "USD"
    assert tx["customer_name"] is None  # not in payment_intent event
    assert tx["event_type"] == "payment_intent.succeeded"


def test_unsupported_event_raises():
    with pytest.raises(ValueError, match="Unsupported"):
        normalize_stripe_event({"type": "customer.created", "id": "evt_x", "data": {"object": {}}})


def test_supported_events_list():
    assert "checkout.session.completed" in SUPPORTED_EVENTS
    assert "payment_intent.succeeded" in SUPPORTED_EVENTS
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/finance/test_stripe_normalizer.py -v
```
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement the normaliser**

```python
# src/integrations/finance_stripe.py
"""
Normalise Stripe webhook events into a common FinanceTransaction dict.

Output dict keys (all events):
    stripe_event_id         str
    stripe_payment_intent_id  str | None
    stripe_customer_id      str | None
    amount_cents            int
    currency                str    — uppercase ISO code e.g. "GBP"
    customer_email          str | None
    customer_name           str | None
    description             str | None
    metadata                dict
    event_type              str
"""
from __future__ import annotations

SUPPORTED_EVENTS = frozenset({
    "checkout.session.completed",
    "payment_intent.succeeded",
})


def normalize_stripe_event(event: dict) -> dict:
    """
    Convert a raw Stripe event dict into a FinanceTransaction dict.
    Raises ValueError for unsupported event types.
    """
    event_type = event.get("type", "")
    if event_type not in SUPPORTED_EVENTS:
        raise ValueError(f"Unsupported Stripe event type: {event_type!r}")

    obj = event.get("data", {}).get("object", {})
    stripe_event_id = event.get("id", "")

    if event_type == "checkout.session.completed":
        return _from_checkout_session(obj, stripe_event_id)
    return _from_payment_intent(obj, stripe_event_id)


def _from_checkout_session(obj: dict, stripe_event_id: str) -> dict:
    customer_details = obj.get("customer_details") or {}
    return {
        "stripe_event_id": stripe_event_id,
        "stripe_payment_intent_id": obj.get("payment_intent"),
        "stripe_customer_id": obj.get("customer"),
        "amount_cents": obj.get("amount_total", 0),
        "currency": (obj.get("currency") or "usd").upper(),
        "customer_email": customer_details.get("email"),
        "customer_name": customer_details.get("name"),
        "description": None,
        "metadata": obj.get("metadata") or {},
        "event_type": "checkout.session.completed",
        "event_created": obj.get("created"),  # Unix timestamp from Stripe event
    }


def _from_payment_intent(obj: dict, stripe_event_id: str) -> dict:
    return {
        "stripe_event_id": stripe_event_id,
        "stripe_payment_intent_id": obj.get("id"),
        "stripe_customer_id": obj.get("customer"),
        "amount_cents": obj.get("amount", 0),
        "currency": (obj.get("currency") or "usd").upper(),
        "customer_email": None,
        "customer_name": None,
        "description": obj.get("description"),
        "metadata": obj.get("metadata") or {},
        "event_type": "payment_intent.succeeded",
        "event_created": obj.get("created"),  # Unix timestamp from Stripe event
    }
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/finance/test_stripe_normalizer.py -v
```
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add src/integrations/finance_stripe.py tests/finance/test_stripe_normalizer.py
git commit -m "feat(finance-addon): Stripe event normaliser"
```

---

## Task 4: QuickBooks API Client

**Files:**
- Create: `src/integrations/quickbooks.py`
- Test: `tests/finance/test_quickbooks_client.py`

The client reads QB OAuth tokens from an existing `WebhookProvider` record (provider_type="quickbooks"). Credentials JSON stored in `credentials_encrypted`:
```json
{
    "client_id": "AB...",
    "client_secret": "...",
    "realm_id": "1234567890",
    "access_token": "...",
    "refresh_token": "..."
}
```
QB API sandbox base URL: `https://sandbox-quickbooks.api.intuit.com/v3/company/{realm_id}`
QB API production base URL: `https://quickbooks.api.intuit.com/v3/company/{realm_id}`
QB token refresh URL: `https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer`

- [ ] **Step 1: Write the failing tests**

```python
# tests/finance/test_quickbooks_client.py
import pytest
from unittest.mock import patch, Mock, MagicMock
from src.integrations.quickbooks import QuickBooksClient


def _make_client(sandbox=True):
    return QuickBooksClient(
        realm_id="123456",
        access_token="tok_access",
        refresh_token="tok_refresh",
        client_id="client_id_xxx",
        client_secret="client_secret_xxx",
        sandbox=sandbox,
    )


def test_base_url_sandbox():
    client = _make_client(sandbox=True)
    assert "sandbox" in client.base_url


def test_base_url_production():
    client = _make_client(sandbox=False)
    assert "sandbox" not in client.base_url


def test_find_customer_found():
    client = _make_client()
    mock_resp = Mock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "QueryResponse": {
            "Customer": [{"Id": "42", "DisplayName": "John Doe"}]
        }
    }
    with patch("requests.get", return_value=mock_resp):
        customer_id = client.find_customer_by_email("john@example.com")
    assert customer_id == "42"


def test_find_customer_not_found():
    client = _make_client()
    mock_resp = Mock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"QueryResponse": {}}
    with patch("requests.get", return_value=mock_resp):
        customer_id = client.find_customer_by_email("nobody@example.com")
    assert customer_id is None


def test_create_customer():
    client = _make_client()
    mock_resp = Mock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"Customer": {"Id": "99", "DisplayName": "Jane"}}
    with patch("requests.post", return_value=mock_resp):
        customer_id = client.create_customer(name="Jane", email="jane@example.com")
    assert customer_id == "99"


def test_create_sales_receipt():
    client = _make_client()
    mock_resp = Mock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "SalesReceipt": {"Id": "SR-1", "TotalAmt": 50.00}
    }
    with patch("requests.post", return_value=mock_resp):
        result = client.create_sales_receipt(
            customer_id="42",
            amount_cents=5000,
            currency="GBP",
            description="Stripe payment",
        )
    assert result["SalesReceipt"]["Id"] == "SR-1"


def test_refresh_token():
    client = _make_client()
    mock_resp = Mock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "access_token": "new_access",
        "refresh_token": "new_refresh",
    }
    with patch("requests.post", return_value=mock_resp):
        new_access, new_refresh = client.refresh_access_token()
    assert new_access == "new_access"
    assert new_refresh == "new_refresh"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/finance/test_quickbooks_client.py -v
```
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement the client**

```python
# src/integrations/quickbooks.py
"""
QuickBooks Online API client.

Reads credentials from a WebhookProvider record (provider_type="quickbooks").
The credentials_encrypted field must contain JSON with keys:
    client_id, client_secret, realm_id, access_token, refresh_token

Usage:
    from src.integrations.quickbooks import QuickBooksClient, client_from_provider
    client = client_from_provider(provider)
    customer_id = client.find_customer_by_email("john@example.com")
    if not customer_id:
        customer_id = client.create_customer("John Doe", "john@example.com")
    client.create_sales_receipt(customer_id, amount_cents=4999, currency="GBP", description="...")
"""
from __future__ import annotations

import base64
import logging
from typing import Optional

import requests

_log = logging.getLogger(__name__)

_QB_PROD_BASE = "https://quickbooks.api.intuit.com/v3/company"
_QB_SANDBOX_BASE = "https://sandbox-quickbooks.api.intuit.com/v3/company"
_QB_TOKEN_URL = "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer"


class QuickBooksClient:
    def __init__(
        self,
        realm_id: str,
        access_token: str,
        refresh_token: str,
        client_id: str,
        client_secret: str,
        sandbox: bool = False,
    ):
        self.realm_id = realm_id
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.client_id = client_id
        self.client_secret = client_secret
        self.sandbox = sandbox
        base = _QB_SANDBOX_BASE if sandbox else _QB_PROD_BASE
        self.base_url = f"{base}/{realm_id}"

    def _auth_headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def find_customer_by_email(self, email: str) -> Optional[str]:
        """Return the QB Customer Id for this email, or None if not found."""
        query = f"SELECT * FROM Customer WHERE PrimaryEmailAddr = '{email}' MAXRESULTS 1"
        resp = requests.get(
            f"{self.base_url}/query",
            headers=self._auth_headers(),
            params={"query": query, "minorversion": "65"},
            timeout=15,
        )
        resp.raise_for_status()
        customers = resp.json().get("QueryResponse", {}).get("Customer", [])
        return customers[0]["Id"] if customers else None

    def create_customer(self, name: str, email: Optional[str] = None) -> str:
        """Create a QB customer and return the new Customer Id."""
        body: dict = {"DisplayName": name}
        if email:
            body["PrimaryEmailAddr"] = {"Address": email}
        resp = requests.post(
            f"{self.base_url}/customer",
            headers=self._auth_headers(),
            json=body,
            params={"minorversion": "65"},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()["Customer"]["Id"]

    def find_or_create_customer(self, name: str, email: Optional[str]) -> str:
        """Return existing customer Id or create new one."""
        if email:
            existing = self.find_customer_by_email(email)
            if existing:
                return existing
        return self.create_customer(name or "Unknown Customer", email)

    def create_sales_receipt(
        self,
        customer_id: str,
        amount_cents: int,
        currency: str,
        description: str = "Stripe payment",
    ) -> dict:
        """
        Create a SalesReceipt in QuickBooks.
        amount_cents is in the smallest currency unit (e.g. 4999 = £49.99).
        Returns the QB API response dict.
        """
        amount = round(amount_cents / 100, 2)
        body = {
            "CustomerRef": {"value": customer_id},
            "CurrencyRef": {"value": currency.upper()},
            "Line": [
                {
                    "Amount": amount,
                    "DetailType": "SalesItemLineDetail",
                    "Description": description,
                    "SalesItemLineDetail": {
                        "ItemRef": {"value": "1", "name": "Services"},
                        "UnitPrice": amount,
                        "Qty": 1,
                    },
                }
            ],
        }
        resp = requests.post(
            f"{self.base_url}/salesreceipt",
            headers=self._auth_headers(),
            json=body,
            params={"minorversion": "65"},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()

    def refresh_access_token(self) -> tuple[str, str]:
        """
        Refresh the QB OAuth access token.
        Returns (new_access_token, new_refresh_token).
        Call this when a 401 is returned and persist the new tokens back to the
        WebhookProvider record.
        """
        credentials = base64.b64encode(
            f"{self.client_id}:{self.client_secret}".encode()
        ).decode()
        resp = requests.post(
            _QB_TOKEN_URL,
            headers={
                "Authorization": f"Basic {credentials}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={"grant_type": "refresh_token", "refresh_token": self.refresh_token},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        self.access_token = data["access_token"]
        self.refresh_token = data["refresh_token"]
        return self.access_token, self.refresh_token


def client_from_provider(provider, app=None) -> QuickBooksClient:
    """
    Build a QuickBooksClient from a WebhookProvider model instance.
    The provider must be provider_type="quickbooks".
    """
    import json
    from src.crypto import decrypt_value

    raw = decrypt_value(provider.credentials_encrypted)
    creds = json.loads(raw)
    return QuickBooksClient(
        realm_id=creds["realm_id"],
        access_token=creds["access_token"],
        refresh_token=creds["refresh_token"],
        client_id=creds["client_id"],
        client_secret=creds["client_secret"],
        sandbox=(provider.environment == "sandbox"),
    )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/finance/test_quickbooks_client.py -v
```
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add src/integrations/quickbooks.py tests/finance/test_quickbooks_client.py
git commit -m "feat(finance-addon): QuickBooks API client"
```

---

## Task 5: Finance Celery Tasks — Mode 1 (Direct QB Sync) + Usage Metering

**Files:**
- Create: `src/tasks/finance_addon.py`
- Modify: `src/celery_inboxiq.py`
- Test: `tests/finance/test_finance_tasks.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/finance/test_finance_tasks.py
import pytest
from unittest.mock import patch, MagicMock, Mock
from datetime import datetime, timezone


def test_process_stripe_event_mode1_creates_sales_receipt(app):
    """Mode 1: direct QB sync — should call QB create_sales_receipt."""
    with app.app_context():
        mock_addon = MagicMock()
        mock_addon.is_active.return_value = True
        mock_addon.config_json = {
            "mode": "direct_sync",
            "stripe_provider_id": "sprov-1",
            "qb_provider_id": "qbprov-1",
        }
        mock_addon.transactions_this_month = 0
        mock_addon.billing_month = None

        mock_qb_client = MagicMock()
        mock_qb_client.find_or_create_customer.return_value = "cust-42"

        event = {
            "id": "evt_test",
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "payment_intent": "pi_test",
                    "customer": "cus_test",
                    "amount_total": 4999,
                    "currency": "gbp",
                    "customer_details": {"email": "a@b.com", "name": "Alice"},
                    "metadata": {},
                }
            },
        }

        with patch("src.tasks.finance_addon.AccountAddOn") as mock_model, \
             patch("src.tasks.finance_addon.client_from_provider", return_value=mock_qb_client), \
             patch("src.tasks.finance_addon.WebhookProvider") as mock_wp, \
             patch("src.tasks.finance_addon.db"):
            mock_model.query.filter_by.return_value.first.return_value = mock_addon
            mock_wp.query.filter_by.return_value.first.return_value = MagicMock()

            from src.tasks.finance_addon import _run_mode1_sync
            _run_mode1_sync(mock_addon, event, account_id=1)

        mock_qb_client.find_or_create_customer.assert_called_once_with("Alice", "a@b.com")
        mock_qb_client.create_sales_receipt.assert_called_once_with(
            customer_id="cust-42",
            amount_cents=4999,
            currency="GBP",
            description="Stripe payment pi_test",
        )


def test_process_stripe_event_addon_inactive(app):
    """If add-on is inactive, task should return early without processing."""
    with app.app_context():
        mock_addon = MagicMock()
        mock_addon.is_active.return_value = False

        with patch("src.tasks.finance_addon.AccountAddOn") as mock_model, \
             patch("src.tasks.finance_addon.client_from_provider") as mock_qb:
            mock_model.query.filter_by.return_value.first.return_value = mock_addon

            from src.tasks.finance_addon import _run_mode1_sync
            _run_mode1_sync(mock_addon, {}, account_id=1)

        mock_qb.assert_not_called()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/finance/test_finance_tasks.py -v
```
Expected: FAIL — `ImportError`

- [ ] **Step 3: Implement the task file**

```python
# src/tasks/finance_addon.py
"""
Finance Add-on Celery tasks.

process_stripe_event  — triggered by inbound Stripe webhook; runs Mode 1 or buffers for Mode 2
generate_weekly_csv_export — Celery Beat task; runs every Friday 08:00 UTC for all Mode 2 accounts
"""
from __future__ import annotations

import csv
import io
import json
import logging
from datetime import datetime, timezone
from typing import Optional

from src.extensions import celery, db

_log = logging.getLogger(__name__)


@celery.task(name="finance_addon.process_stripe_event", queue="inbox", bind=True, max_retries=3)
def process_stripe_event(self, account_id: int, provider_id: str, event: dict):
    """
    Process an inbound Stripe event for a Finance add-on account.
    Mode 1: sync to QuickBooks immediately.
    Mode 2: buffer the normalised transaction in the add-on's pending list.
    """
    from src.models.addons import AccountAddOn

    addon = AccountAddOn.query.filter_by(
        account_id=account_id,
        addon_type="finance",
        status="active",
    ).first()

    if not addon:
        _log.warning("finance_addon: no active addon for account_id=%s", account_id)
        return

    try:
        from src.integrations.finance_stripe import normalize_stripe_event
        tx = normalize_stripe_event(event)
    except ValueError as exc:
        _log.info("finance_addon: skipping unsupported event type: %s", exc)
        return

    _increment_transaction_counter(addon)

    mode = (addon.config_json or {}).get("mode", "csv_export")
    if mode == "direct_sync":
        _run_mode1_sync(addon, event, account_id)
    else:
        _buffer_for_csv(addon, tx)


def _increment_transaction_counter(addon) -> None:
    """Increment monthly transaction counter, resetting if billing month changed."""
    current_month = datetime.now(timezone.utc).strftime("%Y-%m")
    if addon.billing_month != current_month:
        addon.transactions_this_month = 0
        addon.billing_month = current_month
    addon.transactions_this_month += 1
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise


def _run_mode1_sync(addon, event: dict, account_id: int) -> None:
    """Mode 1: push transaction to QuickBooks in real-time."""
    if not addon.is_active():
        return

    from src.integrations.finance_stripe import normalize_stripe_event
    from src.integrations.quickbooks import client_from_provider
    from src.models.automation import WebhookProvider

    config = addon.config_json or {}
    qb_provider_id = config.get("qb_provider_id")
    if not qb_provider_id:
        _log.error("finance_addon mode1: no qb_provider_id in config for account_id=%s", account_id)
        return

    qb_provider = WebhookProvider.query.filter_by(
        id=qb_provider_id,
        account_id=account_id,
        enabled=True,
    ).first()
    if not qb_provider:
        _log.error("finance_addon mode1: QB provider not found id=%s", qb_provider_id)
        return

    try:
        tx = normalize_stripe_event(event)
        qb_client = client_from_provider(qb_provider)

        customer_id = qb_client.find_or_create_customer(
            name=tx["customer_name"] or "Unknown",
            email=tx["customer_email"],
        )

        pi_id = tx.get("stripe_payment_intent_id", "")
        qb_client.create_sales_receipt(
            customer_id=customer_id,
            amount_cents=tx["amount_cents"],
            currency=tx["currency"],
            description=f"Stripe payment {pi_id}".strip(),
        )
        _log.info(
            "finance_addon mode1: synced stripe_event=%s to QB for account_id=%s",
            tx["stripe_event_id"], account_id,
        )
    except Exception as exc:
        _log.error(
            "finance_addon mode1: sync failed account_id=%s error=%s",
            account_id, exc,
        )
        raise


def _buffer_for_csv(addon, tx: dict) -> None:
    """Mode 2: append normalised transaction to the add-on's pending CSV buffer."""
    config = addon.config_json or {}
    pending: list = list(config.get("pending_transactions", []))
    pending.append(tx)
    addon.config_json = {**config, "pending_transactions": pending}
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise


@celery.task(name="finance_addon.generate_weekly_csv_export", queue="inbox")
def generate_weekly_csv_export():
    """
    Celery Beat task — runs every Friday at 08:00 UTC.
    For each active Mode 2 Finance add-on account, generates an Intuit-compatible
    CSV from buffered transactions and emails it to the configured address.
    """
    from src.models.addons import AccountAddOn

    addons = AccountAddOn.query.filter_by(
        addon_type="finance",
        status="active",
    ).all()

    for addon in addons:
        config = addon.config_json or {}
        if config.get("mode") != "csv_export":
            continue
        pending = config.get("pending_transactions", [])
        if not pending:
            continue

        try:
            csv_bytes = _build_intuit_csv(pending)
            csv_email = config.get("csv_email")
            if csv_email:
                _email_csv(addon.account_id, csv_email, csv_bytes)
            # Clear the buffer after successful email
            addon.config_json = {**config, "pending_transactions": []}
            db.session.commit()
        except Exception as exc:
            db.session.rollback()
            _log.error(
                "finance_addon csv_export: failed account_id=%s error=%s",
                addon.account_id, exc,
            )


def _build_intuit_csv(transactions: list[dict]) -> bytes:
    """
    Build a QuickBooks-compatible bank transactions CSV.

    Columns: Date, Description, Amount, Currency
    Date is taken from the Stripe event's `created` Unix timestamp (UTC).
    QuickBooks imports this as bank transactions for reconciliation.
    """
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Date", "Description", "Amount", "Currency"])
    for tx in transactions:
        # Use Stripe event timestamp if available, fall back to today
        created_ts = tx.get("event_created")
        if created_ts:
            date_str = datetime.fromtimestamp(created_ts, tz=timezone.utc).strftime("%m/%d/%Y")
        else:
            date_str = datetime.now(timezone.utc).strftime("%m/%d/%Y")
        amount = round(tx.get("amount_cents", 0) / 100, 2)
        description = tx.get("description") or f"Stripe {tx.get('event_type', 'payment')}"
        currency = tx.get("currency", "GBP")
        writer.writerow([date_str, description, amount, currency])
    return output.getvalue().encode("utf-8")


def _email_csv(account_id: int, recipient: str, csv_bytes: bytes) -> None:
    """
    Send the CSV to the configured accountant email via SMTP.

    `src/notifications/emails.py` does not support attachments, so this uses
    Python stdlib smtplib + email.mime directly, following the same SMTP config
    keys (SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, MAIL_FROM).
    """
    import smtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText
    from email.mime.base import MIMEBase
    from email import encoders
    from datetime import date
    from flask import current_app

    week_label = date.today().strftime("%Y-W%V")
    filename = f"inboxiq_finance_{week_label}.csv"

    host = current_app.config.get("SMTP_HOST")
    if not host:
        _log.info("finance_addon csv_email: SMTP_HOST not configured, skipping email")
        return

    port = current_app.config.get("SMTP_PORT", 587)
    user = current_app.config.get("SMTP_USER")
    password = current_app.config.get("SMTP_PASSWORD")
    mail_from = current_app.config.get("MAIL_FROM", "noreply@kalevent.com")

    msg = MIMEMultipart()
    msg["From"] = mail_from
    msg["To"] = recipient
    msg["Subject"] = f"InboxIQ Finance Export — Week {week_label}"
    msg.attach(MIMEText(
        "Please find this week's Stripe transaction export attached.\n\n"
        "Import into QuickBooks via Banking > Upload transactions.",
        "plain",
    ))

    part = MIMEBase("text", "csv")
    part.set_payload(csv_bytes)
    encoders.encode_base64(part)
    part.add_header("Content-Disposition", f'attachment; filename="{filename}"')
    msg.attach(part)

    with smtplib.SMTP(host, port) as server:
        server.starttls()
        if user and password:
            server.login(user, password)
        server.sendmail(mail_from, [recipient], msg.as_string())
```

- [ ] **Step 4: Add beat schedule and explicit import to `src/celery_inboxiq.py`**

Find the `beat_schedule` dict and add:
```python
"finance_weekly_csv_export": {
    "task": "finance_addon.generate_weekly_csv_export",
    "schedule": crontab(day_of_week=5, hour=8, minute=0),  # Friday 08:00 UTC
},
```

Find the explicit import block and add:
```python
from src.tasks import finance_addon as _finance_addon_tasks  # noqa: F401
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/finance/test_finance_tasks.py -v
```
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/tasks/finance_addon.py src/celery_inboxiq.py tests/finance/test_finance_tasks.py
git commit -m "feat(finance-addon): Celery tasks for Mode 1 QB sync and Mode 2 CSV export"
```

---

## Task 6: Inbound Stripe Webhook Endpoint

**Files:**
- Create: `src/api/v1/finance_webhook.py`
- Modify: `src/api/v1/__init__.py`
- Test: `tests/finance/test_finance_webhook.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/finance/test_finance_webhook.py
import pytest
import json
from unittest.mock import patch, MagicMock


def test_webhook_provider_not_found(client):
    resp = client.post(
        "/api/v1/finance/webhook/stripe/nonexistent-id",
        data=b"{}",
        content_type="application/json",
    )
    assert resp.status_code == 404


def test_webhook_addon_not_active(client, app):
    with app.app_context():
        mock_provider = MagicMock()
        mock_provider.account_id = 1
        mock_provider.webhook_signing_secret_encrypted = None

        mock_addon = None  # no active addon

        with patch("src.api.v1.finance_webhook.WebhookProvider") as mock_wp_cls, \
             patch("src.api.v1.finance_webhook.AccountAddOn") as mock_addon_cls:
            mock_wp_cls.query.filter_by.return_value.first.return_value = mock_provider
            mock_addon_cls.query.filter_by.return_value.first.return_value = mock_addon

            resp = client.post(
                "/api/v1/finance/webhook/stripe/prov-123",
                data=b'{"type":"payment_intent.succeeded"}',
                content_type="application/json",
            )
        assert resp.status_code == 403


def test_webhook_dispatches_task(client, app):
    with app.app_context():
        mock_provider = MagicMock()
        mock_provider.account_id = 1
        mock_provider.webhook_signing_secret_encrypted = None  # skip sig verification

        mock_addon = MagicMock()
        mock_addon.is_active.return_value = True

        event_payload = json.dumps({
            "type": "checkout.session.completed",
            "id": "evt_xxx",
            "data": {"object": {}},
        }).encode()

        with patch("src.api.v1.finance_webhook.WebhookProvider") as mock_wp_cls, \
             patch("src.api.v1.finance_webhook.AccountAddOn") as mock_addon_cls, \
             patch("src.api.v1.finance_webhook.process_stripe_event") as mock_task:
            mock_wp_cls.query.filter_by.return_value.first.return_value = mock_provider
            mock_addon_cls.query.filter_by.return_value.first.return_value = mock_addon

            resp = client.post(
                "/api/v1/finance/webhook/stripe/prov-123",
                data=event_payload,
                content_type="application/json",
            )
        assert resp.status_code == 200
        mock_task.delay.assert_called_once()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/finance/test_finance_webhook.py -v
```
Expected: FAIL — 404

- [ ] **Step 3: Implement the webhook endpoint**

```python
# src/api/v1/finance_webhook.py
"""
Finance Add-on — inbound Stripe webhook handler.

URL: POST /api/v1/finance/webhook/stripe/<provider_id>

The provider_id identifies a WebhookProvider record (provider_type="stripe")
that belongs to a specific InboxIQ account and stores the Stripe signing secret.
This endpoint is unauthenticated — security is via Stripe signature verification.
"""
import json
import logging

from flask import request, jsonify, current_app

from src.api.v1 import v1
from src.models.automation import WebhookProvider
from src.models.addons import AccountAddOn
from src.crypto import decrypt_value
from src.tasks.finance_addon import process_stripe_event

_log = logging.getLogger(__name__)


@v1.route("/finance/webhook/stripe/<provider_id>", methods=["POST"])  # nosemgrep: inboxiq.auth.unprotected-write-endpoint
def finance_stripe_webhook(provider_id):
    """
    Receive Stripe payment events for a Finance add-on account.
    Each account has its own endpoint identified by provider_id.
    """
    raw_body = request.get_data()

    provider = WebhookProvider.query.filter_by(
        id=provider_id,
        provider_type="stripe",
        enabled=True,
    ).first()
    if not provider:
        return jsonify({"error": "not_found"}), 404

    if provider.webhook_signing_secret_encrypted:
        sig_header = request.headers.get("Stripe-Signature", "")
        secret = decrypt_value(provider.webhook_signing_secret_encrypted)
        try:
            import stripe as _stripe
            _stripe.Webhook.construct_event(raw_body, sig_header, secret)
        except Exception:
            _log.warning(
                "finance_webhook: invalid Stripe signature for provider_id=%s", provider_id
            )
            return jsonify({"error": "invalid_signature"}), 400

    addon = AccountAddOn.query.filter_by(
        account_id=provider.account_id,
        addon_type="finance",
        status="active",
    ).first()
    if not addon:
        return jsonify({"error": "addon_not_active"}), 403

    try:
        payload = json.loads(raw_body)
    except Exception:
        return jsonify({"error": "invalid_json"}), 400

    event_type = payload.get("type", "")
    supported = {"checkout.session.completed", "payment_intent.succeeded"}

    if event_type in supported:
        process_stripe_event.delay(
            account_id=provider.account_id,
            provider_id=str(provider.id),
            event=payload,
        )

    return jsonify({"received": True}), 200
```

- [ ] **Step 4: Register in `src/api/v1/__init__.py`**

Add:
```python
from src.api.v1 import finance_webhook as _finance_webhook  # noqa: F401
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/finance/test_finance_webhook.py -v
```
Expected: PASS (3 tests)

- [ ] **Step 6: Commit**

```bash
git add src/api/v1/finance_webhook.py src/api/v1/__init__.py tests/finance/test_finance_webhook.py
git commit -m "feat(finance-addon): inbound Stripe webhook endpoint"
```

---

## Task 7: Pre-Built AutomationRule Template Seed

**Files:**
- Modify: `src/manage.py`
- No test needed (idempotent seed script)

This creates a global `AutomationRule` with `is_template=True` and `template_category="finance"` that all accounts can see in Automation Studio. It has no `account_id` — it is a global template. Add a `seed` CLI command if one doesn't exist.

- [ ] **Step 1: Check if `src/manage.py` has a seed command**

```bash
grep -n "seed\|cli\|@manager\|@app.cli" /Users/kofi/inboxiq/src/manage.py | head -20
```

- [ ] **Step 2: Add the seed command**

In `src/manage.py`, add a new CLI command:

```python
@app.cli.command("seed_finance_template")
def seed_finance_template():
    """Create the Finance add-on pre-built AutomationRule template."""
    from src.models.automation import AutomationRule
    from src.extensions import db

    existing = AutomationRule.query.filter_by(
        is_template=True,
        template_category="finance",
    ).first()

    if existing:
        print(f"Finance template already exists: {existing.id}")
        return

    # AutomationRule.account_id is NOT NULL. Use account_id=1 (founder account) as the
    # template owner. A proper global template system would require a nullable migration.
    # The template is marked is_template=True so it is never executed as a live rule.
    template = AutomationRule(
        account_id=1,
        name="Stripe → QuickBooks",
        description=(
            "Receive Stripe payment events via webhook and sync them to QuickBooks "
            "in real-time, or export a weekly CSV for your accountant."
        ),
        trigger={"event": "stripe.payment_received", "object": "finance_transaction"},
        conditions=[],
        actions=[{"type": "finance_sync"}],
        is_template=True,
        template_category="finance",
        source="template",
        enabled=False,  # templates are not executable directly
    )
    db.session.add(template)
    try:
        db.session.commit()
        print(f"Finance template created: {template.id}")
    except Exception:
        db.session.rollback()
        raise
```

Note: `account_id` is `db.ForeignKey("accounts.id")` with `nullable=False` in the current model. Check the model — if it's NOT NULL, you'll need to add a `nullable=True` migration or use a dedicated system account ID. If the column does not allow NULL, add this step:

```bash
# Run: flask db migrate -m "allow null account_id on global automation templates"
# Then review the migration to confirm it only changes automation_rules.account_id to nullable
```

- [ ] **Step 3: Run the seed**

```bash
flask seed_finance_template
```
Expected: `Finance template created: <uuid>`

Run again to verify idempotency:
```bash
flask seed_finance_template
```
Expected: `Finance template already exists: <uuid>`

- [ ] **Step 4: Commit**

```bash
git add src/manage.py
git commit -m "feat(finance-addon): seed pre-built Finance template in Automation Studio"
```

---

## Task 8: Run Full Test Suite and Verify

- [ ] **Step 1: Run all finance tests**

```bash
pytest tests/finance/ -v
```
Expected: All tests PASS. Note any failures and fix before committing.

- [ ] **Step 2: Run full test suite to check for regressions**

```bash
pytest --tb=short -q
```
Expected: No new failures compared to the pre-implementation baseline.

- [ ] **Step 3: Verify Celery task is registered**

```bash
kubectl exec -n kaley deploy/inboxiq-celery-inbox-worker -- python -c \
  "from src.celery_inboxiq import celery; tasks = list(celery.tasks.keys()); print([t for t in tasks if 'finance' in t])"
```
Expected: `['finance_addon.process_stripe_event', 'finance_addon.generate_weekly_csv_export']`

- [ ] **Step 4: Final commit**

```bash
git add -u
git commit -m "feat(finance-addon): complete backend — webhook, QB client, tasks, template"
```

---

## What This Plan Does NOT Cover (Plan B)

The following are deferred to a separate plan:

- **Settings UI**: UI for users to configure Stripe and QB `WebhookProvider` records for the finance add-on (inside `/settings`)
- **Top Topics gate**: When a Top Topic is Stripe-related, the "Automate →" button checks `finance_addon_active()` and shows the add-on upsell if not active
- **`/use-case/finance` page rewrite**: Full rewrite of the marketing page to reflect the add-on
- **KB article**: How-to guide for setting up the Finance add-on

Plan B should be written after this plan is complete and deployed, so UI copy reflects real endpoint URLs and configuration steps.
