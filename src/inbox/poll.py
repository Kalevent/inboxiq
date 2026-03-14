"""
Inbox polling utilities for InboxIQ.

Gmail uses the Gmail REST API (with OAuth2 access/refresh token).
Outlook/others still fall back to IMAP with the provided password/token.
"""
from __future__ import annotations

import imaplib
import email
import logging
from email.header import decode_header
from typing import Any, Dict, List
import requests
import base64

_log = logging.getLogger(__name__)

# Email types that are non-actionable (no draft reply).
_NON_ACTIONABLE_EMAIL_TYPES = {
    "spam", "marketing", "newsletter", "transactional",
    "auto_reply", "out_of_office", "promotional", "notification",
    "updates", "promotions", "social", "forums",
}


def _should_draft(reply_text: str | None, email_type: str | None, is_automated: bool) -> bool:
    if not reply_text:
        return False
    if is_automated:
        return False
    if (email_type or "").lower() in _NON_ACTIONABLE_EMAIL_TYPES:
        return False
    return True


def writeback_to_provider(
    provider: str | None,
    provider_message_id: str | None,
    provider_thread_id: str | None,
    access_token: str,
    label_cache: dict,
    category: str,
    priority: str,
    reply_text: str | None,
    from_email: str,
    subject: str,
    email_type: str | None = None,
    is_automated: bool = False,
) -> dict:
    """
    Apply an InboxIQ label and optional draft reply to a provider message.

    Args:
        label_cache: mutable dict (conn.metadata_json["label_ids"]) — updated in-place
                     when a new label is created so the caller can persist it.

    Returns:
        {"label_applied": bool, "draft_created": bool}
    """
    if not provider or provider not in ("gmail", "outlook") or not provider_message_id:
        return {"label_applied": False, "draft_created": False}

    _cat = category.title()
    label_name = f"InboxIQ/{_cat}/Urgent" if priority == "P1" else f"InboxIQ/{_cat}"
    draft_needed = _should_draft(reply_text, email_type, is_automated)

    label_applied = False
    draft_created = False
    _log.info(
        "writeback: provider=%s category=%s priority=%s email_type=%s is_automated=%s "
        "reply_text_present=%s draft_needed=%s thread_id=%s",
        provider, category, priority, email_type, is_automated,
        bool(reply_text), draft_needed, bool(provider_thread_id),
    )
    try:
        if provider == "gmail":
            label_id = label_cache.get(label_name)
            if not label_id:
                label_id = ensure_gmail_label(access_token, label_name)
                label_cache[label_name] = label_id
            apply_label_gmail(access_token, provider_message_id, label_id)
            label_applied = True
            if draft_needed and provider_thread_id:
                create_gmail_draft_reply(access_token, provider_thread_id, from_email, subject, reply_text)
                draft_created = True
                _log.info("draft reply created: thread_id=%s subject=%s", provider_thread_id, subject)
        elif provider == "outlook":
            apply_label_outlook(access_token, provider_message_id, label_name)
            label_applied = True
            if draft_needed:
                create_outlook_draft_reply(access_token, provider_message_id, reply_text)
                draft_created = True
    except Exception as exc:
        _log.warning(
            "writeback_to_provider failed: provider=%s error=%s", provider, exc
        )

    return {"label_applied": label_applied, "draft_created": draft_created}

IMAP_HOSTS = {
    "gmail": "imap.gmail.com",
    "outlook": "outlook.office365.com",
}

IMAP_PORT = 993


def _decode(value):
    if not value:
        return ""
    if isinstance(value, bytes):
        try:
            return value.decode()
        except Exception:
            try:
                return value.decode("utf-8", errors="ignore")
            except Exception:
                return ""
    return str(value)


def _decode_header(value: Any) -> str:
    if not value:
        return ""
    decoded = decode_header(value)
    parts = []
    for text, charset in decoded:
        if isinstance(text, bytes):
            try:
                parts.append(text.decode(charset or "utf-8", errors="ignore"))
            except Exception:
                parts.append(text.decode("utf-8", errors="ignore"))
        else:
            parts.append(text)
    return " ".join(parts)


def _gmail_refresh_access_token(refresh_token: str, client_id: str, client_secret: str) -> str:
    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": client_id,
        "client_secret": client_secret,
    }
    resp = requests.post("https://oauth2.googleapis.com/token", data=data, timeout=10)
    resp.raise_for_status()
    payload = resp.json()
    return payload.get("access_token")


def _extract_header(headers: list[dict], name: str) -> str:
    name_lower = name.lower()
    for h in headers or []:
        if (h.get("name") or "").lower() == name_lower:
            return h.get("value") or ""
    return ""


