"""LinkedIn outreach cadence tasks."""
import logging

from celery import shared_task

from src.extensions import db

log = logging.getLogger(__name__)


# Default ICP shape returned by GET /api/v1/linkedin/icp when an account has
# no ICPConfig row yet. New accounts inherit Oliver (ICP 1) per ICP.md at
# the project root — that doc is the source of truth, update it FIRST and
# this constant SECOND. Imported from src/api/v1/linkedin.py — keep the keys
# stable; the Settings UI renders them. Removing this symbol crashes the
# endpoint with ImportError (production incident 2026-05-08).
_ICP_DEFAULTS = {
    "titles": ["Founder", "Co-founder", "Head of Operations"],
    "industries": ["B2B SaaS"],
    "company_size_min": 10,
    "company_size_max": 50,
    "geographies": ["UK", "EU", "US"],
}


def _get_post_by_slug(slug: str):
    from src.models.content import BlogPost
    return db.session.query(BlogPost).filter_by(slug=slug, status="published").first()


def _prospect_to_digest_item(prospect, action_label: str, msg_draft: str, with_post: bool = False) -> dict:
    from src.models.content import BlogPost
    item = {
        "prospect_id": prospect.id,
        "name": prospect.name,
        "company_name": prospect.company_name or "",
        "job_title": prospect.job_title or "",
        "linkedin_url": prospect.linkedin_url,
        "action_label": action_label,
        "msg_draft": msg_draft or "",
    }
    if with_post and prospect.suggested_post_id:
        post = db.session.query(BlogPost).filter_by(id=prospect.suggested_post_id).first()
        if post:
            item["suggested_post_title"] = post.title
            item["suggested_post_url"] = f"https://kalevent.com/blog/{post.slug}"
            notes = prospect.notes or ""
            for line in notes.splitlines():
                if line.startswith("[post match]"):
                    item["match_reason"] = line.replace("[post match]", "").strip()
                    break
    return item


def _send_digest_core(account_id: int) -> dict:
    from datetime import datetime, timezone
    from src.models.campaigns import LinkedInProspect
    from src.notifications.emails import send_linkedin_digest
    from flask import current_app

    now = datetime.now(timezone.utc)
    notify_email = current_app.config.get("ADMIN_EMAILS", "").split(",")[0].strip()
    if not notify_email:
        log.warning("linkedin.send_digest: ADMIN_EMAILS not configured, skipping")
        return {"sent": False, "count": 0}

    due = []

    # All pending connection requests — include those without drafts so nothing is silently dropped
    pending = db.session.query(LinkedInProspect).filter(
        LinkedInProspect.account_id == account_id,
        LinkedInProspect.status == "pending",
    ).all()
    for p in pending:
        due.append(_prospect_to_digest_item(p, "Send connection request", p.msg_1_draft))

    # Message 2 due
    msg2_due = db.session.query(LinkedInProspect).filter(
        LinkedInProspect.account_id == account_id,
        LinkedInProspect.status == "connected",
        LinkedInProspect.message_2_due_at <= now,
        LinkedInProspect.msg_2_draft.isnot(None),
    ).all()
    for p in msg2_due:
        days_ago = (now - p.connected_at.replace(tzinfo=timezone.utc)).days if p.connected_at else "?"
        due.append(_prospect_to_digest_item(p, f"Send message 2 (connected {days_ago} days ago)", p.msg_2_draft, with_post=True))

    # Message 3 due
    msg3_due = db.session.query(LinkedInProspect).filter(
        LinkedInProspect.account_id == account_id,
        LinkedInProspect.status == "message_2_sent",
        LinkedInProspect.message_3_due_at <= now,
        LinkedInProspect.msg_3_draft.isnot(None),
    ).all()
    for p in msg3_due:
        due.append(_prospect_to_digest_item(p, "Send message 3 — soft ask", p.msg_3_draft))

    # Replied — needs qualify/disqualify decision
    replied = db.session.query(LinkedInProspect).filter(
        LinkedInProspect.account_id == account_id,
        LinkedInProspect.status == "replied",
    ).all()
    for p in replied:
        due.append(_prospect_to_digest_item(p, "Follow up — prospect replied, qualify or disqualify", ""))

    if not due:
        log.info("linkedin.send_digest: no actions due today for account %s", account_id)
        return {"sent": False, "count": 0}

    order = {"Send message 3": 0, "Send message 2": 1, "Send connection": 2, "Follow up": 3}
    due.sort(key=lambda x: next((v for k, v in order.items() if x["action_label"].startswith(k)), 4))

    date_label = now.strftime("%a %d %b")
    sent = send_linkedin_digest(notify_email, due, date_label)
    log.info("linkedin.send_digest: account=%s sent=%s count=%d", account_id, sent, len(due))
    return {"sent": sent, "count": len(due)}


