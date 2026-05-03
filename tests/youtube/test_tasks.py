import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone


@pytest.fixture
def mock_blog_post():
    post = MagicMock()
    post.id = "post-123"
    post.title = "How to fix inbox chaos"
    post.content_html = "<p>Your inbox is overwhelming you.</p>"
    post.primary_keyword = "inbox management"
    return post


@pytest.fixture
def mock_pain_point():
    pp = MagicMock()
    pp.id = "pain-123"
    pp.pain_point = "Support emails pile up unread over the weekend"
    pp.consequence = "Customers churn before Monday"
    pp.persona = "Head of Support"
    return pp


def test_generate_scripts_creates_long_form_and_shorts(app, mock_blog_post, mock_pain_point):
    with app.app_context():
        with patch("src.tasks.youtube._get_latest_blog_post", return_value=mock_blog_post), \
             patch("src.tasks.youtube._get_top_pain_point", return_value=mock_pain_point), \
             patch("src.tasks.youtube._run_dspy_script_generation") as mock_dspy, \
             patch("src.tasks.youtube.db") as mock_db:

            mock_dspy.return_value = {
                "script": "You're drowning in support emails...",
                "hook_line": "You're drowning in support emails.",
                "chapter_markers": "[]",
                "cta_line": "Start free at inboxiq.com",
                "illustration_prompts": None,
                "short_scripts": [
                    {"script": "60s short...", "pattern_interrupt_line": "Inbox chaos?", "cta_line": "Link in description."},
                    {"script": "60s short 2...", "pattern_interrupt_line": "Missing replies?", "cta_line": "Link in description."},
                ],
                "seo": {
                    "title": "Never miss a support email again | InboxIQ",
                    "description": "Your inbox is chaos.\nInboxIQ fixes it.\n{{UTM_LINK}}",
                    "tags": '["inbox management", "B2B SaaS"]',
                    "thumbnail_prompt": "Person overwhelmed at desk",
                },
            }

            mock_render = MagicMock()
            mock_render.id = "render-001"
            mock_db.session.query.return_value.filter.return_value.first.return_value = None
            mock_db.session.query.return_value.filter_by.return_value.first.return_value = None

            from src.tasks.youtube import generate_scripts
            result = generate_scripts(account_id=2, video_style="avatar")

            assert result["status"] == "ok"
            assert result["long_form_created"] is True
            assert result["shorts_created"] == 2


def test_render_videos_submits_avatar_to_heygen(app):
    with app.app_context():
        with patch("src.tasks.youtube.heygen_mcp") as mock_heygen, \
             patch("src.tasks.youtube.db") as mock_db:

            mock_video = MagicMock()
            mock_video.id = "vid-1"
            mock_video.video_style = "avatar"
            mock_video.video_type = "long_form"
            mock_video.script = "You are drowning in support emails."
            mock_video.illustration_prompts = None
            mock_video.status = "script_ready"

            mock_db.session.query.return_value.filter.return_value.all.return_value = [mock_video]
            mock_db.session.query.return_value.filter.return_value.filter.return_value.all.return_value = []
            mock_heygen.render_video.return_value = {"status": "submitted", "job_id": "heygen-job-1"}

            from src.tasks.youtube import render_videos
            result = render_videos(account_id=2)

            mock_heygen.render_video.assert_called_once()
            assert result["status"] == "ok"