def fetch_label_changes_gmail(
    access_token: str,
    start_history_id: str,
) -> tuple[list[dict], str | None]:
    """
    Use the Gmail History API to fetch all label additions since start_history_id.

    Returns (changed_messages, new_history_id).
    Each item: {"provider_message_id": str, "provider_label_ids": list[str]}
    where provider_label_ids are the CURRENT labels on the message at time of change.

    Returns ([], None) on any error — non-fatal, corrections are best-effort.
    """
    try:
        resp = requests.get(
            "https://gmail.googleapis.com/gmail/v1/users/me/history",
            headers={"Authorization": f"Bearer {access_token}"},
            params={
                "startHistoryId": start_history_id,
                "historyTypes": "labelAdded",
                "maxResults": 100,
            },
            timeout=10,
        )
        if resp.status_code == 404:
            # historyId expired (>7 days old) — reset by returning None for new_history_id
            return [], None
        if resp.status_code != 200:
            _log.debug("gmail history fetch %s: %s", resp.status_code, resp.text[:200])
            return [], None

        data = resp.json()
        new_history_id: str | None = data.get("historyId")

        # Collect the current label set per changed message (deduplicated by provider_message_id)
        changed: dict[str, list[str]] = {}
        for record in data.get("history") or []:
            for label_change in record.get("labelsAdded") or []:
                msg = label_change.get("message") or {}
                mid = msg.get("id")
                if not mid:
                    continue
                # message.labelIds = ALL current labels on the message (not just the added ones)
                label_ids = msg.get("labelIds") or []
                changed[mid] = label_ids  # last write wins; that's fine

        result = [
            {"provider_message_id": mid, "provider_label_ids": label_ids, "provider": "gmail"}
            for mid, label_ids in changed.items()
        ]
        return result, new_history_id

    except Exception as exc:
        _log.debug("fetch_label_changes_gmail non-fatal: %s", exc)
        return [], None


def fetch_messages_gmail(
    access_token: str,
    refresh_token: str | None,
    client_id: str | None,
    client_secret: str | None,
    limit: int = 5,
) -> tuple[list[Dict[str, Any]], str | None]:
    """
    Fetch latest messages from Gmail using the Gmail API.
    Returns (messages, new_access_token_if_refreshed).
    """
    if not access_token:
        raise ValueError("Missing Gmail access token")

    def _auth_header(token: str) -> dict:
        return {"Authorization": f"Bearer {token}"}

    def _list_messages(token: str) -> requests.Response:
        params = {"maxResults": limit, "labelIds": "INBOX"}
        return requests.get(
            "https://gmail.googleapis.com/gmail/v1/users/me/messages",
            headers=_auth_header(token),
            params=params,
            timeout=10,
        )

    # Try list; refresh once on 401 if we can.
    resp = _list_messages(access_token)
    new_token = None
    if resp.status_code == 401 and refresh_token and client_id and client_secret:
        try:
            new_token = _gmail_refresh_access_token(refresh_token, client_id, client_secret)
            resp = _list_messages(new_token)
        except Exception:
            pass

    if resp.status_code != 200:
        raise ValueError(f"Gmail list failed: {resp.status_code} {resp.text}")

    data = resp.json()
    msg_ids = [m.get("id") for m in data.get("messages", []) if m.get("id")]
    messages: list[Dict[str, Any]] = []

    for mid in msg_ids:
        detail = requests.get(
            f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{mid}",
            headers=_auth_header(new_token or access_token),
            params={"format": "full"},
            timeout=10,
        )
        if detail.status_code != 200:
            continue
        payload = detail.json()
        headers = payload.get("payload", {}).get("headers", [])
        subject = _extract_header(headers, "Subject") or "(no subject)"
        from_email = _extract_header(headers, "From")
        message_id = _extract_header(headers, "Message-ID") or mid
        snippet = payload.get("snippet") or ""
        thread_id = payload.get("threadId")
        body = _walk_parts_plain(payload.get("payload", {})) or snippet

        # Fetch prior messages in the thread for full conversation context
        thread_history = []
        if thread_id:
            try:
                thread_history = fetch_thread_history_gmail(
                    new_token or access_token, thread_id, mid
                )
            except Exception:
                pass

        messages.append(
            {
                "subject": subject,
                "from_email": from_email,
                "body": body,
                "message_id": message_id.strip("<>"),
                "provider_message_id": mid,
                "provider_thread_id": thread_id,
                "provider": "gmail",
                "provider_thread_url": f"https://mail.google.com/mail/u/0/#inbox/{thread_id}" if thread_id else None,
                "history": thread_history,
                # Label IDs currently on the message — used for ClassificationCorrection detection
                "provider_label_ids": payload.get("labelIds") or [],
            }
        )

    return messages, new_token


