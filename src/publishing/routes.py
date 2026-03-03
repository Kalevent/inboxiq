from __future__ import annotations

import json
import os
import re
from datetime import datetime
from typing import Any

from flask import abort, jsonify, request, send_file, render_template, current_app, redirect, url_for
from flask_jwt_extended import jwt_required, get_jwt_identity

from src.extensions import db
from src.ai.client import call_openai
from src.publishing import bp
from src.models.publishing import NewsletterDraft, WhitepaperDraft
from src.publishing.service import (
    create_blog_draft,
    list_blogs,
    publish_blog,
    _read_icp,
)
from src.models.content import BlogPost

try:
    from app.publishing.controllers import SYSTEM_NEWSLETTER, SYSTEM_WHITEPAPER
except Exception:
    SYSTEM_NEWSLETTER = ""
    SYSTEM_WHITEPAPER = ""


def _safe_json() -> dict[str, Any]:
    try:
        payload = request.get_json() or {}
    except Exception:
        payload = {}
    return payload if isinstance(payload, dict) else {}


def _render_newsletter_sync(draft: NewsletterDraft):
    icp = _read_icp()
    audience = (draft.brief_json or {}).get("audience", "")
    brief = (draft.brief_json or {}).get("brief", "")
    feedback = (draft.brief_json or {}).get("feedback", "")
    brief_block = f"Audience: {audience}\n\nBrief: {brief}\n\nFeedback: {feedback}\n\nICP:\n{icp}"
    llm_resp = call_openai(
        [
            {"role": "system", "content": SYSTEM_NEWSLETTER},
            {"role": "user", "content": brief_block},
        ],
        max_tokens=1200,
    )
    content = (llm_resp or {}).get("content") or "{}"
    try:
        payload = json.loads(content or "{}")
    except json.JSONDecodeError:
        fixed = call_openai(
            [
                {"role": "system", "content": "Return strict, valid JSON only."},
                {"role": "user", "content": content},
            ],
            max_tokens=800,
        )
        payload = json.loads((fixed or {}).get("content") or "{}")

    from flask import render_template  # local import to avoid circulars

    html = render_template("email/newsletter.html.j2", **payload)
    draft.rendered_html = html
    draft.status = "ready"
    db.session.commit()
    return html


def _render_whitepaper_sync(draft: WhitepaperDraft):
    icp = _read_icp()
    brief = (draft.brief_json or {}).get("brief", "")
    audience = (draft.brief_json or {}).get("audience", "")
    msg = f"Audience: {audience}\n\nBrief:\n{brief}\n\n---\nICP:\n{icp}"
    llm_resp = call_openai(
        [
            {"role": "system", "content": SYSTEM_WHITEPAPER},
            {"role": "user", "content": msg},
        ],
        max_tokens=1500,
    )
    md = (llm_resp or {}).get("content") or ""
    draft.markdown = md
    draft.status = "ready"
    db.session.commit()
    return md


@bp.post("/blog/draft")
@jwt_required(optional=True)
def blog_draft():
    payload = _safe_json()
    sync = bool(payload.get("sync", True))
    try:
        post, meta = create_blog_draft(payload, run_async=not sync)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:  # pragma: no cover - defensive
        return jsonify({"error": f"Failed to create draft: {exc}"}), 500

    if not sync:
        # Queue async generation via Celery
        try:
            from src.publishing.tasks import draft_blog_task

            draft_blog_task.delay(post.id)
            meta["task"] = "queued"
        except Exception as exc:
            meta["task_error"] = str(exc)

    return (
        jsonify(
            {
                "id": post.id,
                "slug": post.slug,
                "status": post.status,
                "queued": bool(meta.get("queued")),
            }
        ),
        201,
    )


