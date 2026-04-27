import smtplib
from email.message import EmailMessage
from typing import Optional

from flask import current_app


def send_inbox_invite_email(to_email: str, accept_link: str, inviter_name: str, provider: str = "gmail") -> bool:
    """Send an inbox connect invite to a third party (e.g. Oliver's wife's Gmail)."""
    app = current_app
    host = app.config.get("SMTP_HOST")
    port = app.config.get("SMTP_PORT")
    user = app.config.get("SMTP_USER")
    password = app.config.get("SMTP_PASSWORD")
    use_tls = app.config.get("SMTP_USE_TLS", True)
    use_ssl = app.config.get("SMTP_USE_SSL", False)
    mail_from = app.config.get("MAIL_FROM", "noreply@kalevent.com")

    provider_label = "Gmail" if provider == "gmail" else "Outlook"

    if not host:
        app.logger.info({"event": "email.disabled", "reason": "SMTP_HOST not configured", "to": to_email, "accept_link": accept_link})
        return False

    msg = EmailMessage()
    msg["Subject"] = f"{inviter_name} wants to connect your {provider_label} inbox to InboxIQ"
    msg["From"] = mail_from
    msg["To"] = to_email
    msg.set_content(
        f"Hi,\n\n{inviter_name} has set up InboxIQ to help manage email.\n\n"
        f"To connect your {provider_label} inbox, click the link below. "
        f"You'll be taken directly to {provider_label} — no InboxIQ account required.\n\n"
        f"Connect your inbox: {accept_link}\n\n"
        f"This link expires in 72 hours.\n\n"
        f"If you didn't expect this email, you can ignore it.\n\nThanks,\nThe InboxIQ Team"
    )
    msg.add_alternative(
        f"""
        <div style="font-family:-apple-system,sans-serif;max-width:520px;margin:0 auto;padding:24px">
          <h2 style="color:#1e293b;font-size:20px">Connect your {provider_label} inbox</h2>
          <p style="color:#475569">{inviter_name} has set up InboxIQ to help manage email.</p>
          <p style="color:#475569">
            Click the button below to connect your {provider_label} inbox.
            You'll be taken directly to {provider_label} — <strong>no InboxIQ account required</strong>.
          </p>
          <p style="margin:28px 0">
            <a href="{accept_link}"
               style="display:inline-block;background:#4f46e5;color:#fff;padding:12px 24px;
                      border-radius:8px;text-decoration:none;font-weight:600;font-size:15px">
              Connect your {provider_label} inbox →
            </a>
          </p>
          <p style="color:#94a3b8;font-size:13px">This link expires in 72 hours. If you didn't expect this email, you can ignore it.</p>
          <hr style="border:none;border-top:1px solid #e2e8f0;margin:24px 0">
          <p style="color:#94a3b8;font-size:12px">InboxIQ by Kalevent</p>
        </div>
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
        app.logger.info({"event": "email.sent.inbox_invite", "to": to_email})
        return True
    except Exception as exc:
        app.logger.warning({"event": "email.failed.inbox_invite", "to": to_email, "error": str(exc)})
        return False


def send_content_review_email(
    to_email: str,
    title: str,
    slug: str,
    content_preview: str,
    seo_score: str,
    word_count: int,
    readability_score: str,
    blog_url: str
) -> bool:
    """Send content review email with generated blog post details."""
    app = current_app
    host = app.config.get("SMTP_HOST")
    port = app.config.get("SMTP_PORT")
    user = app.config.get("SMTP_USER")
    password = app.config.get("SMTP_PASSWORD")
    use_tls = app.config.get("SMTP_USE_TLS", True)
    use_ssl = app.config.get("SMTP_USE_SSL", False)
    mail_from = app.config.get("MAIL_FROM", "noreply@kalevent.com")

    if not host:
        app.logger.info({
            "event": "email.disabled",
            "reason": "SMTP_HOST not configured",
            "to": to_email
        })
        return False

    # Truncate content preview
    preview = content_preview[:500] + "..." if len(content_preview) > 500 else content_preview

    msg = EmailMessage()
    msg["Subject"] = f"📝 New Blog Post Published: {title}"
    msg["From"] = mail_from
    msg["To"] = to_email
    msg.set_content(
        f"""
Hi,

A new blog post has been auto-published by the Content Generation Agent:

Title: {title}
URL: {blog_url}
Word Count: {word_count}
SEO Score: {seo_score}/100
Readability: {readability_score}/100

Content Preview:
{preview}

Review the full post and suggest improvements by replying to this email.

Thanks,
Content Generation Agent
        """.strip()
    )
    msg.add_alternative(
        f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <h2 style="color: #4F46E5;">📝 New Blog Post Published</h2>

            <p>A new blog post has been auto-published by the Content Generation Agent:</p>

            <div style="background: #F3F4F6; padding: 20px; border-radius: 8px; margin: 20px 0;">
                <h3 style="margin-top: 0; color: #111827;">{title}</h3>

                <div style="margin: 15px 0;">
                    <strong>URL:</strong> <a href="{blog_url}" style="color: #4F46E5;">{blog_url}</a>
                </div>

                <div style="display: flex; gap: 20px; margin: 15px 0;">
                    <div><strong>Word Count:</strong> {word_count}</div>
                    <div><strong>SEO Score:</strong> {seo_score}/100</div>
                    <div><strong>Readability:</strong> {readability_score}/100</div>
                </div>
            </div>

            <div style="background: #FFFBEB; border-left: 4px solid #F59E0B; padding: 15px; margin: 20px 0;">
                <h4 style="margin-top: 0; color: #92400E;">Content Preview</h4>
                <p style="color: #78350F; white-space: pre-wrap;">{preview}</p>
            </div>

            <p>
                <a href="{blog_url}"
                   style="display: inline-block; background: #4F46E5; color: white; padding: 12px 24px;
                          text-decoration: none; border-radius: 6px; margin-top: 10px;">
                    View Full Post →
                </a>
            </p>

            <p style="color: #6B7280; font-size: 14px; margin-top: 30px;">
                <strong>Suggest Improvements:</strong> Reply to this email with your feedback and I'll optimize the content accordingly.
            </p>

            <hr style="border: none; border-top: 1px solid #E5E7EB; margin: 30px 0;">

            <p style="color: #9CA3AF; font-size: 12px;">
                Generated by Content Generation Agent (DSPy-powered)<br>
                Funnel v2.0 | InboxIQ
            </p>
        </div>
        """,
        subtype="html"
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
        return True
    except Exception as exc:
        app.logger.exception("Failed to send content review email: %s", exc)
        return False


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


def send_enterprise_onboarding_notification(
    to_emails: list[str],
    inquiry_name: str,
    inquiry_email: str,
    inquiry_company: str,
    account_id: int | None,
) -> bool:
    """
    Email the engineering/admin team with the kubectl command to activate
    an Enterprise account after a deal is closed.
    """
    app = current_app
    host = app.config.get("SMTP_HOST")
    port = app.config.get("SMTP_PORT")
    user = app.config.get("SMTP_USER")
    password = app.config.get("SMTP_PASSWORD")
    use_tls = app.config.get("SMTP_USE_TLS", True)
    use_ssl = app.config.get("SMTP_USE_SSL", False)
    mail_from = app.config.get("MAIL_FROM", "noreply@kalevent.com")

    if not host:
        app.logger.info({"event": "email.disabled", "reason": "SMTP_HOST not configured"})
        return False

    if account_id:
        command = (
            f"kubectl exec <web-pod> -n kaley -c inboxiq -- "
            f"flask --app src.manage:app set-enterprise-account --account-id {account_id}"
        )
        account_line = f"Account ID: {account_id}"
    else:
        command = (
            "Account not yet created. Look up account by email below, then run:\n"
            "kubectl exec <web-pod> -n kaley -c inboxiq -- "
            "flask --app src.manage:app set-enterprise-account --account-id <ID>"
        )
        account_line = "Account ID: not linked yet (look up by email)"

    body = f"""Enterprise deal approved — action required.

Customer: {inquiry_name}
Email:    {inquiry_email}
Company:  {inquiry_company}
{account_line}

Run this command to activate their Enterprise plan:

  {command}

Then run seed-plans first if you haven't already:
  kubectl exec <web-pod> -n kaley -c inboxiq -- flask --app src.manage:app seed-plans

---
Sent by InboxIQ admin panel.
"""
    body_html = f"""
<p><strong>Enterprise deal approved — action required.</strong></p>
<table style="border-collapse:collapse;font-family:monospace">
  <tr><td style="padding:2px 12px 2px 0"><strong>Customer</strong></td><td>{inquiry_name}</td></tr>
  <tr><td style="padding:2px 12px 2px 0"><strong>Email</strong></td><td>{inquiry_email}</td></tr>
  <tr><td style="padding:2px 12px 2px 0"><strong>Company</strong></td><td>{inquiry_company or "—"}</td></tr>
  <tr><td style="padding:2px 12px 2px 0"><strong>Account ID</strong></td><td>{account_id or "not linked yet"}</td></tr>
</table>
<p>Run this command to activate their Enterprise plan:</p>
<pre style="background:#f4f4f4;padding:12px;border-radius:4px">{command}</pre>
<hr>
<p style="color:#888;font-size:12px">Sent by InboxIQ admin panel.</p>
"""

    msg = EmailMessage()
    msg["Subject"] = f"🚀 Enterprise Activation: {inquiry_name} ({inquiry_company or inquiry_email})"
    msg["From"] = mail_from
    msg["To"] = ", ".join(to_emails)
    msg.set_content(body)
    msg.add_alternative(body_html, subtype="html")

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
        app.logger.info({"event": "email.sent.enterprise_onboarding", "to": to_emails})
        return True
    except Exception as exc:
        app.logger.warning({"event": "email.failed.enterprise_onboarding", "error": str(exc)})
        return False


def send_enterprise_value_report_email(
    to_email: str,
    account_name: str,
    month_label: str,
    ai_decisions: int,
    hours_saved: float,
    value_gbp: float,
) -> bool:
    """
    Monthly value report email sent to Enterprise accounts showing ROI
    delivered in the previous month.
    """
    app = current_app
    host = app.config.get("SMTP_HOST")
    port = app.config.get("SMTP_PORT")
    user = app.config.get("SMTP_USER")
    password = app.config.get("SMTP_PASSWORD")
    use_tls = app.config.get("SMTP_USE_TLS", True)
    use_ssl = app.config.get("SMTP_USE_SSL", False)
    mail_from = app.config.get("MAIL_FROM", "noreply@kalevent.com")

    if not host:
        app.logger.info({"event": "email.disabled", "reason": "SMTP_HOST not configured"})
        return False

    hours_str = f"{hours_saved:,.1f}"
    value_str = f"£{value_gbp:,.0f}"
    decisions_str = f"{ai_decisions:,}"

    body = f"""Hi {account_name},

Here's your InboxIQ value summary for {month_label}:

  Emails handled by AI:  {decisions_str}
  Estimated hours saved: {hours_str} hrs
  Estimated value:       {value_str}

This is the time your team didn't spend manually triaging, categorising,
and drafting replies — InboxIQ handled it automatically.

If you have questions or want to explore expanding your usage, reply to
this email and we'll get back to you.

— The InboxIQ Team
"""
    body_html = f"""
<div style="font-family:sans-serif;max-width:520px;margin:0 auto;padding:24px">
  <h2 style="color:#1e293b">Your InboxIQ Monthly Summary</h2>
  <p style="color:#475569">{month_label} — {account_name}</p>

  <div style="display:flex;gap:16px;margin:24px 0">
    <div style="flex:1;background:#f0f9ff;border-radius:8px;padding:20px;text-align:center">
      <div style="font-size:2rem;font-weight:700;color:#0369a1">{decisions_str}</div>
      <div style="color:#64748b;font-size:0.85rem;margin-top:4px">Emails handled by AI</div>
    </div>
    <div style="flex:1;background:#f0fdf4;border-radius:8px;padding:20px;text-align:center">
      <div style="font-size:2rem;font-weight:700;color:#15803d">{hours_str} hrs</div>
      <div style="color:#64748b;font-size:0.85rem;margin-top:4px">Hours saved</div>
    </div>
    <div style="flex:1;background:#fefce8;border-radius:8px;padding:20px;text-align:center">
      <div style="font-size:2rem;font-weight:700;color:#a16207">{value_str}</div>
      <div style="color:#64748b;font-size:0.85rem;margin-top:4px">Estimated value</div>
    </div>
  </div>

  <p style="color:#475569">This is the time your team didn't spend manually triaging,
  categorising, and drafting replies — InboxIQ handled it automatically.</p>

  <p style="color:#475569">Questions or want to expand usage?
  <a href="mailto:support@kalevent.com">Reply to this email</a> and we'll get back to you.</p>

  <hr style="border:none;border-top:1px solid #e2e8f0;margin:24px 0">
  <p style="color:#94a3b8;font-size:12px">
    InboxIQ by Kalevent · <a href="https://inboxiq.kalevent.com/settings" style="color:#94a3b8">Manage notifications</a>
  </p>
</div>
"""

    msg = EmailMessage()
    msg["Subject"] = f"InboxIQ saved your team {hours_str} hours in {month_label} — {value_str} value"
    msg["From"] = mail_from
    msg["To"] = to_email
    msg.set_content(body)
    msg.add_alternative(body_html, subtype="html")

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
        app.logger.info({"event": "email.sent.enterprise_value_report", "to": to_email, "month": month_label})
        return True
    except Exception as exc:
        app.logger.warning({"event": "email.failed.enterprise_value_report", "to": to_email, "error": str(exc)})
        return False


def send_linkedin_digest(to_email: str, prospects: list[dict], date_label: str) -> bool:
    """
    Send the daily LinkedIn outreach digest email.

    Each prospect dict must have:
        name, company_name, job_title, linkedin_url, action_label,
        msg_draft, prospect_id
    Optional keys:
        suggested_post_title, suggested_post_url, match_reason
    """
    app = current_app
    host = app.config.get("SMTP_HOST")
    if not host:
        app.logger.info({"event": "email.disabled", "reason": "SMTP_HOST not configured"})
        return False

    if not prospects:
        return False

    port = app.config.get("SMTP_PORT")
    user = app.config.get("SMTP_USER")
    password = app.config.get("SMTP_PASSWORD")
    use_tls = app.config.get("SMTP_USE_TLS", True)
    use_ssl = app.config.get("SMTP_USE_SSL", False)
    mail_from = app.config.get("MAIL_FROM", "noreply@kalevent.com")
    base_url = app.config.get("BASE_URL", "https://kalevent.com")

    subject = f"LinkedIn Outreach — {len(prospects)} action{'s' if len(prospects) != 1 else ''} ready ({date_label})"

    sections_html = []
    sections_text = []

    for p in prospects:
        advance_url = f"{base_url}/marketing/linkedin/advance/{p['prospect_id']}"
        post_html = ""
        post_text = ""
        if p.get("suggested_post_title"):
            post_html = (
                f"<p style='margin:4px 0;font-size:13px;color:#94a3b8;'>"
                f"Sharing: <a href='{p['suggested_post_url']}' style='color:#818cf8;'>{p['suggested_post_title']}</a>"
                f"<br><em>{p.get('match_reason', '')}</em></p>"
            )
            post_text = f"\nSharing: {p['suggested_post_title']} ({p['suggested_post_url']})\nWhy: {p.get('match_reason', '')}"

        sections_html.append(f"""
<div style="border:1px solid #1e293b;border-radius:8px;padding:16px;margin-bottom:16px;background:#0f172a;">
  <p style="margin:0 0 4px;font-weight:600;font-size:15px;color:#f1f5f9;">{p['name']} &middot; {p['job_title']} &middot; {p['company_name']}</p>
  <p style="margin:0 0 8px;font-size:12px;"><a href="{p['linkedin_url']}" style="color:#818cf8;">{p['linkedin_url']}</a></p>
  <p style="margin:0 0 8px;font-size:13px;font-weight:500;color:#e2e8f0;">Action: {p['action_label']}</p>
  {post_html}
  <div style="background:#1e293b;border-radius:6px;padding:12px;margin:8px 0;font-size:13px;color:#cbd5e1;font-style:italic;">
    {p['msg_draft'].replace(chr(10), '<br>')}
  </div>
  <a href="{advance_url}" style="display:inline-block;background:#6366f1;color:#fff;text-decoration:none;padding:6px 14px;border-radius:6px;font-size:13px;font-weight:500;">Mark as sent &rarr;</a>
</div>""")

        sections_text.append(
            f"\n{'─'*60}\n"
            f"{p['name']} · {p['job_title']} · {p['company_name']}\n"
            f"{p['linkedin_url']}\n\n"
            f"Action: {p['action_label']}{post_text}\n\n"
            f"{p['msg_draft']}\n\n"
            f"Mark as sent: {advance_url}\n"
        )

    html_body = f"""<!DOCTYPE html><html><body style="background:#020617;color:#f1f5f9;font-family:sans-serif;padding:24px;max-width:640px;margin:0 auto;">
<h2 style="color:#818cf8;margin-bottom:4px;">LinkedIn Outreach</h2>
<p style="color:#94a3b8;margin-top:0;">{len(prospects)} action{'s' if len(prospects) != 1 else ''} ready &mdash; {date_label}</p>
{''.join(sections_html)}
<p style="font-size:11px;color:#475569;margin-top:24px;">Manage your queue: <a href="{base_url}/marketing/linkedin" style="color:#818cf8;">{base_url}/marketing/linkedin</a></p>
</body></html>"""

    text_body = f"LinkedIn Outreach — {len(prospects)} actions ready — {date_label}\n{''.join(sections_text)}"

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = mail_from
    msg["To"] = to_email
    msg.set_content(text_body)
    msg.add_alternative(html_body, subtype="html")

    try:
        if use_ssl:
            with smtplib.SMTP_SSL(host, port) as smtp:
                if user and password:
                    smtp.login(user, password)
                smtp.send_message(msg)
        else:
            with smtplib.SMTP(host, port) as smtp:
                if use_tls:
                    smtp.starttls()
                if user and password:
                    smtp.login(user, password)
                smtp.send_message(msg)
        app.logger.info({"event": "email.sent.linkedin_digest", "to": to_email, "count": len(prospects)})
        return True
    except Exception as exc:
        app.logger.warning({"event": "email.failed.linkedin_digest", "to": to_email, "error": str(exc)})
        return False