def fetch_thread_history_gmail(
    access_token: str,
    thread_id: str,
    current_message_id: str,
    max_messages: int = 6,
) -> List[Dict[str, Any]]:
    """
    Fetch the prior messages in a Gmail thread, excluding the current message.

    Returns a list (oldest-first) of dicts:
      { from_email, body, received_at, is_outbound }

    is_outbound=True means Oliver sent it (it has label SENT).
    Capped at max_messages to keep token counts manageable.
    """
    try:
        resp = requests.get(
            f"https://gmail.googleapis.com/gmail/v1/users/me/threads/{thread_id}",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"format": "full"},
            timeout=10,
        )
        if resp.status_code != 200:
            return []
        thread_data = resp.json()
    except Exception:
        return []

    history = []
    for msg in thread_data.get("messages", []):
        mid = msg.get("id") or ""
        if mid == current_message_id:
            continue
        headers = msg.get("payload", {}).get("headers", [])
        from_email = _extract_header(headers, "From")
        date_str = _extract_header(headers, "Date")
        label_ids = msg.get("labelIds") or []
        is_outbound = "SENT" in label_ids

        body = _walk_parts_plain(msg.get("payload", {})) or msg.get("snippet", "")
        history.append({
            "from_email": from_email,
            "body": body[:300],  # Keep brief to limit token count
            "received_at": date_str,
            "is_outbound": is_outbound,
        })

    # Return oldest-first, capped at max_messages
    return history[-max_messages:]


def fetch_thread_history_outlook(
    access_token: str,
    conversation_id: str,
    current_message_id: str,
    max_messages: int = 6,
) -> List[Dict[str, Any]]:
    """
    Fetch prior messages in an Outlook conversation, excluding the current message.

    Returns a list (oldest-first) of dicts:
      { from_email, body, received_at, is_outbound }
    """
    try:
        resp = requests.get(
            "https://graph.microsoft.com/v1.0/me/messages",
            headers={"Authorization": f"Bearer {access_token}"},
            params={
                "$filter": f"conversationId eq '{conversation_id}'",
                "$select": "id,from,body,receivedDateTime,isDraft",
                "$orderby": "receivedDateTime asc",
                "$top": max_messages + 1,
            },
            timeout=10,
        )
        if resp.status_code != 200:
            return []
        data = resp.json()
    except Exception:
        return []

    history = []
    for msg in data.get("value", []):
        if msg.get("id") == current_message_id or msg.get("isDraft"):
            continue
        from_addr = (msg.get("from") or {}).get("emailAddress") or {}
        from_email = from_addr.get("address") or from_addr.get("name") or ""
        body_content = (msg.get("body") or {}).get("content") or ""
        # Strip HTML tags crudely — full HTML is too noisy for the LLM
        import re as _re
        body_text = _re.sub(r"<[^>]+>", " ", body_content).strip()
        received_at = msg.get("receivedDateTime") or ""
        history.append({
            "from_email": from_email,
            "body": body_text[:300],
            "received_at": received_at,
            "is_outbound": False,  # Graph doesn't cleanly flag sent in this query
        })

    return history[-max_messages:]


def _walk_parts_plain(payload: dict) -> str:
    """Recursively extract plain text body from a Gmail message payload."""
    ctype = payload.get("mimeType", "")
    if ctype == "text/plain":
        data = (payload.get("body") or {}).get("data")
        if data:
            try:
                return base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
            except Exception:
                return ""
    for part in payload.get("parts") or []:
        result = _walk_parts_plain(part)
        if result:
            return result
    return ""


def apply_label_gmail(access_token: str, message_id: str, label: str, mark_read: bool = False):
    """
    Apply a label to a Gmail message. Best-effort; failures bubble to caller.
    """
    ops = {"addLabelIds": [label]}
    if mark_read:
        ops["removeLabelIds"] = ["UNREAD"]
    resp = requests.post(
        f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{message_id}/modify",
        headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
        json=ops,
        timeout=5,
    )
    if resp.status_code >= 300:
        raise ValueError(f"Gmail label failed: {resp.status_code} {resp.text}")
    return True


def apply_label_outlook(access_token: str, message_id: str, category: str, mark_read: bool = False):
    """
    Apply an Outlook category to a message and optionally mark as read.
    Requires Mail.ReadWrite permission.
    """
    payload = {"categories": [category]}
    if mark_read:
        payload["isRead"] = True
    resp = requests.patch(
        f"https://graph.microsoft.com/v1.0/me/messages/{message_id}",
        headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
        json=payload,
        timeout=8,
    )
    if resp.status_code >= 300:
        raise ValueError(f"Outlook label failed: {resp.status_code} {resp.text}")
    return True


