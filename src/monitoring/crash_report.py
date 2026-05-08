import html as _html
import logging
import logging.handlers
import os
import smtplib
import socket
from email.message import EmailMessage
from typing import Optional


class HtmlSMTPHandler(logging.handlers.SMTPHandler):
    """Logging SMTPHandler that sends a multipart text+html email so Gmail
    renders the traceback with monospace and the request context in tidy
    sections instead of as a wall of text. Subject is enriched with the
    exception class + request path so the inbox row alone tells you what
    broke.
    """

    def emit(self, record: logging.LogRecord) -> None:  # noqa: D401
        try:
            msg = EmailMessage()
            msg["From"] = self.fromaddr
            msg["To"] = ", ".join(self.toaddrs)
            msg["Subject"] = self._build_subject(record)

            fmt = self.formatter or logging.Formatter()
            traceback_text = fmt.formatException(record.exc_info) if record.exc_info else ""
            request_path = getattr(record, "request_path", "-")
            remote_addr = getattr(record, "remote_addr", "-")
            log_message = record.getMessage()
            host = socket.gethostname()

            text_body = self._render_text(host, request_path, remote_addr, log_message, traceback_text)
            html_body = self._render_html(host, request_path, remote_addr, log_message, traceback_text, record)

            msg.set_content(text_body)
            msg.add_alternative(html_body, subtype="html")

            port = self.mailport or smtplib.SMTP_PORT
            with smtplib.SMTP(self.mailhost, port, timeout=self.timeout) as server:
                if self.username:
                    if self.secure is not None:
                        server.ehlo()
                        server.starttls(*self.secure)
                        server.ehlo()
                    server.login(self.username, self.password)
                server.send_message(msg)
        except Exception:
            self.handleError(record)

    def _build_subject(self, record: logging.LogRecord) -> str:
        base = self.subject if isinstance(self.subject, str) else "Crash report from InboxIQ"
        exc_class = ""
        if record.exc_info and record.exc_info[0] is not None:
            exc_class = record.exc_info[0].__name__
        path = getattr(record, "request_path", "") or ""
        if exc_class and path and path != "-":
            return f"{base} — {exc_class} on {path}"
        if exc_class:
            return f"{base} — {exc_class}"
        if path and path != "-":
            return f"{base} — {path}"
        return base

    @staticmethod
    def _render_text(host, path, remote, message, traceback_text):
        parts = [
            "Crash occurred",
            f"Host:    {host}",
            f"Path:    {path}",
            f"Remote:  {remote}",
            "",
            str(message),
        ]
        if traceback_text:
            parts.extend(["", traceback_text])
        return "\n".join(parts)

    @staticmethod
    def _render_html(host, path, remote, message, traceback_text, record):
        exc_class = ""
        exc_msg = ""
        if record.exc_info and record.exc_info[0] is not None:
            exc_class = record.exc_info[0].__name__
            exc_msg = str(record.exc_info[1]) if record.exc_info[1] else ""

        def esc(s):
            return _html.escape(str(s)) if s is not None else ""

        rows = [
            ("Host", host),
            ("Path", path),
            ("Remote", remote),
            ("Level", record.levelname),
        ]
        if exc_class:
            rows.append(("Exception", f"{exc_class}: {exc_msg}"))

        meta_rows = "".join(
            f'<tr><td style="color:#64748b;padding:4px 12px 4px 0;font-weight:600;vertical-align:top;white-space:nowrap">{esc(k)}</td>'
            f'<td style="padding:4px 0;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;color:#0f172a;word-break:break-word">{esc(v)}</td></tr>'
            for k, v in rows
        )
        traceback_block = ""
        if traceback_text:
            traceback_block = (
                '<div style="margin-top:16px"><div style="color:#64748b;font-weight:600;margin-bottom:6px">Traceback</div>'
                f'<pre style="background:#0f172a;color:#e2e8f0;padding:14px 16px;border-radius:8px;'
                'font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12.5px;line-height:1.45;'
                f'overflow-x:auto;white-space:pre">{esc(traceback_text)}</pre></div>'
            )

        return (
            '<!doctype html><html><body style="margin:0;padding:24px;background:#f8fafc;'
            'font-family:-apple-system,BlinkMacSystemFont,Segoe UI,Roboto,sans-serif;color:#0f172a">'
            '<div style="max-width:760px;margin:0 auto;background:#fff;border:1px solid #e2e8f0;'
            'border-radius:10px;padding:20px 24px">'
            '<div style="display:flex;align-items:center;gap:8px;margin-bottom:14px">'
            '<span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:#dc2626"></span>'
            '<div style="font-size:16px;font-weight:700">InboxIQ crash report</div></div>'
            f'<table style="border-collapse:collapse;width:100%;font-size:13.5px">{meta_rows}</table>'
            '<div style="margin-top:18px"><div style="color:#64748b;font-weight:600;margin-bottom:4px">Message</div>'
            f'<div style="font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:13px;'
            f'color:#0f172a;background:#f1f5f9;padding:10px 12px;border-radius:6px;white-space:pre-wrap;word-break:break-word">{esc(message)}</div></div>'
            f'{traceback_block}'
            '</div></body></html>'
        )


