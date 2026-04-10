"""
Background tasks for inbox intelligence pipeline.
"""
from __future__ import annotations

from celery import shared_task

from src.app import create_app


@shared_task(name="inbox.sync_gmail_filters", bind=True, max_retries=3, default_retry_delay=60)
def sync_gmail_filters_task(self, connection_id: str) -> None:
    """
    Sync high-confidence SenderProfiles as native Gmail sender filters.
    Requires gmail.settings.basic scope on the connection.
    """
    app = create_app()
    with app.app_context():
        try:
            from src.models.core import InboxConnection
            from src.inbox.gmail_filters import sync_gmail_filters

            conn = InboxConnection.query.get(connection_id)
            if not conn:
                return
            if conn.provider != "gmail" or conn.status != "connected":
                return
            meta = conn.metadata_json or {}
            if not meta.get("sync_gmail_filters"):
                return

            sync_gmail_filters(conn)

        except Exception as exc:
            raise self.retry(exc=exc)


@shared_task(name="inbox.sync_outlook_rules", bind=True, max_retries=3, default_retry_delay=60)
def sync_outlook_rules_task(self, connection_id: str) -> None:
    """
    Sync high-confidence SenderProfiles as native Outlook message rules.
    Triggered when a user correction lands or when the toggle is enabled.
    """
    app = create_app()
    with app.app_context():
        try:
            from src.models.core import InboxConnection
            from src.inbox.outlook_rules import sync_outlook_rules

            conn = InboxConnection.query.get(connection_id)
            if not conn:
                return
            if conn.provider != "outlook" or conn.status != "connected":
                return
            meta = conn.metadata_json or {}
            if not meta.get("sync_outlook_rules"):
                return

            sync_outlook_rules(conn)

        except Exception as exc:
            raise self.retry(exc=exc)


@shared_task(name="inbox.send_demo_emails", bind=True, max_retries=2, default_retry_delay=30, queue="inbox")
def send_demo_emails_task(self, connection_id: str, inbox_email: str) -> None:
    """
    Send two demo emails to a newly connected inbox.

    Triggered once after the first successful inbox connection so the user
    sees the triage pipeline and draft replies appear in Gmail within minutes.
    After both emails are sent, queues a poll with a 30-second countdown to
    give SES time to deliver to the inbox before the poll runs.
    """
    app = create_app()
    with app.app_context():
        try:
            from src.inbox.demo_emails import send_demo_emails
            sent = send_demo_emails(inbox_email=inbox_email, connection_id=connection_id)
            if sent:
                # 30s countdown — gives SES → Gmail/Outlook delivery time before poll
                trigger_demo_poll_task.apply_async(args=[connection_id], countdown=30)
        except Exception as exc:
            raise self.retry(exc=exc)


@shared_task(name="inbox.trigger_demo_poll", bind=True, max_retries=2, default_retry_delay=60, queue="inbox")
def trigger_demo_poll_task(self, connection_id: str) -> None:
    """
    Trigger an immediate inbox poll after demo emails have been delivered.

    Reuses the same poll logic as the dashboard "Poll now" button.
    Called automatically 30 seconds after send_demo_emails_task succeeds.
    """
    app = create_app()
    with app.app_context():
        try:
            from src.api.v1.inboxiq import poll_inbox_service
            poll_inbox_service(connection_id)
        except Exception as exc:
            raise self.retry(exc=exc)