def fetch_gmail_labels(access_token: str) -> list[dict]:
    """
    Return all user-created Gmail labels as a list of {id, name} dicts.
    System labels (INBOX, SENT, TRASH, SPAM, CATEGORY_*, IMPORTANT, etc.)
    are excluded — we only want labels Oliver created himself.
    """
    resp = requests.get(
        "https://gmail.googleapis.com/gmail/v1/users/me/labels",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=8,
    )
    if resp.status_code != 200:
        return []
    return [
        {"id": lbl["id"], "name": lbl["name"]}
        for lbl in resp.json().get("labels", [])
        if lbl.get("type") == "user"
    ]


# Canonical InboxIQ labels — created in every user's inbox on first connection.
# Uses Gmail's `/` nesting syntax so all labels appear grouped under a collapsible
# "InboxIQ" section in the Gmail sidebar, making InboxIQ's presence immediately visible.
INBOXIQ_CANONICAL_LABELS: list[str] = [
    "InboxIQ/Support",
    "InboxIQ/Support/Urgent",
    "InboxIQ/Billing",
    "InboxIQ/Billing/Urgent",
    "InboxIQ/Transactions",
    "InboxIQ/Updates",
    "InboxIQ/Promotions",
    "InboxIQ/Social",
    "InboxIQ/Forums",
]

# Explicitly deprecated label names — always deleted during bootstrap regardless of version.
# Add old names here whenever a canonical label is renamed.
_INBOXIQ_DEPRECATED_LABELS: list[str] = [
    "InboxIQ/Billing-P1",       # renamed to InboxIQ/Billing in v3
    "InboxIQ · Support",        # old dot-separator format from before nested labels
    "InboxIQ · Billing · P1",
    "InboxIQ · Transactions",
    "InboxIQ · Updates",
    "InboxIQ · Promotions",
]

# Gmail label colors — must use Gmail's predefined hex palette.
# backgroundColor is the chip color; textColor is the label text.
_GMAIL_LABEL_COLOURS: dict[str, dict] = {
    "InboxIQ/Support":              {"backgroundColor": "#4a86e8", "textColor": "#ffffff"},  # blue
    "InboxIQ/Support/Urgent":       {"backgroundColor": "#cc3a21", "textColor": "#ffffff"},  # deep red — urgent
    "InboxIQ/Billing":              {"backgroundColor": "#fb4c2f", "textColor": "#ffffff"},  # red
    "InboxIQ/Billing/Urgent":       {"backgroundColor": "#cc3a21", "textColor": "#ffffff"},  # deep red — urgent
    "InboxIQ/Transactions": {"backgroundColor": "#16a766", "textColor": "#ffffff"},  # green
    "InboxIQ/Updates":      {"backgroundColor": "#ffad47", "textColor": "#ffffff"},  # amber
    "InboxIQ/Promotions":   {"backgroundColor": "#a479e2", "textColor": "#ffffff"},  # purple
    "InboxIQ/Social":       {"backgroundColor": "#6d9eeb", "textColor": "#ffffff"},  # light blue — mirrors Gmail's Social tab
    "InboxIQ/Forums":       {"backgroundColor": "#f691b3", "textColor": "#ffffff"},  # pink — mirrors Gmail's Forums tab
}

# Outlook colour presets — Graph API requires "presetN" values, not colour names.
# preset0=red, preset4=green, preset5=teal, preset7=blue, preset8=purple,
# preset9=cranberry, preset1=orange
_OUTLOOK_LABEL_COLOURS: dict[str, str] = {
    "InboxIQ/Support":          "preset7",   # blue
    "InboxIQ/Support/Urgent":   "preset0",   # red — urgent
    "InboxIQ/Billing":          "preset15",  # dark red
    "InboxIQ/Billing/Urgent":   "preset0",   # red — urgent
    "InboxIQ/Transactions":     "preset4",   # green
    "InboxIQ/Updates":          "preset1",   # orange
    "InboxIQ/Promotions":       "preset8",   # purple
    "InboxIQ/Social":           "preset5",   # teal
    "InboxIQ/Forums":           "preset9",   # cranberry
}


