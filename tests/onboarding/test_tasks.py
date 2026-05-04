import pytest
from unittest.mock import patch, MagicMock


def test_send_onboarding_video_email_returns_false_when_smtp_not_configured(app):
    with app.app_context():
        app.config.pop("SMTP_HOST", None)
        from src.notifications.emails import send_onboarding_video_email
        result = send_onboarding_video_email(
            to_email="user@example.com",
            recipient_name="Sarah Jones",
            video_url="https://cdn.heygen.com/v.mp4",
        )
        assert result is False


def test_send_onboarding_video_email_builds_correct_subject(app):
    with app.app_context():
        app.config["SMTP_HOST"] = "smtp.example.com"
        app.config["SMTP_PORT"] = 587
        app.config["SMTP_USER"] = "user"
        app.config["SMTP_PASSWORD"] = "pass"
        app.config["SMTP_USE_TLS"] = True
        app.config["SMTP_USE_SSL"] = False

        captured = {}

        def fake_send(msg):
            captured["subject"] = msg["Subject"]

        with patch("smtplib.SMTP") as mock_smtp:
            mock_server = MagicMock()
            mock_smtp.return_value.__enter__ = lambda s: mock_server
            mock_smtp.return_value.__exit__ = MagicMock(return_value=False)
            mock_server.send_message.side_effect = fake_send

            from src.notifications.emails import send_onboarding_video_email
            result = send_onboarding_video_email(
                to_email="sarah@acme.com",
                recipient_name="Sarah Jones",
                video_url="https://cdn.heygen.com/v.mp4",
            )

        assert result is True
        assert "Sarah" in captured["subject"]
        assert "personalised" in captured["subject"].lower()


def test_send_onboarding_video_email_subject_exact_format(app):
    """Subject must be '{first_name}, your personalised InboxIQ walkthrough is ready'."""
    with app.app_context():
        app.config["SMTP_HOST"] = "smtp.example.com"
        app.config["SMTP_PORT"] = 587
        app.config["SMTP_USER"] = "u"
        app.config["SMTP_PASSWORD"] = "p"
        app.config["SMTP_USE_TLS"] = True
        app.config["SMTP_USE_SSL"] = False

        captured = {}

        def fake_send(msg):
            captured["subject"] = msg["Subject"]

        with patch("smtplib.SMTP") as mock_smtp:
            mock_server = MagicMock()
            mock_smtp.return_value.__enter__ = lambda s: mock_server
            mock_smtp.return_value.__exit__ = MagicMock(return_value=False)
            mock_server.send_message.side_effect = fake_send

            from src.notifications.emails import send_onboarding_video_email
            send_onboarding_video_email(
                to_email="sarah@acme.com",
                recipient_name="Sarah Jones",
                video_url="https://cdn.heygen.com/v.mp4",
            )

        assert captured["subject"] == "Sarah, your personalised InboxIQ walkthrough is ready"


def test_send_onboarding_video_email_empty_name_uses_fallback(app):
    with app.app_context():
        app.config["SMTP_HOST"] = "smtp.example.com"
        app.config["SMTP_PORT"] = 587
        app.config["SMTP_USER"] = "u"
        app.config["SMTP_PASSWORD"] = "p"
        app.config["SMTP_USE_TLS"] = True
        app.config["SMTP_USE_SSL"] = False

        captured = {}

        def fake_send(msg):
            captured["subject"] = msg["Subject"]

        with patch("smtplib.SMTP") as mock_smtp:
            mock_server = MagicMock()
            mock_smtp.return_value.__enter__ = lambda s: mock_server
            mock_smtp.return_value.__exit__ = MagicMock(return_value=False)
            mock_server.send_message.side_effect = fake_send

            from src.notifications.emails import send_onboarding_video_email
            result = send_onboarding_video_email(
                to_email="user@example.com",
                recipient_name="",
                video_url="https://cdn.heygen.com/v.mp4",
            )

        assert result is True
        assert captured["subject"].startswith("there,")


