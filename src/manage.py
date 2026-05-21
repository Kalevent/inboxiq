import csv
import io
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
    Seed the plans table with Free, Starter, Pro, Business, Enterprise.
    Safe to re-run: skips plans that already exist (matched by code).
    Run AFTER Stripe products and prices have been created.
    """
    from src.models.billing import Plan

    definitions = [
        dict(
            code="free",
            price_cents=0, currency="GBP", seats=1,
            ai_decisions_limit=50,
            inbox_limit=1, automation_rules_limit=1,
            byol_enabled=True, audit_log_enabled=False, kb_drafts_enabled=False,
            chat_enabled=False, chat_limit=None,
            automation_enabled=False, automation_runs_limit=None,
            content_gen_enabled=False, content_posts_limit=None,
            lead_discovery_enabled=False, leads_limit=None,
            nurture_enabled=False, nurture_emails_limit=None,
            distribution_enabled=False,
            api_access_enabled=False, registered_apps_limit=0,
        ),
        dict(
            code="starter",
            price_cents=1900, currency="GBP", seats=1,
            ai_decisions_limit=200,
            inbox_limit=1, automation_rules_limit=3,
            byol_enabled=False, audit_log_enabled=False, kb_drafts_enabled=False,
            chat_enabled=False, chat_limit=None,
            automation_enabled=False, automation_runs_limit=None,
            content_gen_enabled=False, content_posts_limit=None,
            lead_discovery_enabled=False, leads_limit=None,
            nurture_enabled=False, nurture_emails_limit=None,
            distribution_enabled=False,
            api_access_enabled=False, registered_apps_limit=0,
            stripe_ai_overage_price_id="price_1TYDDuJSevdfPcyKsatbFchH",
        ),
        dict(
            code="pro",
            price_cents=3900, currency="GBP", seats=2,
            ai_decisions_limit=1000,
            inbox_limit=None, automation_rules_limit=25,
            byol_enabled=True, audit_log_enabled=False, kb_drafts_enabled=False,
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
            price_cents=5900, currency="GBP", seats=5,
            ai_decisions_limit=5000,
            inbox_limit=None, automation_rules_limit=100,
            byol_enabled=True, audit_log_enabled=True, kb_drafts_enabled=True,
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
            code="enterprise",
            price_cents=0, currency="GBP", seats=None,
            ai_decisions_limit=None,
            inbox_limit=None, automation_rules_limit=None,
            byol_enabled=True, audit_log_enabled=True, kb_drafts_enabled=True,
            chat_enabled=True, chat_limit=None,
            automation_enabled=True, automation_runs_limit=None,
            content_gen_enabled=True, content_posts_limit=None,
            lead_discovery_enabled=True, leads_limit=None,
            nurture_enabled=True, nurture_emails_limit=None,
            distribution_enabled=True,
            api_access_enabled=True, registered_apps_limit=999999,
        ),
    ]

    # Columns updated on existing plans when re-running seed
    _UPSERT_COLS = (
        "inbox_limit", "automation_rules_limit",
        "byol_enabled", "audit_log_enabled", "kb_drafts_enabled",
        "price_cents",
    )

    created = 0
    updated = 0
    for defn in definitions:
        existing = Plan.query.filter_by(code=defn["code"]).first()
        if existing:
            changed = False
            for col in _UPSERT_COLS:
                if col in defn and getattr(existing, col) != defn[col]:
                    setattr(existing, col, defn[col])
                    changed = True
            if changed:
                click.echo(f"  update {defn['code']}")
                updated += 1
            else:
                click.echo(f"  skip {defn['code']} (no changes)")
            continue
        plan = Plan(**defn)
        db.session.add(plan)
        click.echo(f"  create {defn['code']}")
        created += 1

    db.session.commit()
    click.echo(f"Done: {created} created, {updated} updated.")


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


@app.cli.command("seed-cost-of-slow-support")
def cli_seed_cost_of_slow_support():
    """
    Seed the 'cost-of-slow-support' blog post.
    Safe to re-run: skips if the slug already exists in the database.
    Fill in TITLE, META_DESCRIPTION, and CONTENT_HTML before running.
    """
    from src.models.content import BlogPost
    from datetime import datetime, timezone

    TITLE = "The Real Cost of Slow Customer Support"
    META_DESCRIPTION = (
        "Slow support responses cost B2B SaaS companies through churn, lost upsells, and "
        "reputation damage. Learn how to measure the impact and fix it with AI triage."
    )
    PRIMARY_KEYWORD = "cost of slow customer support"
    SECONDARY_KEYWORDS = [
        "slow support response time",
        "SLA breach cost",
        "customer churn support",
        "AI email triage",
    ]
    CONTENT_HTML = """\
