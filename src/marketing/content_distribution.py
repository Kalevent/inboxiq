"""
Content distribution automation.

Handles publishing and distributing generated content across channels:
- Blog posts → LinkedIn, Twitter, email newsletter
- Content repurposing (blog → social threads)
- Automated scheduling and cross-posting
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional, Tuple

from src.celery_inboxiq import celery
from src.extensions import db
from src.models.content import BlogPost
from src.models.core import InboxConnection
from src.sanitize import sanitize_html

logger = logging.getLogger(__name__)


@celery.task(name="marketing.publish_blog_post", queue="leads")
def publish_blog_post(blog_post_id: str) -> Dict[str, Any]:
    """
    Publish a blog post and trigger distribution channels.

    Args:
        blog_post_id: BlogPost ID to publish

    Returns:
        Dict with publication status and distribution results
    """
    from src.models import BlogPost

    post = db.session.get(BlogPost, blog_post_id)
    if not post:
        logger.error(f"Blog post {blog_post_id} not found")
        return {"status": "error", "reason": "post_not_found"}

    # Skip only if post is in a state where distribution shouldn't fire.
    if post.status in ("failed",):
        logger.warning(f"Blog post {blog_post_id} status is {post.status}, skipping")
        return {"status": "skipped", "reason": f"status_is_{post.status}"}

    if not post.rendered_html and not post.content_html:
        logger.error(f"Blog post {blog_post_id} has no content")
        return {"status": "error", "reason": "no_content"}

    try:
        # Sanitize content before publishing
        if post.rendered_html:
            post.rendered_html = sanitize_html(post.rendered_html)
        if post.content_html:
            post.content_html = sanitize_html(post.content_html)

        # Mark as published
        post.status = "published"
        post.published_at = datetime.now(timezone.utc)
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise

        logger.info(f"Published blog post: {post.title} ({post.id})")

        # Distribution: enqueue per-platform rows (replaces fire-on-publish).
        from src.marketing.social_distribution import enqueue_blog_post
        try:
            enqueue_blog_post(post)
            post.distributed_at = datetime.now(timezone.utc)
            try:
                db.session.commit()
            except Exception:
                db.session.rollback()
        except Exception:
            logger.exception("Failed to enqueue blog post %s for social distribution", post.id)

        # Newsletter + search-engine submission stay event-driven.
        distribution_results = {}
        try:
            newsletter_result = send_blog_newsletter.delay(blog_post_id)
            distribution_results["newsletter"] = {"task_id": newsletter_result.id, "status": "queued"}
        except Exception as e:
            logger.error(f"Failed to queue newsletter: {e}")
            distribution_results["newsletter"] = {"status": "error", "error": str(e)}

        try:
            seo_result = submit_to_search_engines.delay(blog_post_id)
            distribution_results["seo"] = {"task_id": seo_result.id, "status": "queued"}
        except Exception as e:
            logger.error(f"Failed to queue search engine submission: {e}")
            distribution_results["seo"] = {"status": "error", "error": str(e)}

        return {
            "status": "published",
            "blog_post_id": blog_post_id,
            "title": post.title,
            "published_at": post.published_at.isoformat(),
            "distribution": distribution_results
        }

    except Exception as e:
        logger.exception(f"Failed to publish blog post {blog_post_id}")
        post.status = "failed"
        db.session.commit()
        return {"status": "error", "error": str(e)}


@celery.task(name="marketing.send_blog_newsletter", queue="leads")
def send_blog_newsletter(blog_post_id: str) -> Dict[str, Any]:
    """
    Send email newsletter to opted-in users about a new blog post.
    Each recipient gets a personalised unsubscribe link.
    """
    from flask import current_app
    from itsdangerous import URLSafeSerializer
    from src.models import BlogPost, User, Account

    post = db.session.get(BlogPost, blog_post_id)
    if not post:
        return {"status": "error", "reason": "post_not_found"}

    subscribers = (
        db.session.query(User)
        .join(Account, User.account_id == Account.id)
        .filter(
            Account.deleted == False,  # noqa: E712
            User.email.isnot(None),
            User.newsletter_opt_in == True,  # noqa: E712
        )
        .limit(100)
        .all()
    )

    if not subscribers:
        return {"status": "skipped", "reason": "no_subscribers"}

    base_url = current_app.config.get("SITE_URL", "https://kalevent.com")
    signer = URLSafeSerializer(current_app.config["SECRET_KEY"], salt="newsletter-unsubscribe")

    sent_count = 0
    failed_count = 0

    for user in subscribers:
        try:
            token = signer.dumps(user.id)
            unsub_url = f"{base_url}/unsubscribe/{token}"
            html = _generate_newsletter_html(post, unsubscribe_url=unsub_url)
            success = _send_newsletter_email(
                to_email=user.email,
                user_name=user.name or user.email.split("@")[0],
                post=post,
                html_content=html,
            )
            if success:
                sent_count += 1
            else:
                failed_count += 1
        except Exception as exc:
            logger.error("Failed to send newsletter to %s: %s", user.email, exc)
            failed_count += 1

    return {
        "status": "completed",
        "blog_post_id": blog_post_id,
        "sent": sent_count,
        "failed": failed_count,
        "total_subscribers": len(subscribers),
    }


@celery.task(name="marketing.submit_to_search_engines", queue="leads")
def submit_to_search_engines(blog_post_id: str) -> Dict[str, Any]:
    """
    Submit blog post URL to search engines via IndexNow (Bing, Yandex, others).
    Requires INDEXNOW_API_KEY env var. No-ops silently if key is absent.
    """
    from src.models import BlogPost
    from flask import current_app
    import requests as http

    post = db.session.get(BlogPost, blog_post_id)
    if not post:
        return {"status": "error", "reason": "post_not_found"}

    base_url = current_app.config.get("SITE_URL", "https://kalevent.com")
    post_url = f"{base_url}/blog/{post.slug}"
    api_key = current_app.config.get("INDEXNOW_API_KEY", "")

    if not api_key:
        logger.info("submit_to_search_engines: INDEXNOW_API_KEY not set, skipping")
        return {"status": "skipped", "reason": "no_indexnow_key", "url": post_url}

    results = {}

    # IndexNow — single POST covers Bing, Yandex, Seznam, and others
    try:
        resp = http.post(
            "https://api.indexnow.org/indexnow",
            json={
                "host": base_url.replace("https://", "").replace("http://", "").rstrip("/"),
                "key": api_key,
                "urlList": [post_url],
            },
            headers={"Content-Type": "application/json; charset=utf-8"},
            timeout=10,
        )
        if resp.status_code in (200, 202):
            logger.info("IndexNow accepted %s (status %s)", post_url, resp.status_code)
            results["indexnow"] = {"status": "ok", "http_status": resp.status_code}
        else:
            logger.warning("IndexNow rejected %s: %s %s", post_url, resp.status_code, resp.text[:200])
            results["indexnow"] = {"status": "rejected", "http_status": resp.status_code}
    except Exception as exc:
        logger.error("IndexNow request failed for %s: %s", post_url, exc)
        results["indexnow"] = {"status": "error", "error": str(exc)}

    return {
        "status": "completed",
        "blog_post_id": blog_post_id,
        "url": post_url,
        "search_engines": results,
    }


# Helper functions

def generate_social_content(post: BlogPost) -> Dict[str, Any]:
    """
    Generate social media posts from blog content using DSPy intelligence.

    Uses DistributionIntelligenceModule to:
    - Determine which platforms to use
    - Optimize content for each platform
    - Apply audience segmentation

    Returns:
        Dict with platform-specific content:
        {
            "linkedin": {"text": "...", "url": "...", "hashtags": "..."},
            "twitter": {"thread": ["tweet1", "tweet2", ...], "url": "..."},
            "email": {"subject": "...", "text": "..."}
        }
    """
    from flask import current_app
    from src.dspy.content_distribution import DistributionIntelligenceModule
    from src.dspy import _configure_dspy

    base_url = current_app.config.get("SITE_URL", "https://kalevent.com")
    post_url = f"{base_url}/blog/{post.slug}"

    # Extract content info
    excerpt = post.excerpt or post.summary or (post.markdown[:200] if post.markdown else "")
    funnel_stage = post.funnel_stage or "VISITS"
    target_audience = "VP Revenue Operations, B2B SaaS, 100-500 employees"  # Default ICP

    try:
        # Configure DSPy
        _configure_dspy()

        # Use DSPy intelligence to generate optimal content
        module = DistributionIntelligenceModule()

        strategy = module.forward(
            blog_title=post.title,
            blog_summary=excerpt,
            funnel_stage=funnel_stage,
            target_audience=target_audience,
            primary_keyword=post.primary_keyword,
            content_type="blog_post",
            content_goal="awareness" if funnel_stage == "VISITS" else "education"
        )

        result = {}

        # Build platform-specific content based on DSPy recommendations
        if strategy["platforms"]["linkedin"]:
            linkedin_data = strategy["optimized_content"].get("linkedin", {})
            result["linkedin"] = {
                "text": linkedin_data.get("text", f"🚀 New on the InboxIQ blog: {post.title}\n\n{excerpt}...\n\nRead more: {post_url}"),
                "url": post_url,
                "hashtags": linkedin_data.get("hashtags", "#CustomerSupport #AI #Automation"),
                "cta": linkedin_data.get("cta", "Read more")
            }

        if strategy["platforms"]["twitter"]:
            twitter_data = strategy["optimized_content"].get("twitter", {})
            # Split into thread if content is long
            twitter_text = twitter_data.get("text", f"🧵 New blog post: {post.title}\n\n{excerpt[:200]}...\n\n{post_url}")
            thread = _split_into_twitter_thread(twitter_text, post_url)
            result["twitter"] = {
                "thread": thread,
                "url": post_url,
                "hashtags": twitter_data.get("hashtags", "")
            }

        if strategy["platforms"]["email"]:
            email_data = strategy["optimized_content"].get("email", {})
            result["email"] = {
                "subject": email_data.get("subject_line", f"📬 New: {post.title}"),
                "text": email_data.get("text", excerpt),
                "cta": email_data.get("cta", "Read Full Article")
            }

        # Facebook always gets content (not gated on DSPy strategy)
        result["facebook"] = {
            "text": f"📖 New on our blog: {post.title}\n\n{excerpt}\n\nRead the full article 👇",
            "url": post_url
        }

        logger.info(f"Generated intelligent social content for {post.title}: platforms={list(result.keys())}")

        return result

    except Exception as e:
        logger.error(f"DSPy content generation failed, using fallback: {e}")

        # Fallback to simple content generation
        return {
            "linkedin": {
                "text": f"🚀 New on the InboxIQ blog: {post.title}\n\n{excerpt}...\n\nRead more: {post_url}\n\n#CustomerSupport #AI #Automation",
                "url": post_url
            },
            "twitter": {
                "thread": [
                    f"🧵 New blog post: {post.title}",
                    excerpt[:250] + "...",
                    f"Read the full article: {post_url}"
                ],
                "url": post_url
            },
            "facebook": {
                "text": f"📖 New on our blog: {post.title}\n\n{excerpt}\n\nRead the full article 👇",
                "url": post_url
            }
        }


def _split_into_twitter_thread(text: str, url: str, max_length: int = 280) -> List[str]:
    """
    Split long text into Twitter thread respecting 280 char limit.

    Args:
        text: Full text to split
        url: URL to append to last tweet
        max_length: Max characters per tweet

    Returns:
        List of tweets
    """
    # Split by sentences or paragraphs
    sentences = text.replace('\n\n', '. ').split('. ')
    thread = []
    current_tweet = ""

    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue

        # Check if adding this sentence exceeds limit
        if len(current_tweet) + len(sentence) + 2 > max_length:
            if current_tweet:
                thread.append(current_tweet)
            current_tweet = sentence
        else:
            current_tweet += (". " if current_tweet else "") + sentence

    # Add remaining content
    if current_tweet:
        thread.append(current_tweet)

    # Add URL to last tweet if space allows
    if thread:
        last_tweet = thread[-1]
        if len(last_tweet) + len(url) + 3 <= max_length:
            thread[-1] = f"{last_tweet}\n\n{url}"
        else:
            thread.append(url)

    return thread if thread else [text[:max_length]]


def _get_social_token(provider: str, account_id: int) -> Optional[str]:
    """Decrypt and return the OAuth access token for a social provider scoped to account_id."""
    from src.crypto import decrypt_value
    conn = InboxConnection.query.filter_by(
        provider=provider, account_id=account_id, status="connected"
    ).first()
    if not conn or not conn.metadata_json:
        return None
    enc = conn.metadata_json.get("access_token_enc")
    return decrypt_value(enc) if enc else None


def _post_to_linkedin(item) -> Dict[str, Any]:
    """Post a queue item to LinkedIn company page via UGC Posts API."""
    import requests as http

    token = _get_social_token("linkedin_social", account_id=item.account_id)
    if not token:
        return {"status": "skipped", "reason": "not_connected"}

    org_id = _get_linkedin_org_id(item.account_id)
    if not org_id:
        return {"status": "skipped", "reason": "not_configured"}

    body = {
        "author": f"urn:li:organization:{org_id}",
        "lifecycleState": "PUBLISHED",
        "specificContent": {
            "com.linkedin.ugc.ShareContent": {
                "shareCommentary": {"text": item.caption},
                "shareMediaCategory": "ARTICLE",
                "media": [{
                    "status": "READY",
                    "originalUrl": item.target_url,
                }],
            }
        },
        "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"},
    }

    try:
        resp = http.post(
            "https://api.linkedin.com/v2/ugcPosts",
            json=body,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "X-Restli-Protocol-Version": "2.0.0",
            },
            timeout=15,
        )
        resp.raise_for_status()
        post_urn = resp.json().get("id", "")
        return {
            "status": "ok",
            "platform": "linkedin",
            "post_url": f"https://www.linkedin.com/feed/update/{post_urn}",
        }
    except Exception as exc:
        return {"status": "error", "platform": "linkedin", "error": str(exc)}


def _get_linkedin_org_id(account_id: int) -> Optional[str]:
    """Resolve the LinkedIn company URN ID for an account from its InboxConnection metadata."""
    conn = InboxConnection.query.filter_by(
        provider="linkedin_social", account_id=account_id, status="connected"
    ).first()
    if not conn or not conn.metadata_json:
        return None
    return conn.metadata_json.get("org_id")


def _post_to_twitter(item) -> Dict[str, Any]:
    """Post a queue item as a single tweet via Twitter API v2."""
    import requests as http

    token = _get_social_token("twitter_social", account_id=item.account_id)
    if not token:
        return {"status": "skipped", "reason": "not_connected"}

    # Append target_url if not already present in the caption
    text = item.caption
    if item.target_url and item.target_url not in text:
        text = f"{text}\n\n{item.target_url}"

    body: Dict[str, Any] = {"text": text[:280]}

    try:
        resp = http.post(
            "https://api.twitter.com/2/tweets",
            json=body,
            headers={"Authorization": f"Bearer {token}"},
            timeout=15,
        )
        resp.raise_for_status()
        tweet_id = resp.json().get("data", {}).get("id", "")
        return {
            "status": "ok",
            "platform": "twitter",
            "post_url": f"https://twitter.com/i/web/status/{tweet_id}",
        }
    except Exception as exc:
        return {"status": "error", "platform": "twitter", "error": str(exc)}


def _post_to_facebook(item) -> Dict[str, Any]:
    """Post a queue item to a Facebook Page via Graph API.

    Page ID and page-level access token are resolved from the facebook_social
    InboxConnection for the account.  metadata_json must contain a ``pages``
    list where each entry has ``id`` and ``access_token_enc`` (encrypted with
    src.crypto.encrypt_value).  The first page in the list is used.
    """
    import requests as http

    page_id, page_token = _get_facebook_page_id(item.account_id)
    if not page_id:
        return {"status": "skipped", "reason": "not_connected"}
    if not page_token:
        return {"status": "skipped", "reason": "no_page_token"}

    body: Dict[str, Any] = {"message": item.caption, "access_token": page_token}
    if item.target_url:
        body["link"] = item.target_url

    try:
        resp = http.post(
            f"https://graph.facebook.com/v19.0/{page_id}/feed",
            data=body,
            timeout=15,
        )
        resp.raise_for_status()
        fb_post_id = resp.json().get("id", "")
        return {
            "status": "ok",
            "platform": "facebook",
            "post_url": f"https://www.facebook.com/{fb_post_id}",
        }
    except Exception as exc:
        return {"status": "error", "platform": "facebook", "error": str(exc)}


def _get_facebook_page_id(account_id: int) -> Tuple[Optional[str], Optional[str]]:
    """Resolve the Facebook page ID and decrypted page token for an account.

    Reads the facebook_social InboxConnection for the account and returns the
    first page entry from ``metadata_json["pages"]``.  Page tokens are stored
    as encrypted values under ``access_token_enc`` (per-page).

    Returns:
        Tuple[Optional[str], Optional[str]]: (page_id, page_access_token).
        Both are None if no connected Facebook connection exists.
    """
    from src.crypto import decrypt_value

    conn = InboxConnection.query.filter_by(
        provider="facebook_social", account_id=account_id, status="connected"
    ).first()
    if not conn or not conn.metadata_json:
        return None, None

    pages = conn.metadata_json.get("pages", [])
    if not pages:
        return None, None

    p = pages[0]
    page_id = p.get("id")
    enc = p.get("access_token_enc")
    page_token = decrypt_value(enc) if enc else None
    return page_id, page_token


def _generate_newsletter_html(post: BlogPost, unsubscribe_url: str = "") -> str:
    """Generate HTML newsletter email for a blog post."""
    from flask import current_app
    import html as _html

    base_url = current_app.config.get("SITE_URL", "https://kalevent.com")
    post_url = f"{base_url}/blog/{post.slug}"
    title = _html.escape(post.title or "")
    excerpt = _html.escape(post.excerpt or post.summary or "")

    hero = ""
    if post.hero_image_url:
        alt = _html.escape(post.hero_image_alt or post.title or "")
        hero = f'<img src="{_html.escape(post.hero_image_url)}" alt="{alt}" style="width:100%;height:auto;border-radius:8px;margin-bottom:20px;">'

    unsub_footer = ""
    if unsubscribe_url:
        safe_url = _html.escape(unsubscribe_url)
        unsub_footer = f'<p style="margin:8px 0 0;"><a href="{safe_url}" style="color:#9ca3af;">Unsubscribe</a></p>'

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"><title>{title}</title></head>
<body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;line-height:1.6;color:#333;max-width:600px;margin:0 auto;padding:20px;">
  <div style="background:#f8f9fa;padding:20px;border-radius:8px;margin-bottom:20px;">
    <h1 style="color:#2563eb;margin:0 0 10px;font-size:24px;">{title}</h1>
    <p style="color:#6b7280;margin:0;font-size:14px;">New from the InboxIQ blog</p>
  </div>
  {hero}
  <div style="margin-bottom:20px;">
    <p style="font-size:16px;color:#4b5563;">{excerpt}</p>
  </div>
  <div style="text-align:center;margin:30px 0;">
    <a href="{_html.escape(post_url)}" style="display:inline-block;background:#2563eb;color:white;padding:12px 24px;text-decoration:none;border-radius:6px;font-weight:600;">Read Full Article</a>
  </div>
  <div style="border-top:1px solid #e5e7eb;margin-top:30px;padding-top:20px;text-align:center;color:#6b7280;font-size:12px;">
    <p style="margin:0;">You're receiving this because you're a valued InboxIQ user.</p>
    <p style="margin:4px 0 0;">InboxIQ | Intelligent Inbox Management</p>
    {unsub_footer}
  </div>
</body>
</html>"""


def _send_newsletter_email(to_email: str, user_name: str, post: BlogPost, html_content: str) -> bool:
    """
    Send newsletter email via AWS SES.

    Returns:
        True if sent successfully, False otherwise
    """
    try:
        from src.notifications.emails import send_email

        subject = f"📬 New on the blog: {post.title}"

        return send_email(
            to_email=to_email,
            subject=subject,
            html_body=html_content,
            from_email="blog@kalevent.com"
        )
    except Exception as e:
        logger.error(f"Failed to send newsletter email: {e}")
        return False