def test_queue_onboarding_video_creates_render_and_record(app, db):
    from src.models.campaigns import VideoRender, OnboardingVideo
    from unittest.mock import patch, MagicMock

    mock_account = MagicMock()
    mock_account.name = "Acme Corp"
    mock_account.referral_source = "LinkedIn"
    mock_account.account_id = 2

    mock_user = MagicMock()
    mock_user.name = "Sarah Jones"
    mock_user.email = "sarah@acme.com"
    mock_user.account_id = 2

    with app.app_context():
        with patch("src.tasks.onboarding_video.Account") as mock_account_cls, \
             patch("src.tasks.onboarding_video.User") as mock_user_cls, \
             patch("src.tasks.onboarding_video._run_onboarding_script_generation") as mock_dspy, \
             patch("src.tasks.onboarding_video.heygen_mcp") as mock_heygen:

            mock_account_cls.query.get.return_value = mock_account
            mock_user_cls.query.get.return_value = mock_user
            mock_dspy.return_value = {
                "script": "Sarah, welcome to InboxIQ.",
                "hook_line": "Sarah, welcome.",
                "cta_line": "Check your dashboard now.",
            }
            mock_heygen.render_video.return_value = {"status": "submitted", "job_id": "job-onboard-001"}

            from src.tasks.onboarding_video import queue_onboarding_video
            result = queue_onboarding_video.run(account_id=2, user_id=1)

        assert result["status"] == "ok"
        assert "render_id" in result

        render = db.session.query(VideoRender).filter_by(account_id=2, programme="onboarding").first()
        assert render is not None
        assert render.heygen_job_id == "job-onboard-001"
        assert render.status == "rendering"
        assert render.render_submitted_at is not None
        onboarding = db.session.query(OnboardingVideo).filter_by(account_id=2).first()
        assert onboarding is not None
        assert onboarding.recipient_name == "Sarah Jones"
        assert onboarding.recipient_company == "Acme Corp"


def test_queue_onboarding_video_is_idempotent(app, db):
    from src.models.campaigns import VideoRender, OnboardingVideo

    with app.app_context():
        render = VideoRender(
            account_id=2, programme="onboarding", video_style="avatar", aspect_ratio="16:9"
        )
        db.session.add(render)
        db.session.flush()
        onboarding = OnboardingVideo(
            account_id=2, video_render_id=render.id, recipient_user_id=1, recipient_name="Sarah"
        )
        db.session.add(onboarding)
        db.session.commit()

    with app.app_context():
        with patch("src.tasks.onboarding_video.heygen_mcp") as mock_heygen:
            from src.tasks.onboarding_video import queue_onboarding_video
            result = queue_onboarding_video.run(account_id=2, user_id=1)

        assert result["status"] == "skipped"
        mock_heygen.render_video.assert_not_called()


def test_queue_onboarding_video_skips_when_account_missing(app, db):
    with app.app_context():
        with patch("src.tasks.onboarding_video.Account") as mock_account_cls, \
             patch("src.tasks.onboarding_video.heygen_mcp") as mock_heygen:
            mock_account_cls.query.get.return_value = None

            from src.tasks.onboarding_video import queue_onboarding_video
            result = queue_onboarding_video.run(account_id=999, user_id=1)

        assert result["status"] == "skipped"
        mock_heygen.render_video.assert_not_called()


def test_queue_onboarding_video_returns_error_on_dspy_failure(app, db):
    with app.app_context():
        with patch("src.tasks.onboarding_video.Account") as mock_account_cls, \
             patch("src.tasks.onboarding_video.User") as mock_user_cls, \
             patch("src.tasks.onboarding_video._run_onboarding_script_generation") as mock_dspy:
            mock_account = MagicMock()
            mock_account.name = "Acme"
            mock_account.referral_source = ""
            mock_account.account_id = 2
            mock_account_cls.query.get.return_value = mock_account

            mock_user = MagicMock()
            mock_user.name = "Sarah"
            mock_user.email = "s@a.com"
            mock_user.account_id = 2
            mock_user_cls.query.get.return_value = mock_user

            mock_dspy.side_effect = RuntimeError("DSPy model unavailable")

            from src.tasks.onboarding_video import queue_onboarding_video
            result = queue_onboarding_video.run(account_id=2, user_id=1)

        assert result["status"] == "error"
        assert result["reason"] == "dspy generation failed"


