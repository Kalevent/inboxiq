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
            Lead.deleted != True,
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
            draft_result = drafter(
                prospect_name=prospect.name.split()[0],
                job_title=prospect.job_title or "professional",
                company_name=prospect.company_name or "your company",
                industry=prospect.industry or "SaaS",
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