def bootstrap_inboxiq_labels_gmail(access_token: str) -> dict[str, str]:
    """
    Ensure all InboxIQ canonical labels exist in Gmail with colours applied.
    Labels are nested under 'InboxIQ/' so Gmail groups them as a collapsible
    section in the sidebar — immediately visible and identifiable.
    Returns {label_name: label_id} for all canonical labels.
    """
    resp = requests.get(
        "https://gmail.googleapis.com/gmail/v1/users/me/labels",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=8,
    )
    existing: dict[str, str] = {}
    if resp.status_code == 200:
        for lbl in resp.json().get("labels", []):
            key = lbl["name"].lower()
            existing[key] = lbl["id"]

    # Step 1: Delete explicitly deprecated labels by name — these are known old names.
    deprecated_lower = {n.lower(): n for n in _INBOXIQ_DEPRECATED_LABELS}
    for dep_lower, dep_original in deprecated_lower.items():
        label_id = existing.get(dep_lower)
        if label_id:
            dr = requests.delete(
                f"https://gmail.googleapis.com/gmail/v1/users/me/labels/{label_id}",
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=5,
            )
            if dr.status_code not in (200, 204, 404):
                import logging as _logging
                _logging.getLogger(__name__).warning(
                    "gmail label delete failed: label=%s status=%s", dep_original, dr.status_code
                )

    # Step 2: Delete any other stale top-level InboxIQ/* labels not in the canonical set.
    canonical_lower = {n.lower() for n in INBOXIQ_CANONICAL_LABELS}
    for name_lower, label_id in list(existing.items()):
        if (name_lower.startswith("inboxiq/")
                and name_lower.count("/") == 1
                and name_lower not in canonical_lower
                and name_lower not in deprecated_lower):  # already handled above
            requests.delete(
                f"https://gmail.googleapis.com/gmail/v1/users/me/labels/{label_id}",
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=5,
            )

    result: dict[str, str] = {}
    for label_name in INBOXIQ_CANONICAL_LABELS:
        key = label_name.lower()
        colour = _GMAIL_LABEL_COLOURS.get(label_name)
        if key in existing:
            label_id = existing[key]
            result[label_name] = label_id
            # Patch colour if we have a preset (idempotent — Gmail ignores unchanged values)
            if colour:
                try:
                    requests.patch(
                        f"https://gmail.googleapis.com/gmail/v1/users/me/labels/{label_id}",
                        headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
                        json={"color": colour},
                        timeout=5,
                    )
                except Exception:
                    pass
        else:
            try:
                body: dict = {
                    "name": label_name,
                    "labelListVisibility": "labelShow",
                    "messageListVisibility": "show",
                }
                if colour:
                    body["color"] = colour
                cr = requests.post(
                    "https://gmail.googleapis.com/gmail/v1/users/me/labels",
                    headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
                    json=body,
                    timeout=8,
                )
                if cr.status_code in (200, 201):
                    result[label_name] = cr.json()["id"]
            except Exception:
                pass

    return result


# Gmail filter queries that map Gmail's native ML category tabs to InboxIQ labels.
# These filters fire on new mail arrival — independent of InboxIQ polling — so the
# label appears in the Gmail sidebar even before InboxIQ's next poll cycle.
_GMAIL_CATEGORY_FILTERS: list[tuple[str, str]] = [
    ("category:promotions", "InboxIQ/Promotions"),
    ("category:social",     "InboxIQ/Social"),
    ("category:updates",    "InboxIQ/Updates"),
    ("category:forums",     "InboxIQ/Forums"),
    ("category:purchases",  "InboxIQ/Transactions"),
]


def bootstrap_gmail_filters(access_token: str, label_ids: dict[str, str]) -> None:
    """
    Create Gmail filters that automatically apply InboxIQ labels based on
    Gmail's native ML category tabs (Social, Promotions, Updates, Forums, Purchases).

    Idempotent — fetches existing filters first and skips any that are already
    configured for a given InboxIQ label so re-runs don't create duplicates.

    Args:
        access_token: Valid Gmail OAuth access token
        label_ids: {label_name: gmail_label_id} from bootstrap_inboxiq_labels_gmail
    """
    import logging as _logging
    _log = _logging.getLogger(__name__)

    # Fetch existing filters to avoid duplicates
    existing_resp = requests.get(
        "https://gmail.googleapis.com/gmail/v1/users/me/settings/filters",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=8,
    )
    existing_label_ids: set[str] = set()
    if existing_resp.status_code == 200:
        for f in existing_resp.json().get("filter", []):
            for lid in (f.get("action", {}).get("addLabelIds") or []):
                existing_label_ids.add(lid)

    for query, label_name in _GMAIL_CATEGORY_FILTERS:
        label_id = label_ids.get(label_name)
        if not label_id:
            continue
        if label_id in existing_label_ids:
            continue  # Filter already exists for this label
        try:
            resp = requests.post(
                "https://gmail.googleapis.com/gmail/v1/users/me/settings/filters",
                headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
                json={
                    "criteria": {"query": query},
                    "action": {"addLabelIds": [label_id]},
                },
                timeout=8,
            )
            if resp.status_code not in (200, 201):
                _log.warning("gmail filter create failed: query=%s label=%s status=%s", query, label_name, resp.status_code)
        except Exception as exc:
            _log.warning("gmail filter create error: query=%s error=%s", query, exc)


