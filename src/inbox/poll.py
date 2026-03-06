"""
Inbox polling utilities for InboxIQ.

Gmail uses the Gmail REST API (with OAuth2 access/refresh token).
Outlook/others still fall back to IMAP with the provided password/token.
"""
from __future__ import annotations

import imaplib
import email
from email.header import decode_header
from typing import Any, Dict, List
import requests
import base64

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
        body = ""

        # Try to extract plain text body from parts
        def _walk_parts(part):
            ctype = part.get("mimeType")
            if ctype == "text/plain" and part.get("body", {}).get("data"):
                import base64

                try:
                    return base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8", errors="ignore")
                except Exception:
                    return ""
            for p in part.get("parts") or []:
                val = _walk_parts(p)
                if val:
                    return val
            return ""

        body = _walk_parts(payload.get("payload", {})) or snippet

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
            }
        )

    return messages, new_token


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
    create_resp = requests.post(
        "https://gmail.googleapis.com/gmail/v1/users/me/labels",
        headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
        json={"name": label_name, "labelListVisibility": "labelShow", "messageListVisibility": "show"},
        timeout=8,
    )
    if create_resp.status_code not in (200, 201):
        raise ValueError(f"Gmail label create failed: {create_resp.status_code} {create_resp.text}")
    return create_resp.json()["id"]


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
    """
    import email as email_lib
    from email.mime.text import MIMEText

    msg = MIMEText(body, "plain", "utf-8")
    msg["To"] = to_email
    msg["Subject"] = subject if subject.lower().startswith("re:") else f"Re: {subject}"
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

    # Update the draft body
    patch_resp = requests.patch(
        f"https://graph.microsoft.com/v1.0/me/messages/{draft_id}",
        headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
        json={"body": {"contentType": "Text", "content": body}},
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
            "$select": "subject,from,bodyPreview,body,receivedDateTime,conversationId,internetMessageId",
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
