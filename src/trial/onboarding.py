"""
Trial onboarding email sequence automation.

Sends a 4-email sequence to trial users on Days 1, 3, 5, and 7 after signup.
"""
import os
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional
from jinja2 import Template

from src.extensions import db
from src.models.core import User, Account

logger = logging.getLogger(__name__)


def get_trial_email_templates() -> Dict[int, Dict[str, str]]:
    """
    Get trial onboarding email templates.

    Returns:
        Dict mapping day number to template paths and subjects
    """
    return {
        1: {
            "subject": "Welcome to InboxIQ! Here's how to get started 🚀",
            "template_path": "src/templates/email/trial_onboarding/day1_welcome.html",
        },
        3: {
            "subject": "{{first_name and first_name + ', see' or 'See'}} how teams like yours use InboxIQ",
            "template_path": "src/templates/email/trial_onboarding/day3_use_case.html",
        },
        5: {
            "subject": "Want a personalized demo? (15 min)",
            "template_path": "src/templates/email/trial_onboarding/day5_demo_offer.html",
        },
        7: {
            "subject": "{{first_name or 'Your'}} trial ends tomorrow — upgrade now and save 20%",
            "template_path": "src/templates/email/trial_onboarding/day7_upgrade_urgency.html",
        },
    }


def extract_personalization_variables(user: User, account: Account) -> Dict[str, Any]:
    """
    Extract personalization variables from user and account.

    Args:
        user: User instance
        account: Account instance

    Returns:
        Dict of variables for template rendering
    """
    # Extract first name - prefer user.name, fallback to email parsing
    first_name = ""
    if user.name:
        # If user has a name field, use the first word as first name
        name_parts = user.name.split()
        first_name = name_parts[0].capitalize() if name_parts else user.name.capitalize()
    elif user.email:
        # Fallback: extract from email (e.g., jane.doe@company.com -> Jane)
        email_username = user.email.split('@')[0]
        name_parts = email_username.split('.')
        first_name = name_parts[0].capitalize() if name_parts else email_username.capitalize()

    # Get industry from account (if exists)
    industry = getattr(account, 'industry', None) or ""

    return {
        "first_name": first_name,
        "FirstName": first_name,
        "email": user.email,
        "account_name": account.name,
        "industry": industry,
    }


def render_email_template(template_path: str, variables: Dict[str, Any]) -> str:
    """
    Render email template with personalization variables.

    Args:
        template_path: Path to template file
        variables: Dict of variables to substitute

    Returns:
        Rendered HTML string
    """
    try:
        with open(template_path, 'r') as f:
            template_str = f.read()

        template = Template(template_str)
        return template.render(**variables)
    except Exception as e:
        logger.error(f"Failed to render template {template_path}: {e}")
        return f"<p>Welcome to InboxIQ! Get started at https://kalevent.com/dashboard</p>"


def send_trial_email(
    user_email: str,
    subject: str,
    body_html: str,
    from_email: Optional[str] = None,
    from_name: Optional[str] = None
) -> Dict[str, Any]:
    """
    Send trial onboarding email via AWS SES.

    Args:
        user_email: Recipient email
        subject: Email subject
        body_html: HTML body
        from_email: Sender email (default from env)
        from_name: Sender name (default from env)

    Returns:
        Dict with success status
    """
    import boto3

    from_email = from_email or os.getenv('TRIAL_ONBOARDING_FROM_EMAIL', 'hello@kalevent.com')
    from_name = from_name or os.getenv('TRIAL_ONBOARDING_FROM_NAME', 'Kofi from Kalevent')

    try:
        ses = boto3.client(
            'ses',
            region_name=os.getenv('AWS_REGION', 'us-west-2'),
            aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
            aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY')
        )

        source = f"{from_name} <{from_email}>" if from_name else from_email

        # Convert HTML to plain text fallback (basic version)
        import re
        body_text = re.sub(r'<[^>]+>', '', body_html)
        body_text = re.sub(r'\s+', ' ', body_text).strip()

        response = ses.send_email(
            Source=source,
            Destination={'ToAddresses': [user_email]},
            Message={
                'Subject': {'Data': subject, 'Charset': 'UTF-8'},
                'Body': {
                    'Text': {'Data': body_text, 'Charset': 'UTF-8'},
                    'Html': {'Data': body_html, 'Charset': 'UTF-8'},
                }
            }
        )

        logger.info(f"Trial email sent to {user_email}: {subject} (MessageId: {response['MessageId']})")

        return {
            "success": True,
            "message_id": response['MessageId'],
            "error": None
        }

    except Exception as e:
        logger.error(f"Failed to send trial email to {user_email}: {e}")
        return {
            "success": False,
            "message_id": None,
            "error": str(e)
        }