def test_publish_videos_uploads_to_youtube(app):
    with app.app_context():
        with patch("src.tasks.youtube.youtube_mcp") as mock_yt, \
             patch("src.tasks.youtube.db") as mock_db:

            mock_video = MagicMock()
            mock_video.id = "vid-1"
            mock_video.video_type = "long_form"
            mock_video.heygen_render_url = "https://cdn.heygen.com/video.mp4"
            mock_video.title = "Never miss a support email again | InboxIQ"
            mock_video.description = "Pain.\nResolution.\n{{UTM_LINK}}"
            mock_video.tags = ["inbox management"]
            mock_video.utm_slug = "yt-long-inbox-may-2026"
            mock_video.utm_medium = "long_form"
            mock_video.utm_campaign = "inbox-may-2026"
            mock_video.parent_video_id = None

            mock_db.session.query.return_value.filter.return_value.all.return_value = [mock_video]
            mock_db.session.get.return_value = None
            mock_yt.upload_video.return_value = {
                "status": "published",
                "youtube_video_id": "yt-abc123",
                "youtube_url": "https://www.youtube.com/watch?v=yt-abc123",
            }
            mock_yt.add_end_screen.return_value = {"status": "ok"}
            mock_yt.add_card.return_value = {"status": "ok"}
            mock_yt.post_pinned_comment.return_value = {"status": "ok"}

            from src.tasks.youtube import publish_videos
            result = publish_videos(account_id=2)

            assert result["status"] == "ok"
            assert result["published"] == 1
            mock_yt.upload_video.assert_called_once()
            mock_yt.post_pinned_comment.assert_called_once()


def test_generate_scripts_creates_video_render(app, db):
    from src.models.campaigns import YouTubeVideo, VideoRender
    from unittest.mock import patch, MagicMock

    mock_post = MagicMock()
    mock_post.id = "post-abc"
    mock_post.title = "How to fix inbox chaos"
    mock_post.content_html = "<p>Inbox chaos.</p>"
    mock_post.primary_keyword = "inbox"

    mock_pp = MagicMock()
    mock_pp.id = "pain-abc"
    mock_pp.pain_point = "Emails pile up"
    mock_pp.consequence = "Customers churn"

    # The app fixture already pushes an app_context — use it directly (no nested push).
    with patch("src.tasks.youtube._get_latest_blog_post", return_value=mock_post), \
         patch("src.tasks.youtube._get_top_pain_point", return_value=mock_pp), \
         patch("src.tasks.youtube._run_dspy_script_generation") as mock_dspy, \
         patch("src.tasks.youtube._build_utm_slug", side_effect=lambda vtype, title: f"slug-{vtype}"):

        mock_dspy.return_value = {
            "script": "Your inbox is chaos.",
            "hook_line": "Chaos.",
            "chapter_markers": "[]",
            "cta_line": "Start free.",
            "illustration_prompts": None,
            "short_scripts": [
                {"script": "Short 1.", "pattern_interrupt_line": "Chaos?", "cta_line": "Link."},
            ],
            "seo": {
                "title": "Fix your inbox | InboxIQ",
                "description": "Chaos.\n{{UTM_LINK}}",
                "tags": '["inbox"]',
                "thumbnail_prompt": "Person at desk",
            },
        }

        from src.tasks.youtube import generate_scripts
        # Use .run() to bypass ContextTask and stay in the fixture's app context.
        result = generate_scripts.run(account_id=2, video_style="avatar")

    assert result["status"] == "ok"
    assert result["long_form_created"] is True

    videos = db.session.query(YouTubeVideo).filter_by(account_id=2).all()
    renders = db.session.query(VideoRender).filter_by(account_id=2, programme="youtube").all()
    assert len(renders) == len(videos), "Each YouTubeVideo must have a VideoRender"
    for video in videos:
        assert video.video_render_id is not None
        render = db.session.get(VideoRender, video.video_render_id)
        assert render is not None
        assert render.programme == "youtube"
        aspect = "16:9" if video.video_type == "long_form" else "9:16"
        assert render.aspect_ratio == aspect


def test_send_digest_calls_email_function(app):
    with app.app_context():
        with patch("src.tasks.youtube.send_youtube_digest_email") as mock_email, \
             patch("src.tasks.youtube.db") as mock_db:

            mock_db.session.query.return_value.filter.return_value.all.return_value = []
            mock_db.session.query.return_value.filter.return_value.scalar.return_value = 0

            import os
            os.environ["ADMIN_EMAILS"] = "admin@test.com"

            from src.tasks.youtube import send_digest
            result = send_digest(account_id=2)

            assert result["status"] == "ok"
            mock_email.assert_called_once()
