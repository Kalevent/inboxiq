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
            mock_video.status = "script_ready"

            mock_render = MagicMock()
            mock_render.script = (
                "You are drowning in support emails. InboxIQ triages your inbox "
                "automatically. Start free at inboxiq.com."
            )
            mock_render.aspect_ratio = "16:9"
            mock_render.illustration_prompts = None
            mock_render.dalle_frame_urls = None

            mock_db.session.query.return_value.join.return_value.filter.return_value.all.return_value = [
                (mock_video, mock_render)
            ]
            mock_heygen.render_video.return_value = {"status": "submitted", "job_id": "heygen-job-1"}

            from src.tasks.youtube import render_videos
            result = render_videos.run(account_id=2)

            mock_heygen.render_video.assert_called_once()
            assert result["status"] == "ok"


def test_publish_videos_uploads_to_youtube(app):
    with app.app_context():
        with patch("src.tasks.youtube.youtube_mcp") as mock_yt, \
             patch("src.tasks.youtube.db") as mock_db:

            mock_video = MagicMock()
            mock_video.id = "vid-1"
            mock_video.video_type = "long_form"
            mock_video.title = "Never miss a support email again | InboxIQ"
            mock_video.description = "Pain.\nResolution.\n{{UTM_LINK}}"
            mock_video.tags = ["inbox management"]
            mock_video.utm_slug = "yt-long-inbox-may-2026"
            mock_video.utm_medium = "long_form"
            mock_video.utm_campaign = "inbox-may-2026"
            mock_video.parent_video_id = None

            mock_render = MagicMock()
            mock_render.heygen_render_url = "https://cdn.heygen.com/video.mp4"
            mock_render.status = "render_complete"

            mock_db.session.query.return_value.join.return_value.filter.return_value.all.return_value = [
                (mock_video, mock_render)
            ]
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
            result = publish_videos.run(account_id=2)

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


def test_render_videos_writes_to_video_render(app, db):
    from src.models.campaigns import YouTubeVideo, VideoRender
    from unittest.mock import patch

    with app.app_context():
        render = VideoRender(
            account_id=2, programme="youtube", video_style="avatar",
            aspect_ratio="16:9",
            script=(
                "Your inbox is chaos. InboxIQ triages it automatically and "
                "drafts replies in your voice. Start free at inboxiq.com."
            ),
            status="pending",
        )
        db.session.add(render)
        db.session.flush()
        video = YouTubeVideo(
            account_id=2, icp_pain_point_id="pain-1", video_type="long_form",
            video_style="avatar", video_render_id=render.id,
            utm_slug="yt-long-test-render", utm_medium="long_form",
            status="script_ready",
        )
        db.session.add(video)
        db.session.commit()
        render_id = render.id
        video_id = video.id

    with patch("src.tasks.youtube.heygen_mcp") as mock_heygen:
        mock_heygen.render_video.return_value = {"status": "submitted", "job_id": "job-render-001"}

        with app.app_context():
            from src.tasks.youtube import render_videos
            result = render_videos.run(account_id=2)

        assert result["status"] == "ok"
        assert result["submitted"] == 1

        with app.app_context():
            r = db.session.get(VideoRender, render_id)
            assert r.heygen_job_id == "job-render-001"
            assert r.status == "rendering"
            assert r.render_submitted_at is not None
            v = db.session.get(YouTubeVideo, video_id)
            assert v.status == "rendering"


def test_publish_videos_uses_render_url_and_sets_delivered(app, db):
    from src.models.campaigns import YouTubeVideo, VideoRender
    from unittest.mock import patch

    with app.app_context():
        render = VideoRender(
            account_id=2, programme="youtube", video_style="avatar",
            aspect_ratio="16:9", script="Script.", status="render_complete",
            heygen_render_url="https://cdn.heygen.com/out.mp4",
        )
        db.session.add(render)
        db.session.flush()
        video = YouTubeVideo(
            account_id=2, icp_pain_point_id="pain-1", video_type="long_form",
            video_style="avatar", video_render_id=render.id,
            title="Fix your inbox | InboxIQ",
            description="Pain.\n{{UTM_LINK}}",
            tags=["inbox"],
            utm_slug="yt-long-pub-test", utm_medium="long_form",
            utm_campaign="pub-test", status="render_complete",
        )
        db.session.add(video)
        db.session.commit()
        render_id = render.id
        video_id = video.id

    with patch("src.tasks.youtube.youtube_mcp") as mock_yt:
        mock_yt.upload_video.return_value = {
            "status": "published",
            "youtube_video_id": "yt-pub001",
            "youtube_url": "https://www.youtube.com/watch?v=yt-pub001",
        }
        mock_yt.add_end_screen.return_value = {"status": "ok"}
        mock_yt.add_card.return_value = {"status": "ok"}
        mock_yt.post_pinned_comment.return_value = {"status": "ok"}

        with app.app_context():
            from src.tasks.youtube import publish_videos
            result = publish_videos.run(account_id=2)

        assert result["status"] == "ok"
        assert result["published"] == 1

        with app.app_context():
            r = db.session.get(VideoRender, render_id)
            assert r.status == "delivered"
            v = db.session.get(YouTubeVideo, video_id)
            assert v.status == "published"
            assert v.youtube_video_id == "yt-pub001"

        call_kwargs = mock_yt.upload_video.call_args
        assert call_kwargs.kwargs["file_url"] == "https://cdn.heygen.com/out.mp4"


