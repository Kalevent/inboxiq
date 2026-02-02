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


@app.cli.command("dspy-reset-training")
@click.option("--account-id", default=None, help="Account ID to reset (leave empty for all).")
@click.option("--confirm", is_flag=True, help="Confirm the reset (required).")
def cli_dspy_reset_training(account_id: str | None, confirm: bool):
    """
    Reset DSPy training data by clearing manual_override flags.
    This allows starting fresh with clean training data.
    """
    from src.models import Ticket, DspyTrainingMetric

    if not confirm:
        click.echo("This will reset all manual override training data.")
        click.echo("Run with --confirm to proceed.")
        return

    query = Ticket.query.filter(Ticket.manual_override.is_(True))
    if account_id:
        query = query.filter(Ticket.account_id == account_id)

    count = query.count()
    if count == 0:
        click.echo("No manual overrides found to reset.")
        return

    # Reset manual_override flag
    query.update({Ticket.manual_override: False}, synchronize_session=False)

    # Optionally delete training metrics
    metrics_query = DspyTrainingMetric.query
    if account_id:
        metrics_query = metrics_query.filter(DspyTrainingMetric.account_id == account_id)
    metrics_count = metrics_query.delete(synchronize_session=False)

    db.session.commit()
    click.echo(f"Reset {count} manual overrides and deleted {metrics_count} training metrics.")
    click.echo("New training data will be collected from future manual overrides.")


@app.cli.command("dspy-fix-priorities")
@click.option("--confirm", is_flag=True, help="Confirm the fix (required).")
def cli_dspy_fix_priorities(confirm: bool):
    """
    Fix invalid P0 priorities by converting them to P1.
    """
    from src.models import Ticket

    if not confirm:
        click.echo("This will convert all P0 priorities to P1.")
        click.echo("Run with --confirm to proceed.")
        return

    count = Ticket.query.filter(Ticket.priority == "P0").update(
        {Ticket.priority: "P1"}, synchronize_session=False
    )
    db.session.commit()
    click.echo(f"Fixed {count} tickets with P0 priority (now P1).")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
