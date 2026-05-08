"""Tests for src/monitoring/crash_report.py — Celery task_failure -> email path.

The existing configure_crash_email attaches an SMTPHandler to app.logger only.
Celery tasks log to logging.getLogger(__name__), so task crashes never reach
that handler. configure_celery_crash_email closes that gap by routing
Celery's task_failure signal back into app.logger.error so the SMTPHandler
fires for any failed task.
"""
from unittest.mock import MagicMock, patch

from celery.signals import task_failure


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
