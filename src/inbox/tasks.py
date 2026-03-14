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
