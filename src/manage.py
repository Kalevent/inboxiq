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




@app.cli.command("seed-missing-blog-posts")
def cli_seed_missing_blog_posts():
    """
    Migrate the 'too-many-support-emails' article into the BlogPost table.
    Safe to re-run: skips if the slug already exists in the database.
    Run once in production after deploying the removal of src/blog/content.py.
    """
    from src.models.content import BlogPost
    from datetime import datetime, timezone

    _CONTENT_HTML = '<section class="prose prose-invert prose-headings:font-semibold prose-headings:text-white prose-a:text-indigo-200 prose-li:marker:text-indigo-300 max-w-none">\n  <p>If your support inbox feels like it\u2019s constantly out of control, you\u2019re not alone. Many small teams reach a point where customer emails pile up faster than they can respond. Messages get buried, response times slow down, and customers start to notice. The problem isn\u2019t that your team isn\u2019t working hard enough. It\u2019s that email doesn\u2019t scale the way your business does.</p>\n\n  <h2 class="text-xl">Why small teams drown in support emails</h2>\n  <p>Support inbox overload usually happens because of a few common reasons:</p>\n  <ul>\n    <li>All messages flow into a single shared inbox with no routing.</li>\n    <li>No clear prioritisation (urgent vs. non-urgent, VIP vs. standard).</li>\n    <li>Manual sorting and forwarding that breaks under load.</li>\n    <li>No visibility into what\u2019s been answered or who owns what.</li>\n    <li>Customer growth outpacing process maturity.</li>\n  </ul>\n  <p>At first, this is manageable. Then suddenly, it\u2019s chaos.</p>\n\n  <h2 class="text-xl">The hidden cost of inbox chaos</h2>\n  <ul>\n    <li>Missed or forgotten customer messages.</li>\n    <li>Slower response times and slipping SLAs.</li>\n    <li>Duplicate replies from different agents.</li>\n    <li>Increased stress and burnout for the team.</li>\n    <li>Poor customer satisfaction and avoidable churn.</li>\n  </ul>\n  <p>What feels like a \u201cmessy inbox\u201d quickly turns into a business risk.</p>\n\n  <h2 class="text-xl">Quick diagnostic: are you drowning already?</h2>\n  <ul>\n    <li>How many emails hit your shared inbox per day, and how many arrive outside working hours?</li>\n    <li>What\u2019s your median first-response time on weekdays vs. weekends?</li>\n    <li>How often do customers send a \u201cjust checking in\u201d follow-up because they haven\u2019t heard back?</li>\n  </ul>\n  <p>If those answers are fuzzy or trending the wrong way, you\u2019re scaling on luck, not process.</p>\n\n  <h2 class="text-xl">How small teams actually fix it</h2>\n  <p>High-performing teams don\u2019t just \u201ccheck email more often.\u201d They change how email is handled. Here\u2019s what works:</p>\n  <ol>\n    <li><strong>Centralise messages.</strong> All customer emails should flow into one system\u2014no personal inboxes, no side threads.</li>\n    <li><strong>Categorise automatically.</strong> Sort into Billing, Technical issues, Refunds, and General questions. Manual tagging doesn\u2019t scale.</li>\n    <li><strong>Prioritise intelligently.</strong> Handle urgent or frustrated customers first using signals like sentiment, account value, and SLA commitments.</li>\n    <li><strong>Turn emails into trackable work.</strong> Every email should become a ticket with an owner, status, and due time.</li>\n  </ol>\n\n  <h2 class="text-xl">The modern approach: AI email triage</h2>\n  <p>Instead of hand-sorting, AI can:</p>\n  <ul>\n    <li>Read incoming emails instantly.</li>\n    <li>Understand intent and urgency.</li>\n    <li>Categorise messages consistently.</li>\n    <li>Flag high-priority cases.</li>\n    <li>Create structured tickets with owners and SLAs.</li>\n  </ul>\n  <p>The result: the right person sees the right message in the right order\u2014without manual sorting.</p>\n\n  <h3 class="text-lg">What to automate vs. what to keep human</h3>\n  <ul>\n    <li><strong>Automate:</strong> categorisation, priority assignment, SLA tags, ticket creation, routing, and canned first responses when appropriate.</li>\n    <li><strong>Keep human:</strong> empathy, complex troubleshooting, pricing edge cases, and any situation where tone matters more than speed.</li>\n  </ul>\n\n  <h3 class="text-lg">Implementation blueprint for small teams</h3>\n  <ul>\n    <li>Map your top 8\u201310 categories and agree on definitions (e.g., \u201cBilling\u201d vs. \u201cRefunds\u201d).</li>\n    <li>Define priority rules: sentiment score, VIP domains, SLAs, product tier, outage keywords.</li>\n    <li>Connect all inboxes to a single triage lane (Gmail, Outlook, shared mailboxes).</li>\n    <li>Auto-create tickets with owners and due times; never leave conversations unassigned.</li>\n    <li>Set alerts for stuck tickets (e.g., no reply in 2 hours for P1, 8 hours for P2).</li>\n    <li>Create macros for frequent replies, but always personalise first lines.</li>\n  </ul>\n\n  <h3 class="text-lg">Case example: a five-person team</h3>\n  <p><strong>Before:</strong> 600 emails/week, median FRT 9 hours, 14% tickets breached SLA, weekend backlog spilling into Monday.</p>\n  <p><strong>After AI triage + routing:</strong> median FRT 1h 40m, SLA breaches under 3%, weekend backlog cleared by 10 a.m. Monday, and no double replies.</p>\n  <p>The change wasn\u2019t headcount; it was visibility, ownership, and automation.</p>\n\n  <h3 class="text-lg">One-week launch plan</h3>\n  <ul>\n    <li><strong>Day 1\u20132:</strong> Map categories, define SLAs, document routing rules.</li>\n    <li><strong>Day 3:</strong> Connect inboxes and enable AI categorisation in a shadow/observe mode.</li>\n    <li><strong>Day 4:</strong> Turn on automatic ticket creation and routing for low-risk categories.</li>\n    <li><strong>Day 5:</strong> Add alerts for stalled tickets; set up macros for common questions.</li>\n    <li><strong>Day 6:</strong> Spot-check 50 tickets for accuracy; tighten category rules.</li>\n    <li><strong>Day 7:</strong> Roll out to the team with a 10-minute playbook.</li>\n  </ul>\n\n  <h3 class="text-lg">Operational guardrails</h3>\n  <ul>\n    <li><strong>Ownership:</strong> every email gets an owner within minutes.</li>\n    <li><strong>Visibility:</strong> dashboards for \u201cnew\u201d, \u201cin progress\u201d, \u201cwaiting on customer\u201d, \u201cresolved.\u201d</li>\n    <li><strong>Handoffs:</strong> document how to reassign with context so customers never repeat themselves.</li>\n    <li><strong>Quality:</strong> spot-check 5\u201310 AI-triaged tickets daily to keep accuracy high.</li>\n    <li><strong>Escalation:</strong> define what triggers human review (e.g., negative sentiment + VIP domain).</li>\n  </ul>\n\n  <h3 class="text-lg">Metrics that prove it\u2019s working</h3>\n  <ul>\n    <li>Median first-response time (FRT): trending down and stable during spikes.</li>\n    <li>% of emails auto-categorised correctly: target 90%+, with humans fixing the rest.</li>\n    <li>SLA attainment: P1 and P2 staying green even during promotions or launches.</li>\n    <li>Agent span of control: one agent comfortably handling more volume than before.</li>\n    <li>Backlog health: open tickets older than SLA dropping week over week.</li>\n  </ul>\n\n  <h3 class="text-lg">Tooling checklist</h3>\n  <ul>\n    <li>Shared inbox connected to one triage lane.</li>\n    <li>AI classifier for categories + priority + sentiment.</li>\n    <li>Ticketing with assignment, due dates, and audit trails.</li>\n    <li>Alerts for SLA breaches and unassigned tickets.</li>\n    <li>Macros/templates with variables for speed plus personalisation.</li>\n  </ul>\n\n  <h3 class="text-lg">Sample SLA ladder</h3>\n  <ul>\n    <li><strong>P1:</strong> outage/payment failure keywords or negative sentiment + VIP domain \u2192 1 hour first response, 4 hour resolution target.</li>\n    <li><strong>P2:</strong> billing, refund, or access issues \u2192 4 hour first response, 24 hour resolution target.</li>\n    <li><strong>P3:</strong> general questions, feature requests \u2192 1 business day response, resolution as agreed.</li>\n  </ul>\n\n  <h3 class="text-lg">Weekend or after-hours coverage</h3>\n  <ul>\n    <li>Use an \u201cout-of-hours\u201d rule to send a warm holding message with expected reply times.</li>\n    <li>Auto-promote anything with outage keywords or VIP domains to P1 and alert on-call.</li>\n    <li>Have Monday-morning sweeps for anything older than 18 hours to avoid silent aging.</li>\n  </ul>\n\n  <h3 class="text-lg">60-minute quick start (if you need relief now)</h3>\n  <ul>\n    <li>Forward all support mailboxes into one shared inbox.</li>\n    <li>Turn on AI categorisation in observe mode and check 30 samples.</li>\n    <li>Define three priorities (P1/P2/P3) and route P1 to humans immediately.</li>\n    <li>Create two macros: \u201cWe received this and are on it\u201d and \u201cWe need one more detail.\u201d</li>\n    <li>Add one alert: any unassigned P1 older than 30 minutes pings Slack/email.</li>\n  </ul>\n\n  <h3 class="text-lg">Risks to avoid</h3>\n  <ul>\n    <li>Turning on automation without clear categories (creates noisy routing).</li>\n    <li>Treating all customers the same (ignore VIP signals and contract SLAs).</li>\n    <li>Letting \u201curgent\u201d pile up with no owner (causes double replies and churn).</li>\n    <li>No feedback loop: if agents can\u2019t correct AI decisions, quality stalls.</li>\n  </ul>\n\n  <h3 class="text-lg">Baseline, then improve</h3>\n  <p>Capture a one-week baseline of volume, FRT, and SLA attainment. After you turn on triage, compare week over week. If FRT and SLA stay green while volume rises, you\u2019ve bent the curve. If not, tighten categories, add macros, and review priority rules.</p>\n\n  <h2 class="text-xl">Final thoughts</h2>\n  <p>If your team is overwhelmed by support emails, the solution isn\u2019t more people\u2014it\u2019s better systems. Modern teams don\u2019t fight inbox chaos. They automate it. Start with AI email triage, then layer in routing rules, SLAs, and quality checks. You\u2019ll get faster replies, fewer misses, and a calmer team.</p>\n\n  <p class="mt-4 text-indigo-200">Next step: see how AI Email Triage reduces support workload by 80%. Read the MOFU follow-up (coming soon): <a href="/blog/ai-email-triage" class="font-semibold">AI Email Triage</a>.</p>\n\n  <div class="mt-6 p-4 rounded-xl border border-indigo-500/30 bg-indigo-500/10">\n    <div class="text-sm text-indigo-100 font-semibold mb-1">CTA</div>\n    <p class="text-sm text-slate-200">Ready to stop inbox overload? Start a 7-day free trial of InboxIQ and get AI triage live in under an hour.</p>\n    <div class="mt-3 flex flex-wrap gap-3">\n      <a href="/upgrade" class="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-indigo-500 hover:bg-indigo-400 text-sm font-semibold text-white">Start free trial</a>\n      <a href="/contact" class="inline-flex items-center gap-2 px-4 py-2 rounded-full border border-indigo-300/50 text-sm font-semibold text-indigo-100 hover:bg-indigo-500/10">Talk to us</a>\n    </div>\n  </div>\n\n  <p class="text-xs text-slate-400 mt-6">Repurpose: publish on Medium, Indie Hackers, and as a shortened LinkedIn article, but keep the canonical at /blog/too-many-support-emails.</p>\n</section>'
    _CONTENT_HTML = _CONTENT_HTML.replace("/blog/ai-email-triage", "/ai-email-triage")
    _CONTENT_HTML = _CONTENT_HTML.replace("Read the MOFU follow-up (coming soon):", "Explore the product page:")

    slug = "too-many-support-emails"
    existing = BlogPost.query.filter_by(slug=slug).first()
    if existing:
        click.echo(f"skip {slug} (already in DB as {existing.status})")
        return

    post = BlogPost(
        title="Too Many Support Emails? Here\u2019s How Small Teams Fix It",
        slug=slug,
        status="published",
        content_html=_CONTENT_HTML,
        meta_description="Small teams can tame an overloaded support inbox with automation, routing, and AI email triage instead of hiring more staff.",
        primary_keyword="too many support emails",
        funnel_stage="tofu",
        canonical_url="/blog/too-many-support-emails",
        internal_links=[{"href": "/ai-email-triage", "label": "AI Email Triage", "rel": "next"}],
        word_count=1230,
        read_time_minutes=5,
        published_at=datetime.now(timezone.utc),
    )
    db.session.add(post)
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    click.echo(f"created {slug}")


