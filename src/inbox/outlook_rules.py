"""
Phase 5 — Outlook native rule sync.

When a SenderProfile reaches confidence >= BYPASS_THRESHOLD (0.85), InboxIQ
pushes it as a native Outlook message rule. The rule auto-categorises emails
from that domain at delivery time — before InboxIQ even polls.

This means:
  - Emails from well-known senders are sorted instantly, even if InboxIQ is down.
  - Reduces DSPy calls for domains the model has already learned.

Rules are tracked in InboxConnection.metadata_json["outlook_synced_rules"]
as {domain: outlook_rule_id} so we can update or delete them later.

Graph API:
  POST   /me/mailFolders/inbox/messageRules         create
  PATCH  /me/mailFolders/inbox/messageRules/{id}    update
  DELETE /me/mailFolders/inbox/messageRules/{id}    delete
"""
from __future__ import annotations

import logging
import requests

from src.extensions import db
from src.inbox.sender_profile import BYPASS_THRESHOLD

_log = logging.getLogger(__name__)

_GRAPH_RULES_URL = "https://graph.microsoft.com/v1.0/me/mailFolders/inbox/messageRules"

# Sequence number reserved for InboxIQ rules — high enough to not interfere
# with any rules the user created manually (which typically start at 1).
_INBOXIQ_RULE_SEQUENCE = 900

# Map InboxIQ canonical categories to Outlook masterCategory display names.
# These match the names created by bootstrap_inboxiq_labels_outlook().
_CATEGORY_TO_OUTLOOK = {
    "support":      "InboxIQ/Support",
    "billing":      "InboxIQ/Billing",
    "transactions": "InboxIQ/Transactions",
    "updates":      "InboxIQ/Updates",
    "promotions":   "InboxIQ/Promotions",
    "social":       "InboxIQ/Social",
    "forums":       "InboxIQ/Forums",
    "newsletter":   "InboxIQ/Promotions",   # newsletters → Promotions
    "notification": "InboxIQ/Updates",      # automated notifications → Updates
    "transactional":"InboxIQ/Transactions",
}


def sync_outlook_rules(conn) -> None:
    """
    Idempotent sync: create/update/delete Outlook message rules to match
    high-confidence SenderProfiles for this account.

    Called after a user correction or manually via a settings toggle.
    """
    from src.models.tickets import SenderProfile

    if not conn.access_token:
        return

    # High-confidence account-specific profiles (user_verified OR high confidence)
    profiles = SenderProfile.query.filter(
        SenderProfile.account_id == conn.account_id,
        db.or_(
            SenderProfile.confidence >= BYPASS_THRESHOLD,
            SenderProfile.user_verified.is_(True),
        ),
    ).all()

    meta = dict(conn.metadata_json or {})
    synced: dict[str, str] = meta.get("outlook_synced_rules") or {}

    # Build desired state: {domain: category} for high-confidence profiles
    # that have a valid Outlook category mapping.
    desired: dict[str, str] = {}
    for p in profiles:
        outlook_cat = _CATEGORY_TO_OUTLOOK.get((p.category or "").lower())
        if outlook_cat:
            desired[p.domain] = outlook_cat

    # Create / update rules for desired domains
    for domain, outlook_cat in desired.items():
        existing_rule_id = synced.get(domain)
        try:
            if existing_rule_id:
                _update_outlook_rule(conn.access_token, existing_rule_id, domain, outlook_cat)
            else:
                rule_id = _create_outlook_rule(conn.access_token, domain, outlook_cat)
                if rule_id:
                    synced[domain] = rule_id
        except Exception as exc:
            _log.warning("outlook_rules: failed to sync domain=%s error=%s", domain, exc)

    # Delete rules for domains that dropped below confidence or were removed
    stale_domains = set(synced.keys()) - set(desired.keys())
    for domain in stale_domains:
        rule_id = synced.pop(domain, None)
        if rule_id:
            try:
                _delete_outlook_rule(conn.access_token, rule_id)
            except Exception as exc:
                _log.warning("outlook_rules: failed to delete rule_id=%s error=%s", rule_id, exc)

    meta["outlook_synced_rules"] = synced
    conn.metadata_json = meta
    db.session.commit()

    _log.info(
        "outlook_rules sync complete: account=%s created/updated=%d deleted=%d",
        conn.account_id, len(desired), len(stale_domains),
    )


def _create_outlook_rule(access_token: str, domain: str, outlook_category: str) -> str | None:
    """Create an Outlook message rule. Returns the rule ID or None on failure."""
    payload = {
        "displayName": f"InboxIQ: {domain}",
        "sequence": _INBOXIQ_RULE_SEQUENCE,
        "isEnabled": True,
        "conditions": {
            "senderContains": [f"@{domain}"],
        },
        "actions": {
            "assignCategories": [outlook_category],
        },
    }
    resp = requests.post(
        _GRAPH_RULES_URL,
        headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
        json=payload,
        timeout=10,
    )
    if resp.status_code in (200, 201):
        return resp.json().get("id")
    _log.debug("create_outlook_rule %s → %s: %s", domain, resp.status_code, resp.text[:200])
    return None


def _update_outlook_rule(access_token: str, rule_id: str, domain: str, outlook_category: str) -> None:
    """Update an existing Outlook message rule (category may have changed)."""
    payload = {
        "isEnabled": True,
        "actions": {
            "assignCategories": [outlook_category],
        },
    }
    resp = requests.patch(
        f"{_GRAPH_RULES_URL}/{rule_id}",
        headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
        json=payload,
        timeout=10,
    )
    if resp.status_code not in (200, 204):
        _log.debug("update_outlook_rule %s → %s: %s", rule_id, resp.status_code, resp.text[:200])


def _delete_outlook_rule(access_token: str, rule_id: str) -> None:
    """Delete an Outlook message rule."""
    resp = requests.delete(
        f"{_GRAPH_RULES_URL}/{rule_id}",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=10,
    )
    if resp.status_code not in (200, 204):
        _log.debug("delete_outlook_rule %s → %s: %s", rule_id, resp.status_code, resp.text[:200])
