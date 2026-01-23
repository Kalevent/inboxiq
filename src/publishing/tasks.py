"""
Celery tasks for publishing workflows.
"""
from __future__ import annotations

from src.celery_inboxiq import celery
from src.extensions import db
from src.models import BlogPost
from src.publishing.service import generate_blog_content


@celery.task(name="publishing.draft_blog_task")
def draft_blog_task(blog_id: str) -> None:
    post = BlogPost.query.filter_by(id=blog_id).first()
    if not post:
        return

    try:
        post.status = "generating"
        db.session.commit()

        md_text, rendered, prompt = generate_blog_content(post.brief_json or {})
        post.markdown = md_text
        post.rendered_html = rendered
        post.content_html = rendered
        post.last_prompt = prompt
        post.status = "ready"
        db.session.commit()
    except Exception as exc:
        post.status = "failed"
        post.last_prompt = f"error: {exc}"
        db.session.commit()
        raise
