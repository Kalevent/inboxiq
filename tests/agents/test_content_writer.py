# tests/agents/test_content_writer.py
import json
import pytest
from unittest.mock import MagicMock, patch


class BaseModule:
    """Minimal base class for DSPy Module to inherit from in tests."""
    def __call__(self, *args, **kwargs):
        return self.forward(*args, **kwargs)


def test_build_blog_quality_check_returns_ready_for_high_score(app):
    """build_blog_quality_check module returns 'ready' when quality_score >= 7."""
    from src.dspy.signatures import build_blog_quality_check

    mock_dspy = MagicMock()
    mock_dspy.Module = BaseModule

    mock_result = MagicMock()
    mock_result.quality_score = "8"
    mock_result.publish_decision = "ready"
    mock_result.reason = "Well-structured post."

    mock_module = MagicMock(return_value=mock_result)
    mock_dspy.ChainOfThought.return_value = mock_module

    checker = build_blog_quality_check(mock_dspy)
    result = checker(title="Test", content="body text", target_audience="Head of Support")

    assert result.publish_decision == "ready"
    assert result.quality_score == "8"


def test_content_writer_agent_execute_stores_agent_event(app):
    """execute() writes an AgentEvent row on success."""
    from src.agents.content_writer import ContentWriterAgent

    fake_result = {
        "success": True,
        "blog_post_id": "abc-123",
        "title": "Test Post",
        "slug": "test-post",
        "word_count": 1500,
        "status": "ready",
        "quality_score": "8",
    }
    with patch.object(ContentWriterAgent, "_run_auto", return_value=fake_result), \
         patch.object(ContentWriterAgent, "_store_event") as mock_store:
        agent = ContentWriterAgent(account_id=1)
        goal = json.dumps({"mode": "auto", "niche": "B2B SaaS", "audience": "Head of Support"})
        result = agent.execute(goal)

    assert result["status"] == "ready"
    mock_store.assert_called_once()
    args = mock_store.call_args[0]
    assert args[0] is True   # success=True


def test_content_writer_agent_execute_stores_event_on_failure(app):
    """execute() writes a failed AgentEvent row when _run_auto raises."""
    from src.agents.content_writer import ContentWriterAgent

    with patch.object(ContentWriterAgent, "_run_auto", side_effect=RuntimeError("boom")), \
         patch.object(ContentWriterAgent, "_store_event") as mock_store:
        agent = ContentWriterAgent(account_id=1)
        goal = json.dumps({"mode": "auto", "niche": "B2B SaaS", "audience": "Head of Support"})
        with pytest.raises(RuntimeError):
            agent.execute(goal)

    mock_store.assert_called_once()
    args = mock_store.call_args[0]
    assert args[0] is False   # success=False
    assert "boom" in (args[2] or "")  # error_msg


def test_content_writer_agent_dispatches_pitched_mode(app):
    """execute() with mode=pitched calls _run_pitched, not _run_auto."""
    from src.agents.content_writer import ContentWriterAgent

    fake_result = {"success": True, "blog_post_id": "xyz", "title": "Pitched", "slug": "pitched", "word_count": 1300, "status": "ready", "quality_score": "7"}
    with patch.object(ContentWriterAgent, "_run_pitched", return_value=fake_result) as mock_pitched, \
         patch.object(ContentWriterAgent, "_store_event"):
        agent = ContentWriterAgent(account_id=1)
        goal = json.dumps({"mode": "pitched", "topic_id": "topic-uuid"})
        result = agent.execute(goal)

    mock_pitched.assert_called_once_with("topic-uuid")
    assert result["status"] == "ready"


def test_generate_blog_post_task_delegates_to_agent(app):
    """generate_blog_post Celery task is a thin wrapper around ContentWriterAgent."""
    from src.agents.content_writer import ContentWriterAgent

    fake_result = {"success": True, "blog_post_id": "x", "title": "T", "slug": "t", "word_count": 1500, "status": "ready", "quality_score": "8"}
    with patch.object(ContentWriterAgent, "execute", return_value=fake_result) as mock_exec:
        from src.content.tasks import generate_blog_post
        result = generate_blog_post(niche="B2B SaaS", audience="Head of Support", topic_index=0)

    mock_exec.assert_called_once()
    goal = json.loads(mock_exec.call_args[0][0])
    assert goal["mode"] == "auto"
    assert goal["niche"] == "B2B SaaS"
    assert goal["audience"] == "Head of Support"
    assert goal["topic_index"] == 0
    assert "account_id" in goal


def test_generate_blog_from_pitched_topic_delegates_to_agent(app):
    """generate_blog_from_pitched_topic is a thin wrapper around ContentWriterAgent."""
    from src.agents.content_writer import ContentWriterAgent

    fake_result = {"success": True, "blog_post_id": "y", "title": "P", "slug": "p", "word_count": 1400, "status": "draft", "quality_score": "6"}
    with patch.object(ContentWriterAgent, "execute", return_value=fake_result) as mock_exec:
        from src.content.tasks import generate_blog_from_pitched_topic
        result = generate_blog_from_pitched_topic(topic_id="some-uuid")

    mock_exec.assert_called_once()
    goal = json.loads(mock_exec.call_args[0][0])
    assert goal["mode"] == "pitched"
    assert goal["topic_id"] == "some-uuid"
    assert result == fake_result