def test_queue_onboarding_video_skips_when_user_wrong_account(app, db):
    with app.app_context():
        with patch("src.tasks.onboarding_video.Account") as mock_account_cls, \
             patch("src.tasks.onboarding_video.User") as mock_user_cls:
            mock_account = MagicMock()
            mock_account.name = "Acme"
            mock_account.referral_source = ""
            mock_account_cls.query.get.return_value = mock_account

            mock_user = MagicMock()
            mock_user.name = "Sarah"
            mock_user.email = "s@a.com"
            mock_user.account_id = 99  # Different account!
            mock_user_cls.query.get.return_value = mock_user

            from src.tasks.onboarding_video import queue_onboarding_video
            result = queue_onboarding_video.run(account_id=2, user_id=1)

        assert result["status"] == "skipped"
        assert "account" in result["reason"]


def test_send_onboarding_video_email_returns_false_on_smtp_error(app):
    with app.app_context():
        app.config["SMTP_HOST"] = "smtp.example.com"
        app.config["SMTP_PORT"] = 587
        app.config["SMTP_USER"] = "u"
        app.config["SMTP_PASSWORD"] = "p"
        app.config["SMTP_USE_TLS"] = True
        app.config["SMTP_USE_SSL"] = False

        with patch("smtplib.SMTP") as mock_smtp:
            mock_server = MagicMock()
            mock_smtp.return_value.__enter__ = lambda s: mock_server
            mock_smtp.return_value.__exit__ = MagicMock(return_value=False)
            mock_server.send_message.side_effect = Exception("SMTP connection refused")

            from src.notifications.emails import send_onboarding_video_email
            result = send_onboarding_video_email(
                to_email="user@example.com",
                recipient_name="Bob",
                video_url="https://cdn.heygen.com/v.mp4",
            )

        assert result is False


def test_deliver_onboarding_videos_sends_email_and_sets_sent_at(app, db):
    from src.models.campaigns import VideoRender, OnboardingVideo
    from unittest.mock import patch, MagicMock

    with app.app_context():
        render = VideoRender(
            account_id=2, programme="onboarding", video_style="avatar",
            aspect_ratio="16:9", status="render_complete",
            heygen_render_url="https://cdn.heygen.com/onboard.mp4",
        )
        db.session.add(render)
        db.session.flush()
        onboarding = OnboardingVideo(
            account_id=2, video_render_id=render.id, recipient_user_id=1,
            recipient_name="Sarah Jones",
        )
        db.session.add(onboarding)
        db.session.commit()
        render_id = render.id
        onboarding_id = onboarding.id

    mock_user = MagicMock()
    mock_user.email = "sarah@acme.com"

    with patch("src.tasks.onboarding_video.User") as mock_user_cls, \
         patch("src.tasks.onboarding_video.send_onboarding_video_email") as mock_email:

        mock_user_cls.query.get.return_value = mock_user
        mock_email.return_value = True

        with app.app_context():
            from src.tasks.onboarding_video import deliver_onboarding_videos
            result = deliver_onboarding_videos.run()

        assert result["status"] == "ok"
        assert result["sent"] == 1
        assert result["failed"] == 0
        mock_email.assert_called_once_with(
            to_email="sarah@acme.com",
            recipient_name="Sarah Jones",
            video_url="https://cdn.heygen.com/onboard.mp4",
        )

        with app.app_context():
            from src.models.campaigns import OnboardingVideo as OV
            ov = db.session.get(OV, onboarding_id)
            assert ov.email_sent_at is not None


def test_deliver_onboarding_videos_skips_already_sent(app, db):
    from src.models.campaigns import VideoRender, OnboardingVideo
    from unittest.mock import patch
    from datetime import datetime, timezone

    with app.app_context():
        render = VideoRender(
            account_id=2, programme="onboarding", video_style="avatar",
            aspect_ratio="16:9", status="render_complete",
            heygen_render_url="https://cdn.heygen.com/onboard.mp4",
        )
        db.session.add(render)
        db.session.flush()
        onboarding = OnboardingVideo(
            account_id=2, video_render_id=render.id, recipient_user_id=1,
            recipient_name="Sarah Jones",
            email_sent_at=datetime.now(timezone.utc),
        )
        db.session.add(onboarding)
        db.session.commit()

    with patch("src.tasks.onboarding_video.send_onboarding_video_email") as mock_email:
        with app.app_context():
            from src.tasks.onboarding_video import deliver_onboarding_videos
            result = deliver_onboarding_videos.run()

        assert result["sent"] == 0
        mock_email.assert_not_called()
