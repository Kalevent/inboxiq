"""Tests for src/monitoring/crash_report.py — Celery task_failure -> email path.

The existing configure_crash_email attaches an SMTPHandler to app.logger only.
Celery tasks log to logging.getLogger(__name__), so task crashes never reach
that handler. configure_celery_crash_email closes that gap by routing
Celery's task_failure signal back into app.logger.error so the SMTPHandler
fires for any failed task.
"""
import logging
from unittest.mock import MagicMock, patch

from celery.signals import task_failure


def _make_record_with_traceback(msg="boom"):
    """Build a real LogRecord that includes exc_info, mimicking what
    app.logger.error(..., exc_info=...) produces for the SMTPHandler."""
    try:
        raise ValueError(msg)
    except ValueError:
        import sys
        exc_info = sys.exc_info()
    record = logging.LogRecord(
        name="src.app", level=logging.ERROR, pathname="x.py", lineno=1,
        msg="Exception on /api/v1/test [GET]", args=(), exc_info=exc_info,
    )
    record.request_path = "/api/v1/test"
    record.remote_addr = "1.2.3.4"
    return record


def test_html_smtp_handler_emits_multipart_with_html_alternative(monkeypatch):
    """The new handler must send a MIMEMultipart('alternative') so Gmail
    renders the HTML version with formatted sections and a monospace
    traceback. Plain text is kept as a fallback for non-HTML clients."""
    from src.monitoring.crash_report import HtmlSMTPHandler

    sent_messages = []

    class _FakeSMTP:
        def __init__(self, *a, **kw): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def ehlo(self): pass
        def starttls(self, *a, **kw): pass
        def login(self, *a, **kw): pass
        def send_message(self, msg):
            sent_messages.append(msg)

    monkeypatch.setattr("smtplib.SMTP", _FakeSMTP)

    handler = HtmlSMTPHandler(
        mailhost=("smtp.example.com", 587),
        fromaddr="noreply@kalevent.com",
        toaddrs=["security@kalevent.com"],
        subject="Crash report",
        credentials=("u", "p"),
        secure=(),
    )
    handler.emit(_make_record_with_traceback())

    assert len(sent_messages) == 1
    msg = sent_messages[0]
    assert msg.is_multipart(), "must be multipart for text+html alternatives"
    parts = list(msg.iter_parts())
    content_types = [p.get_content_type() for p in parts]
    assert "text/plain" in content_types and "text/html" in content_types


def test_html_smtp_handler_subject_includes_exception_class_and_path(monkeypatch):
    """Default subject 'Crash report from InboxIQ (...)' is too generic to
    triage without opening the email. The handler should append the
    exception class name + request path so the inbox list alone tells you
    what broke and where."""
    from src.monitoring.crash_report import HtmlSMTPHandler

    sent = []

    class _FakeSMTP:
        def __init__(self, *a, **kw): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def ehlo(self): pass
        def starttls(self, *a, **kw): pass
        def login(self, *a, **kw): pass
        def send_message(self, msg): sent.append(msg)

    monkeypatch.setattr("smtplib.SMTP", _FakeSMTP)

    handler = HtmlSMTPHandler(
        mailhost=("smtp.example.com", 587),
        fromaddr="noreply@kalevent.com",
        toaddrs=["security@kalevent.com"],
        subject="Crash report from InboxIQ (host-1)",
        credentials=("u", "p"),
        secure=(),
    )
    handler.emit(_make_record_with_traceback())

    subject = sent[0]["Subject"]
    assert "ValueError" in subject
    assert "/api/v1/test" in subject


def test_html_body_contains_traceback_in_pre_block(monkeypatch):
    """HTML body must wrap the traceback in <pre> so the indentation and
    arrow markers ('^^^^') render correctly in Gmail."""
    from src.monitoring.crash_report import HtmlSMTPHandler

    sent = []

    class _FakeSMTP:
        def __init__(self, *a, **kw): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def ehlo(self): pass
        def starttls(self, *a, **kw): pass
        def login(self, *a, **kw): pass
        def send_message(self, msg): sent.append(msg)

    monkeypatch.setattr("smtplib.SMTP", _FakeSMTP)

    handler = HtmlSMTPHandler(
        mailhost=("smtp.example.com", 587),
        fromaddr="noreply@kalevent.com",
        toaddrs=["security@kalevent.com"],
        subject="Crash",
        credentials=("u", "p"),
        secure=(),
    )
    handler.emit(_make_record_with_traceback())

    parts = list(sent[0].iter_parts())
    html_part = next(p for p in parts if p.get_content_type() == "text/html")
    html = html_part.get_content()
    assert "<pre" in html, "traceback must be inside <pre> for monospace rendering"
    assert "Traceback" in html
    assert "/api/v1/test" in html, "request path should be visible in the HTML body"
    assert "ValueError" in html


def test_configure_celery_crash_email_registers_handler_for_task_failure():
    """After calling configure_celery_crash_email(app), the celery task_failure
    signal must have a receiver hooked up. Otherwise nothing fires when a task
    crashes."""
    from src.monitoring.crash_report import configure_celery_crash_email

    app = MagicMock()
    app.logger = MagicMock()

    receivers_before = list(task_failure.receivers)
    configure_celery_crash_email(app)
    receivers_after = list(task_failure.receivers)

    assert len(receivers_after) > len(receivers_before), \
        "configure_celery_crash_email must register a task_failure receiver"


def test_celery_task_failure_signal_emits_app_logger_error_with_task_name_and_traceback():
    """When task_failure fires, app.logger.error must be called with the task
    name and traceback so the SMTPHandler attached to app.logger sends an
    email to CRASH_EMAIL_TO."""
    from src.monitoring.crash_report import configure_celery_crash_email

    app = MagicMock()
    app.logger = MagicMock()
    configure_celery_crash_email(app)

    fake_task = MagicMock()
    fake_task.name = "youtube.publish_videos"
    fake_einfo = MagicMock()
    fake_einfo.traceback = "Traceback (most recent call last):\n  File ...\nValueError: boom"

    task_failure.send(
        sender=fake_task,
        task_id="task-id-abc",
        exception=ValueError("boom"),
        args=(2,),
        kwargs={"account_id": 2},
        einfo=fake_einfo,
        traceback=None,
    )

    assert app.logger.error.called, "app.logger.error must be invoked when a celery task fails"
    rendered = " ".join(str(a) for a in app.logger.error.call_args.args) + " " + str(app.logger.error.call_args.kwargs)
    assert "youtube.publish_videos" in rendered, "task name must appear in the logged error"
    assert "ValueError: boom" in rendered or "boom" in rendered, "exception/traceback must appear in the logged error"


def test_configure_celery_crash_email_is_idempotent():
    """Calling configure_celery_crash_email twice must not register duplicate
    handlers — otherwise re-running celery_inboxiq.py at import time could
    fan out one failure into N emails."""
    from src.monitoring.crash_report import configure_celery_crash_email

    app = MagicMock()
    app.logger = MagicMock()

    configure_celery_crash_email(app)
    receivers_after_first = len(task_failure.receivers)
    configure_celery_crash_email(app)
    receivers_after_second = len(task_failure.receivers)

    assert receivers_after_first == receivers_after_second, \
        "calling configure_celery_crash_email twice must not register a second receiver"
