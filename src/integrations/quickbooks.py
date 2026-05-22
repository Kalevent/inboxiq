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


def client_from_provider(provider) -> QuickBooksClient:
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