def _all_account_ids() -> list:
    from src.models.core import Account
    return [row.id for row in db.session.query(Account.id).all()]


@shared_task(name="linkedin.enrich_linkedin_urls")
def enrich_linkedin_urls():
    """Enrich qualifying leads with LinkedIn URLs via SearXNG + Playwright."""
    from src.agents.linkedin_cadence import LinkedInCadenceAgent
    for account_id in _all_account_ids():
        LinkedInCadenceAgent(account_id=account_id).execute(
            "Enrich qualifying leads with LinkedIn URLs. "
            "For EACH lead from get_qualifying_leads:\n"
            "  1. Call find_decision_makers with the lead's company domain.\n"
            "  2. From the candidates, pick at most ONE profile where BOTH the name "
            "matches the lead AND the current employer matches the lead's company. "
            "If no candidate satisfies both, SKIP this lead — do not call enrich_lead_linkedin_url.\n"
            "  3. Verify the chosen profile by browser_navigate + browser_snapshot. "
            "If the snapshot shows a different person or different employer, SKIP.\n"
            "  4. Call enrich_lead_linkedin_url with the verified URL, name, and job_title from the profile.\n"
            "Stop after processing 10 leads or when no qualifying leads remain. "
            "It is BETTER to skip a lead than to attach a wrong URL."
        )


@shared_task(name="linkedin.discover_prospects")
def discover_prospects():
    """Promote enriched leads into the prospect queue."""
    from src.models.leads import Lead
    from src.agents.linkedin_cadence import LinkedInCadenceAgent

    leads = (
        db.session.query(Lead)
        .filter(
            Lead.linkedin_url.isnot(None),
            Lead.fit_score >= 7,
            Lead.outreach_unsubscribed_at.is_(None),
            Lead.deleted.is_(False),
        )
        .all()
    )

    created = 0
    for lead in leads:
        agent = LinkedInCadenceAgent(account_id=lead.account_id)
        result = agent._tool_add_to_prospect_queue(str(lead.id))
        if result.get("created"):
            created += 1

    log.info("linkedin.discover_prospects: created %d new prospects", created)
    return {"created": created}


@shared_task(name="linkedin.draft_messages")
def draft_messages_task():
    """Draft outreach messages for pending prospects.

    First name is resolved in Python before the LLM is called — the model never
    derives or substitutes names, preventing cross-prospect name contamination.
    """
    import dspy as _dspy
    from src.dspy.config import _configure_dspy
    from src.dspy.signatures import build_linkedin_message_draft
    from src.models.campaigns import LinkedInProspect
    from src.models.content import BlogPost
    from src.sanitize import sanitize_html

    _configure_dspy()
    draft_module = build_linkedin_message_draft(_dspy)

    for account_id in _all_account_ids():
        prospects = (
            db.session.query(LinkedInProspect)
            .filter(
                LinkedInProspect.account_id == account_id,
                LinkedInProspect.status == "pending",
                LinkedInProspect.msg_1_draft.is_(None),
            )
            .order_by(LinkedInProspect.created_at.asc())
            .all()
        )

        for prospect in prospects:
            # Resolve first name in Python — never delegate this to the LLM
            raw_name = (prospect.name or "").strip()
            first_name = raw_name.split()[0] if raw_name else "there"

            # Find a relevant published blog post for msg_2
            industry = (prospect.industry or "").strip()
            post = None
            if industry:
                post = (
                    db.session.query(BlogPost)
                    .filter(
                        BlogPost.status == "published",
                        BlogPost.title.ilike(f"%{industry.split()[0]}%"),
                    )
                    .order_by(BlogPost.published_at.desc())
                    .first()
                )
            if not post:
                post = (
                    db.session.query(BlogPost)
                    .filter(BlogPost.status == "published")
                    .order_by(BlogPost.published_at.desc())
                    .first()
                )

            blog_url = f"https://kalevent.com/blog/{post.slug}" if post else ""

            try:
                result = draft_module(
                    first_name=first_name,
                    company_name=prospect.company_name or "",
                    job_title=prospect.job_title or "",
                    industry=industry,
                    product_name="InboxIQ — AI email triage and inbox automation for support teams",
                    blog_post_url=blog_url,
                )
                prospect.msg_1_draft = sanitize_html(result.msg_1)
                prospect.msg_2_draft = sanitize_html(result.msg_2)
                prospect.msg_3_draft = sanitize_html(result.msg_3)
                if post:
                    prospect.suggested_post_id = post.id
                db.session.commit()
                log.info("linkedin.draft_messages: drafted for prospect %s (first_name=%s)", prospect.id, first_name)
            except Exception:
                db.session.rollback()
                log.exception("linkedin.draft_messages: failed for prospect %s", prospect.id)


