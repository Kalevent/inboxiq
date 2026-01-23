import smtplib
from email.message import EmailMessage
from typing import Optional

from flask import current_app


def send_activation_email(to_email: str, activation_link: str, account_name: str) -> bool:
    """Send activation email. Returns True on success, False otherwise."""
    app = current_app
    host = app.config.get("SMTP_HOST")
    port = app.config.get("SMTP_PORT")
    user = app.config.get("SMTP_USER")
    password = app.config.get("SMTP_PASSWORD")
    use_tls = app.config.get("SMTP_USE_TLS", True)
    use_ssl = app.config.get("SMTP_USE_SSL", False)
    mail_from = app.config.get("MAIL_FROM", "noreply@kalevent.com")

    if not host:
        app.logger.info(
            {
                "event": "email.disabled",
                "reason": "SMTP_HOST not configured",
                "to": to_email,
                "activation_link": activation_link,
            }
        )
        return False

    msg = EmailMessage()
    msg["Subject"] = "Activate your InboxIQ account"
    msg["From"] = mail_from
    msg["To"] = to_email
    msg.set_content(
        f"Hi,\n\nWelcome to InboxIQ! Activate your account for {account_name}:\n{activation_link}\n\nThanks,\nThe Kalevent Team"
    )
    msg.add_alternative(
        f"""
        <p>Hi,</p>
        <p>Welcome to InboxIQ! You're 60 seconds away from having an AI agent triage your emails automatically.</p>
        <p><strong>Activate your account:</strong> <a href="{activation_link}">Activate Your Account →</a></p>
        <p>Thanks,<br/>The Kalevent Team</p>
        """,
        subtype="html",
    )

    try:
        if use_ssl:
            with smtplib.SMTP_SSL(host, port) as server:
                if user and password:
                    server.login(user, password)
                server.send_message(msg)
        else:
            with smtplib.SMTP(host, port) as server:
                if use_tls:
                    server.starttls()
                if user and password:
                    server.login(user, password)
                server.send_message(msg)
        app.logger.info({"event": "email.sent", "to": to_email})
        return True
    except Exception as exc:  # pragma: no cover - defensive
        app.logger.warning({"event": "email.failed", "to": to_email, "error": str(exc)})
        return False


def send_password_reset_email(to_email: str, reset_link: str, account_id: int | None = None) -> bool:
    """Send password reset email (optionally including workspace/account id)."""
    app = current_app
    host = app.config.get("SMTP_HOST")
    port = app.config.get("SMTP_PORT")
    user = app.config.get("SMTP_USER")
    password = app.config.get("SMTP_PASSWORD")
    use_tls = app.config.get("SMTP_USE_TLS", True)
    use_ssl = app.config.get("SMTP_USE_SSL", False)
    mail_from = app.config.get("MAIL_FROM", "noreply@kalevent.com")

    if not host:
        app.logger.info({"event": "email.disabled", "reason": "SMTP_HOST not configured", "to": to_email})
        return False

    msg = EmailMessage()
    msg["Subject"] = "Reset your InboxIQ password"
    msg["From"] = mail_from
    msg["To"] = to_email
    workspace_line = f"Workspace ID: {account_id}\n" if account_id is not None else ""
    workspace_html = f"<p><strong>Workspace ID:</strong> {account_id}</p>" if account_id is not None else ""

    msg.set_content(
        "Hi,\n\nWe received a request to reset your InboxIQ password.\n"
        f"{workspace_line}"
        f"Reset your password: {reset_link}\n\n"
        "If you didn't request this, you can ignore this email.\n\nThanks,\nThe Kalevent Team"
    )
    msg.add_alternative(
        f"""
        <p>Hi,</p>
        <p>We received a request to reset your InboxIQ password.</p>
        {workspace_html}
        <p><strong>Reset your password:</strong> <a href="{reset_link}">Reset Password →</a></p>
        <p>If you didn't request this, you can ignore this email.</p>
        <p>Thanks,<br/>The Kalevent Team</p>
        """,
        subtype="html",
    )

    try:
        if use_ssl:
            with smtplib.SMTP_SSL(host, port) as server:
                if user and password:
                    server.login(user, password)
                server.send_message(msg)
        else:
            with smtplib.SMTP(host, port) as server:
                if use_tls:
                    server.starttls()
                if user and password:
                    server.login(user, password)
                server.send_message(msg)
        app.logger.info({"event": "email.sent.reset", "to": to_email})
        return True
    except Exception as exc:  # pragma: no cover - defensive
        app.logger.warning({"event": "email.failed.reset", "to": to_email, "error": str(exc)})
        return False


