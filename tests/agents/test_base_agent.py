import pytest
from unittest.mock import MagicMock, patch


def test_base_agent_execute_calls_react_and_logs_event(app):
    """BaseAgent.execute() runs dspy.ReAct and writes one AgentEvent row."""
    from src.agents.base import BaseAgent
    from src.models.ai import AgentEvent
    from src.extensions import db

    class EchoAgent(BaseAgent):
        agent_name = "echo_test"
        mcp_server_labels = []

        def _get_tools(self):
            def noop_tool():
                "Does nothing."
                return {"ok": True}
            return [noop_tool]

    mock_prediction = MagicMock()
    mock_prediction.result = "Agent completed successfully"

    with app.app_context():
        with patch("src.agents.base.dspy") as mock_dspy:
            mock_react_instance = MagicMock()
            mock_react_instance.return_value = mock_prediction
            mock_dspy.ReAct.return_value = mock_react_instance

            agent = EchoAgent(account_id=1)
            result = agent.execute("do something")

        assert result["success"] is True
        event = db.session.query(AgentEvent).filter_by(agent_name="echo_test").first()
        assert event is not None
        assert event.status == "success"
        assert event.context["goal"] == "do something"
        assert event.context["account_id"] == 1


def test_base_agent_execute_logs_failure_event_on_exception(app):
    """BaseAgent.execute() writes an error AgentEvent when dspy.ReAct raises."""
    from src.agents.base import BaseAgent
    from src.models.ai import AgentEvent
    from src.extensions import db

    class BrokenAgent(BaseAgent):
        agent_name = "broken_test"
        mcp_server_labels = []

        def _get_tools(self):
            return []

    with app.app_context():
        with patch("src.agents.base.dspy") as mock_dspy:
            mock_dspy.ReAct.side_effect = RuntimeError("boom")

            agent = BrokenAgent(account_id=1)
            result = agent.execute("fail")

        assert result["success"] is False
        event = db.session.query(AgentEvent).filter_by(agent_name="broken_test").first()
        assert event is not None
        assert event.status == "error"
        assert "boom" in event.error_message
