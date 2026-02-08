"""
Celery tasks for automated email outreach campaigns.
"""
from celery import shared_task
from src.email_outreach import process_campaign_outreach, process_followup_emails
from src.models import EmailCampaign
from src.extensions import db
from datetime import datetime


@shared_task(name="outreach.send_campaign_emails", bind=True, max_retries=3, queue="leads")
def send_campaign_emails(self, campaign_id: str, max_emails: int = 10):
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