def _crash_reports_enabled() -> bool:
    """Crash emails fire only in production.

    Detection (either signal is sufficient):
      - KUBERNETES_SERVICE_HOST: auto-injected into every pod by kube-dns;
        never set on a developer machine.
      - CRASH_REPORTS_ENABLED=true: explicit opt-in for non-k8s prod or
        for testing the email path deliberately.
    """
    if os.getenv("CRASH_REPORTS_ENABLED", "").lower() in ("1", "true", "yes"):
        return True
    if os.getenv("KUBERNETES_SERVICE_HOST"):
        return True
    return False


class _RequestFilter(logging.Filter):
    """Attach request path/remote to log records when a Flask request context exists."""

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: D401
        try:
            from flask import request

            record.request_path = request.path
            record.remote_addr = request.remote_addr
        except Exception:
            record.request_path = "-"
            record.remote_addr = "-"
        return True


def configure_crash_email(app):
    """
    Add an SMTPHandler that emails unhandled exceptions with a concise traceback.

    Requires env:
      SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SMTP_USE_TLS (default true), MAIL_FROM (optional)
      CRASH_EMAIL_TO (recipient)

    Production-only: a no-op unless _crash_reports_enabled() (KUBERNETES_SERVICE_HOST
    auto-injected in pods, or CRASH_REPORTS_ENABLED=true explicit opt-in). Local dev
    that loads prod.env would otherwise spam security@kalevent.com on every exception.
    """
    if not _crash_reports_enabled():
        app.logger.info("Crash email handler disabled (not in production).")
        return

    mailhost = os.getenv("SMTP_HOST")
    port = int(os.getenv("SMTP_PORT", "587"))
    user = os.getenv("SMTP_USER")
    password = os.getenv("SMTP_PASSWORD")
    use_tls = os.getenv("SMTP_USE_TLS", "true").lower() in ("1", "true", "yes")
    from_addr = os.getenv("MAIL_FROM", "noreply@kalevent.com")
    to_addr = os.getenv("CRASH_EMAIL_TO", "security@kalevent.com")
    subject = f"Crash report from InboxIQ ({socket.gethostname()})"

    if not all([mailhost, user, password, to_addr]):
        app.logger.info("Crash email handler disabled; set SMTP_HOST/SMTP_USER/SMTP_PASSWORD and CRASH_EMAIL_TO to enable.")
        return

    handler = HtmlSMTPHandler(
        mailhost=(mailhost, port),
        fromaddr=from_addr,
        toaddrs=[to_addr],
        subject=subject,
        credentials=(user, password),
        secure=() if use_tls else None,
    )
    # Formatter is only used to render the traceback string; HtmlSMTPHandler
    # builds the multipart body itself.
    handler.setFormatter(logging.Formatter("%(message)s"))
    handler.setLevel(logging.ERROR)
    handler.addFilter(_RequestFilter())

    # Avoid duplicate handlers if create_app is called multiple times.
    if not any(isinstance(h, logging.handlers.SMTPHandler) for h in app.logger.handlers):
        app.logger.addHandler(handler)


# Track registration so configure_celery_crash_email is idempotent across
# repeated imports of celery_inboxiq.py.
_celery_handler_app_ids: set = set()


def configure_celery_crash_email(app):
    """Forward Celery task_failure signals to app.logger.error.

    The SMTPHandler registered by configure_crash_email is attached to
    app.logger only. Celery tasks use logging.getLogger(__name__), so their
    crashes don't reach that handler. This bridges the gap by wiring
    task_failure into app.logger so any failed Celery task pages
    CRASH_EMAIL_TO the same way an unhandled Flask request exception does.

    Production-only: a no-op unless _crash_reports_enabled(). Same gate as
    configure_crash_email — local Celery workers running off prod.env would
    otherwise spam security@kalevent.com on every dev-time task error.

    Idempotent — calling twice for the same app does not register a duplicate
    receiver.
    """
    from celery.signals import task_failure

    if not _crash_reports_enabled():
        return

    if id(app) in _celery_handler_app_ids:
        return
    _celery_handler_app_ids.add(id(app))

    def _on_task_failure(sender=None, task_id=None, exception=None,
                         args=None, kwargs=None, traceback=None,
                         einfo=None, **_extra):
        task_name = getattr(sender, "name", None) or str(sender or "unknown")
        tb = getattr(einfo, "traceback", "") or (str(exception) if exception else "")
        app.logger.error(
            "Celery task failed: %s [task_id=%s]\nargs=%s\nkwargs=%s\n\n%s",
            task_name, task_id, args, kwargs, tb,
        )

    task_failure.connect(_on_task_failure, weak=False)
