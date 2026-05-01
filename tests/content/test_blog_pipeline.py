import pytest
from unittest.mock import patch, MagicMock


def test_generate_blog_post_raises_on_dspy_failure(app):
    """generate_blog_post must raise on DSPy failure so Celery marks it FAILURE."""
    with app.app_context():
        from src.agents.content_writer import ContentWriterAgent
        with patch.object(ContentWriterAgent, "execute", side_effect=RuntimeError("model timeout")):
            from src.content.tasks import generate_blog_post
            with pytest.raises(RuntimeError, match="model timeout"):
                generate_blog_post(niche="B2B SaaS", audience="Head of Support")


def test_determine_post_status_high_score_sets_ready():
    from src.content.tasks import _determine_post_status
    assert _determine_post_status("85") == "ready"
    assert _determine_post_status("70") == "ready"
    assert _determine_post_status("0.85") == "ready"


def test_determine_post_status_low_score_sets_draft():
    from src.content.tasks import _determine_post_status
    assert _determine_post_status("65") == "draft"
    assert _determine_post_status("0") == "draft"
    assert _determine_post_status("bad input") == "draft"


def test_determine_post_status_boundary():
    from src.content.tasks import _determine_post_status
    assert _determine_post_status("69") == "draft"
    assert _determine_post_status("69.9") == "draft"
