"""LinkedIn outreach cadence tasks."""
import json
import logging

from celery import shared_task

from src.dspy import _configure_dspy
from src.extensions import db
from skills.linkedin_cadence.scripts.draft_messages import MessageDrafterModule
from skills.linkedin_cadence.scripts.match_post import BlogPostMatcherModule

log = logging.getLogger(__name__)

_ICP_DEFAULTS = {
    "titles": ["Founder", "Head of Support", "Operations Lead", "Customer Success Lead"],
    "industries": ["B2B SaaS", "Software"],
    "company_size_min": 10,
    "company_size_max": 50,
    "geographies": ["UK", "US", "Nigeria"],
}


def _load_icp(account_id: int) -> dict:
    from src.models.marketing import ICPConfig
    config = db.session.query(ICPConfig).filter_by(account_id=account_id).first()
    if not config:
        return _ICP_DEFAULTS
    return {
        "titles": config.titles or _ICP_DEFAULTS["titles"],
        "industries": config.industries or _ICP_DEFAULTS["industries"],
        "company_size_min": config.company_size_min,
        "company_size_max": config.company_size_max,
        "geographies": config.geographies or _ICP_DEFAULTS["geographies"],
    }


@shared_task(name="linkedin.discover_prospects")
def discover_prospects():
    """
    Promote qualifying Leads into the LinkedIn outreach queue.
    Runs daily at 7:00am. Idempotent — safe to re-run.
    """
    from src.models.leads import Lead
    from src.models.campaigns import LinkedInProspect

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
        account_id = lead.account_id
        exists = db.session.query(LinkedInProspect).filter_by(
            account_id=account_id,
            linkedin_url=lead.linkedin_url,
        ).first()
        if exists:
            continue

        prospect = LinkedInProspect(
            account_id=account_id,
            lead_id=lead.id,
            name=lead.name,
            company_name=lead.company_name,
            job_title=None,
            industry=lead.industry,
            linkedin_url=lead.linkedin_url,
            source="auto",
            status="pending",
            fit_score=lead.fit_score,
        )
        try:
            db.session.add(prospect)
            db.session.commit()
            created += 1
        except Exception:
            db.session.rollback()
            log.exception("Failed to create LinkedInProspect for lead %s", lead.id)

    log.info("linkedin.discover_prospects: created %d new prospects", created)
    return {"created": created}


def _get_published_posts() -> list[dict]:
    """Return [{slug, title, primary_keyword}] for all published blog posts."""
    from src.models.content import BlogPost
    posts = db.session.query(
        BlogPost.slug, BlogPost.title, BlogPost.primary_keyword
    ).filter_by(status="published").all()
    return [
        {"slug": p.slug, "title": p.title, "primary_keyword": p.primary_keyword or ""}
        for p in posts
    ]


def _get_post_by_slug(slug: str):
    from src.models.content import BlogPost
    return db.session.query(BlogPost).filter_by(slug=slug, status="published").first()


@shared_task(name="linkedin.draft_messages")
def draft_messages_task():
    """
    Draft all 3 LinkedIn messages for pending prospects with no drafts.
    Runs daily at 7:30am, after discover_prospects.
    """
    from src.models.campaigns import LinkedInProspect

    prospects = (
        db.session.query(LinkedInProspect)
        .filter(
            LinkedInProspect.status == "pending",
            LinkedInProspect.msg_1_draft.is_(None),
        )
        .all()
    )

    if not prospects:
        log.info("linkedin.draft_messages: no prospects to draft")
        return {"drafted": 0}

    _configure_dspy()
    drafter = MessageDrafterModule()
    matcher = BlogPostMatcherModule()
    posts = _get_published_posts()
    posts_json = json.dumps(posts)

    drafted = 0
    for prospect in prospects:
        try:
            first_name = prospect.name.split()[0] if prospect.name and prospect.name.strip() else "there"
            draft_result = drafter(
                prospect_name=first_name,
                job_title=prospect.job_title or "professional",
                company_name=prospect.company_name or "your company",
                industry=prospect.industry or "SaaS",
                product_name="InboxIQ",
            )

            suggested_post_id = None
            match_reason = None
            if posts:
                match_result = matcher(
                    prospect_industry=prospect.industry or "SaaS",
                    job_title=prospect.job_title or "professional",
                    posts_json=posts_json,
                )
                post = _get_post_by_slug(match_result.selected_slug)
                if post:
                    suggested_post_id = post.id
                    match_reason = match_result.reason
                    msg_2 = draft_result.msg_2.replace(
                        "[POST_TITLE]", post.title
                    ).replace(
                        "[POST_URL]", f"https://kalevent.com/blog/{post.slug}"
                    )
                else:
                    msg_2 = draft_result.msg_2
            else:
                msg_2 = draft_result.msg_2

            prospect.msg_1_draft = draft_result.msg_1
            prospect.msg_2_draft = msg_2
            prospect.msg_3_draft = draft_result.msg_3
            prospect.suggested_post_id = suggested_post_id
            if match_reason:
                prospect.notes = (prospect.notes or "") + f"\n[post match] {match_reason}"

            db.session.commit()
            drafted += 1
        except Exception:
            db.session.rollback()
            log.exception("Failed to draft messages for prospect %s", prospect.id)

    log.info("linkedin.draft_messages: drafted %d prospects", drafted)
    return {"drafted": drafted}


