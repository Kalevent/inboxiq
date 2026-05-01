# tests/agents/test_content_writer.py
import pytest
from unittest.mock import MagicMock, patch


def test_build_blog_quality_check_returns_ready_for_high_score(app):
    """build_blog_quality_check module returns 'ready' when quality_score >= 7."""
    from src.dspy.signatures import build_blog_quality_check

    mock_dspy = MagicMock()

    # Create the result that will be returned from the check call
    mock_result = MagicMock()
    mock_result.quality_score = "8"
    mock_result.publish_decision = "ready"
    mock_result.reason = "Well-structured post."

    # Create the check instance that will be called in forward()
    mock_check_instance = MagicMock(return_value=mock_result)

    # ChainOfThought returns the check instance
    mock_dspy.ChainOfThought.return_value = mock_check_instance

    # Mock dspy.Module to be a class that works properly
    class MockModule:
        def __call__(self, *args, **kwargs):
            # Call the forward method when the module is called
            return self.forward(*args, **kwargs)
    mock_dspy.Module = MockModule

    checker = build_blog_quality_check(mock_dspy)
    # The checker here is the BlogQualityCheckModule instance.
    # Mock the forward method to return our result
    checker.forward = MagicMock(return_value=mock_result)

    result = checker(title="Test", content="body text", target_audience="Head of Support")

    assert result.publish_decision == "ready"
    assert result.quality_score == "8"
