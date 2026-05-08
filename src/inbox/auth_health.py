"""Track consecutive OAuth auth errors per InboxConnection.

When a Gmail/Outlook connection's OAuth token expires, every poll cycle (~5
min) raises a 401, which fires a crash-report email. Without this module that
fans out to ~12 emails per hour per broken connection, drowning the alert
channel. Once the threshold is hit we transition the connection to
'needs_reconnect' — the poll task filters by status='connected' so disabled
connections stop being polled, which also stops the noise.
"""
from __future__ import annotations

AUTH_ERROR_THRESHOLD = 3
META_KEY = "consecutive_auth_errors"


def record_auth_error(conn) -> bool:
    """Increment the consecutive-auth-error counter on the connection.

    Returns True if THIS call caused the transition to 'needs_reconnect'
    (so the caller can fire a single notification). Returns False if the
    counter just incremented without crossing the threshold, or if the
    connection was already disabled.
    """
    meta = dict(conn.metadata_json or {})
    if conn.status == "needs_reconnect":
        # Already disabled — keep the counter monotonic for diagnostics but
        # don't signal a fresh transition (the caller should not re-fire alerts).
        meta[META_KEY] = int(meta.get(META_KEY, 0)) + 1
        conn.metadata_json = meta
        return False

    new_count = int(meta.get(META_KEY, 0)) + 1
    meta[META_KEY] = new_count
    conn.metadata_json = meta

    if new_count >= AUTH_ERROR_THRESHOLD:
        conn.status = "needs_reconnect"
        return True
    return False


def record_poll_success(conn) -> None:
    """Reset the consecutive-auth-error counter after a successful poll."""
    meta = dict(conn.metadata_json or {})
    if meta.get(META_KEY):
        meta[META_KEY] = 0
        conn.metadata_json = meta
