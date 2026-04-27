from celery import shared_task
from src.app import create_app
from src.billing.service import BillingService
from src.billing.jobs import run_trial_checker, run_retry_processor, run_dunning_sender, run_billing_profile_backfill


def _service(app):
    cfg = app.config
    return BillingService(
        stripe_key=cfg.get("STRIPE_SECRET_KEY"),
        secondary_key=cfg.get("SECONDARY_PSP_KEY"),
    )


@shared_task(name="billing.run_trial_checker")
def task_run_trial_checker():
    app = create_app()
    with app.app_context():
        svc = _service(app)
        return run_trial_checker(svc)


@shared_task(name="billing.run_retry_processor")
def task_run_retry_processor():
    app = create_app()
    with app.app_context():
        svc = _service(app)
        return run_retry_processor(svc)


@shared_task(name="billing.run_dunning_sender")
def task_run_dunning_sender():
    app = create_app()
    with app.app_context():
        svc = _service(app)
        return run_dunning_sender(svc)


@shared_task(name="billing.backfill_missing_profiles")
def task_backfill_missing_profiles():
    app = create_app()
    with app.app_context():
        return run_billing_profile_backfill()
