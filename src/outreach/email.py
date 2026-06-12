"""
Automated email outreach system using AWS SES.
Sends personalized emails to leads with tracking and automated follow-ups.
"""
import os
import re
import html as _html
import boto3
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from uuid import uuid4
from jinja2 import Template
from src.extensions import db
from src.models.campaigns import EmailCampaign, EmailOutreach
from src.models.leads import Lead


def _text_to_html(text: str) -> str:
    """Convert a plain-text email body to a minimal HTML MIME part."""
    escaped = _html.escape(text)
    # Linkify bare https:// URLs so they become clickable (and trackable).
    escaped = re.sub(
        r'(https?://[^\s<>"]+)',
        r'<a href="\1" style="color:#5B5BD6;">\1</a>',
        escaped,
    )
    paragraphs = escaped.split('\n\n')
    parts = [
        '<p style="margin:0 0 12px 0;">' + p.replace('\n', '<br>') + '</p>'
        for p in paragraphs if p.strip()
    ]
    return (
        '<div style="font-family:Arial,sans-serif;font-size:14px;line-height:1.6;color:#333333;">'
        + ''.join(parts)
        + '</div>'
    )


def _wrap_links_for_tracking(html: str, outreach_id: str, app_url: str) -> str:
    """Replace every href in the HTML with a tracked redirect URL."""
    from urllib.parse import quote

    def _replace(match):
        original_url = match.group(1)
        # Don't double-wrap tracking or unsubscribe links
        if '/outreach/track/' in original_url or '/outreach/unsubscribe/' in original_url:
            return match.group(0)
        tracked = f"{app_url}/api/v1/outreach/track/{outreach_id}/click?url={quote(original_url, safe='')}"
        return f'href="{tracked}"'

    return re.sub(r'href="(https?://[^"]+)"', _replace, html)


def get_ses_client():
    """Get AWS SES client."""
    return boto3.client(
        'ses',
        region_name=os.getenv('AWS_REGION', 'us-west-2'),
        aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
        aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY')
    )


def render_template(template_str: str, variables: Dict[str, Any]) -> str:
    """
    Render email template with personalization variables.

    Args:
        template_str: Template string with {{variable}} placeholders
        variables: Dict of variables to substitute

    Returns:
        Rendered string
    """
    template = Template(template_str)
    return template.render(**variables)


def extract_variables_from_lead(lead: Lead) -> Dict[str, Any]:
    """
    Extract personalization variables from lead object.

    Args:
        lead: Lead model instance

    Returns:
        Dict of variables for template rendering
    """
    # Extract first name from email or name
    first_name = ""
    if lead.email:
        email_username = lead.email.split('@')[0]
        name_parts = email_username.split('.')
        first_name = name_parts[0].capitalize() if name_parts else email_username.capitalize()

    # Extract company name (clean up hiring text)
    company_name = lead.company_name or ""
    if " hiring " in company_name:
        company_name = company_name.split(" hiring ")[0].strip()

    # Extract signal from notes
    signal = ""
    if lead.notes:
        signal_match = re.search(r'Discovered via buying signal: (\w+)', lead.notes)
        if signal_match:
            signal = signal_match.group(1)

    # Extract URL from notes
    url = ""
    if lead.notes:
        url_match = re.search(r'URL:\s*(https?://[^\s\n]+)', lead.notes)
        if url_match:
            url = url_match.group(1)

    return {
        "FirstName": first_name,
        "first_name": first_name.lower(),
        "CompanyName": company_name,
        "company_name": company_name,
        "Email": lead.email,
        "Signal": signal,
        "signal": signal.lower(),
        "URL": url,
        "Stage": lead.current_funnel_stage,
        # Sender fields — populated by create_outreach_for_lead from inbox owner profile
        "SenderName": "",
        "SenderTitle": "",
        "SenderCompany": "",
    }


