"""
Finance Add-on Celery tasks.

process_stripe_event  — triggered by inbound Stripe webhook; runs Mode 1 or buffers for Mode 2
generate_weekly_csv_export — Celery Beat task; runs every Friday 08:00 UTC for all Mode 2 accounts
"""
from __future__ import annotations

import csv
import io
import logging
from datetime import datetime, timezone

from src.celery_inboxiq import celery
from src.extensions import db
from src.models.addons import AccountAddOn
from src.models.automation import WebhookProvider
from src.integrations.finance_stripe import normalize_stripe_event
from src.integrations.quickbooks import client_from_provider

_log = logging.getLogger(__name__)


@celery.task(name="finance_addon.process_stripe_event", queue="inbox", bind=True, max_retries=3)
def process_stripe_event(self, account_id: int, provider_id: str, event: dict):
    """
    Process an inbound Stripe event for a Finance add-on account.
    Mode 1: sync to QuickBooks immediately.
    Mode 2: buffer the normalised transaction in the add-on's pending list.
    """
    addon = AccountAddOn.query.filter_by(
        account_id=account_id,
        addon_type="finance",
        status="active",
    ).first()

    if not addon:
        _log.warning("finance_addon: no active addon for account_id=%s", account_id)
        return

    try:
        tx = normalize_stripe_event(event)
    except ValueError as exc:
        _log.info("finance_addon: skipping unsupported event type: %s", exc)
        return

    _increment_transaction_counter(addon)

    mode = (addon.config_json or {}).get("mode", "csv_export")
    if mode == "direct_sync":
        _run_mode1_sync(addon, event, account_id)
    else:
        _buffer_for_csv(addon, tx)


def _increment_transaction_counter(addon) -> None:
    """Increment monthly transaction counter, resetting if billing month changed."""
    current_month = datetime.now(timezone.utc).strftime("%Y-%m")
    if addon.billing_month != current_month:
        addon.transactions_this_month = 0
        addon.billing_month = current_month
    addon.transactions_this_month += 1
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise


def _run_mode1_sync(addon, event: dict, account_id: int) -> None:
    """Mode 1: push transaction to QuickBooks in real-time."""
    if not addon.is_active():
        return

    config = addon.config_json or {}
    qb_provider_id = config.get("qb_provider_id")
    if not qb_provider_id:
        _log.error("finance_addon mode1: no qb_provider_id in config for account_id=%s", account_id)
        return

    qb_provider = WebhookProvider.query.filter_by(
        id=qb_provider_id,
        account_id=account_id,
        enabled=True,
    ).first()
    if not qb_provider:
        _log.error("finance_addon mode1: QB provider not found id=%s", qb_provider_id)
        return

    try:
        tx = normalize_stripe_event(event)
        qb_client = client_from_provider(qb_provider)

        customer_id = qb_client.find_or_create_customer(
            name=tx["customer_name"] or "Unknown",
            email=tx["customer_email"],
        )

        pi_id = tx.get("stripe_payment_intent_id", "")
        qb_client.create_sales_receipt(
            customer_id=customer_id,
            amount_cents=tx["amount_cents"],
            currency=tx["currency"],
            description=f"Stripe payment {pi_id}".strip(),
        )
        _log.info(
            "finance_addon mode1: synced stripe_event=%s to QB for account_id=%s",
            tx["stripe_event_id"], account_id,
        )
    except Exception as exc:
        _log.error(
            "finance_addon mode1: sync failed account_id=%s error=%s",
            account_id, exc,
        )
        raise


def _buffer_for_csv(addon, tx: dict) -> None:
    """Mode 2: append normalised transaction to the add-on's pending CSV buffer."""
    config = addon.config_json or {}
    pending: list = list(config.get("pending_transactions", []))
    pending.append(tx)
    addon.config_json = {**config, "pending_transactions": pending}
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise


@celery.task(name="finance_addon.generate_weekly_csv_export", queue="inbox")
def generate_weekly_csv_export():
    """
    Celery Beat task — runs every Friday at 08:00 UTC.
    For each active Mode 2 Finance add-on account, generates an Intuit-compatible
    CSV from buffered transactions and emails it to the configured address.
    """
    addons = AccountAddOn.query.filter_by(
        addon_type="finance",
        status="active",
    ).all()

    for addon in addons:
        config = addon.config_json or {}
        if config.get("mode") != "csv_export":
            continue
        pending = config.get("pending_transactions", [])
        if not pending:
            continue

        try:
            csv_bytes = _build_intuit_csv(pending)
            csv_email = config.get("csv_email")
            if csv_email:
                _email_csv(addon.account_id, csv_email, csv_bytes)
            # Clear the buffer after successful email
            addon.config_json = {**config, "pending_transactions": []}
            db.session.commit()
        except Exception as exc:
            db.session.rollback()
            _log.error(
                "finance_addon csv_export: failed account_id=%s error=%s",
                addon.account_id, exc,
            )


def _build_intuit_csv(transactions: list[dict]) -> bytes:
    """
    Build a QuickBooks-compatible bank transactions CSV.

    Columns: Date, Description, Amount, Currency
    Date is taken from the Stripe event's `created` Unix timestamp (UTC).
    """
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Date", "Description", "Amount", "Currency"])
    for tx in transactions:
        created_ts = tx.get("event_created")
        if created_ts:
            date_str = datetime.fromtimestamp(created_ts, tz=timezone.utc).strftime("%m/%d/%Y")
        else:
            date_str = datetime.now(timezone.utc).strftime("%m/%d/%Y")
        amount = round(tx.get("amount_cents", 0) / 100, 2)
        description = tx.get("description") or f"Stripe {tx.get('event_type', 'payment')}"
        currency = tx.get("currency", "GBP")
        writer.writerow([date_str, description, amount, currency])
    return output.getvalue().encode("utf-8")


def _email_csv(account_id: int, recipient: str, csv_bytes: bytes) -> None:
    """
    Send the CSV to the configured accountant email via SMTP.
    Uses stdlib smtplib directly — src/notifications/emails.py has no attachment support.
    Config keys: SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, MAIL_FROM.
    """
    import smtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText
    from email.mime.base import MIMEBase
    from email import encoders
    from datetime import date
    from flask import current_app

    week_label = date.today().strftime("%Y-W%V")
    filename = f"inboxiq_finance_{week_label}.csv"

    host = current_app.config.get("SMTP_HOST")
    if not host:
        _log.info("finance_addon csv_email: SMTP_HOST not configured, skipping email")
        return

    port = current_app.config.get("SMTP_PORT", 587)
    user = current_app.config.get("SMTP_USER")
    password = current_app.config.get("SMTP_PASSWORD")
    mail_from = current_app.config.get("MAIL_FROM", "noreply@kalevent.com")

    msg = MIMEMultipart()
    msg["From"] = mail_from
    msg["To"] = recipient
    msg["Subject"] = f"InboxIQ Finance Export — Week {week_label}"
    msg.attach(MIMEText(
        "Please find this week's Stripe transaction export attached.\n\n"
        "Import into QuickBooks via Banking > Upload transactions.",
        "plain",
    ))

    part = MIMEBase("text", "csv")
    part.set_payload(csv_bytes)
    encoders.encode_base64(part)
    part.add_header("Content-Disposition", f'attachment; filename="{filename}"')
    msg.attach(part)

    with smtplib.SMTP(host, port) as server:
        server.starttls()
        if user and password:
            server.login(user, password)
        server.sendmail(mail_from, [recipient], msg.as_string())
