import sys
from pathlib import Path

# Ensure project root is on sys.path when running as a script (python src/manage.py)
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.app import create_app
from src.extensions import db
from src import models  # noqa: F401  # ensure models are registered
from src.billing.service import BillingService
from src.billing.jobs import run_trial_checker, run_retry_processor, run_dunning_sender
import click
from datetime import datetime, timedelta, timezone

app = create_app()


@app.shell_context_processor
def make_shell_context():
    """Expose common objects to `flask shell`."""
    return {"db": db, **{name: getattr(models, name) for name in dir(models) if not name.startswith("_")}}


def _billing_service():
    cfg = app.config
    return BillingService(
        stripe_key=cfg.get("STRIPE_SECRET_KEY"),
        secondary_key=cfg.get("SECONDARY_PSP_KEY"),
    )


@app.cli.command("billing-run-trial-checker")
@click.option("--days-notice", default=3, help="Days before expiry to mark as ending soon.")
def cli_billing_trial_checker(days_notice: int):
    """Mark trials ending soon / ended and trigger reminders."""
    svc = _billing_service()
    result = run_trial_checker(svc, now=None, days_notice=days_notice)
    click.echo(result)


@app.cli.command("billing-run-retry")
def cli_billing_retry():
    """Retry past due invoices."""
    svc = _billing_service()
    result = run_retry_processor(svc, now=None)
    click.echo(result)


@app.cli.command("billing-run-dunning")
def cli_billing_dunning():
    """Send dunning notices (placeholder)."""
    svc = _billing_service()
    result = run_dunning_sender(svc, now=None)
    click.echo(result)


@app.cli.command("billing-backfill-trial")
@click.option("--email", required=True, help="User email belonging to the account to backfill.")
@click.option("--days", default=7, show_default=True, help="Trial length in days (default 7).")
def cli_billing_backfill_trial(email: str, days: int):
    """
    Create or update a billing profile for the user's account and set a trial window.
    Useful to backfill trials for existing accounts.
    """
    from src.models import User
    from src.billing.models import CustomerBillingProfile

    user = User.query.filter_by(email=email).first()
    if not user:
        click.echo(f"No user found for {email}")
        return

    account_id = user.account_id
    profile = CustomerBillingProfile.query.filter_by(account_id=account_id).first()
    now = datetime.now(tz=timezone.utc)
    trial_end = now + timedelta(days=days)
    if not profile:
        profile = CustomerBillingProfile(
            account_id=account_id,
            email=email,
            trial_start=now,
            trial_end=trial_end,
            trial_status="active",
            subscription_status="none",
        )
        click.echo(f"Created billing profile for account {account_id} with trial ending {trial_end}")
        db.session.add(profile)
    else:
        profile.email = profile.email or email
        profile.trial_start = now
        profile.trial_end = trial_end
        profile.trial_status = "active"
        if profile.subscription_status in ("none", "", None):
            profile.subscription_status = "trialing"
        click.echo(f"Updated billing profile for account {account_id}; trial ends {trial_end}")
    db.session.commit()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