def test_render_videos_skips_script_missing_product_name(app, db):
    """Pre-render quality gate: a script that never names InboxIQ must be
    marked failed BEFORE submitting to HeyGen ($ per render). Production
    burned 3 renders on a 'chatbot'-only script before this gate existed."""
    from src.models.campaigns import YouTubeVideo, VideoRender
    from unittest.mock import patch

    with app.app_context():
        render = VideoRender(
            account_id=2, programme="youtube", video_style="avatar",
            aspect_ratio="16:9",
            script="Are you drowning in support emails? Chatbots can help. Start free at inboxiq.com.",
            status="pending",
        )
        db.session.add(render)
        db.session.flush()
        video = YouTubeVideo(
            account_id=2, icp_pain_point_id="pain-gate-1", video_type="long_form",
            video_style="avatar", video_render_id=render.id,
            utm_slug="yt-long-gate-no-product", utm_medium="long_form",
            status="script_ready",
        )
        db.session.add(video)
        db.session.commit()
        render_id = render.id
        video_id = video.id

    with patch("src.tasks.youtube.heygen_mcp") as mock_heygen:
        with app.app_context():
            from src.tasks.youtube import render_videos
            result = render_videos.run(account_id=2)

        # HeyGen must NOT be called when script fails the gate.
        mock_heygen.render_video.assert_not_called()
        assert result["failed"] >= 1

        with app.app_context():
            v = db.session.get(YouTubeVideo, video_id)
            r = db.session.get(VideoRender, render_id)
            assert v.status == "failed"
            assert r.status == "failed"


def test_render_videos_skips_script_missing_cta(app, db):
    """Pre-render quality gate: script must include a CTA pointing at the app
    (inboxiq.com). Otherwise the funnel attribution breaks."""
    from src.models.campaigns import YouTubeVideo, VideoRender
    from unittest.mock import patch

    with app.app_context():
        render = VideoRender(
            account_id=2, programme="youtube", video_style="avatar",
            aspect_ratio="16:9",
            script="Support emails pile up. InboxIQ clears your inbox in minutes. The end.",
            status="pending",
        )
        db.session.add(render)
        db.session.flush()
        video = YouTubeVideo(
            account_id=2, icp_pain_point_id="pain-gate-2", video_type="long_form",
            video_style="avatar", video_render_id=render.id,
            utm_slug="yt-long-gate-no-cta", utm_medium="long_form",
            status="script_ready",
        )
        db.session.add(video)
        db.session.commit()
        video_id = video.id

    with patch("src.tasks.youtube.heygen_mcp") as mock_heygen:
        with app.app_context():
            from src.tasks.youtube import render_videos
            render_videos.run(account_id=2)

        mock_heygen.render_video.assert_not_called()

        with app.app_context():
            v = db.session.get(YouTubeVideo, video_id)
            assert v.status == "failed"


def test_render_videos_passes_gate_when_script_has_product_and_cta(app, db):
    """Happy path: a valid script (names InboxIQ + CTA inboxiq.com) reaches HeyGen."""
    from src.models.campaigns import YouTubeVideo, VideoRender
    from unittest.mock import patch

    with app.app_context():
        render = VideoRender(
            account_id=2, programme="youtube", video_style="avatar",
            aspect_ratio="16:9",
            script=(
                "Support emails pile up unread. Customers churn before Monday. "
                "InboxIQ triages your inbox automatically and drafts replies in your voice. "
                "Start free at inboxiq.com."
            ),
            status="pending",
        )
        db.session.add(render)
        db.session.flush()
        video = YouTubeVideo(
            account_id=2, icp_pain_point_id="pain-gate-3", video_type="long_form",
            video_style="avatar", video_render_id=render.id,
            utm_slug="yt-long-gate-happy", utm_medium="long_form",
            status="script_ready",
        )
        db.session.add(video)
        db.session.commit()
        video_id = video.id

    with patch("src.tasks.youtube.heygen_mcp") as mock_heygen:
        mock_heygen.render_video.return_value = {"status": "submitted", "job_id": "job-gate-happy"}
        with app.app_context():
            from src.tasks.youtube import render_videos
            result = render_videos.run(account_id=2)

        mock_heygen.render_video.assert_called_once()
        assert result["submitted"] == 1

        with app.app_context():
            v = db.session.get(YouTubeVideo, video_id)
            assert v.status == "rendering"


