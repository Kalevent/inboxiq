from __future__ import annotations
import logging
import stripe
from flask import current_app
from src.compliance.runner import CheckResult, STATUS_PASS, STATUS_FAIL, STATUS_ERROR

logger = logging.getLogger(__name__)


def check_webhook_secret_configured() -> CheckResult:
    secret = current_app.config.get("STRIPE_WEBHOOK_SECRET")
    return CheckResult(
        id="stripe.webhooks.secret_configured",
        title="Stripe webhook signature secret configured",
        status=STATUS_PASS if secret else STATUS_FAIL,
        soc2_controls=["CC6.6"],
        details="STRIPE_WEBHOOK_SECRET is set — incoming webhooks are signature-verified" if secret
                else "STRIPE_WEBHOOK_SECRET is missing — webhooks are NOT verified",
        evidence=[{"secret_present": bool(secret)}],
    )


def check_webhook_endpoints() -> CheckResult:
    api_key = current_app.config.get("STRIPE_SECRET_KEY")
    if not api_key:
        return CheckResult(
            id="stripe.webhooks.endpoints_registered",
            title="Stripe webhook endpoints registered",
            status=STATUS_ERROR,
            soc2_controls=["CC6.6"],
            details="STRIPE_SECRET_KEY not set — cannot check Stripe webhook endpoints",
        )
    stripe.api_key = api_key
    try:
        endpoints = stripe.WebhookEndpoint.list(limit=20)
        enabled = [e for e in endpoints.data if e.status == "enabled"]
        evidence = [{"url": e.url, "status": e.status, "events": e.enabled_events} for e in endpoints.data]
    except Exception as exc:
        return CheckResult(
            id="stripe.webhooks.endpoints_registered",
            title="Stripe webhook endpoints registered",
            status=STATUS_ERROR,
            soc2_controls=["CC6.6"],
            details=f"Stripe API error: {exc}",
        )
    status = STATUS_PASS if enabled else STATUS_FAIL
    details = (
        f"{len(enabled)} enabled webhook endpoint(s) registered"
        if enabled
        else "No enabled webhook endpoints found in Stripe"
    )
    return CheckResult(
        id="stripe.webhooks.endpoints_registered",
        title="Stripe webhook endpoints registered",
        status=status,
        soc2_controls=["CC6.6"],
        details=details,
        evidence=evidence,
    )


def run_stripe_checks() -> list[CheckResult]:
    results = []
    for fn in [check_webhook_secret_configured, check_webhook_endpoints]:
        try:
            results.append(fn())
        except Exception as exc:
            results.append(CheckResult(id=f"stripe.{fn.__name__}", title=fn.__name__, status=STATUS_ERROR, soc2_controls=[], details=str(exc)))
    return results