<section class="prose prose-invert prose-headings:font-semibold prose-headings:text-white prose-a:text-indigo-200 prose-li:marker:text-indigo-300 max-w-none">

  <p>A customer emails your support team. They wait four hours. Then eight. By the time someone replies, they\u2019ve already posted in a public forum, filed a chargeback, or quietly cancelled. Slow support isn\u2019t just an inconvenience\u2014it has a measurable cost that compounds with every missed SLA.</p>

  <h2 class="text-xl">What \u201cslow\u201d actually looks like</h2>
  <p>Customers don\u2019t grade on a curve. The numbers are unforgiving:</p>
  <ul>
    <li>60\u202f% of customers expect a first response within one hour for email support.</li>
    <li>After four hours with no reply, stated intent to churn roughly doubles.</li>
    <li>A single public complaint can reach thousands of potential buyers before your team has opened the ticket.</li>
  </ul>
  <p>For B2B SaaS the stakes are higher still. Enterprise and mid-market contracts carry SLA clauses\u2014breach them and you trigger credits, executive escalations, or renewal reviews.</p>

  <h2 class="text-xl">Four ways slow support costs you money</h2>

  <h3 class="text-lg">1. Direct churn</h3>
  <p>Poor support experience is the second most common reason B2B customers switch vendors, after price. If your median first-response time is above two hours you are actively contributing to churn your sales team is working hard to prevent. A one-hour improvement in FRT can lift retention by several percentage points\u2014worth tens of thousands of pounds annually at \u00a3500\u202fk ARR.</p>

  <h3 class="text-lg">2. Suppressed expansion revenue</h3>
  <p>Upsells and seat expansions happen when the customer feels cared for. A buyer who waited 12 hours on a billing question will not say yes to a higher plan. Slow support depresses NPS, and low NPS depresses net revenue retention\u2014the metric investors care about most.</p>

  <h3 class="text-lg">3. Agent burnout and error rates</h3>
  <p>When inboxes overflow, agents rush. Rushed agents make mistakes: wrong answers, missed context, duplicate replies. Fixing those errors costs more time than handling the original message correctly would have. Burned-out agents also leave\u2014replacement cost for a support hire is typically 1.5\u20132\u00d7 annual salary once recruitment and ramp-up are included.</p>

  <h3 class="text-lg">4. Reputational damage</h3>
  <p>Review sites and community forums are permanent. A thread titled \u201cSupport took three days to reply\u201d suppresses inbound conversions for months. For SaaS products evaluated on trust, reputation is a sales asset\u2014or a liability you pay for on every demo call.</p>

  <h2 class="text-xl">Why response times slip</h2>
  <p>Teams rarely set out to be slow. It happens because of structural problems that get worse as volume grows:</p>
  <ul>
    <li><strong>No triage at arrival.</strong> Urgent and trivial messages hit the same shared inbox with no routing, so agents decide priority by feel.</li>
    <li><strong>Manual categorisation.</strong> The first minutes of every shift are spent sorting rather than responding.</li>
    <li><strong>No hard ownership.</strong> When everyone is responsible, no one is\u2014messages age silently.</li>
    <li><strong>No early-warning alerts.</strong> Team leads can\u2019t see the backlog clearly enough to reallocate before SLAs breach.</li>
    <li><strong>Context switching.</strong> Agents toggle between inboxes, tickets, and CRM, losing minutes per message.</li>
  </ul>

  <h2 class="text-xl">Putting a number on it</h2>
  <p>A rough model for a 10-person SaaS team at \u00a31\u202fm ARR:</p>
  <ul>
    <li>Average contract value: \u00a35,000\u202f/\u202fyear.</li>
    <li>Churn attributable to poor support (conservative estimate): 5\u202f% of churned accounts.</li>
    <li>10 accounts \u00d7 \u00a35,000 = <strong>\u00a350,000\u202f/\u202fyear in preventable churn.</strong></li>
    <li>Expansion suppression: a further \u00a315,000\u2013\u00a330,000 in upsells that never close.</li>
  </ul>
  <p>For most teams, cutting response time delivers more revenue than any single marketing campaign.</p>

  <h2 class="text-xl">What high-performing support teams do differently</h2>
  <ol>
    <li><strong>Triage at the point of arrival.</strong> Messages are categorised and prioritised the moment they land\u2014not when an agent gets to them.</li>
    <li><strong>Hard ownership.</strong> Every message is assigned within minutes. No shared-inbox drift where everyone assumes someone else will reply.</li>
    <li><strong>SLA alerts before the breach.</strong> Alerts fire at 50\u202f% and 80\u202f% of the SLA window, not after the clock runs out.</li>
    <li><strong>AI-assisted drafts.</strong> Agents review and send rather than compose from scratch, cutting handle time by 40\u201360\u202f%.</li>
    <li><strong>Weekly feedback loops.</strong> Leads review SLA attainment and tighten routing rules before problems compound.</li>
  </ol>

  <h2 class="text-xl">How AI triage changes the equation</h2>
  <p>The single highest-leverage change most teams can make is automating the triage step. When AI reads each incoming message, assigns a category (billing, technical, refund, general), scores urgency, and routes it to the right agent\u2014all before a human has opened the inbox\u2014first-response times drop sharply. Teams using this approach typically see:</p>
  <ul>
    <li>Median FRT cut by 60\u201375\u202f% within the first two weeks.</li>
    <li>SLA attainment rising from 70\u202f% to 90\u202f%+ within a month.</li>
    <li>Agent capacity increasing without adding headcount.</li>
  </ul>
  <p>See how it works end-to-end: <a href="/blog/ai-email-triage" class="font-semibold">AI Email Triage \u2014 How It Works</a>.</p>

  <h2 class="text-xl">A five-step starting point</h2>
  <ol>
    <li>Measure your current median FRT and SLA attainment over the past 30 days.</li>
    <li>Identify your top three bottlenecks: unowned messages, miscategorised tickets, or late escalations.</li>
    <li>Define four to six message categories with unambiguous routing rules.</li>
    <li>Set SLA targets by priority (P1: 1\u202fhour, P2: 4\u202fhours, P3: 1 business day).</li>
    <li>Run AI triage in observe mode for one week, review accuracy, then activate routing.</li>
  </ol>

  <div class="mt-6 p-4 rounded-xl border border-indigo-500/30 bg-indigo-500/10">
    <div class="text-sm text-indigo-100 font-semibold mb-1">Ready to cut response times?</div>
    <p class="text-sm text-slate-200">InboxIQ triages, prioritises, and routes every incoming message automatically. Most teams are live in under an hour.</p>
    <div class="mt-3 flex flex-wrap gap-3">
      <a href="/upgrade" class="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-indigo-500 hover:bg-indigo-400 text-sm font-semibold text-white">Start free trial</a>
      <a href="/contact" class="inline-flex items-center gap-2 px-4 py-2 rounded-full border border-indigo-300/50 text-sm font-semibold text-indigo-100 hover:bg-indigo-500/10">Talk to us</a>
    </div>
  </div>

