"""Task 15: agent failures must emit a log.error so the crash_report SMTPHandler fires.

The throttle is class-level (per agent_name, 60-min cooldown) so a stuck agent
running in a celery beat loop cannot flood support@kalevent.com with one email
per minute.
"""
import logging
from unittest.mock import MagicMock, patch

import pytest

from src.agents.base import BaseAgent


class _FailingDummy(BaseAgent):
    """Agent whose ReAct prediction matches a _FAILURE_PHRASES entry."""
    agent_name = "fail_dummy"
    mcp_server_labels: list = []

    def _get_tools(self):
        return []


@patch("src.agents.base.dspy")
def test_agent_failure_emits_log_error(mock_dspy, app, caplog):
    react = MagicMock()
    react.return_value = MagicMock(
        result="Despite persistent efforts, I was unable to retrieve the qualifying leads."
    )
    mock_dspy.ReAct.return_value = react

    # Reset cooldown so this test isn't blocked by sibling test ordering
    BaseAgent._last_error_email_sent.pop("fail_dummy", None)

    with app.app_context():
        with caplog.at_level(logging.ERROR, logger="src.agents.base"):
            _FailingDummy(account_id=1).execute("test goal")

    error_records = [
        r for r in caplog.records
        if r.levelno == logging.ERROR and "fail_dummy" in r.getMessage()
    ]
    assert len(error_records) >= 1, f"expected >=1 ERROR record for fail_dummy, got {len(error_records)}"


@patch("src.agents.base.dspy")
def test_agent_failure_throttles_repeated_errors(mock_dspy, app, caplog):
    react = MagicMock()
    react.return_value = MagicMock(
        result="Despite persistent efforts, I was unable to retrieve the qualifying leads."
    )
    mock_dspy.ReAct.return_value = react

    BaseAgent._last_error_email_sent.pop("fail_dummy", None)

    with app.app_context():
        with caplog.at_level(logging.ERROR, logger="src.agents.base"):
            for _ in range(5):
                _FailingDummy(account_id=1).execute("test goal")

    error_records = [
        r for r in caplog.records
        if r.levelno == logging.ERROR and "fail_dummy" in r.getMessage()
    ]
    assert len(error_records) == 1, (
        f"expected exactly 1 throttled ERROR in 5 failed runs, got {len(error_records)}"
    )


@patch("src.agents.base.dspy")
def test_agent_success_does_not_emit_error(mock_dspy, app, caplog):
    """Successful runs must NOT trip the SMTPHandler path."""
    react = MagicMock()
    react.return_value = MagicMock(result="All good — completed.")
    mock_dspy.ReAct.return_value = react

    BaseAgent._last_error_email_sent.pop("fail_dummy", None)

    with app.app_context():
        with caplog.at_level(logging.ERROR, logger="src.agents.base"):
            _FailingDummy(account_id=1).execute("test goal")

    error_records = [
        r for r in caplog.records
        if r.levelno == logging.ERROR and "fail_dummy" in r.getMessage()
    ]
    assert error_records == [], "successful run must not emit an ERROR log"
