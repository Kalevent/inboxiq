from typing import Optional
import smtplib
from email.message import EmailMessage
from flask import current_app


def _send_email(to_email: str, subject: str, text_body: str, html_body: Optional[str] = None) -> None:
    """
    Minimal SMTP sender using app config; no-op if SMTP_HOST is unset.
    """
    app = current_app
    host = app.config.get("SMTP_HOST")
    if not host:
        app.logger.info({"event": "billing.email.skipped", "reason": "SMTP_HOST missing", "to": to_email})
        return

    port = app.config.get("SMTP_PORT")
    user = app.config.get("SMTP_USER")
    password = app.config.get("SMTP_PASSWORD")
    use_tls = app.config.get("SMTP_USE_TLS", True)
    use_ssl = app.config.get("SMTP_USE_SSL", False)
    mail_from = app.config.get("MAIL_FROM", "noreply@kalevent.com")

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = mail_from
    msg["To"] = to_email
    msg.set_content(text_body)
    if html_body:
        msg.add_alternative(html_body, subtype="html")

    try:
        if use_ssl:
            with smtplib.SMTP_SSL(host, port) as server:
                if user and password:
                    server.login(user, password)
                server.send_message(msg)
        else:
            with smtplib.SMTP(host, port) as server:
                if use_tls:
                    server.starttls()
                if user and password:
                    server.login(user, password)
                server.send_message(msg)
        app.logger.info({"event": "billing.email.sent", "to": to_email, "subject": subject})
    except Exception as exc:  # pragma: no cover
        app.logger.warning({"event": "billing.email.failed", "to": to_email, "error": str(exc)})


def send_trial_reminder(to_email: str, days_left: int) -> None:
    subject = f"Your InboxIQ trial ends in {days_left} day(s)"
    text = (
        f"Your InboxIQ trial ends in {days_left} day(s). Add a card to keep your agent running without interruption."
    )
    html = (
        f"<p>Your InboxIQ trial ends in <strong>{days_left} day(s)</strong>.</p>"
        "<p>Add a card to keep your agent running without interruption.</p>"
    )
    _send_email(to_email, subject, text, html)


def send_trial_ended(to_email: str) -> None:
    subject = "Your InboxIQ trial has ended — add billing to continue"
    text = (
        "Your trial has ended. Please add a payment method and pick a plan to keep InboxIQ running without interruption."
    )
    html = (
        "<p>Your trial has ended.</p>"
        "<p>Please add a payment method and pick a plan to keep InboxIQ running without interruption.</p>"
    )
    _send_email(to_email, subject, text, html)


def send_payment_receipt(to_email: str, invoice_id: str) -> None:
    subject = "Payment received – InboxIQ"
    text = f"Thank you for your payment. Invoice ID: {invoice_id}"
    html = f"<p>Thank you for your payment.</p><p>Invoice ID: <strong>{invoice_id}</strong></p>"
    _send_email(to_email, subject, text, html)


def send_payment_failure(to_email: str, invoice_id: str, reason: Optional[str] = None) -> None:
    subject = "Action needed: payment failed"
    text = f"We couldn’t process payment for invoice {invoice_id}. Reason: {reason or 'unknown'}"
    html = (
        f"<p>We couldn’t process payment for invoice <strong>{invoice_id}</strong>.</p>"
        f"<p>Reason: {reason or 'unknown'}.</p>"
        "<p>Please update your payment method to avoid service interruption.</p>"
    )
    _send_email(to_email, subject, text, html)


def send_dunning_notice(to_email: str, invoices: list[dict]) -> None:
    """
    Notify a customer about overdue invoices. Accepts a list of summaries with
    keys: id, amount_cents, currency, due_at (datetime or ISO string).
    """
    def _fmt_amount(cents: int, currency: str) -> str:
        return f"{currency} {cents / 100:.2f}"

    lines = ["We could not collect payment for the following invoice(s). Please update your payment method."]
    html_lines = ["<p>We could not collect payment for the following invoice(s).</p><ul>"]
    for inv in invoices:
        amount = _fmt_amount(inv.get("amount_cents", 0), inv.get("currency", ""))
        due_at = inv.get("due_at")
        due_str = due_at.isoformat() if hasattr(due_at, "isoformat") else str(due_at)
        lines.append(f"- Invoice {inv.get('id')} for {amount} was due {due_str}")
        html_lines.append(f"<li>Invoice <strong>{inv.get('id')}</strong> for {amount} was due {due_str}</li>")
    html_lines.append("</ul><p>Please update your payment method to avoid service interruption.</p>")
    lines.append("Please update your payment method to avoid service interruption.")

    subject = "Action needed: payment overdue"
    _send_email(to_email, subject, "\n".join(lines), "".join(html_lines))