@bp.post("/newsletter/draft")
@jwt_required(optional=True)
def newsletter_draft():
    payload = _safe_json()
    campaign_title = (payload.get("campaign_title") or "").strip()
    audience = (payload.get("audience") or "").strip()
    brief = (payload.get("brief") or "").strip()
    sync = bool(payload.get("sync", True))
    if not campaign_title or not audience or not brief:
        return jsonify({"error": "`campaign_title`, `audience`, and `brief` are required."}), 400

    draft = NewsletterDraft(
        campaign_title=campaign_title,
        audience=audience,
        brief_json=payload,
        status="generating" if sync else "queued",
        created_at=datetime.utcnow(),
    )
    db.session.add(draft)
    db.session.commit()

    if not sync:
        try:
            from app.publishing.tasks import draft_newsletter_task  # legacy Celery task

            draft_newsletter_task.delay(str(draft.id))
            return jsonify({"id": str(draft.id), "status": "queued"}), 202
        except Exception:
            # Fall back to sync generation
            draft.status = "generating"
            db.session.commit()

    try:
        _render_newsletter_sync(draft)
    except Exception as exc:
        db.session.delete(draft)
        db.session.commit()
        return jsonify({"error": f"Newsletter generation error: {exc}"}), 502

    return jsonify({"id": str(draft.id), "status": "ready", "preview_url": f"/publishing/preview/{draft.id}"}), 201


@bp.get("/newsletter/drafts")
@jwt_required(optional=True)
def newsletter_drafts():
    drafts = NewsletterDraft.query.order_by(NewsletterDraft.created_at.desc()).all()
    return jsonify(
        {
            "drafts": [
                {
                    "id": str(d.id),
                    "campaign_title": d.campaign_title,
                    "status": d.status,
                    "created_at": d.created_at.isoformat() if d.created_at else None,
                }
                for d in drafts
            ]
        }
    )


@bp.get("/newsletter/drafts/view")
@jwt_required(optional=True)
def newsletter_drafts_view():
    # Keep this view gated; drafts shouldn't be public even if the JSON endpoint is optional.
    if not get_jwt_identity():
        abort(401)

    status = (request.args.get("status") or "all").lower()
    q = (request.args.get("q") or "").strip()
    sort = (request.args.get("sort") or "newest").lower()

    drafts_query = NewsletterDraft.query
    if status != "all":
        drafts_query = drafts_query.filter(NewsletterDraft.status == status)
    if q:
        like = f"%{q}%"
        drafts_query = drafts_query.filter(
            NewsletterDraft.campaign_title.ilike(like) | NewsletterDraft.audience.ilike(like)
        )

    if sort == "oldest":
        drafts_query = drafts_query.order_by(NewsletterDraft.created_at.asc())
    else:
        drafts_query = drafts_query.order_by(NewsletterDraft.created_at.desc())

    drafts = drafts_query.all()
    counts: dict[str, int] = {}
    for d in drafts:
        counts[d.status] = counts.get(d.status, 0) + 1

    return render_template("publishing/newsletter_draft_list.html", drafts=drafts, counts=counts)


@bp.post("/newsletter/publish/<id>")
@jwt_required(optional=True)
def newsletter_publish(id: str):
    d = NewsletterDraft.query.get(id)
    if not d:
        return jsonify({"error": "Draft not found"}), 404
    if d.status != "ready":
        return jsonify({"error": f"Draft status is '{d.status}', cannot publish."}), 409
    d.status = "published"
    db.session.commit()
    return jsonify({"id": str(d.id), "status": "published"})


@bp.get("/preview/<id>")
@jwt_required(optional=True)
def preview(id: str):
    d = NewsletterDraft.query.get(id)
    if not d:
        return jsonify({"error": "Draft not found"}), 404
    if not d.rendered_html:
        return jsonify({"error": "Draft not yet rendered."}), 409
    return d.rendered_html


@bp.post("/whitepaper/draft")
@jwt_required(optional=True)
def whitepaper_draft():
    payload = _safe_json()
    title = (payload.get("title") or "").strip()
    brief = (payload.get("brief") or "").strip()
    audience = (payload.get("audience") or "").strip()
    sync = bool(payload.get("sync", True))
    if not title or not brief or not audience:
        return jsonify({"error": "`title`, `audience`, and `brief` are required."}), 400

    draft = WhitepaperDraft(
        title=title,
        brief_json=payload,
        status="generating" if sync else "queued",
        created_at=datetime.utcnow(),
    )
    db.session.add(draft)
    db.session.commit()

    if not sync:
        try:
            from app.publishing.tasks import draft_whitepaper_task

            draft_whitepaper_task.delay(str(draft.id))
            return jsonify({"id": str(draft.id), "status": "queued"}), 202
        except Exception:
            draft.status = "generating"
            db.session.commit()

    try:
        _render_whitepaper_sync(draft)
    except Exception as exc:
        db.session.delete(draft)
        db.session.commit()
        return jsonify({"error": f"Whitepaper generation error: {exc}"}), 502

    return jsonify({"id": str(draft.id), "status": "ready"}), 201