def test_run_dspy_passes_product_name_to_long_form_predictor(app, mock_blog_post, mock_pain_point):
    """`_run_dspy_script_generation` must pass product_name='InboxIQ' and a
    product_value_proposition to the long form predictor. Without this the
    rendered script never mentions the product (root cause of generic 'chatbot'
    content seen in production)."""
    with app.app_context():
        with patch("src.dspy.config._configure_dspy"), \
             patch("src.dspy.signatures.build_youtube_signatures") as mock_build, \
             patch("dspy.Predict") as mock_predict_cls:

            sentinel = MagicMock()
            sentinel.__name__ = "sig"
            mock_build.return_value = {
                "YouTubeLongFormScript": sentinel,
                "YouTubeShortScript": sentinel,
                "YouTubeSEOMetadata": sentinel,
                "YouTubeIllustrationPrompts": sentinel,
            }
            predictor = MagicMock()
            predictor.script = "Long form script."
            predictor.hook_line = "Pain."
            predictor.chapter_markers = "[]"
            predictor.cta_line = "Start free at inboxiq.com"
            predictor.short_script = "Short."
            predictor.pattern_interrupt_line = "Hook."
            predictor.title = "Title | InboxIQ"
            predictor.description = "Pain.\nResolution.\n{{UTM_LINK}}"
            predictor.tags = '["tag"]'
            predictor.thumbnail_prompt = "Prompt."
            mock_predict_cls.return_value = predictor

            from src.tasks.youtube import _run_dspy_script_generation
            _run_dspy_script_generation(mock_blog_post, mock_pain_point, "avatar")

            # Find the long form predictor invocation (first call) and assert product context was passed.
            long_call = predictor.call_args_list[0]
            assert long_call.kwargs.get("product_name") == "InboxIQ"
            assert long_call.kwargs.get("product_value_proposition"), \
                "product_value_proposition must be passed to long form predictor"


def test_run_dspy_generates_seo_for_each_short(app, mock_blog_post, mock_pain_point):
    """Each short must get its own SEO metadata. In production today shorts
    publish with empty title/description/tags because SEO is only generated
    for the long form."""
    with app.app_context():
        with patch("src.dspy.config._configure_dspy"), \
             patch("src.dspy.signatures.build_youtube_signatures") as mock_build, \
             patch("dspy.Predict") as mock_predict_cls:

            sentinel = MagicMock()
            mock_build.return_value = {
                "YouTubeLongFormScript": sentinel,
                "YouTubeShortScript": sentinel,
                "YouTubeSEOMetadata": sentinel,
                "YouTubeIllustrationPrompts": sentinel,
            }
            predictor = MagicMock()
            predictor.script = "Long form script."
            predictor.hook_line = "Pain."
            predictor.chapter_markers = "[]"
            predictor.cta_line = "Start free at inboxiq.com"
            predictor.short_script = "Short script."
            predictor.pattern_interrupt_line = "Hook."
            predictor.title = "Title | InboxIQ"
            predictor.description = "Pain.\nResolution.\n{{UTM_LINK}}"
            predictor.tags = '["tag"]'
            predictor.thumbnail_prompt = "Prompt."
            mock_predict_cls.return_value = predictor

            from src.tasks.youtube import _run_dspy_script_generation
            result = _run_dspy_script_generation(mock_blog_post, mock_pain_point, "avatar")

            assert len(result["short_scripts"]) == 2
            for short in result["short_scripts"]:
                assert short.get("title"), "Each short must have a non-empty title"
                assert short.get("description"), "Each short must have a description"
                assert short.get("tags") is not None, "Each short must have tags"
                assert short.get("thumbnail_prompt"), "Each short must have a thumbnail_prompt"


