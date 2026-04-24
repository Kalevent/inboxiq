import pytest
from unittest.mock import patch, MagicMock


def test_generate_blog_post_raises_on_dspy_failure(app):
    """generate_blog_post must raise on DSPy failure so Celery marks it FAILURE."""
    with app.app_context():
        with patch("src.content.tasks.initialize_dspy"), \
             patch("src.content.tasks.TopicGeneratorModule") as MockTopicGen:
            MockTopicGen.return_value.side_effect = RuntimeError("model timeout")
            from src.content.tasks import generate_blog_post
            with pytest.raises(RuntimeError, match="model timeout"):
                generate_blog_post(niche="B2B SaaS", audience="Head of Support")
