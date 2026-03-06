import re
from http import HTTPStatus
from flask import jsonify, request
from flask_jwt_extended import jwt_required

from src.api.v1 import v1
from src.extensions import db
from src.models.content import BlogPost
from src.sanitize import sanitize_html


def _slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    return re.sub(r"[\s_-]+", "-", text)[:200]


@v1.route("/blog/posts", methods=["POST"])
@jwt_required()
def create_blog_post():
    """Accept agent-authored blog post submissions and persist as draft."""
    payload = request.get_json(silent=True) or {}

    title = (payload.get("title") or "").strip()
    if not title:
        return jsonify({"error": "title is required"}), HTTPStatus.BAD_REQUEST

    markdown = (payload.get("markdown") or "").strip() or None
    content_html_raw = (payload.get("content_html") or "").strip() or None

    if not markdown and not content_html_raw:
        return jsonify({"error": "markdown or content_html is required"}), HTTPStatus.BAD_REQUEST

    content_html = sanitize_html(content_html_raw) if content_html_raw else None

    slug_base = (payload.get("slug") or "").strip() or _slugify(title)
    slug = slug_base
    suffix = 1
    while db.session.query(BlogPost).filter_by(slug=slug).first():
        slug = f"{slug_base}-{suffix}"
        suffix += 1

    post = BlogPost(
        title=title,
        slug=slug,
        status="draft",
        funnel_stage=(payload.get("funnel_stage") or "").strip() or None,
        primary_keyword=(payload.get("primary_keyword") or "").strip() or None,
        secondary_keywords=payload.get("secondary_keywords") or [],
        summary=(payload.get("summary") or "").strip() or None,
        excerpt=(payload.get("excerpt") or "").strip() or None,
        content_html=content_html,
        markdown=markdown,
        meta_description=(payload.get("meta_description") or "").strip() or None,
        word_count=payload.get("word_count"),
        read_time_minutes=payload.get("read_time_minutes"),
        auto_generated=True,
        dspy_quality_score=payload.get("dspy_quality_score"),
    )

    try:
        db.session.add(post)
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        return jsonify({"error": "database error", "detail": str(exc)}), HTTPStatus.INTERNAL_SERVER_ERROR

    return jsonify(post.to_dict()), HTTPStatus.CREATED
