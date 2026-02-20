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
from typing import Dict, List, Any, Optional

from src.celery_inboxiq import celery
from src.extensions import db
from src.models import BlogPost, GeneratedContent, Account
from src.sanitize import sanitize_html

logger = logging.getLogger(__name__)


@celery.task(name="marketing.publish_blog_post")
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

    # Validate post is ready to publish
    if post.status != "ready":
        logger.warning(f"Blog post {blog_post_id} status is {post.status}, expected 'ready'")
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
        db.session.commit()

        logger.info(f"Published blog post: {post.title} ({post.id})")

        # Trigger distribution channels asynchronously
        distribution_results = {}

        # 1. Distribute to social media
        if post.funnel_stage in ["VISITS", "DISCOVERY"]:  # Only distribute awareness/discovery content
            try:
                social_result = distribute_to_social.delay(blog_post_id)
                distribution_results["social"] = {"task_id": social_result.id, "status": "queued"}
            except Exception as e:
                logger.error(f"Failed to queue social distribution: {e}")
                distribution_results["social"] = {"status": "error", "error": str(e)}

        # 2. Send email newsletter
        try:
            newsletter_result = send_blog_newsletter.delay(blog_post_id)
            distribution_results["newsletter"] = {"task_id": newsletter_result.id, "status": "queued"}
        except Exception as e:
            logger.error(f"Failed to queue newsletter: {e}")
            distribution_results["newsletter"] = {"status": "error", "error": str(e)}

        # 3. Submit to search engines (if enabled)
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


@celery.task(name="marketing.distribute_to_social")
def distribute_to_social(blog_post_id: str) -> Dict[str, Any]:
    """
    Distribute blog post to social media channels (LinkedIn, Twitter).

    Args:
        blog_post_id: BlogPost ID to distribute

    Returns:
        Dict with distribution results per platform
    """
    from src.models import BlogPost

    post = db.session.get(BlogPost, blog_post_id)
    if not post:
        return {"status": "error", "reason": "post_not_found"}

    results = {}

    # Generate social media posts using DSPy
    social_content = _generate_social_content(post)

    # Distribute to LinkedIn
    try:
        linkedin_result = _post_to_linkedin(post, social_content.get("linkedin"))
        results["linkedin"] = linkedin_result
    except Exception as e:
        logger.error(f"LinkedIn distribution failed: {e}")
        results["linkedin"] = {"status": "error", "error": str(e)}

    # Distribute to Twitter
    try:
        twitter_result = _post_to_twitter(post, social_content.get("twitter"))
        results["twitter"] = twitter_result
    except Exception as e:
        logger.error(f"Twitter distribution failed: {e}")
        results["twitter"] = {"status": "error", "error": str(e)}

    return {
        "status": "completed",
        "blog_post_id": blog_post_id,
        "platforms": results
    }


@celery.task(name="marketing.send_blog_newsletter")
def send_blog_newsletter(blog_post_id: str) -> Dict[str, Any]:
    """
    Send email newsletter to subscribers about new blog post.

    Args:
        blog_post_id: BlogPost ID to send newsletter about

    Returns:
        Dict with email sending results
    """
    from src.models import BlogPost, User, Account

    post = db.session.get(BlogPost, blog_post_id)
    if not post:
        return {"status": "error", "reason": "post_not_found"}

    # Get newsletter subscribers (users who opted in)
    # For now, we'll send to all active trial/paid users
    subscribers = db.session.query(User).join(
        Account, User.account_id == Account.id
    ).filter(
        Account.deleted == False,  # noqa: E712
        User.email.isnot(None)
    ).limit(100).all()  # Limit for initial rollout

    if not subscribers:
        return {"status": "skipped", "reason": "no_subscribers"}

    # Generate newsletter content
    newsletter_html = _generate_newsletter_html(post)

    # Send emails
    sent_count = 0
    failed_count = 0

    for user in subscribers:
        try:
            success = _send_newsletter_email(
                to_email=user.email,
                user_name=user.name or user.email.split('@')[0],
                post=post,
                html_content=newsletter_html
            )
            if success:
                sent_count += 1
            else:
                failed_count += 1
        except Exception as e:
            logger.error(f"Failed to send newsletter to {user.email}: {e}")
            failed_count += 1

    return {
        "status": "completed",
        "blog_post_id": blog_post_id,
        "sent": sent_count,
        "failed": failed_count,
        "total_subscribers": len(subscribers)
    }


@celery.task(name="marketing.submit_to_search_engines")
def submit_to_search_engines(blog_post_id: str) -> Dict[str, Any]:
    """
    Submit blog post URL to search engines for indexing.

    Args:
        blog_post_id: BlogPost ID to submit

    Returns:
        Dict with submission results
    """
    from src.models import BlogPost
    from flask import current_app

    post = db.session.get(BlogPost, blog_post_id)
    if not post:
        return {"status": "error", "reason": "post_not_found"}

    # Construct blog post URL
    base_url = current_app.config.get("SITE_URL", "https://kalevent.com")
    post_url = f"{base_url}/blog/{post.slug}"

    results = {}

    # Google Search Console (if configured)
    google_api_key = current_app.config.get("GOOGLE_SEARCH_CONSOLE_KEY")
    if google_api_key:
        try:
            # Would integrate with Google Indexing API here
            # For now, just log
            logger.info(f"Would submit {post_url} to Google Search Console")
            results["google"] = {"status": "not_implemented"}
        except Exception as e:
            results["google"] = {"status": "error", "error": str(e)}

    # Bing Webmaster Tools (if configured)
    bing_api_key = current_app.config.get("BING_WEBMASTER_KEY")
    if bing_api_key:
        try:
            # Would integrate with Bing URL Submission API here
            logger.info(f"Would submit {post_url} to Bing Webmaster Tools")
            results["bing"] = {"status": "not_implemented"}
        except Exception as e:
            results["bing"] = {"status": "error", "error": str(e)}

    return {
        "status": "completed",
        "blog_post_id": blog_post_id,
        "url": post_url,
        "search_engines": results
    }


