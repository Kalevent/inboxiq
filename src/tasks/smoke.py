"""Periodic smoke-test Celery task.

Runs every 15 min via Celery beat (configured in src/celery_inboxiq.py).
Hits the same key public routes scripts/smoke_test.py does, then raises if
any returned 5xx — that propagates up as a Celery task_failure, which the
SMTPHandler wired in src/monitoring/crash_report.py forwards to
CRASH_EMAIL_TO. So a between-deploy regression pages security@ within
~15 min instead of waiting for the next deploy or a customer ticket.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict

from celery import shared_task

from src.monitoring.smoke import check_routes

logger = logging.getLogger(__name__)


@shared_task(name="monitoring.run_smoke_test")
def run_smoke_test() -> Dict[str, Any]:
    base_url = os.getenv("SMOKE_TEST_BASE_URL", "https://kalevent.com")
    results = check_routes(base_url=base_url)
    failures = [r for r in results if r["outcome"] == "fail"]
    passed = len(results) - len(failures)
    if failures:
        # Raise so task_failure fires -> SMTPHandler emails security@.
        # Keep the message short and structured so the alert email surfaces
        # the failing route(s) at a glance.
        summary = ", ".join(f"{r['route']}={r['status']}" for r in failures)
        raise RuntimeError(
            f"Smoke test failed for {base_url}: {len(failures)}/{len(results)} routes 5xx — {summary}"
        )
    return {"status": "ok", "passed": passed, "failed": 0, "base_url": base_url}