@shared_task(name="linkedin.send_digest")
def send_digest_task():
    """
    Collect all prospects due for action today and email the digest.
    Runs daily at 8:00am, after draft_messages_task.
    """
    from datetime import datetime, timezone
    from src.models.campaigns import LinkedInProspect
    from src.models.content import BlogPost
    from src.notifications.emails import send_linkedin_digest
    from flask import current_app

    now = datetime.now(timezone.utc)
    notify_email = current_app.config.get("ADMIN_EMAILS", "").split(",")[0].strip()
    if not notify_email:
        log.warning("linkedin.send_digest: ADMIN_EMAILS not configured, skipping")
        return {"sent": False}

    due = []

    # Connection requests ready to send (pending with drafts)
    pending = db.session.query(LinkedInProspect).filter(
        LinkedInProspect.status == "pending",
        LinkedInProspect.msg_1_draft.isnot(None),
    ).all()
    for p in pending:
        due.append(_prospect_to_digest_item(p, "Send connection request", p.msg_1_draft))

    # Message 2 due
    msg2_due = db.session.query(LinkedInProspect).filter(
        LinkedInProspect.status == "connected",
        LinkedInProspect.message_2_due_at <= now,
        LinkedInProspect.msg_2_draft.isnot(None),
    ).all()
    for p in msg2_due:
        days_ago = (now - p.connected_at.replace(tzinfo=timezone.utc)).days if p.connected_at else "?"
        due.append(_prospect_to_digest_item(p, f"Send message 2 (connected {days_ago} days ago)", p.msg_2_draft, with_post=True))

    # Message 3 due
    msg3_due = db.session.query(LinkedInProspect).filter(
        LinkedInProspect.status == "message_2_sent",
        LinkedInProspect.message_3_due_at <= now,
        LinkedInProspect.msg_3_draft.isnot(None),
    ).all()
    for p in msg3_due:
        due.append(_prospect_to_digest_item(p, "Send message 3 — soft ask", p.msg_3_draft))

    # Replied — needs qualify/disqualify decision
    replied = db.session.query(LinkedInProspect).filter(
        LinkedInProspect.status == "replied",
    ).all()
    for p in replied:
        due.append(_prospect_to_digest_item(p, "Follow up — prospect replied, qualify or disqualify", p.msg_3_draft or ""))

    if not due:
        log.info("linkedin.send_digest: no actions due today")
        return {"sent": False, "count": 0}

    # Order: msg3 first, then msg2, then connection requests, then replied
    order = {"Send message 3": 0, "Send message 2": 1, "Send connection": 2, "Follow up": 3}
    due.sort(key=lambda x: next((v for k, v in order.items() if x["action_label"].startswith(k)), 4))

    date_label = now.strftime("%a %d %b")
    sent = send_linkedin_digest(notify_email, due, date_label)
    log.info("linkedin.send_digest: sent=%s count=%d", sent, len(due))
    return {"sent": sent, "count": len(due)}


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