@app.cli.command("backfill-meta-descriptions")
@click.option("--dry-run", is_flag=True, default=False, help="Preview without saving.")
def cli_backfill_meta_descriptions(dry_run: bool):
    """
    Generate SEO meta descriptions for all published blog posts that don't have one.
    Safe to re-run: skips posts that already have a meta_description.
    """
    from src.models.content import BlogPost
    from src.publishing.service import _generate_meta_description

    posts = (
        BlogPost.query
        .filter(BlogPost.status == "published")
        .filter(
            (BlogPost.meta_description == None) |  # noqa: E711
            (BlogPost.meta_description == "")
        )
        .order_by(BlogPost.published_at.asc())
        .all()
    )

    if not posts:
        click.echo("All published posts already have meta descriptions.")
        return

    click.echo(f"Found {len(posts)} post(s) missing meta descriptions.")
    if dry_run:
        click.echo("Dry run — no changes will be saved.\n")

    updated = 0
    skipped = 0
    for post in posts:
        try:
            desc = _generate_meta_description(post)
            if not desc:
                click.echo(f"  skip  [{post.slug}] — could not generate description")
                skipped += 1
                continue

            click.echo(f"  ok    [{post.slug}]\n        {desc}")

            if not dry_run:
                post.meta_description = desc
                try:
                    db.session.commit()
                except Exception as exc:
                    db.session.rollback()
                    click.echo(f"  ERROR [{post.slug}] DB commit failed: {exc}")
                    skipped += 1
                    continue

            updated += 1

        except Exception as exc:
            click.echo(f"  ERROR [{post.slug}] {exc}")
            skipped += 1

    click.echo(f"\nDone. updated={updated}  skipped={skipped}  dry_run={dry_run}")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
