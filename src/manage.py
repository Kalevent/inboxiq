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
    from src.models.billing import CustomerBillingProfile

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


@app.cli.command("seed-plans")
def cli_seed_plans():
    """
    Seed the plans table with Pro, Business, Scale, Enterprise definitions.
    Safe to re-run: skips plans that already exist (matched by code).
    Run AFTER Stripe products and prices have been created.
    """
    from src.models.billing import Plan

    definitions = [
        dict(
            code="pro",
            price_cents=4900, currency="GBP", seats=2,
            ai_decisions_limit=1000,
            chat_enabled=False, chat_limit=None,
            automation_enabled=False, automation_runs_limit=None,
            content_gen_enabled=False, content_posts_limit=None,
            lead_discovery_enabled=False, leads_limit=None,
            nurture_enabled=False, nurture_emails_limit=None,
            distribution_enabled=False,
            api_access_enabled=False, registered_apps_limit=0,
            stripe_ai_overage_price_id="price_1T3QtBJSevdfPcyKqixrbQD2",
        ),
        dict(
            code="business",
            price_cents=14900, currency="GBP", seats=5,
            ai_decisions_limit=5000,
            chat_enabled=True, chat_limit=200,
            automation_enabled=True, automation_runs_limit=500,
            content_gen_enabled=True, content_posts_limit=8,
            lead_discovery_enabled=False, leads_limit=None,
            nurture_enabled=True, nurture_emails_limit=2000,
            distribution_enabled=False,
            api_access_enabled=True, registered_apps_limit=2,
            stripe_ai_overage_price_id="price_1T3QtBJSevdfPcyKO7az2Bnh",
            stripe_chat_overage_price_id="price_1T3QtCJSevdfPcyKdXODzJ41",
            stripe_automation_overage_price_id="price_1T3QtDJSevdfPcyKWvbnclxe",
            stripe_nurture_overage_price_id="price_1T3QtDJSevdfPcyK5YUJsopX",
        ),
        dict(
            code="scale",
            price_cents=39900, currency="GBP", seats=15,
            ai_decisions_limit=25000,
            chat_enabled=True, chat_limit=1000,
            automation_enabled=True, automation_runs_limit=5000,
            content_gen_enabled=True, content_posts_limit=30,
            lead_discovery_enabled=True, leads_limit=200,
            nurture_enabled=True, nurture_emails_limit=20000,
            distribution_enabled=True,
            api_access_enabled=True, registered_apps_limit=999999,
            stripe_ai_overage_price_id="price_1T3QtEJSevdfPcyKwEr1qCZM",
            stripe_chat_overage_price_id="price_1T3QtEJSevdfPcyK0J9Cq240",
            stripe_automation_overage_price_id="price_1T3QtFJSevdfPcyKSv89eccb",
            stripe_nurture_overage_price_id="price_1T3QtGJSevdfPcyKtq1lPtMK",
            stripe_leads_overage_price_id="price_1T3QtGJSevdfPcyKGoEpkwEj",
        ),
        dict(
            code="enterprise",
            price_cents=0, currency="GBP", seats=None,
            ai_decisions_limit=None,
            chat_enabled=True, chat_limit=None,
            automation_enabled=True, automation_runs_limit=None,
            content_gen_enabled=True, content_posts_limit=None,
            lead_discovery_enabled=True, leads_limit=None,
            nurture_enabled=True, nurture_emails_limit=None,
            distribution_enabled=True,
            api_access_enabled=True, registered_apps_limit=999999,
        ),
    ]

    created = 0
    skipped = 0
    for defn in definitions:
        existing = Plan.query.filter_by(code=defn["code"]).first()
        if existing:
            click.echo(f"  skip {defn['code']} (already exists)")
            skipped += 1
            continue
        plan = Plan(**defn)
        db.session.add(plan)
        click.echo(f"  create {defn['code']}")
        created += 1

    db.session.commit()
    click.echo(f"Done: {created} created, {skipped} skipped.")


@app.cli.command("set-enterprise-account")
@click.option("--account-id", required=True, type=int, help="Account ID to set as Enterprise.")
def cli_set_enterprise_account(account_id: int):
    """
    Set an account to the Enterprise plan with no billing.
    Use for internal/owner accounts that should not be charged.
    The Enterprise plan has unlimited access to all features.
    """
    from src.models.billing import CustomerBillingProfile, Plan

    plan = Plan.query.filter_by(code="enterprise").first()
    if not plan:
        click.echo("Enterprise plan not found. Run `flask seed-plans` first.")
        return

    profile = CustomerBillingProfile.query.filter_by(account_id=account_id).first()
    if not profile:
        click.echo(f"No billing profile for account {account_id}.")
        return

    profile.plan_choice = "enterprise"
    profile.trial_status = "ended"   # Not a trial — a real Enterprise account
    profile.trial_end = None          # No expiry date — trial_checker ignores NULL trial_end
    profile.subscription_status = "active"
    db.session.commit()
    click.echo(f"Account {account_id} set to Enterprise (no billing, unlimited access).")




if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
