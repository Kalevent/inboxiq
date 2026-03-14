"""
Phase 6 — Gmail native filter sync.

When a SenderProfile reaches confidence >= BYPASS_THRESHOLD (0.85), InboxIQ
pushes it as a native Gmail filter. The filter auto-labels emails from that
sender domain at delivery time — before InboxIQ even polls.

Requires the gmail.settings.basic OAuth scope. Existing connections without
the scope must reconnect before the toggle can be enabled.

Filters are tracked in InboxConnection.metadata_json["gmail_synced_filters"]
as {domain: filter_id} so we can delete and recreate when the category changes.

Gmail Settings API (requires gmail.settings.basic):
  GET    /gmail/v1/users/me/settings/filters         list
  POST   /gmail/v1/users/me/settings/filters         create
  DELETE /gmail/v1/users/me/settings/filters/{id}    delete
  (no PATCH — to update, delete and recreate)
"""
from __future__ import annotations

import logging
import requests

from src.extensions import db
from src.inbox.sender_profile import BYPASS_THRESHOLD

_log = logging.getLogger(__name__)

_GMAIL_FILTERS_URL = "https://gmail.googleapis.com/gmail/v1/users/me/settings/filters"
_SETTINGS_BASIC_SCOPE = "https://www.googleapis.com/auth/gmail.settings.basic"

# Map InboxIQ canonical categories to Gmail label names.
# These must match the names created by bootstrap_inboxiq_labels_gmail().
_CATEGORY_TO_GMAIL_LABEL = {
    "support":       "InboxIQ/Support",
    "billing":       "InboxIQ/Billing",
    "transactions":  "InboxIQ/Transactions",
    "updates":       "InboxIQ/Updates",
    "promotions":    "InboxIQ/Promotions",
    "social":        "InboxIQ/Social",
    "forums":        "InboxIQ/Forums",
    "newsletter":    "InboxIQ/Promotions",
    "notification":  "InboxIQ/Updates",
    "transactional": "InboxIQ/Transactions",
}


def has_settings_scope(conn) -> bool:
    """Return True if this connection was granted the gmail.settings.basic scope."""
    scopes = conn.scopes or []
    return _SETTINGS_BASIC_SCOPE in scopes


def sync_gmail_filters(conn) -> None:
    """
    Idempotent sync: create/delete Gmail sender filters to match
    high-confidence SenderProfiles for this account.

    Called after a user correction or when the toggle is enabled.
    Silently skips if the settings scope is not present on the connection.
    """
    from src.models.tickets import SenderProfile

    if not conn.access_token:
        return
    if not has_settings_scope(conn):
        _log.info("gmail_filters: skipping account=%s — settings.basic scope not granted", conn.account_id)
        return

    meta = dict(conn.metadata_json or {})
    label_ids: dict[str, str] = meta.get("label_ids") or {}

    if not label_ids:
        _log.info("gmail_filters: no label_ids cached for connection=%s — run bootstrap first", conn.id)
        return

    # High-confidence account-specific profiles
    profiles = SenderProfile.query.filter(
        SenderProfile.account_id == conn.account_id,
        db.or_(
            SenderProfile.confidence >= BYPASS_THRESHOLD,
            SenderProfile.user_verified.is_(True),
        ),
    ).all()

    # Build desired state: {domain: gmail_label_id}
    desired: dict[str, str] = {}
    for p in profiles:
        label_name = _CATEGORY_TO_GMAIL_LABEL.get((p.category or "").lower())
        if not label_name:
            continue
        label_id = label_ids.get(label_name)
        if not label_id:
            continue
        desired[p.domain] = label_id

    synced: dict[str, str] = meta.get("gmail_synced_filters") or {}

    # Delete filters for stale domains or where the label_id changed
    to_delete = {
        domain: fid
        for domain, fid in synced.items()
        if domain not in desired or desired[domain] != _get_filter_label_id(conn.access_token, fid)
    }
    for domain, filter_id in to_delete.items():
        try:
            _delete_gmail_filter(conn.access_token, filter_id)
            synced.pop(domain, None)
        except Exception as exc:
            _log.warning("gmail_filters: delete failed domain=%s error=%s", domain, exc)

    # Create filters for new desired domains (and re-create any just deleted)
    for domain, label_id in desired.items():
        if domain in synced:
            continue  # Already exists with correct label
        try:
            filter_id = _create_gmail_filter(conn.access_token, domain, label_id)
            if filter_id:
                synced[domain] = filter_id
        except Exception as exc:
            _log.warning("gmail_filters: create failed domain=%s error=%s", domain, exc)

    # Remove stale entries whose delete succeeded
    for domain in list(synced.keys()):
        if domain not in desired:
            synced.pop(domain, None)

    meta["gmail_synced_filters"] = synced
    conn.metadata_json = meta
    db.session.commit()

    _log.info(
        "gmail_filters sync complete: account=%s active=%d",
        conn.account_id, len(synced),
    )


def _create_gmail_filter(access_token: str, domain: str, label_id: str) -> str | None:
    """
    Create a Gmail filter: from:@domain.com → addLabel.
    Returns the filter ID or None on failure.
    """
    payload = {
        "criteria": {"from": f"@{domain}"},
        "action": {"addLabelIds": [label_id]},
    }
    resp = requests.post(
        _GMAIL_FILTERS_URL,
        headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
        json=payload,
        timeout=10,
    )
    if resp.status_code in (200, 201):
        return resp.json().get("id")
    _log.debug("create_gmail_filter %s → %s: %s", domain, resp.status_code, resp.text[:200])
    return None


def _delete_gmail_filter(access_token: str, filter_id: str) -> None:
    """Delete a Gmail filter by ID."""
    resp = requests.delete(
        f"{_GMAIL_FILTERS_URL}/{filter_id}",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=10,
    )
    if resp.status_code not in (200, 204):
        _log.debug("delete_gmail_filter %s → %s", filter_id, resp.status_code)


def _get_filter_label_id(access_token: str, filter_id: str) -> str | None:
    """
    Fetch the addLabelIds for an existing filter to check if it needs updating.
    Returns the first addLabelId or None.
    """
    try:
        resp = requests.get(
            f"{_GMAIL_FILTERS_URL}/{filter_id}",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=8,
        )
        if resp.status_code == 200:
            ids = resp.json().get("action", {}).get("addLabelIds") or []
            return ids[0] if ids else None
    except Exception:
        pass
    return None
