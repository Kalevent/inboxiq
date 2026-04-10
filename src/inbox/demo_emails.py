"""
Demo email sender for newly connected inboxes.

Sends two realistic customer-style emails to a newly connected inbox
so the user sees the triage pipeline and draft replies appear within
minutes of connecting — without waiting for real customer emails.

Email 1 — a support query that gets classified as Support and receives
           a KB-grounded draft reply.
Email 2 — a scheduling request that gets classified and receives a draft
           with calendar slots injected when a calendar is connected.

Provider strategy
-----------------
Gmail   → Gmail messages.insert API (bypasses all spam/routing filters,
          lands directly in INBOX). Requires gmail.modify scope which is
          already in GOOGLE_GMAIL_SCOPES.
Outlook → SES (Microsoft is permissive enough; SES delivers reliably).
"""
import os
import logging
from email.mime.text import MIMEText
from email.utils import formatdate, make_msgid

logger = logging.getLogger(__name__)

# kalevent.com domain is SES-verified — any @kalevent.com address can send.
# These look like real customer addresses so the triage pipeline treats them
# as human-written and generates draft replies.
_DEMO_SUPPORT_FROM = "alex.chen@kalevent.com"
_DEMO_SCHEDULING_FROM = "sam.rivera@kalevent.com"

# ── Email 1 — Support query ───────────────────────────────────────────────────

_SUPPORT_SUBJECT = "Can't log in after resetting my password"

_SUPPORT_BODY = """\
Hi,

I reset my password earlier today but I'm still getting an "incorrect password" \
error when I try to sign in. I've cleared my browser cache and tried a private \
window — neither worked.

My account email is alex.chen@demoexample.com. Could you help me get back in?

Thanks,
Alex"""

# ── Email 2 — Scheduling request ─────────────────────────────────────────────

_SCHEDULING_SUBJECT = "Interested in a demo — when are you free this week?"

_SCHEDULING_BODY = """\
Hi,

I came across your product while looking for ways to reduce the time our team \
spends handling support email. We're a 14-person B2B SaaS company and our \
founder is still in the inbox every morning.

I'd love to see a quick 15-minute demo if you have time this week or next. \
Does Thursday or Friday afternoon work?

Sam Rivera
Head of Operations, Riverdale Software"""


# ── RFC2822 builder ───────────────────────────────────────────────────────────

def _build_rfc2822(
    to_email: str,
    from_email: str,
    from_name: str,
    subject: str,
    body: str,
) -> bytes:
    """Build a minimal RFC2822 message as bytes using stdlib only."""
    msg = MIMEText(body, "plain", "utf-8")
    msg["From"] = f"{from_name} <{from_email}>"
    msg["To"] = to_email
    msg["Subject"] = subject
    msg["Date"] = formatdate(localtime=False)
    msg["Message-ID"] = make_msgid(domain="kalevent.com")
    return msg.as_bytes()


# ── Gmail API injection ───────────────────────────────────────────────────────

def _inject_via_gmail_api(
    access_token: str,
    to_email: str,
    from_email: str,
    from_name: str,
    subject: str,
    body: str,
) -> bool:
    """
    Inject a message directly into the user's Gmail inbox via the Gmail API.

    Uses messages.insert (uploadType=media) which bypasses all spam and
    routing filters — the message lands in INBOX immediately with no
    deliverability risk. Requires gmail.modify scope (already granted).
    """
    import requests

    try:
        raw = _build_rfc2822(to_email, from_email, from_name, subject, body)
        resp = requests.post(
            "https://www.googleapis.com/upload/gmail/v1/users/me/messages/insert",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "message/rfc822",
            },
            params={"uploadType": "media"},
            data=raw,
            timeout=15,
        )
        if resp.status_code in (200, 201):
            return True
        logger.error(
            "Gmail API inject failed to %s: %s %s",
            to_email, resp.status_code, resp.text,
        )
        return False
    except Exception as exc:
        logger.error("Gmail API inject exception for %s: %s", to_email, exc)
        return False


# ── SES sender (Outlook / fallback) ──────────────────────────────────────────

def _send_via_ses(
    to_email: str,
    from_email: str,
    from_name: str,
    subject: str,
    body: str,
) -> bool:
    """Send a plain-text email via SES. No tracking pixel — looks like a real email."""
    import boto3
    try:
        ses = boto3.client(
            "ses",
            region_name=os.getenv("AWS_REGION", "us-west-2"),
            aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
        )
        ses.send_email(
            Source=f"{from_name} <{from_email}>",
            Destination={"ToAddresses": [to_email]},
            Message={
                "Subject": {"Data": subject, "Charset": "UTF-8"},
                "Body": {"Text": {"Data": body, "Charset": "UTF-8"}},
            },
        )
        return True
    except Exception as exc:
        logger.error("Demo email SES send failed to %s: %s", to_email, exc)
        return False


# ── Public entry point ────────────────────────────────────────────────────────

def send_demo_emails(inbox_email: str, connection_id: str) -> bool:
    """
    Send two demo emails to a newly connected inbox.

    Idempotent — checks metadata_json.demo_emails_sent before sending.
    Marks the flag after both emails are delivered.

    Provider strategy:
      gmail   → Gmail messages.insert API (guaranteed INBOX delivery, no spam risk)
      outlook → SES (delivers reliably to Outlook/Hotmail)

    Args:
        inbox_email:    The connected inbox email address (user's Gmail/Outlook).
        connection_id:  InboxConnection.id — used to read provider/token and
                        mark demo_emails_sent.

    Returns:
        True if both emails were sent (or already sent previously).
    """
    from src.extensions import db
    from src.models.core import InboxConnection

    conn = InboxConnection.query.get(connection_id)
    if not conn:
        logger.warning("send_demo_emails: connection %s not found", connection_id)
        return False

    meta = conn.metadata_json or {}
    if meta.get("demo_emails_sent"):
        logger.info(
            "send_demo_emails: already sent for connection %s, skipping", connection_id
        )
        return True

    provider = (conn.provider or "").lower()

    def _send(from_email: str, from_name: str, subject: str, body: str) -> bool:
        if provider == "gmail":
            if not conn.access_token:
                logger.error(
                    "send_demo_emails: no access_token for Gmail connection %s", connection_id
                )
                return False
            return _inject_via_gmail_api(
                conn.access_token, inbox_email, from_email, from_name, subject, body
            )
        # Outlook and any other future provider: SES
        return _send_via_ses(inbox_email, from_email, from_name, subject, body)

    ok1 = _send(_DEMO_SUPPORT_FROM, "Alex Chen", _SUPPORT_SUBJECT, _SUPPORT_BODY)
    ok2 = _send(_DEMO_SCHEDULING_FROM, "Sam Rivera", _SCHEDULING_SUBJECT, _SCHEDULING_BODY)

    if ok1 and ok2:
        meta["demo_emails_sent"] = True
        conn.metadata_json = meta
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
        logger.info(
            "send_demo_emails: both sent to %s via %s (connection %s)",
            inbox_email, provider, connection_id,
        )

    return ok1 and ok2
