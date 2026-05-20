from flask import current_app
from src.models.content import BlogPost

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
  "section",
]
ALLOWED_ATTRS = {
  "a": ["href", "title", "rel", "class"],
  "img": ["src", "alt", "title"],
  "code": ["class"],
  "pre": ["class"],
  "span": ["class"],
  "div": ["class"],
  "section": ["class"],
  "p": ["class"],
  "h1": ["class"],
  "h2": ["class"],
  "h3": ["class"],
  "h4": ["class"],
  "ol": ["class"],
  "ul": ["class"],
  "li": ["class"],
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


def _strip_dead_blog_links(raw: str, published: set) -> str:
  """Replace <a href="/blog/SLUG">…</a> with plain text when SLUG isn't published."""
  if not raw or not published:
    return raw

  def _replace(m):
    slug = m.group(1)
    inner = m.group(2)
    if slug in published:
      return m.group(0)
    current_app.logger.warning("content_html: stripping dead blog link /blog/%s", slug)
    return inner

  try:
    return re.sub(
      r'<a\s[^>]*href=["\']\/blog\/([a-z0-9-]+)["\'][^>]*>(.*?)<\/a>',
      _replace,
      raw,
      flags=re.IGNORECASE | re.DOTALL,
    )
  except Exception:
    return raw


def _published_blog_slugs() -> set:
  """Return the set of slugs for all currently published blog posts."""
  try:
    rows = BlogPost.query.with_entities(BlogPost.slug).filter_by(status="published").all()
    return {r[0] for r in rows}
  except Exception:
    return set()


def _safe_internal_links(links):
  published = _published_blog_slugs()
  cleaned = []
  for link in links or []:
    href = link.get("href")
    if not href or href.startswith("javascript:"):
      continue
    # Drop /blog/<slug> links whose target post isn't published yet.
    if href.startswith("/blog/"):
      slug = href.split("/blog/", 1)[1].split("?")[0].split("#")[0]
      if slug and slug not in published:
        current_app.logger.warning("internal_links: dropping dead link %s (not published)", href)
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
      published = _published_blog_slugs()
      safe_posts = []
      for p in posts:
        data = p.to_dict()
        raw_html = data.get("content_html") or ""
        cleaned_html = _strip_leading_image(_strip_leading_heading(raw_html))
        cleaned_html = _strip_dead_blog_links(cleaned_html, published)
        data["content_html"] = _sanitize_html(cleaned_html)
        data["internal_links"] = _resolve_internal_links(data.get("internal_links"))
        safe_posts.append(data)
      return safe_posts
  except Exception as exc:
    current_app.logger.error("BlogPost query failed: %s", exc)
  return []


def load_blog_post(slug: str):
  """Fetch a single blog post by slug."""
  try:
    post = BlogPost.query.filter_by(slug=slug, status="published").first()
    if post:
      published = _published_blog_slugs()
      data = post.to_dict()
      raw_html = data.get("content_html") or ""
      cleaned_html = _strip_leading_image(_strip_leading_heading(raw_html))
      cleaned_html = _strip_dead_blog_links(cleaned_html, published)
      data["content_html"] = _sanitize_html(cleaned_html)
      data["internal_links"] = _resolve_internal_links(data.get("internal_links"))
      return data
  except Exception as exc:
    current_app.logger.error("BlogPost lookup failed for slug %s: %s", slug, exc)
  return None


def extract_faq_pairs(markdown_text):
  """
  Parse Q&A pairs from a '## Frequently Asked Questions' section in markdown.
  Returns list of {"q": str, "a": str} dicts, max 6 pairs.
  Expects bold questions: **Question?** followed by answer paragraph.
  """
  if not markdown_text:
    return []
  faq_match = re.search(
    r"##\s+Frequently Asked Questions\s*\n(.*?)(?=\n##|\Z)",
    markdown_text,
    re.DOTALL | re.IGNORECASE,
  )
  if not faq_match:
    return []
  faq_block = faq_match.group(1)
  pattern = re.compile(r"\*\*(.+?)\*\*\s*\n+(.+?)(?=\n\n\*\*|\Z)", re.DOTALL)
  pairs = []
  for match in pattern.finditer(faq_block):
    q = match.group(1).strip()
    a = " ".join(match.group(2).strip().split())
    if q and a:
      pairs.append({"q": q, "a": a})
    if len(pairs) >= 6:
      break
  return pairs
