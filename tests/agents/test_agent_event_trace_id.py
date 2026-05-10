"""Task 14: AgentEvent must persist OTel trace_id; failure email must include
a clickable Phoenix URL constructed from that trace_id."""
import logging
from unittest.mock import patch, MagicMock

import pytest

from src.agents.base import BaseAgent
from src.models.ai import AgentEvent
from src.extensions import db


class _Dummy(BaseAgent):
    agent_name = "trace_test"
    mcp_server_labels: list = []

    def _get_tools(self):
        return []


@pytest.fixture
def full_app(app):
    """Re-export the conftest `app` fixture under the name used by Task 14 spec.

    The shared conftest already creates the AgentEvent table; we just need an
    app context for the duration of the test.
    """
    with app.app_context():
        yield app


def test_agent_event_has_trace_id_column():
    assert "trace_id" in AgentEvent.__table__.columns
    col = AgentEvent.__table__.columns["trace_id"]
    assert col.nullable is True
    assert str(col.type).startswith("VARCHAR")


@patch("src.agents.base.dspy")
@patch("src.agents.base.trace")
def test_store_event_populates_trace_id_from_current_span(mock_trace, mock_dspy, full_app):
    span_ctx = MagicMock()
    span_ctx.is_valid = True
    span_ctx.trace_id = 0xabc123
    span = MagicMock()
    span.get_span_context.return_value = span_ctx
    mock_trace.get_current_span.return_value = span
    mock_dspy.ReAct.return_value = MagicMock(return_value=MagicMock(result="OK done"))

    _Dummy(account_id=1).execute("test goal")

    row = db.session.query(AgentEvent).filter_by(agent_name="trace_test").first()
    assert row is not None
    assert row.trace_id == format(0xabc123, "032x")


@patch("src.agents.base.dspy")
@patch("src.agents.base.trace")
def test_store_event_handles_invalid_span(mock_trace, mock_dspy, full_app):
    span_ctx = MagicMock()
    span_ctx.is_valid = False
    span = MagicMock()
    span.get_span_context.return_value = span_ctx
    mock_trace.get_current_span.return_value = span
    mock_dspy.ReAct.return_value = MagicMock(return_value=MagicMock(result="OK done"))

    _Dummy(account_id=1).execute("test goal")

    row = (
        db.session.query(AgentEvent)
        .filter_by(agent_name="trace_test")
        .order_by(AgentEvent.created_at.desc())
        .first()
    )
    assert row.trace_id is None


@patch("src.agents.base.dspy")
@patch("src.agents.base.trace")
def test_failure_log_includes_phoenix_url(mock_trace, mock_dspy, full_app, caplog, monkeypatch):
    monkeypatch.setenv("PHOENIX_URL", "https://phoenix.kalevent.com")
    span_ctx = MagicMock()
    span_ctx.is_valid = True
    span_ctx.trace_id = 0xdef456
    span = MagicMock()
    span.get_span_context.return_value = span_ctx
    mock_trace.get_current_span.return_value = span
    mock_dspy.ReAct.return_value = MagicMock(return_value=MagicMock(
        result="Despite persistent efforts, I was unable to retrieve qualifying leads."
    ))
    BaseAgent._last_error_email_sent.pop("trace_test", None)

    with caplog.at_level(logging.ERROR, logger="src.agents.base"):
        _Dummy(account_id=1).execute("test goal")

    err = next(
        (r for r in caplog.records if r.levelno == logging.ERROR and "trace_test" in r.getMessage()),
        None,
    )
    assert err is not None
    msg = err.getMessage()
    assert "phoenix.kalevent.com" in msg
    assert format(0xdef456, "032x") in msg
