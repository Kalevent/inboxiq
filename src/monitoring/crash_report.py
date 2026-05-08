import logging
import logging.handlers
import os
import socket
from typing import Optional


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
    """
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

    handler = logging.handlers.SMTPHandler(
        mailhost=(mailhost, port),
        fromaddr=from_addr,
        toaddrs=[to_addr],
        subject=subject,
        credentials=(user, password),
        secure=() if use_tls else None,
    )
    # Include message plus traceback, similar to the sample crash email.
    handler.setFormatter(
        logging.Formatter(
            "Crash occurred\n"
            "Path: %(request_path)s\n"
            "Remote: %(remote_addr)s\n\n"
            "%(message)s\n\n"
            "%(exc_text)s"
        )
    )
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

    Idempotent — calling twice for the same app does not register a duplicate
    receiver.
    """
    from celery.signals import task_failure

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