def bootstrap_inboxiq_labels_outlook(access_token: str) -> dict[str, str]:
    """
    Ensure all InboxIQ canonical categories exist in Outlook.
    Creates any that are missing; skips ones that already exist.
    Returns {label_name: category_id} for all canonical categories.
    """
    resp = requests.get(
        "https://graph.microsoft.com/v1.0/me/outlook/masterCategories",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=8,
    )
    existing: dict[str, str] = {}
    if resp.status_code == 200:
        existing = {
            cat["displayName"].lower(): cat["id"]
            for cat in resp.json().get("value", [])
        }

    result: dict[str, str] = {}
    for label_name in INBOXIQ_CANONICAL_LABELS:
        key = label_name.lower()
        colour = _OUTLOOK_LABEL_COLOURS.get(label_name, "none")
        if key in existing:
            cat_id = existing[key]
            result[label_name] = cat_id
            # Patch colour — idempotent, fixes categories created before preset values were correct
            try:
                requests.patch(
                    f"https://graph.microsoft.com/v1.0/me/outlook/masterCategories/{cat_id}",
                    headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
                    json={"color": colour},
                    timeout=8,
                )
            except Exception:
                pass
        else:
            try:
                cr = requests.post(
                    "https://graph.microsoft.com/v1.0/me/outlook/masterCategories",
                    headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
                    json={"displayName": label_name, "color": colour},
                    timeout=8,
                )
                if cr.status_code in (200, 201):
                    result[label_name] = cr.json()["id"]
            except Exception:
                pass

    return result


def fetch_outlook_categories(access_token: str) -> list[dict]:
    """
    Return all user-created Outlook categories as a list of {id, name} dicts.
    Uses the Graph API masterCategories endpoint — these are the categories
    the user has defined in Outlook, equivalent to Gmail labels.
    """
    resp = requests.get(
        "https://graph.microsoft.com/v1.0/me/outlook/masterCategories",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=8,
    )
    if resp.status_code != 200:
        return []
    return [
        {"id": cat["id"], "name": cat["displayName"]}
        for cat in resp.json().get("value", [])
        if cat.get("displayName")
    ]


def ensure_gmail_label(access_token: str, label_name: str) -> str:
    """
    Return the Gmail label ID for label_name, creating it if it doesn't exist.
    Caches nothing — callers should store label IDs in InboxConnection.metadata_json.
    """
    resp = requests.get(
        "https://gmail.googleapis.com/gmail/v1/users/me/labels",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=8,
    )
    if resp.status_code == 200:
        for lbl in resp.json().get("labels", []):
            if lbl.get("name", "").lower() == label_name.lower():
                return lbl["id"]
    # Label doesn't exist — create it
    _body: dict = {"name": label_name, "labelListVisibility": "labelShow", "messageListVisibility": "show"}
    _colour = _GMAIL_LABEL_COLOURS.get(label_name)
    if _colour:
        _body["color"] = _colour
    create_resp = requests.post(
        "https://gmail.googleapis.com/gmail/v1/users/me/labels",
        headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
        json=_body,
        timeout=8,
    )
    if create_resp.status_code not in (200, 201):
        raise ValueError(f"Gmail label create failed: {create_resp.status_code} {create_resp.text}")
    return create_resp.json()["id"]


_INBOXIQ_FOOTER_HTML = (
    '<br><hr style="border:none;border-top:1px solid #e5e7eb;margin:20px 0">'
    '<p style="color:#9ca3af;font-size:11px;margin:0;font-family:sans-serif">'
    '&#9889; Drafted by <strong>InboxIQ</strong> &middot; Review before sending'
    '</p>'
)
_INBOXIQ_FOOTER_TEXT = "\n\n--\nDrafted by InboxIQ · Review before sending"