def should_send_trial_email(user: User, day: int) -> bool:
    """
    Check if a trial email should be sent to this user on this day.

    Args:
        user: User instance
        day: Day number (1, 3, 5, 7)

    Returns:
        True if email should be sent, False otherwise
    """
    if not user or not user.created_at:
        return False

    # Check if user has password set (activated account)
    if not user.password_hash:
        return False

    # Calculate days since signup
    now = datetime.now(timezone.utc)
    days_since_signup = (now - user.created_at).days

    # Send on exact day (with 24-hour window)
    return days_since_signup == day or (days_since_signup == day and (now - user.created_at).total_seconds() / 3600 < 24)


def enroll_user_in_trial_onboarding(user_id: int) -> Dict[str, Any]:
    """
    Enroll user in trial onboarding sequence (send Day 1 email immediately).

    This is triggered when a user activates their account.

    Args:
        user_id: User ID

    Returns:
        Dict with enrollment status
    """
    try:
        user = db.session.get(User, user_id)
        if not user:
            return {"success": False, "error": "User not found"}

        account = db.session.get(Account, user.account_id)
        if not account:
            return {"success": False, "error": "Account not found"}

        # Get Day 1 template
        templates = get_trial_email_templates()
        day1_template = templates.get(1)
        if not day1_template:
            return {"success": False, "error": "Day 1 template not found"}

        # Extract personalization variables
        variables = extract_personalization_variables(user, account)

        # Render subject and body
        subject_template = Template(day1_template["subject"])
        subject = subject_template.render(**variables)

        body_html = render_email_template(day1_template["template_path"], variables)

        # Send email
        result = send_trial_email(
            user_email=user.email,
            subject=subject,
            body_html=body_html
        )

        if result["success"]:
            logger.info(f"User {user_id} enrolled in trial onboarding (Day 1 sent)")
            return {
                "success": True,
                "message": "Trial onboarding started",
                "email_sent": True,
                "day": 1
            }
        else:
            logger.error(f"Failed to send Day 1 email to user {user_id}: {result['error']}")
            return {
                "success": False,
                "error": result["error"],
                "email_sent": False
            }

    except Exception as e:
        logger.error(f"Error enrolling user {user_id} in trial onboarding: {e}")
        return {"success": False, "error": str(e)}


def process_trial_onboarding_emails(max_emails: int = 100) -> Dict[str, Any]:
    """
    Process trial onboarding emails for all users (Days 3, 5, 7).

    This runs daily via Celery Beat to send scheduled emails.

    Args:
        max_emails: Maximum emails to send in this batch

    Returns:
        Dict with processing results
    """
    try:
        templates = get_trial_email_templates()
        now = datetime.now(timezone.utc)
        sent_count = 0
        error_count = 0
        results = []

        # Get all users with activated accounts (have password set)
        users = User.query.filter(
            User.password_hash.isnot(None),
            User.created_at.isnot(None)
        ).all()

        for user in users:
            if sent_count >= max_emails:
                break

            # Calculate days since signup
            days_since_signup = (now - user.created_at).days

            # Check if we should send an email today
            for day in [3, 5, 7]:
                if days_since_signup == day:
                    account = db.session.get(Account, user.account_id)
                    if not account:
                        continue

                    # Get template for this day
                    template_info = templates.get(day)
                    if not template_info:
                        continue

                    # Extract personalization variables
                    variables = extract_personalization_variables(user, account)

                    # Render subject and body
                    subject_template = Template(template_info["subject"])
                    subject = subject_template.render(**variables)

                    body_html = render_email_template(template_info["template_path"], variables)

                    # Send email
                    result = send_trial_email(
                        user_email=user.email,
                        subject=subject,
                        body_html=body_html
                    )

                    if result["success"]:
                        sent_count += 1
                        results.append({
                            "user_id": user.id,
                            "email": user.email,
                            "day": day,
                            "success": True
                        })
                        logger.info(f"Sent Day {day} trial email to user {user.id}")
                    else:
                        error_count += 1
                        results.append({
                            "user_id": user.id,
                            "email": user.email,
                            "day": day,
                            "success": False,
                            "error": result["error"]
                        })
                        logger.error(f"Failed to send Day {day} email to user {user.id}: {result['error']}")

                    break  # Only send one email per user per day

        return {
            "success": True,
            "sent": sent_count,
            "errors": error_count,
            "processed": len(results),
            "results": results
        }

    except Exception as e:
        logger.error(f"Error processing trial onboarding emails: {e}")
        return {
            "success": False,
            "error": str(e),
            "sent": 0,
            "errors": 0
        }
