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
