"""
Celery tasks for automated email outreach campaigns.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from celery import shared_task
from src.outreach.email import process_campaign_outreach, process_followup_emails
from src.models.campaigns import EmailCampaign, EmailOutreach
from src.extensions import db
from datetime import datetime, timedelta

if TYPE_CHECKING:
    from src.models.tickets import Ticket


@shared_task(name="outreach.process_all_campaigns", queue="leads")
def process_all_campaigns(max_emails_per_campaign: int = 6):
    """Send initial outreach emails for all active campaigns. Runs daily via beat schedule."""
    campaigns = db.session.query(EmailCampaign).filter(
        EmailCampaign.status == "active",
    ).all()
    results = []
    for campaign in campaigns:
        try:
            result = process_campaign_outreach(campaign.id, max_emails=max_emails_per_campaign)
            results.append({"campaign_id": campaign.id, **result})
        except Exception as exc:
            results.append({"campaign_id": campaign.id, "error": str(exc), "sent": 0})
    return results


@shared_task(name="outreach.send_campaign_emails", bind=True, max_retries=3, queue="leads")
def send_campaign_emails(self, campaign_id: str, max_emails: int = 6):
    # Default capped at 6/week to stay within Hunter.io free plan (25/month).
    """
    Send initial outreach emails for a campaign.
    """
    try:
        results = process_campaign_outreach(campaign_id, max_emails=max_emails)
        return results
    except Exception as e:
        if self.request.retries < self.max_retries:
            raise self.retry(exc=e, countdown=300)
        return {"error": str(e), "sent": 0}


@shared_task(name="outreach.process_followups", queue="leads")
def process_followups():
    """
    Process scheduled follow-up emails for all active campaigns.
    """
    try:
        results = process_followup_emails(max_emails=50)
        return results
    except Exception as e:
        return {"error": str(e), "sent": 0}


@shared_task(name="outreach.track_email_event", queue="leads")
def track_email_event(outreach_id: str, event_type: str, timestamp: str = None):
    """
    Track email events from AWS SES.
    """
    from src.models import EmailOutreach, EmailCampaign

    try:
        outreach = db.session.query(EmailOutreach).filter(EmailOutreach.id == outreach_id).first()
        if not outreach:
            return {"error": "Outreach not found"}

        campaign = db.session.query(EmailCampaign).filter(EmailCampaign.id == outreach.campaign_id).first()
        event_time = datetime.fromisoformat(timestamp) if timestamp else datetime.now()

        if event_type == 'open':
            if not outreach.first_opened_at:
                outreach.first_opened_at = event_time
                outreach.status = 'opened'
                campaign.total_opened += 1
            outreach.open_count += 1
        elif event_type == 'click':
            if not outreach.first_clicked_at:
                outreach.first_clicked_at = event_time
                outreach.status = 'clicked'
                campaign.total_clicked += 1
            outreach.click_count += 1
        elif event_type == 'delivered':
            outreach.delivered_at = event_time
            outreach.status = 'delivered'
        elif event_type == 'replied':
            outreach.replied_at = event_time
            outreach.status = 'replied'
            campaign.total_replied += 1
            outreach.next_followup_at = None

        db.session.commit()
        return {"success": True}
    except Exception as e:
        db.session.rollback()
        return {"error": str(e)}


def _advance_lead_stage(campaign: EmailCampaign, outreach: "EmailOutreach", reply: "Ticket") -> None:
    """Advance the matching Lead to Qualified / consideration when they reply to outreach."""
    from src.models.leads import Lead, LeadFunnelStage

    lead = db.session.query(Lead).filter_by(
        account_id=campaign.account_id,
        email=outreach.recipient_email,
    ).first()
    if not lead:
        return

    now = reply.created_at or datetime.now()

    # Only advance forward — never downgrade a Qualified/Closed lead
    if lead.status in ("New Lead", "Contacted"):
        lead.status = "Qualified"

    if lead.current_funnel_stage in ("visits", "discovery"):
        lead.current_funnel_stage = "consideration"
        lead.stage_entered_at = now
        db.session.add(LeadFunnelStage(
            lead_id=lead.id,
            stage="consideration",
            sub_stage="outreach_replied",
            entered_at=now,
            notes=f"Replied to campaign: {campaign.name}",
        ))

    lead.last_engagement_at = now


def _draft_outreach_reply(
    campaign: EmailCampaign,
    outreach: "EmailOutreach",
    reply: "Ticket",
) -> str:
    """Use DSPy to draft a warm, context-aware reply to an outreach response. Returns empty string on failure."""
    try:
        from src.dspy import _configure_dspy
        import dspy as _dspy
        from src.dspy.signatures import build_outreach_reply_drafter

        _configure_dspy()
        drafter = build_outreach_reply_drafter(_dspy)
        result = drafter(
            lead_name=outreach.recipient_name or outreach.recipient_email or "there",
            campaign_name=campaign.name or "",
            original_subject=outreach.subject or "",
            reply_preview=(reply.body_preview or "").strip()[:500],
        )
        return (result.reply_text or "").strip()
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("outreach reply draft failed: %s", exc)
        return ""


def _notify_reply(campaign: EmailCampaign, outreach: "EmailOutreach", reply: "Ticket") -> None:
    """Send a plain-text SES notification to the account owner when a lead replies,
    including an AI-drafted suggested response."""
    import os
    import boto3
    from src.models.core import User

    owner = db.session.query(User).filter_by(
        account_id=campaign.account_id, role="owner"
    ).first()
    if not owner or not owner.email:
        return

    lead_email = outreach.recipient_email or ""
    lead_name = outreach.recipient_name or lead_email
    snippet = (reply.body_preview or "").strip()[:300]
    subject_line = reply.subject or "(no subject)"

    draft = _draft_outreach_reply(campaign, outreach, reply)
    draft_section = (
        f"\n--- Suggested reply (review before sending) ---\n{draft}\n"
        if draft else ""
    )

    body = (
        f"Hi {owner.name or 'there'},\n\n"
        f"{lead_name} ({lead_email}) just replied to your outreach campaign "
        f'"{campaign.name}".\n\n'
        f"Subject: {subject_line}\n"
        + (f'Their message:\n"{snippet}"\n' if snippet else "")
        + draft_section
        + "\nLog in to InboxIQ to respond:\nhttps://app.kalevent.com\n\n"
        "— InboxIQ"
    )

    try:
        ses = boto3.client(
            "ses",
            region_name=os.getenv("AWS_REGION", "eu-west-2"),
            aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
        )
        ses.send_email(
            Source="InboxIQ <hello@kalevent.com>",
            Destination={"ToAddresses": [owner.email]},
            Message={
                "Subject": {"Data": f"💬 {lead_name} replied to your outreach", "Charset": "UTF-8"},
                "Body": {"Text": {"Data": body, "Charset": "UTF-8"}},
            },
        )
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("outreach reply notification failed: %s", exc)


@shared_task(name="outreach.scan_for_replies", queue="leads")
def scan_for_replies():
    """
    Detect inbound replies by matching Ticket.from_email against EmailOutreach.recipient_email
    for the same account. Marks matched outreaches as replied and cancels their follow-ups.

    Runs periodically (every 4 hours). Only scans outreaches sent within the last 90 days
    to keep the query bounded.
    """
    from src.models.tickets import Ticket

    cutoff = datetime.now() - timedelta(days=90)

    open_outreaches = db.session.query(EmailOutreach).filter(
        EmailOutreach.status.in_(["sent", "delivered", "opened"]),
        EmailOutreach.sent_at >= cutoff,
    ).all()

    # Track (campaign_id, recipient_email) so total_replied is incremented only once per lead
    counted_pairs: set = set()
    matched = 0

    for outreach in open_outreaches:
        campaign = db.session.get(EmailCampaign, outreach.campaign_id)
        if not campaign or not campaign.account_id:
            continue

        reply = db.session.query(Ticket).filter(
            Ticket.account_id == campaign.account_id,
            Ticket.from_email == outreach.recipient_email,
            Ticket.created_at > outreach.sent_at,
        ).first()

        if not reply:
            continue

        outreach.status = "replied"
        outreach.replied_at = reply.created_at
        outreach.next_followup_at = None

        pair = (outreach.campaign_id, outreach.recipient_email)
        if pair not in counted_pairs:
            campaign.total_replied += 1
            counted_pairs.add(pair)
            _advance_lead_stage(campaign, outreach, reply)
            _notify_reply(campaign, outreach, reply)

        matched += 1

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise

    return {"scanned": len(open_outreaches), "replies_found": matched}