def create_gmail_draft_reply(
    access_token: str,
    thread_id: str,
    to_email: str,
    subject: str,
    body: str,
) -> str:
    """
    Create a draft reply in the Gmail thread. Returns the new draft ID.
    The draft appears collapsed under the thread — Oliver clicks to expand, review, and send.
    Sent as multipart/alternative (plain + HTML) so the InboxIQ attribution footer
    is visible but unobtrusive, confirming to Oliver that this draft is AI-generated.
    """
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    subject_header = subject if subject.lower().startswith("re:") else f"Re: {subject}"

    msg = MIMEMultipart("alternative")
    msg["To"] = to_email
    msg["Subject"] = subject_header

    # Plain-text part — always included for non-HTML clients
    plain_body = body + _INBOXIQ_FOOTER_TEXT
    msg.attach(MIMEText(plain_body, "plain", "utf-8"))

    # HTML part — preferred by Gmail; body lines → <p> blocks, attribution footer appended
    html_paragraphs = "".join(
        f"<p>{line}</p>" if line.strip() else "<br>"
        for line in body.splitlines()
    )
    html_body = f"<div style=\"font-family:sans-serif;font-size:14px;line-height:1.6\">{html_paragraphs}{_INBOXIQ_FOOTER_HTML}</div>"
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")

    resp = requests.post(
        "https://gmail.googleapis.com/gmail/v1/users/me/drafts",
        headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
        json={"message": {"threadId": thread_id, "raw": raw}},
        timeout=10,
    )
    if resp.status_code not in (200, 201):
        raise ValueError(f"Gmail draft create failed: {resp.status_code} {resp.text}")
    return resp.json()["id"]


def create_outlook_draft_reply(
    access_token: str,
    message_id: str,
    body: str,
) -> str:
    """
    Create a draft reply to an Outlook message via Microsoft Graph.
    Returns the new draft message ID.
    """
    resp = requests.post(
        f"https://graph.microsoft.com/v1.0/me/messages/{message_id}/createReply",
        headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
        json={},
        timeout=10,
    )
    if resp.status_code not in (200, 201):
        raise ValueError(f"Outlook createReply failed: {resp.status_code} {resp.text}")
    draft_id = resp.json().get("id")

    # Update the draft body — use HTML so the attribution footer renders correctly
    html_paragraphs = "".join(
        f"<p>{line}</p>" if line.strip() else "<br>"
        for line in body.splitlines()
    )
    html_body = (
        f"<div style=\"font-family:sans-serif;font-size:14px;line-height:1.6\">"
        f"{html_paragraphs}{_INBOXIQ_FOOTER_HTML}</div>"
    )
    patch_resp = requests.patch(
        f"https://graph.microsoft.com/v1.0/me/messages/{draft_id}",
        headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
        json={"body": {"contentType": "HTML", "content": html_body}},
        timeout=10,
    )
    if patch_resp.status_code >= 300:
        raise ValueError(f"Outlook draft update failed: {patch_resp.status_code} {patch_resp.text}")
    return draft_id