</section>"""

    slug = "cost-of-slow-support"
    existing = BlogPost.query.filter_by(slug=slug).first()
    if existing:
        click.echo(f"skip {slug} (already in DB as {existing.status})")
        return

    post = BlogPost(
        title=TITLE,
        slug=slug,
        status="published",
        content_html=CONTENT_HTML,
        meta_description=META_DESCRIPTION,
        primary_keyword=PRIMARY_KEYWORD,
        secondary_keywords=SECONDARY_KEYWORDS,
        funnel_stage="tofu",
        canonical_url="/blog/cost-of-slow-support",
        internal_links=[{"href": "/blog/ai-email-triage", "label": "AI Email Triage", "rel": "next"}],
        word_count=760,
        read_time_minutes=4,
        published_at=datetime.now(timezone.utc),
    )
    db.session.add(post)
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    click.echo(f"created {slug}")


@app.cli.command("seed-ai-support-agent")
def cli_seed_ai_support_agent():
    """
    Seed the 'ai-support-agent' blog post.
    Safe to re-run: skips if the slug already exists.
    """
    from src.models.content import BlogPost
    from datetime import datetime, timezone

    slug = "ai-support-agent"
    existing = BlogPost.query.filter_by(slug=slug).first()
    if existing:
        click.echo(f"skip {slug} (already in DB as {existing.status})")
        return

    CONTENT_HTML = '<section class="prose prose-invert max-w-none">\n  <p>AI support agents read customer messages, understand intent and urgency, and take action—triaging, replying, and routing—without waiting for a human to sort the queue. Teams adopt them to cut response times, shrink backlogs, and keep SLAs green without adding headcount.</p>\n\n  <h2>Why teams adopt AI support agents</h2>\n  <ul>\n    <li>Slower first-response times during spikes.</li>\n    <li>Manual routing creates inconsistent SLAs.</li>\n    <li>Backlogs spill over weekends or launches.</li>\n    <li>Expensive outsourcing that still misses context.</li>\n  </ul>\n\n  <h2>What an AI support agent does</h2>\n  <ul>\n    <li>Understands intent (billing, refunds, access, bug, sales).</li>\n    <li>Assigns priority with sentiment + SLA + account tier.</li>\n    <li>Creates tickets with owners and due times.</li>\n    <li>Suggests or drafts replies for human review.</li>\n    <li>Escalates edge cases (negative sentiment + VIP domain).</li>\n  </ul>\n\n  <h2>How it works in your stack</h2>\n  <ul>\n    <li>Connect inboxes (Gmail/Outlook/shared) to a triage lane.</li>\n    <li>Run classification (intent, priority, sentiment) per message.</li>\n    <li>Auto-create tickets in your helpdesk with owners and SLA timers.</li>\n    <li>Provide agent-crafted replies for common intents; require human send on risky cases.</li>\n    <li>Log decisions for audit and continuous improvement.</li>\n  </ul>\n\n  <h2>Comparison to legacy workflows</h2>\n  <ul>\n    <li><strong>Manual triage:</strong> slow, inconsistent, high cognitive load.</li>\n    <li><strong>Outsourcing:</strong> faster headcount but low context, higher cost, inconsistent quality.</li>\n    <li><strong>AI agent:</strong> consistent routing, faster FRT, lower cost per ticket, better auditability.</li>\n  </ul>\n\n  <h2>Guardrails for quality</h2>\n  <ul>\n    <li>Confidence thresholds before auto-send.</li>\n    <li>Human-in-loop for negative sentiment, VIP, or payment disputes.</li>\n    <li>Daily spot-checks of 10–20 AI-handled tickets.</li>\n    <li>One-click corrections to retrain routing rules.</li>\n  </ul>\n\n  <h2>Metrics to track (BOFU focus)</h2>\n  <ul>\n    <li><strong>Trial signups and activations:</strong> inbox connected + ticket created.</li>\n    <li><strong>Speed:</strong> first-response time by priority.</li>\n    <li><strong>SLA:</strong> attainment for P1/P2.</li>\n    <li><strong>Automation:</strong> % of tickets auto-routed and auto-drafted replies.</li>\n  </ul>\n\n  <h2>Implementation checklist</h2>\n  <ul>\n    <li>Map top intents and SLAs (P1/P2/P3) with VIP rules.</li>\n    <li>Enable AI triage in observe mode; review 50+ samples.</li>\n    <li>Turn on auto-routing for low-risk intents; keep human send for sensitive cases.</li>\n    <li>Add alerts: P1 unassigned for 15 minutes; P2 no response for 4 hours.</li>\n    <li>Roll out macros + AI drafts; require human send for billing disputes/VIP refunds.</li>\n  </ul>\n\n  <h2>Final thoughts</h2>\n  <p>AI support agents aren’t about replacing humans—they remove the manual work that slows humans down. The result: faster replies, consistent SLAs, calmer teams, and fewer missed opportunities.</p>\n\n  <p class="mt-4 text-indigo-200">Next step: <a href="/upgrade" class="font-semibold">Start a trial and connect your inbox</a>.</p>\n</section>'

    post = BlogPost(
        title="What Is an AI Support Agent? (And Why Teams Are Adopting Them)",
        slug=slug,
        status="published",
        content_html=CONTENT_HTML,
        meta_description="Understand what an AI support agent does, how it improves response times and SLAs, and why teams adopt it to drive trial activation.",
        primary_keyword="ai support agent",
        funnel_stage="bofu",
        canonical_url="/blog/ai-support-agent",
        internal_links=[
            {"href": "/upgrade", "label": "Start trial", "rel": "next"},
            {"href": "/blog/ai-email-triage", "label": "AI Email Triage", "rel": "next"},
        ],
        word_count=420,
        read_time_minutes=2,
        published_at=datetime(2025, 12, 13, 12, 42, 33, tzinfo=timezone.utc),
    )
    db.session.add(post)
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    click.echo(f"created {slug}")


@app.cli.command("seed-email-to-ticket-automation")
def cli_seed_email_to_ticket_automation():
    """
    Seed the 'email-to-ticket-automation' blog post.
    Safe to re-run: skips if the slug already exists.
    """
    from src.models.content import BlogPost
    from datetime import datetime, timezone

    slug = "email-to-ticket-automation"
    existing = BlogPost.query.filter_by(slug=slug).first()
    if existing:
        click.echo(f"skip {slug} (already in DB as {existing.status})")
        return

    CONTENT_HTML = '<section class="prose prose-invert max-w-none">\n  <p>Email to ticket automation turns every inbound customer email into a trackable ticket with an owner, SLA, and audit trail—without manual sorting. This guide shows how to implement it step by step so nothing gets missed and every response is accountable.</p>\n\n  <h2>Why automate email to ticket</h2>\n  <ul>\n    <li>Shared inboxes lose ownership.</li>\n    <li>Urgent messages get buried.</li>\n    <li>Manual tagging is slow and inconsistent.</li>\n    <li>No SLA clock or visibility once an email is “read.”</li>\n  </ul>\n\n  <h2>What great automation does</h2>\n  <ul>\n    <li>Captures every email into a single triage lane.</li>\n    <li>Classifies intent (billing, refunds, access, bug, sales).</li>\n    <li>Sets priority (sentiment + SLA tier + VIP domain).</li>\n    <li>Creates tickets with owner, due time, and status.</li>\n    <li>Routes to the right queue/team automatically.</li>\n    <li>Logs decisions for audit and learning.</li>\n  </ul>\n\n  <h2>Implementation blueprint (step-by-step)</h2>\n  <ol>\n    <li><strong>Centralise inboxes:</strong> forward or connect Gmail/Outlook/shared mailboxes into one triage lane.</li>\n    <li><strong>Define categories and SLAs:</strong> 8–10 intents, plus P1/P2/P3 rules (VIP, sentiment, outage keywords).</li>\n    <li><strong>Enable AI classification:</strong> intent + priority + sentiment; run in observe mode for 1–2 days.</li>\n    <li><strong>Auto-create tickets:</strong> every email becomes a ticket with owner, status, and due time; no unassigned items.</li>\n    <li><strong>Routing rules:</strong> route by category/priority/SLA; send P1 to humans immediately.</li>\n    <li><strong>Alerts:</strong> P1 unassigned &gt;15m; P2 no reply &gt;4h; daily digest of stuck tickets.</li>\n    <li><strong>QA loop:</strong> spot-check 20 tickets daily; correct misroutes; tighten rules weekly.</li>\n  </ol>\n\n  <h2>What to automate vs keep human</h2>\n  <ul>\n    <li><strong>Automate:</strong> categorisation, priority tags, ticket creation, routing, SLA flags, first acknowledgements.</li>\n    <li><strong>Keep human:</strong> empathy, pricing exceptions, complex troubleshooting, high-stakes refunds.</li>\n  </ul>\n\n  <h2>Guardrails</h2>\n  <ul>\n    <li>Confidence thresholds before auto-actions.</li>\n    <li>Human-in-loop for negative sentiment + VIP or payment disputes.</li>\n    <li>One-click reclassify to correct AI decisions.</li>\n    <li>Audit trail on every classification/routing event.</li>\n  </ul>\n\n  <h2>Metrics to track (MOFU)</h2>\n  <ul>\n    <li>Internal clicks to demo/BOFU comparison from this article.</li>\n    <li>Demo views originating from /blog/email-to-ticket-automation.</li>\n    <li>Operational: % auto-routed, median first-response time by priority, SLA attainment for P1/P2.</li>\n  </ul>\n\n  <h2>Expected outcomes</h2>\n  <ul>\n    <li>100% of emails captured as tickets.</li>\n    <li>Manual sorting reduced by 60–80%.</li>\n    <li>Faster FRT and fewer SLA breaches during spikes.</li>\n  </ul>\n\n  <h2>Final thoughts</h2>\n  <p>Email to ticket automation isn’t just speed—it’s accountability. When every email is a ticket with an owner, a clock, and clear routing, teams reply faster, customers stay happier, and SLAs stay green.</p>\n\n  <p class="mt-4 text-indigo-200">Next step: watch the demo and compare AI support agents for your team.</p>\n</section>'

    post = BlogPost(
        title="Email to Ticket Automation: How It Works (Step-by-Step)",
        slug=slug,
        status="published",
        content_html=CONTENT_HTML,
        meta_description="Step-by-step guide to email to ticket automation with AI classification, routing, SLAs, and full accountability.",
        primary_keyword="email to ticket automation",
        funnel_stage="mofu",
        canonical_url="/blog/email-to-ticket-automation",
        internal_links=[
            {"href": "/upgrade#demo", "label": "See the demo", "rel": "next"},
            {"href": "/blog/ai-support-agent", "label": "AI Support Agent", "rel": "next"},
        ],
        word_count=430,
        read_time_minutes=2,
        published_at=datetime(2025, 12, 13, 16, 50, 32, tzinfo=timezone.utc),
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


@app.cli.command("fix-cross-account-connections")
@click.option("--confirm", is_flag=True, default=False, help="Actually delete the bad rows (omit to dry-run).")
def cli_fix_cross_account_connections(confirm: bool):
    """
    Find and remove InboxConnection rows whose email_address matches a User login
    email that belongs to a DIFFERENT account than the connection's account_id.

    These rows are data corruption: a personal mailbox filed under the wrong account.

    Run without --confirm first to review what would be deleted, then re-run with
    --confirm to perform the deletion.
    """
    from src.models.core import InboxConnection, User

    bad_rows = (
        db.session.query(InboxConnection, User)
        .join(User, db.func.lower(User.email) == db.func.lower(InboxConnection.email_address))
        .filter(
            InboxConnection.account_id.isnot(None),
            InboxConnection.account_id != User.account_id,
        )
        .all()
    )

    if not bad_rows:
        click.echo("No cross-account connections found. Database is clean.")
        return

    click.echo(f"Found {len(bad_rows)} bad connection(s):\n")
    for conn, real_owner in bad_rows:
        click.echo(
            f"  id={conn.id}"
            f"  email={conn.email_address}"
            f"  provider={conn.provider}"
            f"  filed_under_account={conn.account_id}"
            f"  real_owner_account={real_owner.account_id}"
            f"  status={conn.status}"
            f"  created={conn.created_at.date() if conn.created_at else 'unknown'}"
        )

    if not confirm:
        click.echo("\nDry run — no rows deleted. Re-run with --confirm to delete.")
        return

    ids_to_delete = [conn.id for conn, _ in bad_rows]
    deleted = (
        InboxConnection.query
        .filter(InboxConnection.id.in_(ids_to_delete))
        .delete(synchronize_session=False)
    )
    try:
        db.session.commit()
        click.echo(f"\nDeleted {deleted} bad connection(s).")
    except Exception as exc:
        db.session.rollback()
        click.echo(f"ERROR: rollback — {exc}")
        raise


@app.cli.command("set-user-role")
@click.option("--email", required=True, help="User email to update.")
@click.option("--role", required=True, type=click.Choice(["owner", "admin", "agent", "viewer", "billing"]), help="Role to assign.")
def cli_set_user_role(email: str, role: str):
    """Set the role for a user by email."""
    from src.models.core import User
    user = User.query.filter(User.email.ilike(email.strip())).first()
    if not user:
        click.echo(f"No user found for {email}")
        return
    old_role = user.role
    user.role = role
    try:
        db.session.commit()
        click.echo(f"Updated {email}: {old_role} → {role}")
    except Exception as exc:
        db.session.rollback()
        click.echo(f"ERROR: {exc}")
        raise


@app.cli.command("remove-inbox-connection")
@click.option("--email", required=True, help="Email address of the inbox connection to remove.")
@click.option("--confirm", is_flag=True, default=False, help="Actually delete the row (omit to dry-run).")
def cli_remove_inbox_connection(email: str, confirm: bool):
    """
    Remove a specific InboxConnection by email address.
    Run without --confirm first to preview, then re-run with --confirm to delete.
    """
    from src.models.core import InboxConnection

    conns = InboxConnection.query.filter(
        db.func.lower(InboxConnection.email_address) == email.strip().lower()
    ).all()

    if not conns:
        click.echo(f"No inbox connection found for {email}")
        return

    for conn in conns:
        click.echo(
            f"  id={conn.id}"
            f"  email={conn.email_address}"
            f"  provider={conn.provider}"
            f"  account_id={conn.account_id}"
            f"  status={conn.status}"
            f"  created={conn.created_at.date() if conn.created_at else 'unknown'}"
        )

    if not confirm:
        click.echo("\nDry run — no rows deleted. Re-run with --confirm to delete.")
        return

    ids = [c.id for c in conns]
    deleted = InboxConnection.query.filter(InboxConnection.id.in_(ids)).delete(synchronize_session=False)
    try:
        db.session.commit()
        click.echo(f"\nDeleted {deleted} connection(s) for {email}.")
    except Exception as exc:
        db.session.rollback()
        click.echo(f"ERROR: rollback — {exc}")
        raise


@app.cli.command("leads-export-csv")
@click.option("--min-fit-score", default=7, show_default=True, help="Minimum fit score to include.")
@click.option("--output", default="-", help="Output file path (default: stdout).")
def cli_leads_export_csv(min_fit_score: int, output: str):
    """
    Export qualified leads to CSV for manual LinkedIn prospecting.
    Includes name, company, email, industry, fit_score, linkedin_url, source, notes.
    """
    from src.models.leads import Lead

    with app.app_context():
        leads = (
            Lead.query
            .filter(Lead.fit_score >= min_fit_score, Lead.deleted.is_(False))
            .order_by(Lead.fit_score.desc())
            .all()
        )

    fieldnames = ["name", "company_name", "email", "industry", "fit_score",
                  "linkedin_url", "source", "qualification_status", "notes"]

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for lead in leads:
        writer.writerow({
            "name": lead.name or "",
            "company_name": lead.company_name or "",
            "email": lead.email or "",
            "industry": lead.industry or "",
            "fit_score": lead.fit_score or "",
            "linkedin_url": lead.linkedin_url or "",
            "source": lead.source or "",
            "qualification_status": lead.qualification_status or "",
            "notes": (lead.notes or "").replace("\n", " "),
        })

    content = buf.getvalue()
    if output == "-":
        click.echo(content, nl=False)
    else:
        Path(output).write_text(content)
        click.echo(f"Exported {len(leads)} leads to {output}")


@app.cli.command("fix-blog-content-html")
@click.option("--slug", default=None, help="Only fix this slug. Omit to fix all published posts.")
def cli_fix_blog_content_html(slug):
    """Strip DSPy artifacts (Meta Description lines) from stored content_html."""
    import re
    from src.models.content import BlogPost

    q = db.session.query(BlogPost).filter(BlogPost.status == "published")
    if slug:
        q = q.filter(BlogPost.slug == slug)
    posts = q.all()
    fixed = 0
    for post in posts:
        html = post.content_html or ""
        cleaned = re.sub(r'<p[^>]*>\s*(<strong>)?Meta Description(</strong>)?:.*?</p>', '', html, flags=re.IGNORECASE | re.DOTALL)
        if cleaned != html:
            post.content_html = cleaned
            fixed += 1
    try:
        db.session.commit()
        click.echo(f"Fixed {fixed} post(s).")
    except Exception:
        db.session.rollback()
        raise


@app.cli.command("register-playwright-mcp")
def cli_register_playwright_mcp():
    """Insert or update the playwright-mcp entry in MCPServerCatalog."""
    from src.models.ai import MCPServerCatalog

    existing = MCPServerCatalog.query.filter_by(label="playwright-mcp").first()
    if existing:
        existing.command = ["npx", "@playwright/mcp@0.0.72"]
        existing.env = {}
        existing.enabled = True
        click.echo("playwright-mcp updated.")
    else:
        db.session.add(MCPServerCatalog(
            label="playwright-mcp",
            command=["npx", "@playwright/mcp@0.0.72"],
            env={},
            enabled=True,
        ))
        click.echo("playwright-mcp registered.")
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise


@app.cli.command("purge-junk-leads")
@click.option("--dry-run/--no-dry-run", default=True, help="Preview without deleting (default). Pass --no-dry-run to delete.")
def cli_purge_junk_leads(dry_run: bool):
    """Remove leads created from job boards, social platforms, and article pages."""
    from src.models.leads import Lead

    _JUNK_EMAIL_DOMAINS = {
        "linkedin.com", "reddit.com", "twitter.com", "x.com", "facebook.com",
        "medium.com", "substack.com", "quora.com", "wikipedia.org",
        "greenhouse.io", "lever.co", "indeed.com", "glassdoor.com",
        "youtube.com", "instagram.com", "tiktok.com",
    }
    _ARTICLE_PREFIXES = (
        "the ultimate guide", "how to", "how do", "why ", "what is",
        "top ", "best ", "r/", "guide to", "guide:",
    )
    _ARTICLE_KEYWORDS = ["guide", "tutorial", "article", " vs ", "hiring ", " job ", " jobs"]

    all_leads = db.session.query(Lead).filter(Lead.deleted.is_(False)).all()
    to_delete = []

    for lead in all_leads:
        email_domain = lead.email.split("@")[-1].lower() if lead.email and "@" in lead.email else ""
        name_lower = (lead.company_name or "").lower()

        if email_domain in _JUNK_EMAIL_DOMAINS:
            to_delete.append((lead.id, lead.company_name, f"junk email: {lead.email}"))
            continue
        if len(lead.company_name or "") > 70:
            to_delete.append((lead.id, lead.company_name, "name too long (article title)"))
            continue
        if any(name_lower.startswith(p) for p in _ARTICLE_PREFIXES):
            to_delete.append((lead.id, lead.company_name, "article title prefix"))
            continue
        if any(kw in name_lower for kw in _ARTICLE_KEYWORDS):
            to_delete.append((lead.id, lead.company_name, "article title keyword"))

    if not to_delete:
        click.echo("No junk leads found.")
        return

    click.echo(f"{'[DRY RUN] Would delete' if dry_run else 'Deleting'} {len(to_delete)} junk leads:")
    for lead_id, name, reason in to_delete:
        click.echo(f"  {lead_id[:8]}  {(name or '')[:50]:<50}  ({reason})")

    if not dry_run:
        ids = [r[0] for r in to_delete]
        db.session.query(Lead).filter(Lead.id.in_(ids)).update(
            {"deleted": True}, synchronize_session=False
        )
        try:
            db.session.commit()
            click.echo(f"Soft-deleted {len(ids)} leads.")
        except Exception:
            db.session.rollback()
            raise
    else:
        click.echo("\nRun with --no-dry-run to actually delete.")


@app.cli.command("export-prospects-csv")
@click.option("--min-score", default=4, show_default=True, help="Minimum fit_score to include")
@click.option("--output", default="prospects.csv", show_default=True, help="Output file path")
def cli_export_prospects_csv(min_score: int, output: str):
    """Export discovered leads to CSV for manual LinkedIn outreach."""
    import csv
    from src.models.leads import Lead

    leads = (
        db.session.query(Lead)
        .filter(
            Lead.fit_score >= min_score,
            Lead.deleted.is_(False),
            Lead.company_name.isnot(None),
        )
        .order_by(Lead.fit_score.desc(), Lead.created_at.desc())
        .all()
    )

    if not leads:
        click.echo(f"No leads found with fit_score >= {min_score}.")
        return

    fields = [
        "name", "company_name", "industry", "email",
        "linkedin_url", "fit_score", "intent_score",
        "qualification_status", "source", "notes", "created_at",
    ]

    with open(output, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for lead in leads:
            writer.writerow({
                "name": lead.name or "",
                "company_name": lead.company_name or "",
                "industry": lead.industry or "",
                "email": lead.email or "",
                "linkedin_url": lead.linkedin_url or "",
                "fit_score": lead.fit_score or 0,
                "intent_score": lead.intent_score or 0,
                "qualification_status": lead.qualification_status or "",
                "source": lead.source or "",
                "notes": lead.notes or "",
                "created_at": lead.created_at.isoformat() if lead.created_at else "",
            })

    click.echo(f"Exported {len(leads)} leads to {output}")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
