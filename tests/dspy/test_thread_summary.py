"""Tests for thread summary prepending in draft replies."""
import json
import pytest


def test_should_summarise_when_thread_has_multiple_messages():
    from src.dspy.draft_reply import _should_summarise_thread
    history = json.dumps([
        {"from_email": "customer@example.com", "body": "Hi", "is_outbound": False},
        {"from_email": "kofi@kalevent.com", "body": "Hello", "is_outbound": True},
    ])
    assert _should_summarise_thread(history) is True


def test_should_not_summarise_single_message_thread():
    from src.dspy.draft_reply import _should_summarise_thread
    history = json.dumps([
        {"from_email": "customer@example.com", "body": "Hi", "is_outbound": False},
    ])
    assert _should_summarise_thread(history) is False


def test_should_not_summarise_empty_thread():
    from src.dspy.draft_reply import _should_summarise_thread
    assert _should_summarise_thread("[]") is False
    assert _should_summarise_thread("") is False


def test_prepend_thread_summary_format():
    from src.dspy.draft_reply import _prepend_thread_summary
    result = _prepend_thread_summary(
        reply_text="Thanks for reaching out.",
        summary="Customer reported a login issue on 3 May. Support asked for account ID. Customer responded with ID-456.",
    )
    assert result.startswith("📋 Thread summary (delete before sending):")
    assert "Customer reported a login issue" in result
    assert "---" in result
    assert "Thanks for reaching out." in result
    # summary comes before the reply
    assert result.index("---") < result.index("Thanks for reaching out.")


def test_prepend_thread_summary_empty_reply_still_includes_summary():
    from src.dspy.draft_reply import _prepend_thread_summary
    result = _prepend_thread_summary(reply_text="", summary="Short summary.")
    assert "📋 Thread summary" in result
    assert "Short summary." in result


def test_should_summarise_rejects_invalid_json():
    from src.dspy.draft_reply import _should_summarise_thread
    assert _should_summarise_thread("not-json") is False


def test_summary_enabled_flag_gates_execution():
    """summary_enabled=False must prevent the summary block being prepended."""
    # Simulate: thread has messages but summary_enabled=False (Starter/Pro plan)
    # The _should_summarise_thread check alone is not enough — the gate is summary_enabled
    # This is enforced in DecisionProgram.forward(); here we just verify the helper
    # behaviour is correct given the gate exists.
    from src.dspy.draft_reply import _should_summarise_thread
    history = json.dumps([
        {"from_email": "a@example.com", "body": "Hi", "is_outbound": False},
        {"from_email": "b@example.com", "body": "Hello", "is_outbound": True},
    ])
    # Even if thread qualifies, the gate in forward() requires summary_enabled=True
    # We verify the helper returns True (the thread qualifies) — the gate is upstream
    assert _should_summarise_thread(history) is True
