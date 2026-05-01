"""LinkedIn outreach cadence tasks."""
import logging

from celery import shared_task

from src.extensions import db

log = logging.getLogger(__name__)


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

    # Connection requests ready to send (pending with drafts)
    pending = db.session.query(LinkedInProspect).filter(
        LinkedInProspect.account_id == account_id,
        LinkedInProspect.status == "pending",
        LinkedInProspect.msg_1_draft.isnot(None),
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
            "For each lead from get_qualifying_leads: call find_decision_makers via MCP, "
            "verify with browser_navigate and browser_snapshot, then call enrich_lead_linkedin_url."
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
    """Draft outreach messages for pending prospects."""
    from src.agents.linkedin_cadence import LinkedInCadenceAgent
    for account_id in _all_account_ids():
        LinkedInCadenceAgent(account_id=account_id).execute(
            "For each prospect from get_pending_prospects: "
            "1) Call get_relevant_blog_post with the prospect's industry to find a relevant blog post. "
            "2) Draft three LinkedIn outreach messages — msg_1 is a concise connection request (under 200 chars), "
            "msg_2 is a value-add message that references the blog post URL if one was found, "
            "msg_3 is a soft ask for a 15-minute call. "
            "3) Call save_drafted_messages with all three drafts and the suggested_post_id if a blog post was found."
        )


@shared_task(name="linkedin.send_digest")
def send_digest_task():
    """Send today's LinkedIn action digest email."""
    for account_id in _all_account_ids():
        _send_digest_core(account_id)
