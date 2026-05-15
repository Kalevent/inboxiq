"""
Celery tasks: async audit log writes and 14-day retention purge.
"""
import logging
from datetime import datetime, timedelta, timezone

from src.celery_inboxiq import celery
from src.extensions import db
from src.models.auth import AuditLog

log = logging.getLogger(__name__)


@celery.task(
    name="inboxiq.write_audit_entry",
    queue="inbox",
    ignore_result=True,
)
def write_audit_entry(
    account_id: int,
    user_id: int | None,
    action: str,
    resource_id: str | None,
    ip_address: str | None,
    user_agent: str | None,
    method: str | None = None,
    status_code: int | None = None,
) -> None:
    """Write one audit log row. Called from the after_request hook via .delay()."""
    try:
        metadata: dict = {}
        if method:
            metadata["method"] = method
        if status_code is not None:
            metadata["status_code"] = status_code

        entry = AuditLog(
            account_id=account_id,
            user_id=user_id,
            action=action,
            resource_type="url",
            resource_id=(resource_id or "")[:255],
            ip_address=ip_address,
            user_agent=(user_agent or "")[:300],
            metadata_json=metadata,
        )
        db.session.add(entry)
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        log.warning("write_audit_entry failed: %s", exc)


@celery.task(
    name="inboxiq.purge_old_audit_logs",
    queue="inbox",
    ignore_result=True,
)
def purge_old_audit_logs() -> None:
    """Delete audit log entries older than 14 days (rolling retention window)."""
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(days=14)
        deleted = (
            db.session.query(AuditLog)
            .filter(AuditLog.created_at < cutoff)
            .delete(synchronize_session=False)
        )
        db.session.commit()
        log.info("purge_old_audit_logs: deleted %d rows older than %s", deleted, cutoff.date())
    except Exception as exc:
        db.session.rollback()
        log.error("purge_old_audit_logs failed: %s", exc)