# Helper functions

def _generate_social_content(post: BlogPost) -> Dict[str, Any]:
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


def _post_to_linkedin(post: BlogPost, content: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Post to LinkedIn via API.

    Returns:
        Dict with posting result
    """
    if not content:
        return {"status": "skipped", "reason": "no_content"}

    # TODO: Implement LinkedIn API integration
    # Would use LinkedIn Share API: https://docs.microsoft.com/en-us/linkedin/marketing/integrations/community-management/shares/share-api

    logger.info(f"Would post to LinkedIn: {content.get('text', '')[:100]}...")

    return {
        "status": "not_implemented",
        "platform": "linkedin",
        "message": "LinkedIn API integration pending"
    }


def _post_to_twitter(post: BlogPost, content: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Post thread to Twitter via API.

    Returns:
        Dict with posting result
    """
    if not content:
        return {"status": "skipped", "reason": "no_content"}

    # TODO: Implement Twitter API integration
    # Would use Twitter API v2: https://developer.twitter.com/en/docs/twitter-api/tweets/manage-tweets/api-reference/post-tweets

    thread = content.get("thread", [])
    logger.info(f"Would post Twitter thread with {len(thread)} tweets")

    return {
        "status": "not_implemented",
        "platform": "twitter",
        "message": "Twitter API integration pending",
        "thread_length": len(thread)
    }


def _generate_newsletter_html(post: BlogPost) -> str:
    """
    Generate HTML email newsletter from blog post.

    Returns:
        HTML email content
    """
    from flask import current_app

    base_url = current_app.config.get("SITE_URL", "https://kalevent.com")
    post_url = f"{base_url}/blog/{post.slug}"

    # Simple newsletter template
    # TODO: Use proper email template with Jinja2
    html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{post.title}</title>
</head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
    <div style="background: #f8f9fa; padding: 20px; border-radius: 8px; margin-bottom: 20px;">
        <h1 style="color: #2563eb; margin: 0 0 10px 0; font-size: 24px;">{post.title}</h1>
        <p style="color: #6b7280; margin: 0; font-size: 14px;">New from the InboxIQ blog</p>
    </div>

    {f'<img src="{post.hero_image_url}" alt="{post.hero_image_alt or post.title}" style="width: 100%; height: auto; border-radius: 8px; margin-bottom: 20px;">' if post.hero_image_url else ''}

    <div style="margin-bottom: 20px;">
        <p style="font-size: 16px; color: #4b5563;">{post.excerpt or post.summary or ''}</p>
    </div>

    <div style="text-align: center; margin: 30px 0;">
        <a href="{post_url}" style="display: inline-block; background: #2563eb; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px; font-weight: 600;">
            Read Full Article
        </a>
    </div>

    <div style="border-top: 1px solid #e5e7eb; margin-top: 30px; padding-top: 20px; text-align: center; color: #6b7280; font-size: 12px;">
        <p>You're receiving this because you're a valued InboxIQ user.</p>
        <p>InboxIQ | Intelligent Inbox Management</p>
    </div>
</body>
</html>"""

    return html


def _send_newsletter_email(to_email: str, user_name: str, post: BlogPost, html_content: str) -> bool:
    """
    Send newsletter email via AWS SES.

    Returns:
        True if sent successfully, False otherwise
    """
    try:
        from src.email_utils import send_email

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


@celery.task(name="marketing.auto_publish_ready_posts")
def auto_publish_ready_posts(max_posts: int = 5) -> Dict[str, Any]:
    """
    Automatically publish blog posts that are in 'ready' status.

    This task runs periodically to publish queued blog posts.

    Args:
        max_posts: Maximum number of posts to publish in one run

    Returns:
        Dict with publication results
    """
    from src.models import BlogPost

    ready_posts = db.session.query(BlogPost).filter(
        BlogPost.status == "ready"
    ).order_by(
        BlogPost.created_at.asc()
    ).limit(max_posts).all()

    if not ready_posts:
        return {"status": "no_posts", "published": 0}

    results = []
    for post in ready_posts:
        try:
            result = publish_blog_post.delay(post.id)
            results.append({
                "post_id": post.id,
                "title": post.title,
                "task_id": result.id,
                "status": "queued"
            })
        except Exception as e:
            logger.error(f"Failed to queue publication for {post.id}: {e}")
            results.append({
                "post_id": post.id,
                "title": post.title,
                "status": "error",
                "error": str(e)
            })

    return {
        "status": "completed",
        "published": len(results),
        "posts": results
    }
