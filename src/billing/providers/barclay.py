import hashlib
import hmac
import os
from typing import Dict, Any, Tuple
from datetime import datetime, timezone

from src.billing.providers.base import PaymentProvider


class BarclayHostedProvider(PaymentProvider):
    """
    Hosted Payment Page integration scaffold for Barclaycard.
    Reads required env vars and builds a signed beginWebPayment payload.
    """

    name = "barclay"

    def __init__(
        self,
        enterprise_id: str | None = None,
        client_id: str | None = None,
        hmac_secret: str | None = None,
        wsdl_url: str | None = None,
        endpoint_url: str | None = None,
        store_result_url: str | None = None,
        environment: str | None = None,
        api_version: str | None = None,
    ):
        self.enterprise_id = enterprise_id or os.getenv("BARCLAY_ENTERPRISE_ID", "")
        self.client_id = client_id or os.getenv("BARCLAY_CLIENT_ID", "")
        self.hmac_secret = hmac_secret or os.getenv("BARCLAY_HMAC_SECRET", "")
        self.wsdl_url = wsdl_url or os.getenv("BARCLAY_WSDL_URL", "")
        self.endpoint_url = endpoint_url or os.getenv("BARCLAY_ENDPOINT_URL", "")
        self.store_result_url = store_result_url or os.getenv("BARCLAY_STORE_RESULT_URL", "")
        self.environment = environment or os.getenv("BARCLAY_ENVIRONMENT", "ECommerce")
        self.api_version = api_version or os.getenv("BARCLAY_API_VERSION", "36")

    def _guard(self):
        missing = []
        if not self.enterprise_id:
            missing.append("BARCLAY_ENTERPRISE_ID")
        if not self.client_id:
            missing.append("BARCLAY_CLIENT_ID")
        if not self.hmac_secret:
            missing.append("BARCLAY_HMAC_SECRET")
        if not self.endpoint_url:
            missing.append("BARCLAY_ENDPOINT_URL")
        if missing:
            raise RuntimeError(f"Missing Barclay env vars: {', '.join(missing)}")

    # PaymentProvider interface — for hosted flows, these are stubs to avoid misuse.
    def create_payment_method_from_token(self, token: str, email: str) -> Dict[str, Any]:
        raise NotImplementedError("Barclay hosted flow does not use direct card tokens.")

    def attach_payment_method_to_customer(self, payment_method_id: str, customer_ref: str) -> Dict[str, Any]:
        raise NotImplementedError("Barclay hosted flow manages payment method via hosted page.")

    def create_subscription(self, customer_ref: str, plan_code: str) -> Dict[str, Any]:
        raise NotImplementedError("Use create_hosted_payment to redirect user for Barclay payments.")

    def create_invoice(self, customer_ref: str, amount_cents: int, currency: str) -> Dict[str, Any]:
        raise NotImplementedError("Use create_hosted_payment to redirect user for Barclay payments.")

    def pay_invoice(self, invoice_provider_id: str) -> Dict[str, Any]:
        raise NotImplementedError("Barclay hosted flow charges on hosted page; use handle_webhook/handle_callback.")

    def handle_webhook(self, payload: Dict[str, Any], headers: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
        # Hosted Payment Page typically returns via redirect; webhooks may be optional.
        event_type = payload.get("event") or "hosted.callback"
        return event_type, payload

    # Hosted Payment Page helpers
    def create_hosted_payment(self, order: Dict[str, Any]) -> Dict[str, Any]:
        """
        Build a hosted payment URL + signature. Order should include:
        amount_cents, currency, transaction_reference, customer_email.
        """
        self._guard()
        ref = order.get("transaction_reference")
        amount = order.get("amount_cents")
        currency = order.get("currency", "GBP")
        if not ref or amount is None:
            raise ValueError("transaction_reference and amount_cents are required for Barclay hosted payment")

        # Minimal signature: HMAC-SHA256 over "{enterprise_id}{ref}{amount}{currency}"
        message = f"{self.enterprise_id}{ref}{amount}{currency}".encode()
        signature = hmac.new(self.hmac_secret.encode(), message, hashlib.sha256).hexdigest()

        redirect_url = f"{self.endpoint_url}?enterpriseId={self.enterprise_id}&clientId={self.client_id}&transactionReference={ref}"
        return {
            "redirect_url": redirect_url,
            "signature": signature,
            "store_result_url": self.store_result_url,
        }

    def handle_callback(self, transaction_reference: str, status: str, raw: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalize callback response after user returns from hosted payment page.
        """
        return {
            "transaction_reference": transaction_reference,
            "status": status,
            "raw": raw,
        }

    # SOAP helpers (stubbed: only build payload; network call intentionally omitted)
    def _hmac_token(self, trans_no: str, amount: int, currency: str) -> str:
        message = f"{self.enterprise_id}{trans_no}{amount}{currency}".encode()
        return hmac.new(self.hmac_secret.encode(), message, hashlib.sha256).hexdigest()

    def _utc_now_ms(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

    def begin_web_payment(self, order: Dict[str, Any]) -> Dict[str, Any]:
        """
        Build beginWebPayment payload; does NOT call Barclays (requires SOAP client).
        """
        self._guard()
        trans_no = order.get("trans_no") or order.get("transaction_reference") or "tmp-ref"
        amount = int(order.get("amount_cents") or 0)
        currency = order.get("currency", "GBP")
        auth_token = self._hmac_token(trans_no, amount, currency)
        requester = {
            "enterpriseID": self.enterprise_id,
            "clientID": self.client_id,
            "transNo": trans_no,
            "environment": self.environment,
            "version": self.api_version,
            "authToken": auth_token,
        }
        web_payment_request = {
            "requester": requester,
            "transactionTime": self._utc_now_ms(),
            "authType": "AuthAndSettle",
            "paymentMethod": "Card",
            "authenticate": True,
            "purchaseAmount": amount,
            "currencyCode": currency,
            "purchaseDescription": order.get("description", "InboxIQ Subscription"),
            "billingAddress": order.get("billingAddress") or {},
            "storeResultPage": self.store_result_url,
        }
        redirect_url = f"{self.endpoint_url}?enterpriseId={self.enterprise_id}&clientId={self.client_id}&transNo={trans_no}"
        return {
            "redirect_url": redirect_url,
            "transaction_reference": trans_no,
            "request": web_payment_request,
            "note": "SOAP call not executed; supply real client to call beginWebPayment.",
        }

    def get_web_payment(self, transaction_reference: str) -> Dict[str, Any]:
        self._guard()
        return {
            "transaction_reference": transaction_reference,
            "status": "pending",
            "note": "SOAP getWebPayment call not executed; implement with Barclays client.",
        }

    def update_web_payment(self, transaction_reference: str, auth_type: str, amount: int | None = None) -> Dict[str, Any]:
        self._guard()
        return {
            "transaction_reference": transaction_reference,
            "auth_type": auth_type,
            "amount": amount,
            "note": "SOAP updateWebPayment call not executed; implement with Barclays client.",
        }

    def cancel_web_payment(self, transaction_reference: str) -> Dict[str, Any]:
        self._guard()
        return {
            "transaction_reference": transaction_reference,
            "status": "cancelled",
            "note": "SOAP cancelWebPayment call not executed; implement with Barclays client.",
        }