def send_email_via_ses(
    from_email: str,
    from_name: Optional[str],
    to_email: str,
    subject: str,
    body_text: str,
    body_html: Optional[str] = None,
    tracking_pixel_url: Optional[str] = None,
    unsubscribe_url: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Send email via AWS SES.

    Args:
        from_email: Sender email address
        from_name: Sender display name
        to_email: Recipient email address
        subject: Email subject
        body_text: Plain text body
        body_html: HTML body (optional)
        tracking_pixel_url: URL for open tracking pixel (optional)

    Returns:
        Dict with success status and SES message ID
    """
    ses = get_ses_client()

    # Build source address
    source = f"{from_name} <{from_email}>" if from_name else from_email

    # Append unsubscribe footer to both body variants
    if unsubscribe_url:
        body_text = body_text + f"\n\n--\nTo stop receiving these emails: {unsubscribe_url}"
        if body_html:
            body_html += (
                '<p style="font-size:11px;color:#999999;margin-top:24px;">'
                f'To stop receiving these emails, <a href="{unsubscribe_url}" style="color:#999999;">unsubscribe here</a>.'
                '</p>'
            )

    # Add tracking pixel to HTML body
    if body_html and tracking_pixel_url:
        body_html += f'<img src="{tracking_pixel_url}" width="1" height="1" alt="" />'

    # Build message
    message = {
        'Subject': {'Data': subject, 'Charset': 'UTF-8'},
        'Body': {
            'Text': {'Data': body_text, 'Charset': 'UTF-8'}
        }
    }

    if body_html:
        message['Body']['Html'] = {'Data': body_html, 'Charset': 'UTF-8'}

    try:
        # Build send_email kwargs
        send_kwargs = {
            'Source': source,
            'Destination': {'ToAddresses': [to_email]},
            'Message': message,
        }

        # Only add ConfigurationSetName if configured (for tracking)
        config_set = os.getenv('SES_CONFIGURATION_SET')
        if config_set:
            send_kwargs['ConfigurationSetName'] = config_set

        response = ses.send_email(**send_kwargs)

        return {
            "success": True,
            "message_id": response['MessageId'],
            "error": None
        }

    except Exception as e:
        return {
            "success": False,
            "message_id": None,
            "error": str(e)
        }


def _fetch_profile_from_provider(inbox) -> dict:
    """
    Fetch sender profile fields from the connected provider API.

    Returns a dict with any of: display_name, title, company.
    On any failure returns an empty dict — callers must handle missing keys.
    """
    import requests as _req
    token = inbox.access_token
    if not token:
        return {}

    try:
        if inbox.provider == "outlook":
            resp = _req.get(
                "https://graph.microsoft.com/v1.0/me",
                headers={"Authorization": f"Bearer {token}"},
                timeout=5,
            )
            if resp.ok:
                data = resp.json()
                result = {}
                if data.get("displayName"):
                    result["display_name"] = data["displayName"]
                if data.get("jobTitle"):
                    result["title"] = data["jobTitle"]
                if data.get("companyName"):
                    result["company"] = data["companyName"]
                return result

        elif inbox.provider == "gmail":
            # sendAs returns the "From" name the user configured in Gmail settings
            resp = _req.get(
                "https://gmail.googleapis.com/gmail/v1/users/me/settings/sendAs",
                headers={"Authorization": f"Bearer {token}"},
                timeout=5,
            )
            if resp.ok:
                addresses = resp.json().get("sendAs", [])
                primary = next(
                    (a for a in addresses if a.get("isPrimary")),
                    addresses[0] if addresses else None,
                )
                if primary and primary.get("displayName"):
                    return {"display_name": primary["displayName"]}

    except Exception:
        pass

    return {}


def _populate_sender_variables(variables: Dict[str, Any], campaign: EmailCampaign) -> None:
    """Fill SenderName/SenderTitle/SenderCompany from the inbox owner's profile.

    Priority for each field:
      SenderName    — provider API display name > InboxConnection.display_name > campaign.from_name
      SenderTitle   — User.title (manual override) > provider API jobTitle (Outlook only)
      SenderCompany — Account.name > provider API companyName (Outlook only)
    """
    from src.models.core import InboxConnection, Account, User

    inbox = db.session.query(InboxConnection).filter_by(
        account_id=campaign.account_id,
        email_address=campaign.from_email,
    ).first()

    user = db.session.query(User).filter_by(
        email=campaign.from_email,
        account_id=campaign.account_id,
    ).first()

    account = db.session.get(Account, campaign.account_id)

    # Try provider API — non-blocking, empty dict on any failure
    provider_profile = _fetch_profile_from_provider(inbox) if inbox else {}

    # Cache the provider title onto User so it persists without repeated API calls
    if user and not user.title and provider_profile.get("title"):
        try:
            user.title = provider_profile["title"]
            db.session.commit()
        except Exception:
            db.session.rollback()

    variables["SenderName"] = (
        provider_profile.get("display_name")
        or (inbox.display_name if inbox else None)
        or campaign.from_name
        or ""
    )
    variables["SenderTitle"] = (
        (user.title if user and user.title else None)
        or provider_profile.get("title")
        or ""
    )
    variables["SenderCompany"] = (
        (account.name if account else None)
        or provider_profile.get("company")
        or ""
    )


def create_outreach_for_lead(
    campaign: EmailCampaign,
    lead: Lead,
    sequence_step: int = 0
) -> Optional[EmailOutreach]:
    """
    Create outreach record for a lead.

    Args:
        campaign: EmailCampaign instance
        lead: Lead instance
        sequence_step: 0=initial, 1=first follow-up, 2=second follow-up

    Returns:
        EmailOutreach instance or None if lead already contacted
    """
    # Check if lead already has outreach for this campaign
    existing = db.session.query(EmailOutreach).filter(
        EmailOutreach.campaign_id == campaign.id,
        EmailOutreach.lead_id == lead.id
    ).first()

    if existing:
        return None  # Skip duplicate

    # Extract personalization variables
    variables = extract_variables_from_lead(lead)

    # Populate sender fields from the inbox owner's profile
    _populate_sender_variables(variables, campaign)

    # Render subject and body
    subject = render_template(campaign.subject_template, variables)
    body_text = render_template(campaign.body_template, variables)
    body_html = None  # TODO: Add HTML template support

    # Create outreach record
    outreach = EmailOutreach(
        campaign_id=campaign.id,
        lead_id=lead.id,
        sequence_step=sequence_step,
        subject=subject,
        body_text=body_text,
        body_html=body_html,
        recipient_email=lead.email,
        recipient_name=variables['FirstName'],
        status='pending',
        unsubscribe_token=str(uuid4()),
    )

    db.session.add(outreach)
    db.session.flush()

    return outreach


def send_outreach_email(outreach: EmailOutreach, campaign: EmailCampaign) -> bool:
    """
    Send an outreach email via SES.

    Args:
        outreach: EmailOutreach instance
        campaign: EmailCampaign instance

    Returns:
        True if sent successfully, False otherwise
    """
    app_url = os.getenv('APP_URL', 'https://api.kalevent.com')

    # Build HTML body from text if not already set, then wrap all links for click tracking
    html_body = outreach.body_html or _text_to_html(outreach.body_text)
    html_body = _wrap_links_for_tracking(html_body, outreach.id, app_url)

    # Generate tracking pixel URL
    tracking_pixel_url = f"{app_url}/api/v1/outreach/track/{outreach.id}/open"

    # Build unsubscribe URL
    unsubscribe_url = (
        f"{app_url}/api/v1/outreach/unsubscribe/{outreach.unsubscribe_token}"
        if outreach.unsubscribe_token else None
    )

    # Send email
    result = send_email_via_ses(
        from_email=campaign.from_email,
        from_name=campaign.from_name,
        to_email=outreach.recipient_email,
        subject=outreach.subject,
        body_text=outreach.body_text,
        body_html=html_body,
        tracking_pixel_url=tracking_pixel_url,
        unsubscribe_url=unsubscribe_url,
    )

    if result['success']:
        # Update outreach status
        outreach.status = 'sent'
        outreach.ses_message_id = result['message_id']
        outreach.sent_at = datetime.now()

        # Schedule follow-up if enabled
        if campaign.follow_up_enabled and outreach.sequence_step < len(campaign.follow_up_delay_days):
            delay_days = campaign.follow_up_delay_days[outreach.sequence_step]
            outreach.next_followup_at = datetime.now() + timedelta(days=delay_days)

        # Update campaign stats
        campaign.total_sent += 1

        db.session.commit()
        return True

    else:
        # Update error status
        outreach.status = 'failed'
        outreach.error_message = result['error']
        outreach.retry_count += 1
        db.session.commit()
        return False


def process_campaign_outreach(campaign_id: str, max_emails: int = 10) -> Dict[str, Any]:
    """
    Process outreach for a campaign (send initial emails to new leads).

    Args:
        campaign_id: EmailCampaign ID
        max_emails: Maximum emails to send in this batch

    Returns:
        Dict with results summary
    """
    campaign = db.session.query(EmailCampaign).filter(EmailCampaign.id == campaign_id).first()
    if not campaign:
        return {"error": "Campaign not found"}

    if campaign.status != 'active':
        return {"error": "Campaign is not active"}

    # Check if campaign has reached max recipients
    if campaign.max_recipients and campaign.total_sent >= campaign.max_recipients:
        campaign.status = 'completed'
        campaign.completed_at = datetime.now()
        db.session.commit()
        return {"message": "Campaign completed (max recipients reached)", "sent": 0}

    # Find leads to contact — require a real, non-empty email address
    query = db.session.query(Lead).filter(
        Lead.email.isnot(None),
        Lead.email != '',
        Lead.email.contains('@'),
        Lead.outreach_unsubscribed_at.is_(None),
        ~Lead.email.startswith('contact@'),
    )

    # Apply targeting filters
    if campaign.target_funnel_stage:
        query = query.filter(Lead.current_funnel_stage == campaign.target_funnel_stage)

    if campaign.target_source:
        query = query.filter(Lead.source == campaign.target_source)

    # Exclude leads already contacted by this campaign
    contacted_lead_ids = db.session.query(EmailOutreach.lead_id).filter(
        EmailOutreach.campaign_id == campaign.id
    ).all()
    contacted_lead_ids = [lid[0] for lid in contacted_lead_ids]

    if contacted_lead_ids:
        query = query.filter(~Lead.id.in_(contacted_lead_ids))

    # Randomise order so repeated runs don't always see the same leads
    from sqlalchemy import func
    leads = query.order_by(func.random()).limit(max_emails * 3).all()[:max_emails]

    results = {
        "campaign_id": campaign_id,
        "leads_found": len(leads),
        "sent": 0,
        "failed": 0,
        "errors": []
    }

    # Send emails
    for lead in leads:
        # Check max recipients again
        if campaign.max_recipients and campaign.total_sent >= campaign.max_recipients:
            break

        # Skip leads without real, personal emails
        if not lead.email:
            continue
        email_lower = lead.email.lower()
        _bad_domains = {
            'linkedin.com', 'twitter.com', 'facebook.com', 'gmail.com',
            'yahoo.com', 'hotmail.com', 'outlook.com', 'greenhouse.io',
            'lever.co', 'indeed.com', 'glassdoor.com',
        }
        _bad_prefixes = (
            'contact@', 'info@', 'support@', 'hello@', 'admin@',
            'noreply@', 'no-reply@', 'team@', 'hr@', 'jobs@',
            'careers@', 'press@', 'sales@', 'marketing@', 'billing@',
        )
        domain = email_lower.split('@')[1] if '@' in email_lower else ''
        if domain in _bad_domains or any(email_lower.startswith(p) for p in _bad_prefixes):
            continue

        # Create outreach record
        outreach = create_outreach_for_lead(campaign, lead, sequence_step=0)
        if not outreach:
            continue

        # Send email
        success = send_outreach_email(outreach, campaign)

        if success:
            results['sent'] += 1
        else:
            results['failed'] += 1
            results['errors'].append(f"Failed to send to {lead.email}: {outreach.error_message}")

    return results


def process_followup_emails(campaign_id: Optional[str] = None, max_emails: int = 50) -> Dict[str, Any]:
    """
    Process follow-up emails for campaigns.
    Sends scheduled follow-ups for leads who haven't responded.

    Args:
        campaign_id: Optional campaign ID to process (None = all campaigns)
        max_emails: Maximum emails to send in this batch

    Returns:
        Dict with results summary
    """
    # Find outreaches due for follow-up
    query = db.session.query(EmailOutreach).filter(
        EmailOutreach.next_followup_at.isnot(None),
        EmailOutreach.next_followup_at <= datetime.now(),
        EmailOutreach.followup_sent == False,
        EmailOutreach.status.in_(['sent', 'delivered', 'opened'])  # Not replied/bounced
    )

    if campaign_id:
        query = query.filter(EmailOutreach.campaign_id == campaign_id)

    outreaches = query.limit(max_emails).all()

    results = {
        "followups_found": len(outreaches),
        "sent": 0,
        "failed": 0,
        "errors": []
    }

    for outreach in outreaches:
        campaign = db.session.query(EmailCampaign).filter(EmailCampaign.id == outreach.campaign_id).first()
        if not campaign or campaign.status != 'active':
            continue

        lead = db.session.query(Lead).filter(Lead.id == outreach.lead_id).first()
        if not lead:
            continue

        # Create new outreach for follow-up
        next_step = outreach.sequence_step + 1
        followup_outreach = create_outreach_for_lead(campaign, lead, sequence_step=next_step)

        if followup_outreach:
            success = send_outreach_email(followup_outreach, campaign)

            if success:
                # Mark original as followed up
                outreach.followup_sent = True
                db.session.commit()
                results['sent'] += 1
            else:
                results['failed'] += 1
                results['errors'].append(f"Failed follow-up to {lead.email}")

    return results


# ── ICP cold outreach templates ───────────────────────────────────────────────
# Hunter.io free plan = 25 searches/month. Cap weekly sends at 6 to stay
# safely under 25/month (6 × 4 weeks = 24).

HUNTER_FREE_MONTHLY_CAP = 25
OUTREACH_WEEKLY_CAP = 6

ICP_COLD_EMAIL_SUBJECT = "Before you hire a support manager, {{ CompanyName }}"

ICP_COLD_EMAIL_BODY = """Hi {{ FirstName }},

Quick question — how much time does {{ CompanyName }} spend each week writing the same support replies?

I ask because most founders at your stage are still handling it from Gmail, and the pattern is usually the same: 30-40% of incoming email is the same 8 questions on repeat. Password resets, billing queries, "how does X work."

InboxIQ connects to Gmail or Outlook and places a draft reply directly in the thread before you open it. You see the email, the draft is already there, you review and send. No new tool to open. No dashboard to check.

Here is what one of those threads looks like: the email arrives, InboxIQ applies a label (Support · P2), and a draft reply referencing your help docs is waiting in the thread. For a meeting request, available calendar slots are included in the draft — no Calendly link needed.

Takes 2 minutes to connect your inbox and see it live: https://kalevent.com/signup?utm_source=outreach&utm_medium=email&utm_campaign=icp_cold

Or if you would rather see it on a real inbox first — happy to do a 15-minute walkthrough.

- {{ SenderName }}
{{ SenderTitle }}
{{ SenderCompany }}"""

ICP_COLD_EMAIL_FOLLOWUP = """Hi {{ FirstName }},

Following up briefly.

If support email is still eating into your mornings — connect your inbox here and see it working in under 2 minutes: https://kalevent.com/signup?utm_source=outreach&utm_medium=email&utm_campaign=icp_cold_followup

If the timing is not right, no problem at all.

- {{ SenderName }}
{{ SenderTitle }}"""


def get_icp_cold_outreach_templates() -> dict:
    """
    Returns subject, body, and follow-up for ICP cold outreach.
    Designed for Hunter.io free plan: 25 searches/month, 6 emails/week.
    """
    return {
        "subject": ICP_COLD_EMAIL_SUBJECT,
        "body": ICP_COLD_EMAIL_BODY,
        "followup": ICP_COLD_EMAIL_FOLLOWUP,
        "weekly_cap": OUTREACH_WEEKLY_CAP,
        "monthly_cap": HUNTER_FREE_MONTHLY_CAP,
    }
