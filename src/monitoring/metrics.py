"""
Prometheus metrics for per-account cost tracking.

Usage in Celery tasks:
    from src.monitoring.metrics import record_task_cost

    record_task_cost("inbox.triage_email", account_id=account_id, duration_seconds=elapsed)

Usage in API routes:
    from src.monitoring.metrics import record_api_request

    record_api_request("/api/v1/tickets", account_id=account_id, status=200, duration_seconds=elapsed)
"""

import os
import time
import logging
from contextlib import contextmanager

_log = logging.getLogger(__name__)

_ENABLED = os.getenv("PROMETHEUS_METRICS_ENABLED", "false").lower() in ("1", "true", "yes")

# Lazy-initialised registries — only created if PROMETHEUS_METRICS_ENABLED=true
_task_duration = None
_task_total = None
_api_duration = None
_api_total = None


def _init():
    global _task_duration, _task_total, _api_duration, _api_total
    if _task_duration is not None:
        return
    try:
        from prometheus_client import Histogram, Counter
        _task_duration = Histogram(
            "inboxiq_task_duration_seconds",
            "Celery task duration in seconds",
            ["task_name", "account_id", "status"],
            buckets=[0.1, 0.5, 1, 2, 5, 10, 30, 60, 120, 300],
        )
        _task_total = Counter(
            "inboxiq_task_total",
            "Total Celery task executions",
            ["task_name", "account_id", "status"],
        )
        _api_duration = Histogram(
            "inboxiq_api_duration_seconds",
            "API request duration per account",
            ["endpoint", "account_id", "method", "status"],
            buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1, 2, 5],
        )
        _api_total = Counter(
            "inboxiq_api_total",
            "Total API requests per account",
            ["endpoint", "account_id", "method", "status"],
        )
    except Exception as exc:
        _log.warning("Prometheus metrics init failed: %s", exc)


def record_task_cost(task_name: str, account_id, duration_seconds: float, status: str = "success"):
    """Record duration and count for a Celery task, labelled by account."""
    if not _ENABLED:
        return
    _init()
    if _task_duration is None:
        return
    label = str(account_id) if account_id else "unknown"
    try:
        _task_duration.labels(task_name=task_name, account_id=label, status=status).observe(duration_seconds)
        _task_total.labels(task_name=task_name, account_id=label, status=status).inc()
    except Exception as exc:
        _log.debug("metrics record_task_cost failed: %s", exc)


def record_api_request(endpoint: str, account_id, method: str, status: int, duration_seconds: float):
    """Record API request duration and count per account."""
    if not _ENABLED:
        return
    _init()
    if _api_duration is None:
        return
    label = str(account_id) if account_id else "anonymous"
    status_str = str(status)
    try:
        _api_duration.labels(endpoint=endpoint, account_id=label, method=method, status=status_str).observe(duration_seconds)
        _api_total.labels(endpoint=endpoint, account_id=label, method=method, status=status_str).inc()
    except Exception as exc:
        _log.debug("metrics record_api_request failed: %s", exc)


@contextmanager
def track_task(task_name: str, account_id):
    """Context manager — wraps a task body and records duration + status."""
    start = time.perf_counter()
    status = "success"
    try:
        yield
    except Exception:
        status = "failure"
        raise
    finally:
        elapsed = time.perf_counter() - start
        record_task_cost(task_name, account_id=account_id, duration_seconds=elapsed, status=status)


# ---------------------------------------------------------------------------
# Domain metrics for LinkedIn cadence, agents, and MCP tool calls.
#
# Unlike the cost-tracking metrics above (lazy-init, gated by
# PROMETHEUS_METRICS_ENABLED), these are registered eagerly at import time so
# they are always exposed via the /metrics endpoint and visible in Prometheus.
# ---------------------------------------------------------------------------
from prometheus_client import Counter, Gauge, Histogram  # noqa: E402

linkedin_status_transitions = Counter(
    "inboxiq_linkedin_prospect_status_transitions",
    "LinkedInProspect status transitions",
    ["from_status", "to_status", "account_id"],
)

agent_react_max_iters_hit = Counter(
    "inboxiq_agent_react_max_iters_hit",
    "DSPy ReAct loops that hit max_iters without finishing",
    ["agent_name"],
)

agent_status = Counter(
    "inboxiq_agent_status",
    "Agent invocation outcome (success vs error vs llm_give_up)",
    ["agent_name", "status"],
)

mcp_tool_call_duration = Histogram(
    "inboxiq_mcp_tool_call_duration_seconds",
    "Duration of MCP tool calls from agents",
    ["server_label", "tool"],
    buckets=(0.1, 0.5, 1, 2, 5, 10, 30, 60),
)

linkedin_acceptance_ratio = Gauge(
    "inboxiq_linkedin_acceptance_ratio",
    "Rolling 7d connection-accepted / connection-sent ratio",
    ["account_id"],
)
