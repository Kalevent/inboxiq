# tests/agents/test_content_writer.py
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
