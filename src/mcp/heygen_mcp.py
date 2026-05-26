"""
HeyGen MCP — AI video rendering wrapper.

Generic: no YouTube coupling. Reusable for Ads production.
Follows the same pattern as social_distribution_mcp.py.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List

import requests

logger = logging.getLogger(__name__)

HEYGEN_API_BASE = "https://api.heygen.com"


def render_video(
    script: str,
    avatar_id: str,
    voice_id: str,
    video_format: str = "mp4",
    aspect_ratio: str = "16:9",
) -> Dict[str, Any]:
    """
    Submit an avatar talking-head video render job to HeyGen.

    Returns:
        {"status": "submitted", "job_id": "..."} on success
        {"status": "error", "error": "..."} on failure
    """
    api_key = os.getenv("HEYGEN_API_KEY")
    if not api_key:
        return {"status": "error", "error": "HEYGEN_API_KEY not configured"}

    dimension = {
        "16:9": {"width": 1280, "height": 720},
        "9:16": {"width": 720, "height": 1280},
    }.get(aspect_ratio, {"width": 1280, "height": 720})

    payload = {
        "video_inputs": [
            {
                "character": {
                    "type": "avatar",
                    "avatar_id": avatar_id,
                    "avatar_style": "normal",
                },
                "voice": {
                    "type": "text",
                    "input_text": script,
                    "voice_id": voice_id,
                },
                "background": {"type": "color", "value": "#f8fafc"},
            }
        ],
        "dimension": dimension,
        "aspect_ratio": aspect_ratio,
    }

    try:
        resp = requests.post(
            f"{HEYGEN_API_BASE}/v2/video/generate",
            json=payload,
            headers={"X-Api-Key": api_key, "Content-Type": "application/json"},
            timeout=30,
        )
        if resp.status_code != 200:
            return {"status": "error", "error": f"HeyGen API {resp.status_code}: {resp.text[:200]}"}
        data = resp.json().get("data", {})
        return {"status": "submitted", "job_id": data.get("video_id")}
    except Exception as exc:
        logger.exception("heygen.render_video failed")
        return {"status": "error", "error": str(exc)}


def render_illustration_video(
    script: str,
    voice_id: str,
    frame_urls: List[str],
    aspect_ratio: str = "16:9",
) -> Dict[str, Any]:
    """
    Submit an illustration-style video: DALL-E frames as scene backgrounds + voiceover.

    Returns: {"status": "submitted", "job_id": "..."} or {"status": "error", ...}
    """
    api_key = os.getenv("HEYGEN_API_KEY")
    if not api_key:
        return {"status": "error", "error": "HEYGEN_API_KEY not configured"}

    if not frame_urls:
        return {"status": "error", "error": "frame_urls is empty — illustration frames required"}

    dimension = {
        "16:9": {"width": 1280, "height": 720},
        "9:16": {"width": 720, "height": 1280},
    }.get(aspect_ratio, {"width": 1280, "height": 720})

    # First frame carries the full voiceover; subsequent frames are visual-only
    video_inputs = []
    for i, url in enumerate(frame_urls):
        voice = (
            {"type": "text", "input_text": script, "voice_id": voice_id}
            if i == 0
            else {"type": "silence", "duration": 1}
        )
        video_inputs.append({
            "voice": voice,
            "background": {"type": "image", "url": url},
        })

    payload = {"video_inputs": video_inputs, "dimension": dimension, "aspect_ratio": aspect_ratio}

    try:
        resp = requests.post(
            f"{HEYGEN_API_BASE}/v2/video/generate",
            json=payload,
            headers={"X-Api-Key": api_key, "Content-Type": "application/json"},
            timeout=30,
        )
        if resp.status_code != 200:
            return {"status": "error", "error": f"HeyGen API {resp.status_code}: {resp.text[:200]}"}
        data = resp.json().get("data", {})
        return {"status": "submitted", "job_id": data.get("video_id")}
    except Exception as exc:
        logger.exception("heygen.render_illustration_video failed")
        return {"status": "error", "error": str(exc)}


def get_render_status(job_id: str) -> Dict[str, Any]:
    """
    Poll a HeyGen render job for status.

    Returns:
        {"status": "processing"} — still rendering
        {"status": "completed", "render_url": "https://..."} — done
        {"status": "failed", "error": "..."} — failed
        {"status": "error", "error": "..."} — API/network error
    """
    api_key = os.getenv("HEYGEN_API_KEY")
    if not api_key:
        return {"status": "error", "error": "HEYGEN_API_KEY not configured"}

    try:
        resp = requests.get(
            f"{HEYGEN_API_BASE}/v1/video_status.get",
            params={"video_id": job_id},
            headers={"X-Api-Key": api_key},
            timeout=15,
        )
        if resp.status_code != 200:
            return {"status": "error", "error": f"HeyGen API {resp.status_code}: {resp.text[:200]}"}
        data = resp.json().get("data", {})
        heygen_status = data.get("status", "processing")
        if heygen_status == "completed":
            return {"status": "completed", "render_url": data.get("video_url", "")}
        if heygen_status == "failed":
            return {"status": "failed", "error": data.get("error", "unknown")}
        return {"status": "processing"}
    except Exception as exc:
        logger.exception("heygen.get_render_status failed")
        return {"status": "error", "error": str(exc)}
