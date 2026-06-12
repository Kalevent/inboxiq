"""
Social Distribution MCP Server

Provides MCP tools for distributing content to social media platforms:
- LinkedIn API integration
- Twitter/X API integration
- Content scheduling and analytics

Tools:
- post_to_linkedin: Share content on LinkedIn
- post_to_twitter: Post tweets or threads on Twitter/X
- schedule_social_post: Schedule content for future posting
- get_social_analytics: Retrieve engagement metrics
"""
from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


def post_to_linkedin(
    text: str,
    url: Optional[str] = None,
    image_url: Optional[str] = None,
    account_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Post content to LinkedIn.

    Args:
        text: Post text content (max 3000 characters)
        url: Optional URL to share
        image_url: Optional image URL to attach
        account_id: LinkedIn account/page ID (defaults to personal profile)

    Returns:
        Dict with post result:
        {
            "status": "success" | "error",
            "post_id": "urn:li:share:...",
            "url": "https://linkedin.com/feed/update/...",
            "error": "error message if failed"
        }
    """
    # Validate input
    if not text or len(text) > 3000:
        return {
            "status": "error",
            "error": "Text is required and must be ≤3000 characters"
        }

    import requests as http

    access_token = os.getenv("LINKEDIN_ACCESS_TOKEN")
    if not access_token:
        return {"status": "error", "error": "LINKEDIN_ACCESS_TOKEN not configured"}

    org_id = account_id or os.getenv("LINKEDIN_ORG_ID", "")
    if not org_id:
        return {"status": "error", "error": "LINKEDIN_ORG_ID not configured"}

    media = []
    if url:
        media.append({
            "status": "READY",
            "originalUrl": url,
            "title": {"text": url},
        })

    body: Dict[str, Any] = {
        "author": f"urn:li:organization:{org_id}",
        "lifecycleState": "PUBLISHED",
        "specificContent": {
            "com.linkedin.ugc.ShareContent": {
                "shareCommentary": {"text": text},
                "shareMediaCategory": "ARTICLE" if media else "NONE",
                **({"media": media} if media else {}),
            }
        },
        "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"},
    }

    try:
        resp = http.post(
            "https://api.linkedin.com/v2/ugcPosts",
            json=body,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
                "X-Restli-Protocol-Version": "2.0.0",
            },
            timeout=15,
        )
        resp.raise_for_status()
        post_id = resp.json().get("id", "")
        logger.info(f"LinkedIn post created: {post_id}")
        return {
            "status": "success",
            "post_id": post_id,
            "url": f"https://www.linkedin.com/feed/update/{post_id}",
        }
    except Exception as exc:
        logger.error(f"LinkedIn API error: {exc}")
        return {"status": "error", "error": str(exc)}


def post_to_twitter(
    text: Optional[str] = None,
    thread: Optional[List[str]] = None,
    reply_to_id: Optional[str] = None,
    media_urls: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Post to Twitter/X (single tweet or thread).

    Args:
        text: Single tweet text (max 280 characters)
        thread: List of tweet texts for thread posting
        reply_to_id: Tweet ID to reply to (for threads)
        media_urls: Optional list of media URLs to attach

    Returns:
        Dict with post result:
        {
            "status": "success" | "error",
            "tweet_ids": ["123...", "456..."],
            "urls": ["https://twitter.com/.../status/123..."],
            "error": "error message if failed"
        }
    """
    # Validate input
    if not text and not thread:
        return {
            "status": "error",
            "error": "Either 'text' or 'thread' is required"
        }

    if text and len(text) > 280:
        return {
            "status": "error",
            "error": "Tweet text must be ≤280 characters"
        }

    if thread:
        for i, tweet in enumerate(thread):
            if len(tweet) > 280:
                return {
                    "status": "error",
                    "error": f"Thread tweet #{i+1} exceeds 280 characters"
                }

    import requests as http
    from requests_oauthlib import OAuth1

    api_key = os.getenv("TWITTER_API_KEY")
    api_secret = os.getenv("TWITTER_API_SECRET")
    access_token = os.getenv("TWITTER_ACCESS_TOKEN")
    access_secret = os.getenv("TWITTER_ACCESS_SECRET")

    if not all([api_key, api_secret, access_token, access_secret]):
        return {"status": "error", "error": "Twitter API credentials not fully configured"}

    auth = OAuth1(api_key, api_secret, access_token, access_secret)
    tweets = thread if thread else [text]
    tweet_ids = []
    reply_to = reply_to_id

    for tweet_text in tweets:
        body: Dict[str, Any] = {"text": tweet_text[:280]}
        if reply_to:
            body["reply"] = {"in_reply_to_tweet_id": reply_to}
        try:
            resp = http.post(
                "https://api.twitter.com/2/tweets",
                json=body,
                auth=auth,
                timeout=15,
            )
            resp.raise_for_status()
            tweet_id = resp.json().get("data", {}).get("id")
            tweet_ids.append(tweet_id)
            reply_to = tweet_id
        except Exception as exc:
            logger.error(f"Twitter API error on tweet {len(tweet_ids)+1}: {exc}")
            break

    if tweet_ids:
        logger.info(f"Twitter thread posted: {len(tweet_ids)} tweet(s)")
        return {
            "status": "success",
            "tweet_ids": tweet_ids,
            "urls": [f"https://twitter.com/i/web/status/{tid}" for tid in tweet_ids],
        }
    return {"status": "error", "error": "no tweets posted"}


def schedule_social_post(
    platform: str,
    content: Dict[str, Any],
    scheduled_at: str,
    timezone: str = "UTC"
) -> Dict[str, Any]:
    """
    Schedule a social media post for future publishing.

    Args:
        platform: Social platform ("linkedin" | "twitter")
        content: Platform-specific content dict
        scheduled_at: ISO 8601 datetime string (e.g., "2026-02-20T14:00:00Z")
        timezone: Timezone for scheduled_at (default: UTC)

    Returns:
        Dict with scheduling result:
        {
            "status": "success" | "error",
            "schedule_id": "uuid...",
            "scheduled_at": "2026-02-20T14:00:00Z",
            "platform": "linkedin",
            "error": "error message if failed"
        }
    """
    from uuid import uuid4

    # Validate platform
    if platform not in ["linkedin", "twitter"]:
        return {
            "status": "error",
            "error": "Platform must be 'linkedin' or 'twitter'"
        }

    # Validate scheduled time is in future
    try:
        scheduled_dt = datetime.fromisoformat(scheduled_at.replace('Z', '+00:00'))
        if scheduled_dt <= datetime.now(timezone=timezone.utc):
            return {
                "status": "error",
                "error": "scheduled_at must be in the future"
            }
    except ValueError as e:
        return {
            "status": "error",
            "error": f"Invalid datetime format: {e}"
        }

    # TODO: Store scheduled post in database and implement scheduler
    # Could use Celery Beat with dynamic schedules or custom scheduler table

    schedule_id = str(uuid4())

    logger.info(f"Scheduled {platform} post for {scheduled_at}: {schedule_id}")

    return {
        "status": "not_implemented",
        "message": "Social post scheduling pending",
        "would_schedule": {
            "schedule_id": schedule_id,
            "platform": platform,
            "scheduled_at": scheduled_at,
            "content": content
        }
    }


def get_social_analytics(
    platform: str,
    post_id: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
) -> Dict[str, Any]:
    """
    Retrieve social media engagement analytics.

    Args:
        platform: Social platform ("linkedin" | "twitter")
        post_id: Specific post ID to get analytics for (optional)
        start_date: Start date for aggregate analytics (ISO 8601)
        end_date: End date for aggregate analytics (ISO 8601)

    Returns:
        Dict with analytics data:
        {
            "status": "success" | "error",
            "platform": "linkedin",
            "metrics": {
                "impressions": 1234,
                "engagements": 56,
                "clicks": 23,
                "shares": 12,
                "comments": 8
            },
            "posts": [...] (if querying multiple posts)
        }
    """
    if platform not in ["linkedin", "twitter"]:
        return {
            "status": "error",
            "error": "Platform must be 'linkedin' or 'twitter'"
        }

    # TODO: Implement analytics API integration
    # LinkedIn: https://docs.microsoft.com/en-us/linkedin/marketing/integrations/community-management/organizations/organization-access-control
    # Twitter: https://developer.twitter.com/en/docs/twitter-api/metrics

    logger.info(f"Analytics request for {platform}: post_id={post_id}, dates={start_date} to {end_date}")

    return {
        "status": "not_implemented",
        "message": f"{platform.capitalize()} analytics API integration pending",
        "would_query": {
            "platform": platform,
            "post_id": post_id,
            "start_date": start_date,
            "end_date": end_date
        }
    }


# MCP Server metadata
MCP_SERVER_NAME = "social-distribution"
MCP_SERVER_VERSION = "0.1.0"

MCP_TOOLS = [
    {
        "name": "post_to_linkedin",
        "description": "Post content to LinkedIn",
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Post text (max 3000 chars)"},
                "url": {"type": "string", "description": "Optional URL to share"},
                "image_url": {"type": "string", "description": "Optional image URL"},
                "account_id": {"type": "string", "description": "LinkedIn account/page ID"}
            },
            "required": ["text"]
        }
    },
    {
        "name": "post_to_twitter",
        "description": "Post to Twitter/X (single tweet or thread)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Single tweet text (max 280 chars)"},
                "thread": {"type": "array", "items": {"type": "string"}, "description": "Thread of tweets"},
                "reply_to_id": {"type": "string", "description": "Tweet ID to reply to"},
                "media_urls": {"type": "array", "items": {"type": "string"}, "description": "Media URLs to attach"}
            }
        }
    },
    {
        "name": "schedule_social_post",
        "description": "Schedule a social post for future publishing",
        "inputSchema": {
            "type": "object",
            "properties": {
                "platform": {"type": "string", "enum": ["linkedin", "twitter"]},
                "content": {"type": "object", "description": "Platform-specific content"},
                "scheduled_at": {"type": "string", "description": "ISO 8601 datetime"},
                "timezone": {"type": "string", "description": "Timezone (default: UTC)"}
            },
            "required": ["platform", "content", "scheduled_at"]
        }
    },
    {
        "name": "get_social_analytics",
        "description": "Retrieve social media engagement analytics",
        "inputSchema": {
            "type": "object",
            "properties": {
                "platform": {"type": "string", "enum": ["linkedin", "twitter"]},
                "post_id": {"type": "string", "description": "Specific post ID"},
                "start_date": {"type": "string", "description": "Start date (ISO 8601)"},
                "end_date": {"type": "string", "description": "End date (ISO 8601)"}
            },
            "required": ["platform"]
        }
    }
]


if __name__ == "__main__":
    # Example usage
    print("Social Distribution MCP Server")
    print(f"Version: {MCP_SERVER_VERSION}")
    print(f"Available tools: {len(MCP_TOOLS)}")
    for tool in MCP_TOOLS:
        print(f"  - {tool['name']}: {tool['description']}")
