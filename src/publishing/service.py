"""
Shared helpers for publishing/blog flows (draft, generate, publish).
Kept minimal to mirror the inboxiq-style agent expectations.
"""
from __future__ import annotations

import html
import logging
import os
import re
from datetime import datetime
from typing import Any, Dict, List, Tuple
from uuid import uuid4

import requests
from flask import current_app

from src.extensions import db
from src.models.content import BlogPost
from src.dspy.config import _configure_dspy
from src.dspy.signatures import build_blog_writer, build_meta_description_generator

_log = logging.getLogger(__name__)


def _search_web(query: str, max_results: int = 5) -> List[Dict[str, Any]]:
    """
    Synchronous SearXNG search. Returns a list of {title, url, snippet} dicts.
    Returns [] silently on any failure so blog generation always continues.
    """
    base_url = os.getenv("SEARXNG_URL", "").rstrip("/")
    if not base_url:
        return []
    try:
        resp = requests.get(
            f"{base_url}/search",
            params={"q": query, "format": "json"},
            headers={"User-Agent": "InboxIQ-BlogWriter/1.0"},
            timeout=8,
        )
        resp.raise_for_status()
        results = resp.json().get("results", [])[:max_results]
        return [
            {
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "snippet": (r.get("content") or r.get("snippet") or "")[:300],
            }
            for r in results
            if r.get("title") or r.get("content")
        ]
    except Exception as exc:
        _log.debug("blog search failed (non-fatal): %s", exc)
        return []


def _format_research(results: List[Dict[str, Any]]) -> str:
    if not results:
        return ""
    lines = ["--- Web Research ---"]
    for r in results:
        lines.append(f"• {r['title']}")
        if r["snippet"]:
            lines.append(f"  {r['snippet']}")
    lines.append("--- End Research ---")
    return "\n".join(lines)


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

    journey_stage = _coerce_str(brief_data.get("journey_stage")) or "awareness"
    target_keywords = _coerce_str(brief_data.get("target_keywords"))

    # Research the topic before writing — gives the LLM real-world context
    # instead of writing from the brief alone.
    search_query = f"{title} {audience}".strip() or title
    research = _format_research(_search_web(search_query))
    enriched_brief = f"{brief}\n\n{research}".strip() if research else brief

    try:
        _, _, dspy = _configure_dspy()
        writer = build_blog_writer(dspy)
        result = writer(
            title=title,
            audience=audience,
            brief=enriched_brief,
            journey_stage=journey_stage,
            feedback=feedback,
            icp=icp,
            target_keywords=target_keywords,
        )
        md_text = _coerce_str(result.seo_markdown) or _fallback_blog_md(title, brief, audience)
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


def _generate_meta_description(post: BlogPost) -> str:
    """Generate a 140-160 char SEO meta description via DSPy. Falls back to excerpt."""
    excerpt = post.excerpt or _derive_excerpt(post.markdown or "")
    fallback = excerpt[:160].rsplit(" ", 1)[0] if len(excerpt) > 160 else excerpt
    try:
        _, _, dspy = _configure_dspy()
        generator = build_meta_description_generator(dspy)
        result = generator(
            title=post.title or "",
            excerpt=excerpt[:300],
            primary_keyword=post.primary_keyword or "",
        )
        generated = (result.meta_description or "").strip().strip('"').strip("'")
        if 100 <= len(generated) <= 200:
            return generated
    except Exception as exc:
        _log.debug("meta_description generation failed (non-fatal): %s", exc)
    return fallback


def publish_blog(post_id: str) -> BlogPost:
    post = BlogPost.query.filter_by(id=post_id).first()
    if not post:
        raise LookupError("Blog post not found.")

    if not re.fullmatch(r"[a-z0-9-]+", post.slug):
        raise ValueError("Invalid slug; must match [a-z0-9-]+.")

    if not post.content_html:
        post.content_html = post.rendered_html or _render_markdown(post.markdown or "")

    if not post.meta_description:
        post.meta_description = _generate_meta_description(post)

    post.status = "published"
    post.published_at = datetime.utcnow()
    post.updated_at = datetime.utcnow()
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return post


def list_blogs(include_unpublished: bool = False) -> list[BlogPost]:
    query = BlogPost.query
    if not include_unpublished:
        query = query.filter(BlogPost.status == "published")
    return (
        query.order_by(BlogPost.published_at.desc().nullslast(), BlogPost.created_at.desc())
        .all()
    )
