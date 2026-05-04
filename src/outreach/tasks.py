"""
Celery tasks for automated email outreach campaigns.
"""
from celery import shared_task
from src.outreach.email import process_campaign_outreach, process_followup_emails
from src.models.campaigns import EmailCampaign, EmailOutreach
from src.extensions import db
from datetime import datetime, timedelta


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

        matched += 1

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise

    return {"scanned": len(open_outreaches), "replies_found": matched}
