"""
Shared helpers for publishing/blog flows (draft, generate, publish).
Kept minimal to mirror the inboxiq-style agent expectations.
"""
from __future__ import annotations

import html
import os
import re
from datetime import datetime
from typing import Any, Dict, Tuple
from uuid import uuid4

from flask import current_app

from src.extensions import db
from src.models import BlogPost
from src.ai.client import call_openai

SYSTEM_BLOG = """You are a B2B SaaS marketing writer. Create concise blog articles with a clear CTA, short intro, and scannable sections. Keep tone confident, direct, and helpful. Return Markdown only."""


def _safe_json_dict(data: Any) -> dict:
    return data if isinstance(data, dict) else {}


def _read_icp() -> str:
    path = None
    try:
        path = current_app.config.get("ICP_PATH")
    except Exception:
        path = None
    path = path or "ICP.md"
    if not os.path.exists(path):
        return ""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return ""


def _render_markdown(md_text: str) -> str:
    if not md_text:
        return ""
    try:
        import markdown  # type: ignore

        return markdown.markdown(md_text)
    except Exception:
        escaped = html.escape(md_text)
        paragraphs = [f"<p>{p.strip()}</p>" for p in escaped.split("\n\n") if p.strip()]
        return "".join(paragraphs) or f"<p>{escaped}</p>"


def _slugify_base(title: str) -> str:
    slug = title.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")
    return slug or uuid4().hex[:8]


def unique_slug(title: str) -> str:
    base = _slugify_base(title)
    slug = base
    idx = 2
    while BlogPost.query.filter_by(slug=slug).first() is not None:
        slug = f"{base}-{idx}"
        idx += 1
    return slug


def _coerce_str(val: Any) -> str:
    return val if isinstance(val, str) else str(val or "").strip()


def _fallback_blog_md(title: str, brief: str, audience: str) -> str:
    headline = title or "New Article"
    brief_txt = brief or "No brief provided."
    audience_txt = audience or "general audience"
    return (
        f"# {headline}\n\n"
        f"**Audience:** {audience_txt}\n\n"
        f"## Overview\n{brief_txt}\n\n"
        "## Key Takeaways\n- Point one\n- Point two\n- Point three\n\n"
        "## Call to Action\nReady to learn more? Contact our team."
    )


def generate_blog_content(brief_data: dict) -> Tuple[str, str, str]:
    """
    Return markdown, rendered HTML, and the composed prompt used.
    Falls back to deterministic Markdown when the LLM is unavailable.
    """
    title = _coerce_str(brief_data.get("title"))
    audience = _coerce_str(brief_data.get("audience"))
    brief = _coerce_str(brief_data.get("brief"))
    feedback = _coerce_str(brief_data.get("feedback"))
    icp = _read_icp()

    composite = (
        f"Title: {title}\n"
        f"Audience: {audience}\n\n"
        f"Brief:\n{brief}\n\n"
        f"Feedback:\n{feedback}\n\n"
        f"ICP:\n{icp}"
    )

    try:
        llm_resp = call_openai(
            [
                {"role": "system", "content": SYSTEM_BLOG},
                {"role": "user", "content": composite},
            ],
            max_tokens=900,
        )
        md_text = _coerce_str(llm_resp.get("content")) or _fallback_blog_md(title, brief, audience)
    except Exception:
        md_text = _fallback_blog_md(title, brief, audience)

    rendered = _render_markdown(md_text)
    return md_text, rendered, composite


def _derive_excerpt(markdown_text: str, limit: int = 260) -> str:
    plain = re.sub(r"\s+", " ", re.sub(r"[#*_`>-]", " ", markdown_text)).strip()
    return plain[:limit]


def _derive_word_count(markdown_text: str) -> int:
    tokens = re.findall(r"\w+", markdown_text)
    return len(tokens)


def create_blog_draft(data: dict, run_async: bool = False) -> Tuple[BlogPost, dict]:
    brief_json = _safe_json_dict(data)
    title = _coerce_str(brief_json.get("title"))
    audience = _coerce_str(brief_json.get("audience"))
    brief = _coerce_str(brief_json.get("brief"))
    if not title or not brief or not audience:
        raise ValueError("title, brief, and audience are required.")

    slug = unique_slug(title)
    post = BlogPost(
        title=title,
        slug=slug,
        status="queued" if run_async else "generating",
        summary=brief,
        brief_json=brief_json,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.session.add(post)
    db.session.commit()

    if run_async:
        return post, {"queued": True}

    md_text, rendered, prompt = generate_blog_content(brief_json)
    post.markdown = md_text
    post.rendered_html = rendered
    post.content_html = rendered
    post.last_prompt = prompt
    post.status = "ready"
    post.excerpt = _derive_excerpt(md_text)
    post.word_count = _derive_word_count(md_text)
    post.read_time_minutes = max(3, round((post.word_count or 0) / float(225))) if post.word_count else None
    post.updated_at = datetime.utcnow()
    db.session.commit()
    return post, {"queued": False}


def publish_blog(post_id: str) -> BlogPost:
    post = BlogPost.query.filter_by(id=post_id).first()
    if not post:
        raise LookupError("Blog post not found.")

    if not re.fullmatch(r"[a-z0-9-]+", post.slug):
        raise ValueError("Invalid slug; must match [a-z0-9-]+.")

    if not post.content_html:
        post.content_html = post.rendered_html or _render_markdown(post.markdown or "")

    post.status = "published"
    post.published_at = datetime.utcnow()
    post.updated_at = datetime.utcnow()
    db.session.commit()
    return post


def list_blogs(include_unpublished: bool = False) -> list[BlogPost]:
    query = BlogPost.query
    if not include_unpublished:
        query = query.filter(BlogPost.status == "published")
    return (
        query.order_by(BlogPost.published_at.desc().nullslast(), BlogPost.created_at.desc())
        .all()
    )
