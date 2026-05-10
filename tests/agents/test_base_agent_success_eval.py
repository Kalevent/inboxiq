from unittest.mock import patch, MagicMock

import pytest

from src.agents.base import BaseAgent


class _Dummy(BaseAgent):
    agent_name = "dummy_eval"
    mcp_server_labels = []

    def _get_tools(self):
        return []


def test_status_error_when_llm_admits_failure(app):
    """If the LLM result text matches a known failure phrase, status must be error."""
    with app.app_context():
        with patch("src.agents.base.dspy") as mock_dspy:
            react = MagicMock()
            react.return_value = MagicMock(
                result="Despite persistent efforts, I was unable to retrieve the qualifying leads."
            )
            mock_dspy.ReAct.return_value = react

            res = _Dummy(account_id=1).execute("test goal")

        assert res["success"] is False
        assert "llm_admitted_failure" in (res.get("error") or "")


def test_status_error_when_max_iters_hit(app):
    """If tool_calls reaches max_iters, status must be error."""
    with app.app_context():
        with patch("src.agents.base.dspy") as mock_dspy:
            agent = _Dummy(account_id=1)
            agent.max_iters = 3

            def _react_factory(signature, tools, max_iters):
                def _invoke(goal):
                    for _ in range(agent.max_iters):
                        agent.tool_calls.append({"tool": "noop"})
                    return MagicMock(result="OK done")
                return _invoke

            mock_dspy.ReAct.side_effect = _react_factory

            res = agent.execute("test goal")

        assert res["success"] is False
        assert "max_iters" in (res.get("error") or "")


def test_status_success_when_clean_completion(app):
    """Clean result text under max_iters -> success."""
    with app.app_context():
        with patch("src.agents.base.dspy") as mock_dspy:
            react = MagicMock()
            react.return_value = MagicMock(result="Successfully enriched 3 leads.")
            mock_dspy.ReAct.return_value = react

            res = _Dummy(account_id=1).execute("test goal")

        assert res["success"] is True
        assert res.get("error") is None
