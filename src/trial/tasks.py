"""
Celery tasks for trial onboarding email sequence.
"""
from celery import shared_task
from src.trial_onboarding import process_trial_onboarding_emails, enroll_user_in_trial_onboarding
import logging

logger = logging.getLogger(__name__)


@shared_task(name="trial.process_onboarding_emails", queue="leads")
def process_trial_onboarding_emails_task(max_emails: int = 100):
    """
    Process scheduled trial onboarding emails (Days 3, 5, 7).

    Runs daily via Celery Beat to send emails to users at the right stage of their trial.

    Args:
        max_emails: Maximum emails to send in this batch (default: 100)

    Returns:
        Dict with processing results
    """
    try:
        result = process_trial_onboarding_emails(max_emails=max_emails)
        logger.info(f"Trial onboarding emails processed: {result['sent']} sent, {result['errors']} errors")
        return result
    except Exception as e:
        logger.error(f"Error processing trial onboarding emails: {e}")
        return {"success": False, "error": str(e), "sent": 0, "errors": 0}


@shared_task(name="trial.enroll_user", queue="leads")
def enroll_user_in_trial_task(user_id: int):
    """
    Enroll user in trial onboarding sequence (send Day 1 email).

    Triggered when a user activates their account.

    Args:
        user_id: User ID to enroll

    Returns:
        Dict with enrollment status
    """
    try:
        result = enroll_user_in_trial_onboarding(user_id)
        if result["success"]:
            logger.info(f"User {user_id} enrolled in trial onboarding")
        else:
            logger.error(f"Failed to enroll user {user_id}: {result.get('error')}")
        return result
    except Exception as e:
        logger.error(f"Error enrolling user {user_id} in trial: {e}")
        return {"success": False, "error": str(e)}
