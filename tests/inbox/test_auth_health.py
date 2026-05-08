"""Tests for src/inbox/auth_health.py — auto-disable inbox connections after
N consecutive auth errors.

Production today logs an inbox.poll.auth_error every poll cycle (~5 min) for
every connection with a stale OAuth token. Two broken tokens = ~25 emails per
hour to security@. The fix: count consecutive auth errors in metadata_json and
transition InboxConnection.status to 'needs_reconnect' after the threshold.
The poll task already filters status='connected' so transitioned connections
stop being polled, which also stops the email noise.
"""
"""record_auth_error/record_poll_success are pure functions that mutate the
two attributes (metadata_json, status). Tests use a tiny stand-in struct so
they don't depend on Flask/DB setup."""


class _FakeConn:
    def __init__(self, status="connected", metadata_json=None):
        self.status = status
        self.metadata_json = metadata_json or {}


def test_first_auth_error_increments_counter_keeps_status_connected():
    from src.inbox.auth_health import record_auth_error
    conn = _FakeConn()
    transitioned = record_auth_error(conn)
    assert (conn.metadata_json or {}).get("consecutive_auth_errors") == 1
    assert conn.status == "connected", "first auth error must not disable the connection"
    assert transitioned is False


def test_third_consecutive_auth_error_transitions_to_needs_reconnect():
    from src.inbox.auth_health import record_auth_error
    conn = _FakeConn()
    record_auth_error(conn)
    record_auth_error(conn)
    assert conn.status == "connected"
    transitioned = record_auth_error(conn)
    assert (conn.metadata_json or {}).get("consecutive_auth_errors") == 3
    assert conn.status == "needs_reconnect"
    assert transitioned is True, "third error must report the disable transition"


def test_successful_poll_resets_consecutive_auth_error_counter():
    from src.inbox.auth_health import record_auth_error, record_poll_success
    conn = _FakeConn()
    record_auth_error(conn)
    record_auth_error(conn)
    assert (conn.metadata_json or {}).get("consecutive_auth_errors") == 2
    record_poll_success(conn)
    assert (conn.metadata_json or {}).get("consecutive_auth_errors") == 0


def test_subsequent_auth_error_after_disabled_does_not_re_transition():
    """Once disabled, further calls should be idempotent — no double 'transitioned'
    signals (which would fan out as duplicate emails)."""
    from src.inbox.auth_health import record_auth_error
    conn = _FakeConn()
    for _ in range(3):
        record_auth_error(conn)
    assert conn.status == "needs_reconnect"
    transitioned = record_auth_error(conn)
    assert transitioned is False