def test_generate_scripts_persists_short_seo_to_db(app, db):
    """End-to-end: shorts saved to YouTubeVideo must have non-empty title."""
    from src.models.campaigns import YouTubeVideo
    from unittest.mock import patch, MagicMock

    mock_post = MagicMock()
    mock_post.id = "post-shorts-seo"
    mock_post.title = "Inbox chaos"
    mock_post.content_html = "<p>chaos</p>"
    mock_post.primary_keyword = "inbox"

    mock_pp = MagicMock()
    mock_pp.id = "pain-shorts-seo"
    mock_pp.pain_point = "Emails pile up"
    mock_pp.consequence = "Customers churn"

    counter = {"n": 0}
    def _slug(vtype, title):
        counter["n"] += 1
        return f"slug-{vtype}-{counter['n']}"

    with patch("src.tasks.youtube._get_latest_blog_post", return_value=mock_post), \
         patch("src.tasks.youtube._get_top_pain_point", return_value=mock_pp), \
         patch("src.tasks.youtube._run_dspy_script_generation") as mock_dspy, \
         patch("src.tasks.youtube._build_utm_slug", side_effect=_slug):

        mock_dspy.return_value = {
            "script": "Long.",
            "hook_line": "Hook.",
            "chapter_markers": "[]",
            "cta_line": "CTA.",
            "illustration_prompts": None,
            "short_scripts": [
                {
                    "script": "Short 1.",
                    "pattern_interrupt_line": "Hook 1.",
                    "cta_line": "Link 1.",
                    "title": "Short 1 title | InboxIQ",
                    "description": "Pain.\nResolution.\n{{UTM_LINK}}",
                    "tags": ["inbox"],
                    "thumbnail_prompt": "Prompt 1.",
                },
                {
                    "script": "Short 2.",
                    "pattern_interrupt_line": "Hook 2.",
                    "cta_line": "Link 2.",
                    "title": "Short 2 title | InboxIQ",
                    "description": "Pain.\nResolution.\n{{UTM_LINK}}",
                    "tags": ["inbox"],
                    "thumbnail_prompt": "Prompt 2.",
                },
            ],
            "seo": {
                "title": "Long title | InboxIQ",
                "description": "Pain.\n{{UTM_LINK}}",
                "tags": '["inbox"]',
                "thumbnail_prompt": "Long prompt.",
            },
        }

        from src.tasks.youtube import generate_scripts
        result = generate_scripts.run(account_id=2, video_style="avatar")
        assert result["status"] == "ok"
        assert result["shorts_created"] == 2

    shorts = db.session.query(YouTubeVideo).filter_by(account_id=2, video_type="short").all()
    assert len(shorts) == 2
    for s in shorts:
        assert s.title, f"Short {s.id} has empty title"
        assert s.description, f"Short {s.id} has empty description"
        assert s.tags, f"Short {s.id} has empty tags"


def test_send_digest_calls_email_function(app):
    with app.app_context():
        with patch("src.tasks.youtube.send_youtube_digest_email") as mock_email, \
             patch("src.tasks.youtube.db") as mock_db:

            mock_db.session.query.return_value.filter.return_value.all.return_value = []
            mock_db.session.query.return_value.join.return_value.filter.return_value.all.return_value = []
            mock_db.session.query.return_value.filter.return_value.scalar.return_value = 0

            import os
            os.environ["ADMIN_EMAILS"] = "admin@test.com"

            from src.tasks.youtube import send_digest
            result = send_digest.run(account_id=2)

            assert result["status"] == "ok"
            mock_email.assert_called_once()


def test_send_digest_marks_stale_renders_failed(app, db):
    from src.models.campaigns import YouTubeVideo, VideoRender
    from unittest.mock import patch
    from datetime import timedelta
    import os

    with app.app_context():
        old_submitted_at = datetime.now(timezone.utc) - timedelta(hours=25)
        render = VideoRender(
            account_id=2, programme="youtube", video_style="avatar",
            aspect_ratio="16:9", script="Script.", status="rendering",
            render_submitted_at=old_submitted_at,
        )
        db.session.add(render)
        db.session.flush()
        video = YouTubeVideo(
            account_id=2, icp_pain_point_id="pain-1", video_type="long_form",
            video_style="avatar", video_render_id=render.id,
            utm_slug="yt-long-stale-test", utm_medium="long_form",
            utm_campaign="stale-test", status="rendering",
        )
        db.session.add(video)
        db.session.commit()
        render_id = render.id
        video_id = video.id

    os.environ["ADMIN_EMAILS"] = "admin@test.com"

    with patch("src.tasks.youtube.send_youtube_digest_email"), \
         patch("src.tasks.youtube.youtube_mcp"):

        with app.app_context():
            from src.tasks.youtube import send_digest
            send_digest.run(account_id=2)

        with app.app_context():
            r = db.session.get(VideoRender, render_id)
            assert r.status == "failed"
            v = db.session.get(YouTubeVideo, video_id)
            assert v.status == "failed"
