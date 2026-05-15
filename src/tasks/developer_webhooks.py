"""
Celery task: deliver outbound webhook events to registered app endpoints.
Fired after a ticket is created from a registered app.
"""
import time
import logging
import requests as requests_lib

from src.celery_inboxiq import celery
from src.extensions import db
from src.models.developer import AppProductAccess, AppWebhookDelivery

log = logging.getLogger(__name__)

_PROVIDER_TO_PRODUCT = {
    "chat":    "chat",
    "inboxiq": "chat",
    "forms":   "forms",
    "form":    "forms",
}


def _product_slug_for_provider(provider: str) -> str:
    return _PROVIDER_TO_PRODUCT.get((provider or "").lower(), "intake_api")


@celery.task(
    name="inboxiq.deliver_app_webhook",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    queue="inbox",
)
def deliver_app_webhook(self, app_id: str, product_slug: str, event: str, payload: dict) -> dict:
    """POST a webhook event to the app's configured endpoint and log the attempt."""
    access = AppProductAccess.query.filter_by(
        app_id=app_id, product_slug=product_slug, status="approved"
    ).first()

    if not access or not access.webhook_url:
        return {"status": "skipped", "reason": "no webhook_url"}

    start = time.monotonic()
    status_code = None
    response_body = None
    error = None
    success = False

    try:
        resp = requests_lib.post(
            access.webhook_url,
            json=payload,
            timeout=10,
            allow_redirects=False,
            headers={"User-Agent": "InboxIQ-Webhook/1.0", "Content-Type": "application/json"},
        )
        latency_ms = int((time.monotonic() - start) * 1000)
        status_code = resp.status_code
        response_body = resp.text[:500]
        success = 200 <= resp.status_code < 300
    except requests_lib.exceptions.Timeout:
        latency_ms = 10000
        error = "timeout"
    except requests_lib.exceptions.ConnectionError as exc:
        latency_ms = int((time.monotonic() - start) * 1000)
        error = f"connection_error: {str(exc)[:120]}"
    except Exception as exc:
        latency_ms = int((time.monotonic() - start) * 1000)
        error = f"unexpected: {str(exc)[:120]}"
        log.error("deliver_app_webhook unexpected error app=%s: %s", app_id, exc)

    delivery = AppWebhookDelivery(
        app_id=app_id,
        product_slug=product_slug,
        event=event,
        success=success,
        status_code=status_code,
        response_body=response_body,
        error=error,
        latency_ms=latency_ms,
    )
    try:
        db.session.add(delivery)
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        log.error("deliver_app_webhook failed to log delivery app=%s: %s", app_id, exc)

    if not success and error:
        try:
            raise self.retry(countdown=60 * (2 ** self.request.retries))
        except self.MaxRetriesExceededError:
            log.warning("deliver_app_webhook max retries exceeded app=%s event=%s", app_id, event)

    return {"status": "ok" if success else "failed", "status_code": status_code, "latency_ms": latency_ms}
