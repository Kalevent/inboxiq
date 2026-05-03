"""
YouTube MCP — YouTube Data API v3 wrapper.

Tools:
- upload_video: Upload MP4 from URL to YouTube channel
- add_end_screen: Add end screen card to a published video
- add_card: Add a mid-video card linking to the website
- post_pinned_comment: Post and pin a comment on a video
- get_video_stats: Retrieve view count and like count
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List

import requests

logger = logging.getLogger(__name__)


def _build_youtube_client():
    """Build authenticated YouTube API client using stored OAuth refresh token."""
    client_id = os.getenv("YOUTUBE_CLIENT_ID")
    client_secret = os.getenv("YOUTUBE_CLIENT_SECRET")
    refresh_token = os.getenv("YOUTUBE_REFRESH_TOKEN")

    if not all([client_id, client_secret, refresh_token]):
        missing = [k for k, v in {
            "YOUTUBE_CLIENT_ID": client_id,
            "YOUTUBE_CLIENT_SECRET": client_secret,
            "YOUTUBE_REFRESH_TOKEN": refresh_token,
        }.items() if not v]
        raise ValueError(f"Missing YouTube credentials: {', '.join(missing)}")

    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    creds = Credentials(
        token=None,
        refresh_token=refresh_token,
        client_id=client_id,
        client_secret=client_secret,
        token_uri="https://oauth2.googleapis.com/token",
    )
    return build("youtube", "v3", credentials=creds)


def upload_video(
    file_url: str,
    title: str,
    description: str,
    tags: List[str],
    category_id: str = "28",
) -> Dict[str, Any]:
    """
    Download MP4 from file_url and upload to YouTube channel.

    Returns:
        {"status": "published", "youtube_video_id": "...", "youtube_url": "..."}
        {"status": "error", "error": "..."}
    """
    if not os.getenv("YOUTUBE_CLIENT_ID"):
        return {"status": "error", "error": "YOUTUBE_CLIENT_ID not configured"}

    try:
        youtube = _build_youtube_client()
    except ValueError as exc:
        return {"status": "error", "error": str(exc)}

    try:
        import io
        from googleapiclient.http import MediaIoBaseUpload

        video_resp = requests.get(file_url, timeout=120, stream=True)
        video_resp.raise_for_status()

        video_bytes = io.BytesIO(video_resp.content)
        media = MediaIoBaseUpload(video_bytes, mimetype="video/mp4", resumable=True)

        request = youtube.videos().insert(
            part="snippet,status",
            body={
                "snippet": {
                    "title": title,
                    "description": description,
                    "tags": tags,
                    "categoryId": category_id,
                },
                "status": {"privacyStatus": "public"},
            },
            media_body=media,
        )
        response = request.execute()
        video_id = response["id"]
        return {
            "status": "published",
            "youtube_video_id": video_id,
            "youtube_url": f"https://www.youtube.com/watch?v={video_id}",
        }
    except Exception as exc:
        logger.exception("youtube_mcp.upload_video failed")
        return {"status": "error", "error": str(exc)}


def add_end_screen(video_id: str, cta_url: str) -> Dict[str, Any]:
    """Add an end screen card (last 20 seconds) linking to cta_url."""
    if not os.getenv("YOUTUBE_CLIENT_ID"):
        return {"status": "error", "error": "YOUTUBE_CLIENT_ID not configured"}

    try:
        youtube = _build_youtube_client()
        youtube.videos().update(
            part="endScreens",
            body={
                "id": video_id,
                "endScreens": {
                    "elements": [
                        {
                            "type": "link",
                            "linkType": "url",
                            "externalLinkParameters": {"url": cta_url},
                            "position": {"cornerPosition": "bottomRight"},
                            "timing": {"type": "offsetFromEnd", "offsetMs": 20000},
                        }
                    ]
                },
            },
        ).execute()
        return {"status": "ok"}
    except Exception as exc:
        logger.exception("youtube_mcp.add_end_screen failed")
        return {"status": "error", "error": str(exc)}


def add_card(video_id: str, cta_url: str, offset_ms: int) -> Dict[str, Any]:
    """Add a mid-video link card at offset_ms milliseconds."""
    if not os.getenv("YOUTUBE_CLIENT_ID"):
        return {"status": "error", "error": "YOUTUBE_CLIENT_ID not configured"}

    try:
        youtube = _build_youtube_client()
        youtube.videos().update(
            part="cards",
            body={
                "id": video_id,
                "cards": {
                    "cardDetails": [
                        {
                            "linkDetails": {"url": cta_url, "urlScheme": "https"},
                            "cardType": "link",
                            "teaserText": "Start free",
                        }
                    ]
                },
            },
        ).execute()
        return {"status": "ok"}
    except Exception as exc:
        logger.exception("youtube_mcp.add_card failed")
        return {"status": "error", "error": str(exc)}


def post_pinned_comment(video_id: str, comment_text: str) -> Dict[str, Any]:
    """Post a comment on the video and pin it."""
    if not os.getenv("YOUTUBE_CLIENT_ID"):
        return {"status": "error", "error": "YOUTUBE_CLIENT_ID not configured"}
    if not os.getenv("YOUTUBE_CHANNEL_ID"):
        return {"status": "error", "error": "YOUTUBE_CHANNEL_ID not configured"}

    try:
        youtube = _build_youtube_client()
        channel_id = os.getenv("YOUTUBE_CHANNEL_ID")
        comment_resp = youtube.commentThreads().insert(
            part="snippet",
            body={
                "snippet": {
                    "videoId": video_id,
                    "topLevelComment": {
                        "snippet": {
                            "textOriginal": comment_text,
                            "authorChannelId": {"value": channel_id},
                        }
                    },
                }
            },
        ).execute()
        comment_id = comment_resp["id"]
        youtube.comments().setModerationStatus(
            id=comment_id, moderationStatus="published", banAuthor=False
        ).execute()
        return {"status": "ok", "comment_id": comment_id}
    except Exception as exc:
        logger.exception("youtube_mcp.post_pinned_comment failed")
        return {"status": "error", "error": str(exc)}


def get_video_stats(video_id: str) -> Dict[str, Any]:
    """
    Return view count and like count for a published video.

    Returns: {"status": "ok", "view_count": 0, "like_count": 0} or {"status": "error", ...}
    """
    if not os.getenv("YOUTUBE_CLIENT_ID"):
        return {"status": "error", "error": "YOUTUBE_CLIENT_ID not configured"}

    try:
        youtube = _build_youtube_client()
        resp = youtube.videos().list(part="statistics", id=video_id).execute()
        items = resp.get("items", [])
        if not items:
            return {"status": "error", "error": f"Video {video_id} not found"}
        stats = items[0].get("statistics", {})
        return {
            "status": "ok",
            "view_count": int(stats.get("viewCount", 0)),
            "like_count": int(stats.get("likeCount", 0)),
        }
    except Exception as exc:
        logger.exception("youtube_mcp.get_video_stats failed")
        return {"status": "error", "error": str(exc)}
