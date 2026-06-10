from __future__ import annotations

import os
import logging
import markdown
from flask import render_template, abort, request
from markupsafe import Markup

from src.kb import bp
from src.sanitize import sanitize_html

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Content manifest — single source of truth for categories and articles.
# Article markdown files live in src/kb/articles/<category>/<article>.md
# ---------------------------------------------------------------------------

KB_CATEGORIES = [
    {
        "slug": "getting-started",
        "title": "Getting Started",
        "icon": "rocket",
        "description": "Connect your inbox and see InboxIQ working within minutes.",
        "articles": [
            {"slug": "how-inboxiq-works", "title": "How InboxIQ works"},
            {"slug": "connect-gmail", "title": "Connect your Gmail inbox"},
            {"slug": "connect-outlook", "title": "Connect your Outlook inbox"},
            {"slug": "invite-teammate-inbox", "title": "Invite a teammate's inbox"},
            {"slug": "what-happens-after-connect", "title": "What happens after you connect"},
            {"slug": "ai-meeting-scheduling", "title": "AI meeting scheduling"},
        ],
    },
    {
        "slug": "triage-and-ai",
        "title": "Triage & AI",
        "icon": "sparkles",
        "description": "How InboxIQ reads, classifies, and drafts replies to your emails.",
        "articles": [
            {"slug": "how-emails-are-classified", "title": "How emails are classified"},
            {"slug": "gmail-labels", "title": "Understanding Gmail labels"},
            {"slug": "outlook-categories", "title": "Understanding Outlook categories"},
            {"slug": "ai-draft-replies", "title": "AI draft replies — how they work"},
            {"slug": "confidence-threshold", "title": "Adjusting your confidence threshold"},
        ],
    },
    {
        "slug": "automation-studio",
        "title": "Automation Studio",
        "icon": "bolt",
        "description": "Build rules that act on AI-classified emails automatically.",
        "articles": [
            {"slug": "how-rules-work", "title": "How rules work"},
            {"slug": "conditions", "title": "Available conditions"},
            {"slug": "actions", "title": "Available actions"},
            {"slug": "inbox-actions", "title": "Inbox actions — Gmail & Outlook"},
            {"slug": "rule-recipes", "title": "Rule recipes and examples"},
            {"slug": "finance-addon", "title": "Finance Add-on — Stripe to QuickBooks"},
        ],
    },
    {
        "slug": "knowledge-base",
        "title": "Knowledge Base Setup",
        "icon": "book",
        "description": "Train InboxIQ on your product, past replies, and help articles.",
        "articles": [
            {"slug": "adding-content", "title": "Adding articles and past replies"},
            {"slug": "connecting-help-centre", "title": "Connecting your help centre"},
            {"slug": "how-inboxiq-learns", "title": "How InboxIQ learns from corrections"},
        ],
    },
    {
        "slug": "security",
        "title": "Security",
        "icon": "shield",
        "description": "Passkeys, two-factor authentication, and team access control.",
        "articles": [
            {"slug": "passkeys", "title": "Passkeys — register and sign in"},
            {"slug": "two-factor-auth", "title": "Two-factor authentication (TOTP)"},
            {"slug": "team-roles", "title": "Team roles and permissions"},
        ],
    },
    {
        "slug": "billing",
        "title": "Billing & Account",
        "icon": "credit-card",
        "description": "Plans, subscriptions, and account management.",
        "articles": [
            {"slug": "plans-and-pricing", "title": "Plans and pricing"},
            {"slug": "manage-subscription", "title": "Managing your subscription"},
            {"slug": "delete-account", "title": "Deleting your account"},
        ],
    },
    {
        "slug": "troubleshooting",
        "title": "Troubleshooting",
        "icon": "wrench",
        "description": "Fix the most common issues quickly.",
        "articles": [
            {"slug": "email-not-appearing", "title": "Email not appearing in InboxIQ"},
            {"slug": "label-not-showing", "title": "Label not showing in Gmail"},
            {"slug": "draft-not-appearing", "title": "Draft not appearing in the thread"},
            {"slug": "reconnect-inbox", "title": "Reconnecting a disconnected inbox"},
        ],
    },
    {
        "slug": "faq",
        "title": "FAQs",
        "icon": "question",
        "description": "The questions we hear most often, answered directly.",
        "articles": [
            {"slug": "does-inboxiq-send-emails", "title": "Does InboxIQ send emails without my approval?"},
            {"slug": "can-inboxiq-read-all-emails", "title": "Can InboxIQ read all my emails, including personal ones?"},
            {"slug": "what-happens-if-i-disconnect", "title": "What happens if I disconnect my inbox?"},
            {"slug": "team-visibility", "title": "Will my teammates see each other's emails?"},
            {"slug": "stop-drafts-for-sender", "title": "How do I stop InboxIQ drafting for a specific sender?"},
            {"slug": "disable-draft-reply", "title": "Can I switch off Draft Reply in my account?"},
            {"slug": "multiple-inboxes", "title": "Can I connect more than one inbox?"},
            {"slug": "data-on-deletion", "title": "What happens to my data if I delete my account?"},
            {"slug": "how-long-to-learn", "title": "How long does InboxIQ take to learn my style?"},
            {"slug": "gmail-aliases", "title": "Does InboxIQ work with Gmail aliases and shared inboxes?"},
            {"slug": "charged-but-not-used", "title": "I was charged but didn't use InboxIQ this month"},
            {"slug": "reset-password", "title": "How do I reset my password?"},
            {"slug": "add-a-user", "title": "How do I add a user or teammate?"},
            {"slug": "mobile-app", "title": "Where can I download the mobile app?"},
        ],
    },
]