@shared_task(name="linkedin.send_digest")
def send_digest_task():
    """Send today's LinkedIn action digest email."""
    for account_id in _all_account_ids():
        _send_digest_core(account_id)


@shared_task(name="linkedin.expire_pending_connections")
def expire_pending_connections():
    """Disqualify connection requests that have not been accepted within 21 days."""
    from datetime import datetime, timezone, timedelta
    from src.models.campaigns import LinkedInProspect

    cutoff = datetime.now(timezone.utc) - timedelta(days=21)
    expired = db.session.query(LinkedInProspect).filter(
        LinkedInProspect.status == "connection_sent",
        LinkedInProspect.connection_sent_at <= cutoff,
    ).all()

    count = 0
    for prospect in expired:
        try:
            prospect.status = "disqualified"
            notes = prospect.notes or ""
            prospect.notes = notes + "\n[auto-disqualified] Connection request not accepted after 21 days."
            db.session.commit()
            count += 1
        except Exception:
            db.session.rollback()
            log.exception("linkedin.expire_pending_connections: failed to disqualify prospect %s", prospect.id)

    log.info("linkedin.expire_pending_connections: disqualified %d prospects", count)
    return {"disqualified": count}


@shared_task(name="linkedin.update_acceptance_ratio_gauge")
def update_acceptance_ratio_gauge():
    """Refresh the inboxiq_linkedin_acceptance_ratio gauge per account (7d rolling)."""
    from datetime import datetime, timezone, timedelta
    from src.models.campaigns import LinkedInProspect
    from src.monitoring.metrics import linkedin_acceptance_ratio
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    for account_id in _all_account_ids():
        sent = db.session.query(LinkedInProspect).filter(
            LinkedInProspect.account_id == account_id,
            LinkedInProspect.connection_sent_at >= cutoff,
        ).count()
        accepted = db.session.query(LinkedInProspect).filter(
            LinkedInProspect.account_id == account_id,
            LinkedInProspect.connected_at >= cutoff,
        ).count()
        ratio = (accepted / sent) if sent > 0 else 0.0
        linkedin_acceptance_ratio.labels(account_id=str(account_id)).set(ratio)


@shared_task(name="linkedin.review_mismatched_prospects")
def review_mismatched_prospects():
    """Flip prospect rows whose name and URL slug share no meaningful tokens.

    The enrichment agent picks LinkedIn URLs via LLM judgement, with no
    deterministic check that the URL belongs to the named lead. This sweeps
    rows already in the cadence whose stored name/URL pair fails the same
    token-overlap heuristic the enrichment guardrail now applies on write,
    moving them to needs_review so they drop out of the daily digest.
    """
    from src.models.campaigns import LinkedInProspect
    from src.agents.linkedin_cadence import name_url_tokens_match

    active_statuses = ["pending", "connection_sent", "connected", "message_2_sent", "message_3_sent", "replied"]
    candidates = db.session.query(LinkedInProspect).filter(
        LinkedInProspect.status.in_(active_statuses),
        LinkedInProspect.name.isnot(None),
        LinkedInProspect.linkedin_url.isnot(None),
    ).all()

    flagged = 0
    for prospect in candidates:
        if name_url_tokens_match(prospect.name, prospect.linkedin_url):
            continue
        prospect.status = "needs_review"
        notes = prospect.notes or ""
        prospect.notes = notes + f"\n[auto-flagged] name={prospect.name!r} did not match URL slug {prospect.linkedin_url}"
        flagged += 1

    if flagged:
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            log.exception("linkedin.review_mismatched_prospects: commit failed")
            return {"flagged": 0}

    log.info("linkedin.review_mismatched_prospects: flagged %d prospects", flagged)
    return {"flagged": flagged}
