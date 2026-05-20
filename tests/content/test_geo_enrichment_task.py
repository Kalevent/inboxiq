import os, pytest
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("INBOXIQ_ENCRYPTION_KEY", "test-encryption-key-for-unit-tests")

from unittest.mock import patch, MagicMock
from sqlalchemy.pool import StaticPool
from src.app import create_app
from src.extensions import db as _db
from src.models.content import BlogPost


@pytest.fixture
def app():
    app = create_app()
    app.config["TESTING"] = True
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite://"
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
        "connect_args": {"check_same_thread": False},
        "poolclass": StaticPool,
    }
    with app.app_context():
        BlogPost.__table__.create(_db.engine, checkfirst=True)
        yield app
        _db.session.remove()
        BlogPost.__table__.drop(_db.engine, checkfirst=True)


def test_enrich_skips_posts_with_existing_faq(app):
    with app.app_context():
        post = BlogPost(
            id="post-1", slug="test-post", title="Test",
            status="published",
            markdown="# Test\n\n## Frequently Asked Questions\n\n**Q?**\n\nA.",
            dspy_quality_score=0.8,
        )
        _db.session.add(post)
        _db.session.commit()

        with patch("src.content.tasks._configure_dspy"), \
             patch("src.content.tasks.BlogFAQGeneratorModule") as mock_module:
            from src.content.tasks import enrich_blog_posts_for_geo
            result = enrich_blog_posts_for_geo()

        mock_module.assert_not_called()
        assert result["skipped"] == 1
        assert result["enriched"] == 0


def test_enrich_skips_low_quality_posts(app):
    with app.app_context():
        post = BlogPost(
            id="post-2", slug="test-post-2", title="Test 2",
            status="published", markdown="# Test\n\nNo FAQ here.",
            dspy_quality_score=0.3,
        )
        _db.session.add(post)
        _db.session.commit()

        with patch("src.content.tasks._configure_dspy"), \
             patch("src.content.tasks.BlogFAQGeneratorModule") as mock_module:
            from src.content.tasks import enrich_blog_posts_for_geo
            result = enrich_blog_posts_for_geo()

        mock_module.assert_not_called()
        assert result["skipped"] == 1


def test_enrich_appends_faq_to_eligible_post(app):
    with app.app_context():
        post = BlogPost(
            id="post-3", slug="test-post-3", title="Test 3",
            status="published",
            markdown="# Test\n\nContent without FAQ section.",
            dspy_quality_score=0.8,
            content_html="<p>Content</p>",
        )
        _db.session.add(post)
        _db.session.commit()

        mock_prediction = MagicMock()
        mock_prediction.faq_markdown = "## Frequently Asked Questions\n\n**Q?**\n\nA."
        mock_module_instance = MagicMock()
        mock_module_instance.return_value = mock_prediction

        with patch("src.content.tasks._configure_dspy"), \
             patch("src.content.tasks.BlogFAQGeneratorModule", return_value=mock_module_instance):
            from src.content.tasks import enrich_blog_posts_for_geo
            result = enrich_blog_posts_for_geo()

        refreshed = _db.session.get(BlogPost, "post-3")
        assert "## Frequently Asked Questions" in refreshed.markdown
        assert result["enriched"] == 1
