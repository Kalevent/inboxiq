"""Tests for the periodic smoke-test Celery task.

The deploy-time smoke test catches breakage at deploy time. But a regression
between deploys (memory leak, dependency upstream outage, DB drift, expired
service-account creds) goes unnoticed until a customer complains. This task
runs the same checks every 15 min via Celery beat; failures fire crash email
through the SMTPHandler we wired up earlier today.
"""
from unittest.mock import patch


def test_check_routes_returns_failures_for_5xx_routes():
    """check_routes must surface 5xx routes as failures so the task can decide
    whether to raise. 2xx and 3xx must be treated as pass; 4xx auth gates pass."""
    from src.monitoring import smoke

    fake_responses = {
        "/": 200,
        "/dashboard": 302,           # auth wall — pass
        "/health": 200,
        "/some-broken-route": 500,   # fail
    }

    def _fake_status(url):
        path = url.split("/", 3)[-1]
        path = "/" + path if not path.startswith("/") else path
        # _fake_status is given full URL; recover the path
        from urllib.parse import urlparse
        path = urlparse(url).path
        return fake_responses.get(path, 404)

    with patch("src.monitoring.smoke._do_request", side_effect=_fake_status):
        result = smoke.check_routes(
            base_url="https://example.com",
            routes=["/", "/dashboard", "/health", "/some-broken-route"],
        )

    failed = [r for r in result if r["outcome"] == "fail"]
    passed = [r for r in result if r["outcome"] == "pass"]
    assert len(failed) == 1
    assert failed[0]["route"] == "/some-broken-route"
    assert failed[0]["status"] == 500
    assert len(passed) == 3


def test_run_smoke_test_task_raises_when_any_route_fails():
    """The beat-scheduled task must raise on any failure so Celery's
    task_failure signal fires — that's what triggers the SMTPHandler crash
    email through the chain we wired today."""
    from src.tasks.smoke import run_smoke_test

    fake_results = [
        {"route": "/", "status": 200, "outcome": "pass"},
        {"route": "/health", "status": 500, "outcome": "fail"},
    ]
    with patch("src.tasks.smoke.check_routes", return_value=fake_results):
        try:
            run_smoke_test.run()
        except Exception as exc:
            assert "/health" in str(exc), "exception must name the failing route"
            assert "500" in str(exc)
        else:
            raise AssertionError("run_smoke_test must raise when a route fails")


def test_run_smoke_test_task_succeeds_when_all_routes_pass():
    """No raise = no email. All-pass returns a structured result for logs."""
    from src.tasks.smoke import run_smoke_test

    fake_results = [
        {"route": "/", "status": 200, "outcome": "pass"},
        {"route": "/health", "status": 200, "outcome": "pass"},
    ]
    with patch("src.tasks.smoke.check_routes", return_value=fake_results):
        result = run_smoke_test.run()

    assert result["status"] == "ok"
    assert result["passed"] == 2
    assert result["failed"] == 0