def send_test_email(to_email: str) -> bool:
    """Send a simple test email to validate delivery. Returns True on success."""
    app = current_app
    host = app.config.get("SMTP_HOST")
    port = app.config.get("SMTP_PORT")
    user = app.config.get("SMTP_USER")
    password = app.config.get("SMTP_PASSWORD")
    use_tls = app.config.get("SMTP_USE_TLS", True)
    use_ssl = app.config.get("SMTP_USE_SSL", False)
    mail_from = app.config.get("MAIL_FROM", "noreply@kalevent.com")

    if not host:
        app.logger.info({"event": "email.disabled", "reason": "SMTP_HOST not configured", "to": to_email})
        return False

    msg = EmailMessage()
    msg["Subject"] = "InboxIQ test email"
    msg["From"] = mail_from
    msg["To"] = to_email
    msg.set_content(
        "Hi,\n\nThis is a test email from InboxIQ to validate your delivery pipeline. "
        "If you received this, your agent can ingest and triage emails.\n\nThanks,\nThe Kalevent Team"
    )
    msg.add_alternative(
        """
        <p>Hi,</p>
        <p>This is a test email from <strong>InboxIQ</strong> to validate your delivery pipeline.</p>
        <p>If you received this, your agent can ingest and triage emails.</p>
        <p>Thanks,<br/>The Kalevent Team</p>
        """,
        subtype="html",
    )

    try:
        if use_ssl:
            with smtplib.SMTP_SSL(host, port) as server:
                if user and password:
                    server.login(user, password)
                server.send_message(msg)
        else:
            with smtplib.SMTP(host, port) as server:
                if use_tls:
                    server.starttls()
                if user and password:
                    server.login(user, password)
                server.send_message(msg)
        app.logger.info({"event": "email.sent.test", "to": to_email})
        return True
    except Exception as exc:  # pragma: no cover - defensive
        app.logger.warning({"event": "email.failed.test", "to": to_email, "error": str(exc)})
        return False


def send_onboarding_reminder(to_email: str, stage: int) -> bool:
    """Send staged onboarding reminder emails (stage 1/2/3). Returns True on success."""
    app = current_app
    host = app.config.get("SMTP_HOST")
    port = app.config.get("SMTP_PORT")
    user = app.config.get("SMTP_USER")
    password = app.config.get("SMTP_PASSWORD")
    use_tls = app.config.get("SMTP_USE_TLS", True)
    use_ssl = app.config.get("SMTP_USE_SSL", False)
    mail_from = app.config.get("MAIL_FROM", "noreply@kalevent.com")

    if not host:
        app.logger.info({"event": "email.disabled", "reason": "SMTP_HOST not configured", "to": to_email})
        return False

    stage_templates = {
        1: {
          "subject": "Ready to see your AI agent triage its first email?",
          "body": (
              "You’re almost done! Connect your inbox to activate automatic triage.\n\n"
              "Connect Inbox →"
          ),
          "body_html": (
              "<p>You’re almost done! Connect your inbox to activate automatic triage.</p>"
              "<p><strong>Connect Inbox →</strong></p>"
          ),
        },
        2: {
          "subject": "Your AI Support Agent is waiting to be activated",
          "body": (
              "InboxIQ is most powerful once connected to your email.\n\n"
              "With one click, you’ll unlock:\n"
              "✓ Automatic ticket creation\n"
              "✓ Priority + sentiment detection\n"
              "✓ Faster response times\n\n"
              "Activate your agent now →"
          ),
          "body_html": (
              "<p>InboxIQ is most powerful once connected to your email.</p>"
              "<p>With one click, you’ll unlock:</p>"
              "<ul>"
              "<li>Automatic ticket creation</li>"
              "<li>Priority + sentiment detection</li>"
              "<li>Faster response times</li>"
              "</ul>"
              "<p><strong>Activate your agent now →</strong></p>"
          ),
        },
        3: {
          "subject": "Still drowning in support emails? Let’s finish setup.",
          "body": (
              "InboxIQ can eliminate 80% of your triage workload.\n\n"
              "Want help setting it up? Book a free 10-minute onboarding call.\n\n"
              "Book Onboarding →"
          ),
          "body_html": (
              "<p>InboxIQ can eliminate 80% of your triage workload.</p>"
              "<p>Want help setting it up? Book a free 10-minute onboarding call.</p>"
              "<p><strong>Book Onboarding →</strong></p>"
          ),
        },
    }

    template = stage_templates.get(stage)
    if not template:
        app.logger.warning({"event": "email.reminder.skipped", "to": to_email, "reason": f"invalid stage {stage}"})
        return False

    msg = EmailMessage()
    msg["Subject"] = template["subject"]
    msg["From"] = mail_from
    msg["To"] = to_email
    msg.set_content(template["body"])
    msg.add_alternative(template["body_html"], subtype="html")

    try:
        if use_ssl:
            with smtplib.SMTP_SSL(host, port) as server:
                if user and password:
                    server.login(user, password)
                server.send_message(msg)
        else:
            with smtplib.SMTP(host, port) as server:
                if use_tls:
                    server.starttls()
                if user and password:
                    server.login(user, password)
                server.send_message(msg)
        app.logger.info({"event": "email.sent.reminder", "to": to_email, "stage": stage})
        return True
    except Exception as exc:  # pragma: no cover - defensive
        app.logger.warning({"event": "email.failed.reminder", "to": to_email, "stage": stage, "error": str(exc)})
        return False
