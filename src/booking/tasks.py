import logging
import os

from celery import shared_task

logger = logging.getLogger(__name__)

_FROM_EMAIL = os.getenv("TRIAL_ONBOARDING_FROM_EMAIL", "hello@kalevent.com")
_FROM_NAME = os.getenv("TRIAL_ONBOARDING_FROM_NAME", "Kofi from InboxIQ")


@shared_task(name="booking.send_confirmation_reply", bind=True, max_retries=3, default_retry_delay=60, queue="inbox")
def send_booking_confirmation_reply(self, booking_id: str) -> None:
    """Send a confirmation email to the person who just booked a meeting via SES."""
    from src.app import create_app
    app = create_app()
    with app.app_context():
        try:
            import boto3
            from src.extensions import db
            from src.models.misc import Booking
            from src.models.core import Account

            booking = db.session.get(Booking, booking_id)
            if not booking or booking.status != "confirmed":
                logger.warning("Booking %s not found or not confirmed — skipping reply", booking_id)
                return

            account = db.session.get(Account, booking.account_id)
            account_name = account.name if account else "InboxIQ"

            slot_label = booking.slot_start.strftime("%A %d %B %Y at %H:%M UTC") if booking.slot_start else "the scheduled time"
            meet_link = booking.meet_link or ""

            subject = f"Re: {booking.subject}" if booking.subject else "Your meeting is confirmed"

            body_html = f"""<!DOCTYPE html>
<html>
<body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Arial,sans-serif;color:#333;max-width:600px;margin:0 auto;padding:20px;">
  <p>Hi {booking.booked_by_name or 'there'},</p>
  <p>Your meeting is confirmed for <strong>{slot_label}</strong>.</p>
  {"<p><a href='" + meet_link + "' style='background:#4F46E5;color:#fff;padding:10px 20px;border-radius:6px;text-decoration:none;font-weight:600;'>Join meeting</a></p>" if meet_link else ""}
  <p>Looking forward to speaking with you.</p>
  <p style="color:#666;font-size:13px;">— {account_name}</p>
</body>
</html>"""

            import re
            body_text = re.sub(r'<[^>]+>', '', body_html)
            body_text = re.sub(r'\s+', ' ', body_text).strip()

            ses = boto3.client(
                'ses',
                region_name=os.getenv('AWS_REGION', 'us-west-2'),
                aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
                aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
            )
            source = f"{_FROM_NAME} <{_FROM_EMAIL}>"
            ses.send_email(
                Source=source,
                Destination={'ToAddresses': [booking.booked_by_email]},
                Message={
                    'Subject': {'Data': subject, 'Charset': 'UTF-8'},
                    'Body': {
                        'Text': {'Data': body_text, 'Charset': 'UTF-8'},
                        'Html': {'Data': body_html, 'Charset': 'UTF-8'},
                    },
                },
            )
            logger.info("Booking confirmation reply sent to %s (booking=%s)", booking.booked_by_email, booking_id)
        except Exception as exc:
            logger.error("Booking confirmation reply failed (booking=%s): %s", booking_id, exc)
            raise self.retry(exc=exc)