def _ms_refresh_access_token(refresh_token: str, client_id: str, client_secret: str, tenant_id: str | None) -> str:
    tenant = tenant_id or "common"
    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": client_id,
        "client_secret": client_secret,
        "scope": "https://graph.microsoft.com/.default offline_access",
    }
    resp = requests.post(f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token", data=data, timeout=10)
    resp.raise_for_status()
    payload = resp.json()
    return payload.get("access_token")


def fetch_category_changes_outlook(
    access_token: str,
    modified_since: str,
) -> tuple[list[dict], str]:
    """
    Fetch Outlook messages whose categories changed since modified_since.

    Uses Graph API $filter=lastModifiedDateTime gt <iso> — the Outlook equivalent
    of Gmail's History API. Catches corrections on already-triaged messages that
    would never appear in the normal top-N poll.

    Returns (changed_messages, new_since_timestamp).
    Each item: {"provider_message_id": str, "provider_categories": list[str], "provider": "outlook"}

    Returns ([], now_iso) on any error — non-fatal, corrections are best-effort.
    """
    from datetime import datetime, timezone as _tz
    now_iso = datetime.now(_tz.utc).isoformat()
    try:
        resp = requests.get(
            "https://graph.microsoft.com/v1.0/me/messages",
            headers={"Authorization": f"Bearer {access_token}"},
            params={
                "$filter": f"lastModifiedDateTime gt {modified_since}",
                "$select": "id,categories,internetMessageId",
                "$top": 100,
                "$orderby": "lastModifiedDateTime desc",
            },
            timeout=10,
        )
        if resp.status_code != 200:
            _log.debug("outlook category changes %s: %s", resp.status_code, resp.text[:200])
            return [], now_iso

        changed = []
        for msg in resp.json().get("value") or []:
            mid = msg.get("id")
            if mid:
                changed.append({
                    "provider_message_id": mid,
                    "provider_categories": msg.get("categories") or [],
                    "provider": "outlook",
                })
        return changed, now_iso

    except Exception as exc:
        _log.debug("fetch_category_changes_outlook non-fatal: %s", exc)
        return [], now_iso


def fetch_messages_outlook(
    access_token: str,
    refresh_token: str | None,
    client_id: str | None,
    client_secret: str | None,
    tenant_id: str | None,
    limit: int = 5,
) -> tuple[list[Dict[str, Any]], str | None]:
    """
    Fetch latest messages from Outlook via Microsoft Graph.
    Returns (messages, new_access_token_if_refreshed).
    """
    if not access_token:
        raise ValueError("Missing Outlook access token")

    def _auth_header(token: str) -> dict:
        return {"Authorization": f"Bearer {token}"}

    def _list_messages(token: str) -> requests.Response:
        params = {
            "$top": limit,
            "$select": "subject,from,bodyPreview,body,receivedDateTime,conversationId,internetMessageId,categories",
            "$orderby": "receivedDateTime desc",
        }
        return requests.get(
            "https://graph.microsoft.com/v1.0/me/messages",
            headers=_auth_header(token),
            params=params,
            timeout=10,
        )

    resp = _list_messages(access_token)
    new_token = None
    if resp.status_code == 401 and refresh_token and client_id and client_secret:
        try:
            new_token = _ms_refresh_access_token(refresh_token, client_id, client_secret, tenant_id)
            resp = _list_messages(new_token)
        except Exception:
            pass

    if resp.status_code != 200:
        raise ValueError(f"Outlook list failed: {resp.status_code} {resp.text}")

    data = resp.json()
    items = data.get("value") or []
    messages: list[Dict[str, Any]] = []

    for m in items:
        subject = m.get("subject") or "(no subject)"
        from_obj = (m.get("from") or {}).get("emailAddress") or {}
        from_email = from_obj.get("address") or ""
        message_id = (m.get("internetMessageId") or m.get("id") or "").strip("<>")
        snippet = m.get("bodyPreview") or ""
        body_content = (m.get("body") or {}).get("content") or snippet
        conv_id = m.get("conversationId")

        # Fetch prior messages in the conversation for full context
        thread_history = []
        if conv_id:
            try:
                thread_history = fetch_thread_history_outlook(
                    new_token or access_token, conv_id, m.get("id", "")
                )
            except Exception:
                pass

        messages.append(
            {
                "subject": subject,
                "from_email": from_email,
                "body": body_content,
                "message_id": message_id,
                "provider_message_id": m.get("id"),
                "provider_thread_id": conv_id,
                "provider": "outlook",
                "provider_thread_url": f"https://outlook.office.com/mail/inbox/id/{conv_id}" if conv_id else None,
                "history": thread_history,
                "provider_categories": m.get("categories") or [],
            }
        )

    return messages, new_token


def fetch_messages_imap(provider: str, email_address: str, password: str, limit: int = 5) -> List[Dict[str, Any]]:
    host = IMAP_HOSTS.get(provider)
    if not host:
        raise ValueError(f"IMAP not configured for provider {provider}")
    mail = imaplib.IMAP4_SSL(host, IMAP_PORT)
    mail.login(email_address, password)
    mail.select("INBOX")
    status, data = mail.search(None, "UNSEEN")
    if status != "OK":
        return []
    ids = data[0].split()
    # take last N message IDs
    ids = ids[-limit:]
    messages: List[Dict[str, Any]] = []
    for msg_id in ids:
        status, msg_data = mail.fetch(msg_id, "(RFC822)")
        if status != "OK" or not msg_data:
            continue
        raw_email = msg_data[0][1]
        msg = email.message_from_bytes(raw_email)
        subject = _decode_header(msg.get("Subject", ""))
        from_email = _decode_header(msg.get("From", ""))
        message_id = msg.get("Message-ID") or f"{provider}-{msg_id.decode()}"

        body = ""
        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get("Content-Disposition") or "")
                if content_type == "text/plain" and "attachment" not in content_disposition:
                    try:
                        body = part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", errors="ignore")
                    except Exception:
                        body = part.get_payload()
                    break
        else:
            try:
                body = msg.get_payload(decode=True).decode(msg.get_content_charset() or "utf-8", errors="ignore")
            except Exception:
                body = msg.get_payload()

        messages.append(
            {
                "subject": subject or "(no subject)",
                "from_email": from_email or email_address,
                "body": body or "",
                "message_id": message_id.strip("<>"),
                "provider": provider,
            }
        )
    try:
        mail.close()
    except Exception:
        pass
    mail.logout()
    return messages