# Build fast-lookup maps
_CAT_BY_SLUG: dict[str, dict] = {c["slug"]: c for c in KB_CATEGORIES}
_ARTICLE_MAP: dict[tuple, dict] = {
    (c["slug"], a["slug"]): a
    for c in KB_CATEGORIES
    for a in c["articles"]
}

ARTICLES_DIR = os.path.join(os.path.dirname(__file__), "articles")


def _load_article(category_slug: str, article_slug: str) -> str | None:
    """Load and render a markdown article. Returns sanitized HTML or None."""
    path = os.path.join(ARTICLES_DIR, category_slug, f"{article_slug}.md")
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        raw = f.read()
    html = markdown.markdown(
        raw,
        extensions=["markdown.extensions.fenced_code", "markdown.extensions.tables", "markdown.extensions.toc"],
    )
    return Markup(sanitize_html(html))


def _search_articles(query: str) -> list[dict]:
    """Simple full-text search across all article files."""
    query_lower = query.strip().lower()
    if not query_lower:
        return []
    results = []
    for cat in KB_CATEGORIES:
        for art in cat["articles"]:
            path = os.path.join(ARTICLES_DIR, cat["slug"], f"{art['slug']}.md")
            if not os.path.exists(path):
                # Match on title only
                score = art["title"].lower().count(query_lower) * 5
                if score:
                    results.append({
                        "category": cat,
                        "article": art,
                        "snippet": art["title"],
                        "score": score,
                    })
                continue
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            content_lower = content.lower()
            title_lower = art["title"].lower()
            title_hits = title_lower.count(query_lower) * 5
            content_hits = content_lower.count(query_lower)
            score = title_hits + content_hits
            if score == 0:
                continue
            idx = content_lower.find(query_lower)
            start = max(0, idx - 80)
            end = min(len(content), idx + len(query_lower) + 80)
            snippet = content[start:end].replace("\n", " ").strip()
            if start > 0:
                snippet = "…" + snippet
            if end < len(content):
                snippet += "…"
            results.append({
                "category": cat,
                "article": art,
                "snippet": snippet,
                "score": score,
            })
    results.sort(key=lambda r: r["score"], reverse=True)
    return results[:20]


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@bp.route("/")
@bp.route("")
def kb_home():
    return render_template(
        "kb/home.html",
        title="Help Centre",
        categories=KB_CATEGORIES,
    )


@bp.route("/search")
def kb_search():
    query = request.args.get("q", "").strip()
    results = _search_articles(query) if query else []
    return render_template(
        "kb/search.html",
        title=f'Search: {query}' if query else "Search",
        query=query,
        results=results,
        categories=KB_CATEGORIES,
    )


@bp.route("/<category_slug>")
def kb_category(category_slug: str):
    cat = _CAT_BY_SLUG.get(category_slug)
    if not cat:
        abort(404)
    return render_template(
        "kb/category.html",
        title=cat["title"],
        category=cat,
        categories=KB_CATEGORIES,
    )


@bp.route("/<category_slug>/<article_slug>")
def kb_article(category_slug: str, article_slug: str):
    cat = _CAT_BY_SLUG.get(category_slug)
    if not cat:
        abort(404)
    art = _ARTICLE_MAP.get((category_slug, article_slug))
    if not art:
        abort(404)
    content = _load_article(category_slug, article_slug)
    if content is None:
        abort(404)
    # Prev / next within category
    articles = cat["articles"]
    idx = next((i for i, a in enumerate(articles) if a["slug"] == article_slug), None)
    prev_art = articles[idx - 1] if idx and idx > 0 else None
    next_art = articles[idx + 1] if idx is not None and idx < len(articles) - 1 else None
    return render_template(
        "kb/article.html",
        title=art["title"],
        category=cat,
        article=art,
        content=content,
        prev_article=prev_art,
        next_article=next_art,
        categories=KB_CATEGORIES,
    )