@bp.get("/whitepaper/download/<id>")
@jwt_required(optional=True)
def whitepaper_download(id: str):
    d = WhitepaperDraft.query.get(id)
    if not d:
        return jsonify({"error": "Draft not found"}), 404
    if d.pdf_url and os.path.exists(d.pdf_url):
        try:
            return send_file(d.pdf_url, as_attachment=True, download_name=f"{d.title or 'whitepaper'}.pdf")
        except Exception:
            pass
    return jsonify({"id": str(d.id), "markdown": d.markdown or ""})


@bp.post("/blog/publish/<post_id>")
@jwt_required(optional=True)
def blog_publish(post_id: str):
    try:
        post = publish_blog(post_id)
    except LookupError as exc:
        return jsonify({"error": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:  # pragma: no cover - defensive
        return jsonify({"error": f"Failed to publish: {exc}"}), 500
    published_at = post.published_at.isoformat() if post.published_at else None
    return jsonify({"id": post.id, "slug": post.slug, "status": post.status, "published_at": published_at})


@bp.post("/blog/<post_id>/delete")
@jwt_required(optional=True)
def blog_delete(post_id: str):
    """Delete an unpublished blog draft. Published posts are protected."""
    post = BlogPost.query.filter_by(id=post_id).first()
    if not post:
        post = BlogPost.query.filter_by(slug=post_id).first()
    if not post:
        return jsonify({"error": "Draft not found"}), 404
    if post.status == "published":
        return jsonify({"error": "Cannot delete a published post"}), 400
    try:
        db.session.delete(post)
        db.session.commit()
    except Exception as exc:  # pragma: no cover - defensive
        db.session.rollback()
        return jsonify({"error": f"Failed to delete draft: {exc}"}), 500

    # Support both API and form submissions.
    if request.headers.get("Accept", "").startswith("application/json") or request.is_json:
        return jsonify({"deleted": True, "id": post_id})
    return redirect(url_for("publishing.blog_list_view"))


@bp.get("/blogs")
@jwt_required(optional=True)
def blog_list():
    include_unpublished = request.args.get("include_unpublished", "false").lower() == "true"
    posts = list_blogs(include_unpublished=include_unpublished)
    payload = {
        "posts": [
            {
                "id": p.id,
                "title": p.title,
                "slug": p.slug,
                "status": p.status,
                "published_at": p.published_at.isoformat() if p.published_at else None,
            }
            for p in posts
        ]
    }
    pretty = request.args.get("pretty", "").lower() in ("1", "true", "yes")
    if pretty:
        return current_app.response_class(
            json.dumps(payload, indent=2, sort_keys=True),
            mimetype="application/json",
        )
    return jsonify(payload)


@bp.get("/blogs/view")
@jwt_required(optional=True)
def blog_list_view():
    # If the user has a JWT, allow viewing drafts; otherwise show only published.
    identity = get_jwt_identity()
    include_unpublished_param = request.args.get("include_unpublished", "true").lower() != "false"
    include_unpublished = bool(identity) and include_unpublished_param
    posts = list_blogs(include_unpublished=include_unpublished)
    return render_template("publishing/blog_draft_list.html", posts=posts)


@bp.get("/blog/draft/<post_id>")
@jwt_required()  # require auth to view drafts
def blog_draft_preview(post_id: str):
    post = BlogPost.query.filter_by(id=post_id).first()
    if not post:
        post = BlogPost.query.filter_by(slug=post_id).first()
    if not post:
        return jsonify({"error": "Draft not found"}), 404
    # If it is already published, bounce to the public page so Preview still works for slugs.
    if post.status == "published":
        return redirect(url_for("blog.blog_post", slug=post.slug))
    rendered = post.rendered_html or post.content_html or ""
    markdown = post.markdown or ""
    return render_template(
        "publishing/blog_draft_preview.html",
        post=post,
        rendered_html=rendered,
        markdown=markdown,
    )
