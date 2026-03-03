from flask import current_app
from src.models.content import BlogPost
from src.blog.content import get_fallback_posts, get_fallback_post_by_slug

import html
import re
from copy import deepcopy

try:
  import bleach
except ImportError:  # pragma: no cover - optional dependency
  bleach = None

ALLOWED_TAGS = [
  "p",
  "ul",
  "ol",
  "li",
  "strong",
  "em",
  "h1",
  "h2",
  "h3",
  "h4",
  "h5",
  "h6",
  "a",
  "br",
  "code",
  "pre",
  "blockquote",
  "hr",
  "table",
  "thead",
  "tbody",
  "tr",
  "th",
  "td",
  "img",
  "span",
  "div",
]
ALLOWED_ATTRS = {
  "a": ["href", "title", "rel"],
  "img": ["src", "alt", "title"],
  "code": ["class"],
  "pre": ["class"],
  "span": ["class"],
  "div": ["class"],
  "th": ["align"],
  "td": ["align"],
}
ALLOWED_PROTOCOLS = ["http", "https", "mailto", "tel"]
DEFAULT_INTERNAL_LINKS = [
  {"href": "/ai-email-triage", "label": "See the demo", "rel": "cta"},
  {"href": "/email-triage", "label": "AI Email Triage", "rel": "cta"},
]


def _sanitize_html(raw: str) -> str:
  """Sanitize HTML to reduce XSS risk. Falls back to escaping when bleach is absent."""
  if not raw:
    return ""
  if bleach:
    return bleach.clean(raw, tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRS, protocols=ALLOWED_PROTOCOLS, strip=True)
  return html.escape(raw)


def _strip_leading_heading(raw: str) -> str:
  """Remove the first <h1>…</h1> to avoid duplicate titles (page template already renders a title)."""
  if not raw:
    return ""
  try:
    pattern = re.compile(r"<h1[^>]*>.*?</h1>", flags=re.IGNORECASE | re.DOTALL)
    return pattern.sub("", raw, count=1)
  except Exception:
    return raw


def _strip_leading_image(raw: str) -> str:
  """Remove the first <img>… to avoid stacking a hero-like image before the body."""
  if not raw:
    return ""
  try:
    pattern = re.compile(r"<img[^>]*>", flags=re.IGNORECASE | re.DOTALL)
    return pattern.sub("", raw, count=1)
  except Exception:
    return raw


def _safe_internal_links(links):
  cleaned = []
  for link in links or []:
    href = link.get("href")
    if not href or (href.startswith("javascript:")):  # guard obvious bad inputs
      continue
    cleaned.append(link)
  return cleaned


def _default_internal_links():
  return deepcopy(DEFAULT_INTERNAL_LINKS)


def _resolve_internal_links(raw_links):
  cleaned = _safe_internal_links(raw_links)
  return cleaned if cleaned else _default_internal_links()


def load_blog_posts():
  """Fetch published blog posts; fall back to seed content if table is empty or missing."""
  try:
    posts = (
      BlogPost.query.filter_by(status="published")
      .order_by(BlogPost.published_at.desc().nullslast(), BlogPost.created_at.desc())
      .all()
    )
    if posts:
      safe_posts = []
      for p in posts:
        data = p.to_dict()
        raw_html = data.get("content_html") or ""
        cleaned_html = _strip_leading_image(_strip_leading_heading(raw_html))
        data["content_html"] = _sanitize_html(cleaned_html)
        data["internal_links"] = _resolve_internal_links(data.get("internal_links"))
        safe_posts.append(data)
      return safe_posts
  except Exception as exc:  # table may not exist yet
    current_app.logger.warning("BlogPost query failed; using fallback seed content: %s", exc)
  return get_fallback_posts()


def load_blog_post(slug: str):
  """Fetch a single blog post by slug."""
  try:
    post = BlogPost.query.filter_by(slug=slug, status="published").first()
    if post:
      data = post.to_dict()
      raw_html = data.get("content_html") or ""
      cleaned_html = _strip_leading_image(_strip_leading_heading(raw_html))
      data["content_html"] = _sanitize_html(cleaned_html)
      data["internal_links"] = _resolve_internal_links(data.get("internal_links"))
      return data
  except Exception as exc:  # table may not exist yet
    current_app.logger.warning("BlogPost lookup failed for slug %s; using fallback: %s", slug, exc)
  return get_fallback_post_by_slug(slug)
