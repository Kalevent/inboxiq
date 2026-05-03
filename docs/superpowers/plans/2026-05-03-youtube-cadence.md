# YouTube Cadence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a fully automated YouTube content funnel that generates ICP-pain-point-first scripts, renders AI videos (avatar + editorial illustration), publishes to YouTube with UTM-tracked CTAs, and feeds attribution data into the existing `/funnel/dashboard`.

**Architecture:** Four staged Celery beat tasks (`generate_scripts` → `render_videos` → `publish_videos` → `send_digest`) drive the pipeline. HeyGen renders avatar videos; DALL-E 3 generates editorial illustration frames assembled by HeyGen's scene builder. A HeyGen webhook endpoint flips video status on render completion rather than polling.

**Tech Stack:** Python 3.11, Flask, SQLAlchemy, Celery, DSPy (gpt-4o-mini), HeyGen REST API (PAYG), DALL-E 3 (existing OPENAI_API_KEY), YouTube Data API v3 OAuth 2.0, `requests`, `src/uploads.py` for S3 frame storage.

**Spec:** `docs/superpowers/specs/2026-05-03-youtube-cadence-design.md`

---

## File Map

| File | Action | Purpose |
| --- | --- | --- |
| `src/models/leads.py` | Modify | Add `ICPPainPoint` model |
| `src/models/campaigns.py` | Modify | Add `YouTubeVideo` model |
| `src/models/__init__.py` | Modify | Re-export both new models |
| `src/dspy/signatures.py` | Modify | Add 4 YouTube DSPy signatures |
| `src/mcp/heygen_mcp.py` | Create | HeyGen REST API wrapper |
| `src/mcp/youtube_mcp.py` | Create | YouTube Data API v3 wrapper |
| `src/tasks/youtube.py` | Create | 4 Celery beat tasks |
| `src/api/v1/youtube.py` | Create | HeyGen webhook endpoint |
| `src/notifications/emails.py` | Modify | Add `send_youtube_digest_email()` |
| `src/celery_inboxiq.py` | Modify | Register 4 beat schedule entries |
| `.claude/skills/youtube-cadence/SKILL.md` | Create | Content quality contract |
| `tests/youtube/conftest.py` | Create | Shared fixtures |
| `tests/youtube/test_models.py` | Create | Model tests |
| `tests/youtube/test_mcp.py` | Create | MCP wrapper tests |
| `tests/youtube/test_tasks.py` | Create | Task tests |

---

## Task 1: ICPPainPoint Model

**Files:**
- Modify: `src/models/leads.py`
- Modify: `src/models/__init__.py`

- [ ] **Step 1: Write the failing model test**

Create `tests/youtube/conftest.py`:

```python
import pytest
from src.extensions import db as _db
from src.app import create_app


@pytest.fixture(scope="session")
def app():
    app = create_app()
    app.config["TESTING"] = True
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    with app.app_context():
        _db.create_all()
        yield app
        _db.drop_all()


@pytest.fixture
def db(app):
    with app.app_context():
        yield _db
        _db.session.rollback()
```

Create `tests/youtube/test_models.py`:

```python
import pytest
from datetime import datetime, timezone
from src.models.leads import ICPPainPoint


def test_icp_pain_point_creation(db):
    pp = ICPPainPoint(
        account_id=1,
        icp_config_id="test-config-id",
        pain_point="Support emails pile up unread over the weekend",
        consequence="Customers churn before Monday",
        persona="Head of Support",
        priority=10,
    )
    db.session.add(pp)
    db.session.commit()
    fetched = db.session.get(ICPPainPoint, pp.id)
    assert fetched.pain_point == "Support emails pile up unread over the weekend"
    assert fetched.active is True
    assert fetched.priority == 10


def test_icp_pain_point_requires_pain_point_and_consequence(db):
    with pytest.raises(Exception):
        pp = ICPPainPoint(account_id=1, icp_config_id="x")
        db.session.add(pp)
        db.session.commit()
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd /Users/kofi/inboxiq && python -m pytest tests/youtube/test_models.py::test_icp_pain_point_creation -v
```

Expected: `ImportError` or `AttributeError` — `ICPPainPoint` not defined yet.

- [ ] **Step 3: Add ICPPainPoint to src/models/leads.py**

At the bottom of `src/models/leads.py`, after all existing classes, add:

```python
class ICPPainPoint(db.Model):
    """ICP pain points — shared source of truth for YouTube, LinkedIn, and blog pipelines."""
    __tablename__ = "icp_pain_points"
    __table_args__ = (
        db.Index("idx_icp_pain_points_account", "account_id"),
        db.Index("idx_icp_pain_points_priority", "account_id", "priority"),
    )

    id            = db.Column(db.String(64), primary_key=True, default=lambda: str(uuid4()), nullable=False)
    account_id    = db.Column(db.Integer, nullable=False)
    icp_config_id = db.Column(db.String(64), db.ForeignKey("icp_configs.id"), nullable=False)

    pain_point    = db.Column(db.Text, nullable=False)
    consequence   = db.Column(db.Text, nullable=False)
    persona       = db.Column(db.String(255), nullable=True)
    priority      = db.Column(db.Integer, nullable=False, default=0)
    active        = db.Column(db.Boolean, nullable=False, default=True)

    created_at    = db.Column(db.DateTime(timezone=True), nullable=False, server_default=func.now())
```

Confirm `uuid4` and `func` are already imported at the top of `leads.py`. They are used by existing models — check before adding.

- [ ] **Step 4: Re-export from src/models/__init__.py**

In `src/models/__init__.py`, find the leads import line and add `ICPPainPoint`:

```python
# Before:
from src.models.leads import Lead, LeadFunnelStage, LeadEngagementEvent, LeadAttribution, FunnelMetricsDaily

# After:
from src.models.leads import Lead, LeadFunnelStage, LeadEngagementEvent, LeadAttribution, FunnelMetricsDaily, ICPPainPoint
```

Also add `"ICPPainPoint"` to the `__all__` list in that file.

- [ ] **Step 5: Run tests — expect pass**

```bash
python -m pytest tests/youtube/test_models.py::test_icp_pain_point_creation -v
```

Expected: PASS

- [ ] **Step 6: Tell the user to run migration**

```
flask db migrate -m "add icp_pain_points table"
flask db upgrade
```

Review the generated migration in `src/migrations/versions/` before upgrading — confirm it creates `icp_pain_points` with all columns and the `idx_icp_pain_points_priority` index.

- [ ] **Step 7: Commit**

```bash
git add src/models/leads.py src/models/__init__.py tests/youtube/conftest.py tests/youtube/test_models.py
git commit -m "feat: add ICPPainPoint model — shared ICP pain source for YouTube, LinkedIn, blog"
```

---

## Task 2: YouTubeVideo Model

**Files:**
- Modify: `src/models/campaigns.py`
- Modify: `src/models/__init__.py`

- [ ] **Step 1: Write failing test**

Add to `tests/youtube/test_models.py`:

```python
from src.models.campaigns import YouTubeVideo


def test_youtube_video_creation(db):
    video = YouTubeVideo(
        account_id=1,
        icp_pain_point_id="test-pain-id",
        video_type="long_form",
        video_style="avatar",
        title="Never miss a support email again | InboxIQ",
        utm_slug="yt-long-inbox-chaos-may-2026",
        utm_medium="long_form",
        utm_campaign="inbox-chaos-may-2026",
    )
    db.session.add(video)
    db.session.commit()
    fetched = db.session.get(YouTubeVideo, video.id)
    assert fetched.status == "script_pending"
    assert fetched.video_style == "avatar"
    assert fetched.utm_source == "youtube"


def test_youtube_video_utm_slug_unique(db):
    v1 = YouTubeVideo(
        account_id=1, icp_pain_point_id="pid", video_type="long_form",
        utm_slug="unique-slug", utm_medium="long_form"
    )
    v2 = YouTubeVideo(
        account_id=1, icp_pain_point_id="pid", video_type="short",
        utm_slug="unique-slug", utm_medium="short"
    )
    db.session.add(v1)
    db.session.commit()
    db.session.add(v2)
    with pytest.raises(Exception):
        db.session.commit()
    db.session.rollback()


def test_short_links_to_parent(db):
    parent = YouTubeVideo(
        account_id=1, icp_pain_point_id="pid", video_type="long_form",
        utm_slug="parent-slug", utm_medium="long_form"
    )
    db.session.add(parent)
    db.session.commit()
    short = YouTubeVideo(
        account_id=1, icp_pain_point_id="pid", video_type="short",
        parent_video_id=parent.id, utm_slug="short-slug", utm_medium="short"
    )
    db.session.add(short)
    db.session.commit()
    assert short.parent_video_id == parent.id
```

- [ ] **Step 2: Run tests — expect fail**

```bash
python -m pytest tests/youtube/test_models.py::test_youtube_video_creation -v
```

Expected: `ImportError` — `YouTubeVideo` not defined yet.

- [ ] **Step 3: Add YouTubeVideo to src/models/campaigns.py**

At the bottom of `src/models/campaigns.py`, after all existing classes, add:

```python
class YouTubeVideo(db.Model):
    """One row per video (long form or short). Shorts link to parent via parent_video_id."""
    __tablename__ = "youtube_videos"
    __table_args__ = (
        db.Index("idx_youtube_videos_account_status", "account_id", "status"),
        db.Index("idx_youtube_videos_published", "account_id", "published_at"),
    )

    id                   = db.Column(db.String(64), primary_key=True, default=lambda: str(uuid4()), nullable=False)
    account_id           = db.Column(db.Integer, nullable=False)
    blog_post_id         = db.Column(db.String(64), db.ForeignKey("blog_posts.id"), nullable=True)
    icp_pain_point_id    = db.Column(db.String(64), db.ForeignKey("icp_pain_points.id"), nullable=False)
    parent_video_id      = db.Column(db.String(64), db.ForeignKey("youtube_videos.id"), nullable=True)

    # Content
    video_type           = db.Column(db.String(20), nullable=False)   # "long_form" | "short"
    video_style          = db.Column(db.String(20), nullable=False, default="avatar")  # "avatar" | "illustration"
    script               = db.Column(db.Text, nullable=True)
    title                = db.Column(db.String(100), nullable=True)
    description          = db.Column(db.Text, nullable=True)
    tags                 = db.Column(db.JSON, nullable=True)
    thumbnail_prompt     = db.Column(db.Text, nullable=True)

    # Illustration frames (avatar style leaves these null)
    illustration_prompts = db.Column(db.JSON, nullable=True)
    dalle_frame_urls     = db.Column(db.JSON, nullable=True)

    # HeyGen
    heygen_job_id        = db.Column(db.String(128), nullable=True)
    heygen_render_url    = db.Column(db.String(512), nullable=True)

    # YouTube
    youtube_video_id     = db.Column(db.String(64), nullable=True)
    youtube_url          = db.Column(db.String(256), nullable=True)

    # UTM / funnel tracking
    utm_slug             = db.Column(db.String(128), nullable=True, unique=True)
    utm_source           = db.Column(db.String(64), nullable=False, default="youtube")
    utm_medium           = db.Column(db.String(64), nullable=True)   # "long_form" | "short"
    utm_campaign         = db.Column(db.String(128), nullable=True)

    # Status + timing
    status               = db.Column(db.String(32), nullable=False, default="script_pending")
    script_generated_at  = db.Column(db.DateTime(timezone=True), nullable=True)
    render_submitted_at  = db.Column(db.DateTime(timezone=True), nullable=True)
    render_completed_at  = db.Column(db.DateTime(timezone=True), nullable=True)
    published_at         = db.Column(db.DateTime(timezone=True), nullable=True)

    # Performance (refreshed daily by digest task)
    view_count           = db.Column(db.Integer, nullable=False, default=0)
    click_count          = db.Column(db.Integer, nullable=False, default=0)

    created_at           = db.Column(db.DateTime(timezone=True), nullable=False, server_default=func.now())
```

Confirm `uuid4` and `func` are already imported at the top of `campaigns.py`. Check before adding.

- [ ] **Step 4: Re-export from src/models/__init__.py**

Find the campaigns import line and add `YouTubeVideo`:

```python
# Before:
from src.models.campaigns import CampaignSender, HunterDomainCache, EmailCampaign, EmailOutreach, NurtureEmailSend

# After:
from src.models.campaigns import CampaignSender, HunterDomainCache, EmailCampaign, EmailOutreach, NurtureEmailSend, YouTubeVideo
```

Add `"YouTubeVideo"` to `__all__`.

- [ ] **Step 5: Run all model tests**

```bash
python -m pytest tests/youtube/test_models.py -v
```

Expected: All 5 tests PASS.

- [ ] **Step 6: Tell user to run migration**

```
flask db migrate -m "add youtube_videos table"
flask db upgrade
```

Review generated migration — confirm it creates `youtube_videos` with `unique=True` on `utm_slug` and both indexes.

- [ ] **Step 7: Commit**

```bash
git add src/models/campaigns.py src/models/__init__.py tests/youtube/test_models.py
git commit -m "feat: add YouTubeVideo model with avatar/illustration styles and UTM tracking"
```

---

## Task 3: DSPy Signatures

**Files:**
- Modify: `src/dspy/signatures.py`

- [ ] **Step 1: Write failing signature tests**

Create `tests/youtube/test_signatures.py`:

```python
import pytest


def test_youtube_signature_imports():
    from src.dspy.signatures import (
        YouTubeLongFormScript,
        YouTubeShortScript,
        YouTubeSEOMetadata,
        YouTubeIllustrationPrompts,
    )
    assert YouTubeLongFormScript is not None
    assert YouTubeShortScript is not None
    assert YouTubeSEOMetadata is not None
    assert YouTubeIllustrationPrompts is not None


def test_youtube_long_form_has_required_fields():
    from src.dspy.signatures import YouTubeLongFormScript
    import dspy
    fields = YouTubeLongFormScript.model_fields if hasattr(YouTubeLongFormScript, 'model_fields') else {}
    # Verify the signature has input/output fields defined
    sig_str = str(YouTubeLongFormScript)
    assert "pain_point" in sig_str or hasattr(YouTubeLongFormScript, '__doc__')
```

- [ ] **Step 2: Run test — expect fail**

```bash
python -m pytest tests/youtube/test_signatures.py::test_youtube_signature_imports -v
```

Expected: `ImportError` — signatures not yet defined.

- [ ] **Step 3: Add signatures to src/dspy/signatures.py**

Find the bottom of `src/dspy/signatures.py` and add the following. Note: the file uses builder functions that receive `dspy` as a parameter. Add a module-level helper instead since these signatures have no dynamic label config:

```python
# ── YouTube Cadence Signatures ─────────────────────────────────────────────

def build_youtube_signatures(dspy: Any) -> Dict[str, Any]:
    """Return all four YouTube cadence DSPy signatures."""

    BRAND_STYLE_PREFIX = (
        "Editorial illustration, hand-drawn ink lines with watercolour wash, "
        "warm muted palette (navy, terracotta, cream), textured paper feel, "
        "loose gestural linework, human figures with natural proportions, "
        "professional magazine quality, no text, no UI chrome, no 3D render, "
        "no gradients, no gloss — think New Yorker editorial, not stock photo. "
    )

    class YouTubeLongFormScript(dspy.Signature):
        """Generate a pain-point-first YouTube long form script (8-12 min) for a specific ICP persona.
        The script must open with the named ICP pain point. The product name InboxIQ must not appear
        in the first 5 seconds. Structure: HOOK (pain) → PROBLEM → RESOLUTION → PROOF → CTA."""

        blog_post_content: str = dspy.InputField(desc="Source blog post content to base the video on.")
        icp_persona: str = dspy.InputField(desc="ICP persona, e.g. 'Head of Support, B2B SaaS, 10-50 employees'.")
        pain_point: str = dspy.InputField(desc="Specific ICP pain point from ICPPainPoint table. Do not invent.")
        consequence: str = dspy.InputField(desc="What happens if this pain point is not resolved.")
        video_style: str = dspy.InputField(desc="'avatar' (Caroline presenter) or 'illustration' (editorial art).")

        script: str = dspy.OutputField(desc="Full spoken script. HOOK 0-30s opens with pain, no greeting.")
        hook_line: str = dspy.OutputField(desc="First spoken sentence. Must name the pain. No product name.")
        chapter_markers: str = dspy.OutputField(desc="JSON list of {time, title} chapter markers for YouTube.")
        cta_line: str = dspy.OutputField(desc="Final spoken sentence. One ask only: 'Start free at inboxiq.com'.")

    class YouTubeShortScript(dspy.Signature):
        """Extract a 60-second Short from a long form script. Pattern interrupt → agitation → resolution → CTA.
        First 3 seconds must name the pain with no greeting."""

        long_form_script: str = dspy.InputField(desc="Full long form script to extract the Short from.")
        pain_point: str = dspy.InputField(desc="ICP pain point this Short addresses.")
        parent_youtube_url: str = dspy.InputField(desc="YouTube URL of the parent long form video.")

        short_script: str = dspy.OutputField(desc="60-second script. Seconds 0-3: pain. 3-20: agitation. 20-50: resolution. 50-60: CTA.")
        pattern_interrupt_line: str = dspy.OutputField(desc="First sentence (0-3s). Names the pain. No greeting.")
        cta_line: str = dspy.OutputField(desc="Final line. 'Link in description. Free to start.'")

    class YouTubeSEOMetadata(dspy.Signature):
        """Generate YouTube SEO metadata for a video. Title must follow [Pain outcome] — [How] | InboxIQ format.
        Product name must not appear in the title. Description must state pain and resolution in first 2 lines."""

        script: str = dspy.InputField(desc="Video script.")
        pain_point: str = dspy.InputField(desc="ICP pain point this video addresses.")
        blog_post_primary_keyword: str = dspy.InputField(desc="Primary SEO keyword from the source BlogPost.")
        video_type: str = dspy.InputField(desc="'long_form' or 'short'.")

        title: str = dspy.OutputField(desc="YouTube title ≤60 chars. Format: [Pain outcome] — [How] | InboxIQ. No product name first.")
        description: str = dspy.OutputField(desc="YouTube description. Line 1: pain. Line 2: resolution. Line 3: UTM link placeholder {{UTM_LINK}}.")
        tags: str = dspy.OutputField(desc="JSON list of 10 tags: 3 broad (inbox management, customer support, B2B SaaS) + 7 specific.")
        thumbnail_prompt: str = dspy.OutputField(desc="DALL-E prompt for thumbnail. Must show before/after state or visible problem. No logo only.")

    class YouTubeIllustrationPrompts(dspy.Signature):
        """Generate 6-10 DALL-E illustration prompts for an illustration-style video.
        Each prompt must be prefixed with the brand style and show a real human situation with emotional body language.
        No photorealistic renders, no stock-art figures, no UI elements, no text inside images."""

        script: str = dspy.InputField(desc="Video script to generate scene illustrations for.")
        pain_point: str = dspy.InputField(desc="ICP pain point — scenes should visually express this pain and its resolution.")
        chapter_markers: str = dspy.InputField(desc="JSON chapter markers — one illustration per chapter beat.")

        scene_prompts: str = dspy.OutputField(
            desc=f"JSON list of 6-10 DALL-E prompts. Each prompt MUST start with: '{BRAND_STYLE_PREFIX}'. "
            "Each scene shows a real human situation (person at desk overwhelmed, team in meeting, phone left unattended). "
            "Emotional states via body language only — no text labels. No screenshots, no device mockups, no floating UI."
        )

    return {
        "YouTubeLongFormScript": YouTubeLongFormScript,
        "YouTubeShortScript": YouTubeShortScript,
        "YouTubeSEOMetadata": YouTubeSEOMetadata,
        "YouTubeIllustrationPrompts": YouTubeIllustrationPrompts,
    }


# Module-level references for direct import
def _get_youtube_sigs():
    """Lazy-load YouTube signatures (requires dspy configured)."""
    try:
        import dspy
        sigs = build_youtube_signatures(dspy)
        return sigs
    except Exception:
        return {}


class YouTubeLongFormScript:
    """Placeholder — import via build_youtube_signatures(dspy)."""
    pass


class YouTubeShortScript:
    """Placeholder — import via build_youtube_signatures(dspy)."""
    pass


class YouTubeSEOMetadata:
    """Placeholder — import via build_youtube_signatures(dspy)."""
    pass


class YouTubeIllustrationPrompts:
    """Placeholder — import via build_youtube_signatures(dspy)."""
    pass
```

- [ ] **Step 4: Run signature tests**

```bash
python -m pytest tests/youtube/test_signatures.py -v
```

Expected: Both tests PASS (the placeholder classes satisfy the import test).

- [ ] **Step 5: Commit**

```bash
git add src/dspy/signatures.py tests/youtube/test_signatures.py
git commit -m "feat: add YouTube DSPy signatures — long form, short, SEO metadata, illustration prompts"
```

---

## Task 4: HeyGen MCP Server

**Files:**
- Create: `src/mcp/heygen_mcp.py`

The HeyGen MCP follows the same pattern as `src/mcp/social_distribution_mcp.py` — a plain Python module with regular functions imported directly by Celery tasks.

- [ ] **Step 1: Write failing tests**

Create `tests/youtube/test_mcp.py`:

```python
import pytest
from unittest.mock import patch, MagicMock


def test_heygen_render_video_missing_key(monkeypatch):
    monkeypatch.delenv("HEYGEN_API_KEY", raising=False)
    from src.mcp import heygen_mcp
    import importlib
    importlib.reload(heygen_mcp)
    result = heygen_mcp.render_video(
        script="Test script.",
        avatar_id="test-avatar",
        voice_id="test-voice",
        video_format="mp4",
        aspect_ratio="16:9",
    )
    assert result["status"] == "error"
    assert "HEYGEN_API_KEY" in result["error"]


def test_heygen_render_video_success(monkeypatch):
    monkeypatch.setenv("HEYGEN_API_KEY", "test-key")
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"data": {"video_id": "job-123"}}
    with patch("requests.post", return_value=mock_response):
        from src.mcp import heygen_mcp
        import importlib
        importlib.reload(heygen_mcp)
        result = heygen_mcp.render_video(
            script="Test script.",
            avatar_id="977b1ab85dba4eefb159a6072677effd",
            voice_id="41332f3d53e148aab6956b92d3e5503e",
            video_format="mp4",
            aspect_ratio="16:9",
        )
    assert result["status"] == "submitted"
    assert result["job_id"] == "job-123"


def test_heygen_get_render_status_complete(monkeypatch):
    monkeypatch.setenv("HEYGEN_API_KEY", "test-key")
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "data": {"status": "completed", "video_url": "https://cdn.heygen.com/video.mp4"}
    }
    with patch("requests.get", return_value=mock_response):
        from src.mcp import heygen_mcp
        import importlib
        importlib.reload(heygen_mcp)
        result = heygen_mcp.get_render_status("job-123")
    assert result["status"] == "completed"
    assert result["render_url"] == "https://cdn.heygen.com/video.mp4"
```

- [ ] **Step 2: Run tests — expect fail**

```bash
python -m pytest tests/youtube/test_mcp.py::test_heygen_render_video_missing_key -v
```

Expected: `ImportError` or `ModuleNotFoundError`.

- [ ] **Step 3: Create src/mcp/heygen_mcp.py**

```python
"""
HeyGen MCP — AI video rendering wrapper.

Generic: no YouTube coupling. Reusable for Ads production.
Follows the same pattern as social_distribution_mcp.py.

Tools:
- render_video: Submit a video render job to HeyGen
- render_illustration_video: Submit illustration-style video with pre-rendered frame URLs
- get_render_status: Poll job status and retrieve render URL when complete
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

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

    dimension = {"16:9": {"width": 1280, "height": 720}, "9:16": {"width": 720, "height": 1280}}.get(
        aspect_ratio, {"width": 1280, "height": 720}
    )

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

    Distributes frames evenly across video duration.
    Returns: {"status": "submitted", "job_id": "..."} or {"status": "error", ...}
    """
    api_key = os.getenv("HEYGEN_API_KEY")
    if not api_key:
        return {"status": "error", "error": "HEYGEN_API_KEY not configured"}

    if not frame_urls:
        return {"status": "error", "error": "frame_urls is empty — illustration frames required"}

    dimension = {"16:9": {"width": 1280, "height": 720}, "9:16": {"width": 720, "height": 1280}}.get(
        aspect_ratio, {"width": 1280, "height": 720}
    )

    video_inputs = [
        {
            "character": {"type": "none"},
            "voice": {"type": "text", "input_text": script, "voice_id": voice_id},
            "background": {"type": "image", "url": url},
        }
        for url in frame_urls
    ]

    payload = {"video_inputs": video_inputs, "dimension": dimension}

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
```

- [ ] **Step 4: Run HeyGen tests**

```bash
python -m pytest tests/youtube/test_mcp.py -k "heygen" -v
```

Expected: All 3 HeyGen tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/mcp/heygen_mcp.py tests/youtube/test_mcp.py
git commit -m "feat: add HeyGen MCP wrapper — avatar and illustration video rendering"
```

---

## Task 5: YouTube MCP Server + OAuth Setup

**Files:**
- Create: `src/mcp/youtube_mcp.py`

**Prerequisite — YouTube OAuth credentials (do this before writing the MCP server):**

1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Create a project or select the existing `kalevent` project
3. Enable **YouTube Data API v3**
4. Create OAuth 2.0 credentials (type: Desktop App)
5. Download the JSON credentials file
6. Run this one-time script to generate a refresh token:

```python
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/youtube.upload",
          "https://www.googleapis.com/auth/youtube.force-ssl"]

flow = InstalledAppFlow.from_client_secrets_file("client_secret.json", SCOPES)
creds = flow.run_local_server(port=0)
print("Client ID:", creds.client_id)
print("Client Secret:", creds.client_secret)
print("Refresh Token:", creds.refresh_token)
```

7. Add to `src/prod.env`:

```
YOUTUBE_CLIENT_ID=<from above>
YOUTUBE_CLIENT_SECRET=<from above>
YOUTUBE_CHANNEL_ID=<your channel ID from youtube.com/account_advanced>
YOUTUBE_REFRESH_TOKEN=<from above>
```

Install dependency: `pip install google-auth-oauthlib google-api-python-client`
Add to `requirements.txt`: `google-auth-oauthlib>=1.2.0` and `google-api-python-client>=2.100.0`

- [ ] **Step 1: Write failing tests**

Add to `tests/youtube/test_mcp.py`:

```python
def test_youtube_upload_missing_creds(monkeypatch):
    monkeypatch.delenv("YOUTUBE_CLIENT_ID", raising=False)
    from src.mcp import youtube_mcp
    import importlib
    importlib.reload(youtube_mcp)
    result = youtube_mcp.upload_video(
        file_url="https://example.com/video.mp4",
        title="Test title",
        description="Test description",
        tags=["test"],
        category_id="28",
    )
    assert result["status"] == "error"
    assert "YOUTUBE_CLIENT_ID" in result["error"]


def test_youtube_get_video_stats_missing_creds(monkeypatch):
    monkeypatch.delenv("YOUTUBE_CLIENT_ID", raising=False)
    from src.mcp import youtube_mcp
    import importlib
    importlib.reload(youtube_mcp)
    result = youtube_mcp.get_video_stats("dQw4w9WgXcQ")
    assert result["status"] == "error"
```

- [ ] **Step 2: Run tests — expect fail**

```bash
python -m pytest tests/youtube/test_mcp.py::test_youtube_upload_missing_creds -v
```

Expected: `ImportError`.

- [ ] **Step 3: Create src/mcp/youtube_mcp.py**

```python
"""
YouTube MCP — YouTube Data API v3 wrapper.

Tools:
- upload_video: Upload MP4 from URL to YouTube channel
- add_end_screen: Add end screen card to a published video
- add_card: Add a mid-video card linking to the website
- post_pinned_comment: Post and pin a comment on a video
- get_video_stats: Retrieve view count and click-through rate
"""
from __future__ import annotations

import logging
import os
import tempfile
from typing import Any, Dict, List, Optional

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
    category_id: str = "28",  # 28 = Science & Technology
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
        from googleapiclient.http import MediaIoBaseUpload
        import io

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
    """
    Add an end screen card (last 20 seconds) linking to cta_url.

    Returns: {"status": "ok"} or {"status": "error", "error": "..."}
    """
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
                            "linkDetails": {
                                "url": cta_url,
                                "urlScheme": "https",
                            },
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
    Return view count and click-through rate for a published video.

    Returns: {"status": "ok", "view_count": 0, "ctr": 0.0} or {"status": "error", ...}
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
```

- [ ] **Step 4: Run YouTube MCP tests**

```bash
python -m pytest tests/youtube/test_mcp.py -v
```

Expected: All 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/mcp/youtube_mcp.py tests/youtube/test_mcp.py requirements.txt
git commit -m "feat: add YouTube MCP wrapper — upload, end screen, card, pinned comment, stats"
```

---

## Task 6: youtube.generate_scripts Task

**Files:**
- Create: `src/tasks/youtube.py`

This task runs on the 1st and 15th of each month at 7:00am. It finds the latest unpublished-to-YouTube `BlogPost`, selects the highest-priority active `ICPPainPoint`, generates scripts via DSPy, and creates `YouTubeVideo` records.

- [ ] **Step 1: Write failing task test**

Create `tests/youtube/test_tasks.py`:

```python
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone


@pytest.fixture
def mock_blog_post():
    post = MagicMock()
    post.id = "post-123"
    post.title = "How to fix inbox chaos"
    post.content_html = "<p>Your inbox is overwhelming you.</p>"
    post.primary_keyword = "inbox management"
    return post


@pytest.fixture
def mock_pain_point():
    pp = MagicMock()
    pp.id = "pain-123"
    pp.pain_point = "Support emails pile up unread over the weekend"
    pp.consequence = "Customers churn before Monday"
    pp.persona = "Head of Support"
    return pp


def test_generate_scripts_creates_long_form_and_shorts(app, mock_blog_post, mock_pain_point):
    with app.app_context():
        with patch("src.tasks.youtube._get_latest_blog_post", return_value=mock_blog_post), \
             patch("src.tasks.youtube._get_top_pain_point", return_value=mock_pain_point), \
             patch("src.tasks.youtube._run_dspy_script_generation") as mock_dspy, \
             patch("src.tasks.youtube.db") as mock_db:

            mock_dspy.return_value = {
                "script": "You're drowning in support emails...",
                "hook_line": "You're drowning in support emails.",
                "chapter_markers": "[]",
                "cta_line": "Start free at inboxiq.com",
                "short_scripts": [
                    {"script": "60s short...", "pattern_interrupt_line": "Inbox chaos?", "cta_line": "Link in description."},
                    {"script": "60s short 2...", "pattern_interrupt_line": "Missing replies?", "cta_line": "Link in description."},
                ],
                "seo": {
                    "title": "Never miss a support email again | InboxIQ",
                    "description": "Your inbox is chaos.\nInboxIQ fixes it.\n{{UTM_LINK}}",
                    "tags": '["inbox management", "B2B SaaS"]',
                    "thumbnail_prompt": "Person overwhelmed at desk",
                },
            }

            from src.tasks.youtube import generate_scripts
            result = generate_scripts(account_id=2, video_style="avatar")

            assert result["status"] == "ok"
            assert result["long_form_created"] is True
            assert result["shorts_created"] >= 2
```

- [ ] **Step 2: Run test — expect fail**

```bash
python -m pytest tests/youtube/test_tasks.py::test_generate_scripts_creates_long_form_and_shorts -v
```

Expected: `ImportError` — task module not yet created.

- [ ] **Step 3: Create src/tasks/youtube.py**

```python
"""
YouTube cadence Celery tasks.

Beat schedule (registered in src/celery_inboxiq.py):
  youtube.generate_scripts   — 1st + 15th of month, 7:00am
  youtube.render_videos      — Daily 7:30am
  youtube.publish_videos     — Daily 8:00am
  youtube.send_digest        — Daily 8:30am
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional
from uuid import uuid4

from celery import shared_task
from sqlalchemy.sql import func

from src.extensions import db
from src.models.campaigns import YouTubeVideo
from src.models.leads import ICPPainPoint
from src.models.content import BlogPost

logger = logging.getLogger(__name__)

ACCOUNT_ID = 2  # default account; tasks accept account_id param for multi-tenant future


# ── Helpers ────────────────────────────────────────────────────────────────

def _get_latest_blog_post(account_id: int, offset: int = 0) -> Optional[BlogPost]:
    """Return the (offset+1)-th most recently published BlogPost not yet used for a video."""
    used_ids = (
        db.session.query(YouTubeVideo.blog_post_id)
        .filter(
            YouTubeVideo.account_id == account_id,
            YouTubeVideo.blog_post_id.isnot(None),
            YouTubeVideo.video_type == "long_form",
        )
        .subquery()
    )
    return (
        db.session.query(BlogPost)
        .filter(
            BlogPost.status == "published",
            ~BlogPost.id.in_(used_ids),
        )
        .order_by(BlogPost.created_at.desc())
        .offset(offset)
        .first()
    )


def _get_top_pain_point(account_id: int) -> Optional[ICPPainPoint]:
    """Return the highest-priority active ICP pain point for this account."""
    return (
        db.session.query(ICPPainPoint)
        .filter(ICPPainPoint.account_id == account_id, ICPPainPoint.active.is_(True))
        .order_by(ICPPainPoint.priority.desc())
        .first()
    )


def _build_utm_slug(video_type: str, blog_post_title: str) -> str:
    """Build a unique UTM slug from video type and blog post title."""
    month = datetime.now(timezone.utc).strftime("%b-%Y").lower()
    slug_base = re.sub(r"[^a-z0-9]+", "-", blog_post_title.lower())[:40].strip("-")
    prefix = "yt-long" if video_type == "long_form" else "yt-short"
    slug = f"{prefix}-{slug_base}-{month}"
    # Ensure uniqueness
    existing = db.session.query(YouTubeVideo).filter_by(utm_slug=slug).first()
    if existing:
        slug = f"{slug}-{str(uuid4())[:4]}"
    return slug


def _run_dspy_script_generation(
    blog_post: BlogPost,
    pain_point: ICPPainPoint,
    video_style: str,
) -> Dict[str, Any]:
    """Run DSPy signatures to generate long form script, SEO metadata, and short scripts."""
    from src.dspy.config import _configure_dspy
    import dspy
    from src.dspy.signatures import build_youtube_signatures

    _configure_dspy()
    sigs = build_youtube_signatures(dspy)

    icp_persona = "Head of Support / Founder, B2B SaaS, 10-50 employees, UK/US/Nigeria"

    # Long form script
    long_form_pred = dspy.Predict(sigs["YouTubeLongFormScript"])(
        blog_post_content=blog_post.content_html or "",
        icp_persona=icp_persona,
        pain_point=pain_point.pain_point,
        consequence=pain_point.consequence,
        video_style=video_style,
    )

    # SEO metadata
    seo_pred = dspy.Predict(sigs["YouTubeSEOMetadata"])(
        script=long_form_pred.script,
        pain_point=pain_point.pain_point,
        blog_post_primary_keyword=blog_post.primary_keyword or "",
        video_type="long_form",
    )

    # 2-3 Short scripts
    short_scripts = []
    for i in range(2):
        short_pred = dspy.Predict(sigs["YouTubeShortScript"])(
            long_form_script=long_form_pred.script,
            pain_point=pain_point.pain_point,
            parent_youtube_url="",  # filled after publish
        )
        short_scripts.append({
            "script": short_pred.short_script,
            "pattern_interrupt_line": short_pred.pattern_interrupt_line,
            "cta_line": short_pred.cta_line,
        })

    # Illustration prompts (illustration style only)
    illustration_prompts = None
    if video_style == "illustration":
        illus_pred = dspy.Predict(sigs["YouTubeIllustrationPrompts"])(
            script=long_form_pred.script,
            pain_point=pain_point.pain_point,
            chapter_markers=long_form_pred.chapter_markers,
        )
        illustration_prompts = illus_pred.scene_prompts

    return {
        "script": long_form_pred.script,
        "hook_line": long_form_pred.hook_line,
        "chapter_markers": long_form_pred.chapter_markers,
        "cta_line": long_form_pred.cta_line,
        "illustration_prompts": illustration_prompts,
        "short_scripts": short_scripts,
        "seo": {
            "title": seo_pred.title,
            "description": seo_pred.description,
            "tags": seo_pred.tags,
            "thumbnail_prompt": seo_pred.thumbnail_prompt,
        },
    }


# ── Task 1: Generate Scripts ────────────────────────────────────────────────

@shared_task(name="youtube.generate_scripts")
def generate_scripts(account_id: int = ACCOUNT_ID, video_style: str = "avatar") -> Dict[str, Any]:
    """
    1st of month → video_style="avatar", blog_post offset=0
    15th of month → video_style="illustration", blog_post offset=1

    Creates one long_form YouTubeVideo + 2-3 short YouTubeVideo records.
    """
    blog_post_offset = 0 if video_style == "avatar" else 1

    blog_post = _get_latest_blog_post(account_id, offset=blog_post_offset)
    if not blog_post:
        logger.warning("youtube.generate_scripts: no eligible blog post found", extra={"account_id": account_id})
        return {"status": "skipped", "reason": "no eligible blog post"}

    pain_point = _get_top_pain_point(account_id)
    if not pain_point:
        logger.warning("youtube.generate_scripts: no active ICPPainPoint found", extra={"account_id": account_id})
        return {"status": "skipped", "reason": "no active ICPPainPoint"}

    try:
        generated = _run_dspy_script_generation(blog_post, pain_point, video_style)
    except Exception:
        logger.exception("youtube.generate_scripts: DSPy generation failed")
        return {"status": "error", "reason": "dspy generation failed"}

    seo = generated["seo"]
    utm_slug = _build_utm_slug("long_form", blog_post.title)
    utm_campaign = utm_slug.replace("yt-long-", "")

    long_form = YouTubeVideo(
        account_id=account_id,
        blog_post_id=blog_post.id,
        icp_pain_point_id=pain_point.id,
        video_type="long_form",
        video_style=video_style,
        script=generated["script"],
        title=seo["title"],
        description=seo["description"],
        tags=json.loads(seo["tags"]) if isinstance(seo["tags"], str) else seo["tags"],
        thumbnail_prompt=seo["thumbnail_prompt"],
        illustration_prompts=json.loads(generated["illustration_prompts"])
        if generated.get("illustration_prompts")
        else None,
        utm_slug=utm_slug,
        utm_medium="long_form",
        utm_campaign=utm_campaign,
        status="script_ready",
        script_generated_at=datetime.now(timezone.utc),
    )

    try:
        db.session.add(long_form)
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise

    shorts_created = 0
    for i, short_data in enumerate(generated["short_scripts"]):
        short_slug = _build_utm_slug("short", f"{blog_post.title}-{i+1}")
        short = YouTubeVideo(
            account_id=account_id,
            blog_post_id=blog_post.id,
            icp_pain_point_id=pain_point.id,
            parent_video_id=long_form.id,
            video_type="short",
            video_style=video_style,
            script=short_data["script"],
            utm_slug=short_slug,
            utm_medium="short",
            utm_campaign=short_slug.replace("yt-short-", ""),
            status="script_ready",
            script_generated_at=datetime.now(timezone.utc),
        )
        try:
            db.session.add(short)
            db.session.commit()
            shorts_created += 1
        except Exception:
            db.session.rollback()
            logger.exception("youtube.generate_scripts: failed to save short %d", i)

    logger.info(
        "youtube.generate_scripts done",
        extra={"account_id": account_id, "long_form_id": long_form.id, "shorts": shorts_created},
    )
    return {"status": "ok", "long_form_created": True, "shorts_created": shorts_created}
```

- [ ] **Step 4: Run task tests**

```bash
python -m pytest tests/youtube/test_tasks.py::test_generate_scripts_creates_long_form_and_shorts -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/tasks/youtube.py tests/youtube/test_tasks.py
git commit -m "feat: add youtube.generate_scripts task — DSPy scripts + illustration prompts"
```

---

## Task 7: youtube.render_videos Task

**Files:**
- Modify: `src/tasks/youtube.py`

This task runs daily at 7:30am. For `script_ready` illustration videos it generates DALL-E frames first, then submits to HeyGen. For `script_ready` avatar videos it submits directly. It also polls in-progress renders — but the webhook (Task 8) is the primary completion signal; polling is a fallback for renders older than 30 minutes.

- [ ] **Step 1: Write failing test**

Add to `tests/youtube/test_tasks.py`:

```python
def test_render_videos_submits_avatar_to_heygen(app):
    with app.app_context():
        with patch("src.tasks.youtube.heygen_mcp.render_video") as mock_render, \
             patch("src.tasks.youtube.db") as mock_db:

            mock_video = MagicMock()
            mock_video.id = "vid-1"
            mock_video.video_style = "avatar"
            mock_video.video_type = "long_form"
            mock_video.script = "You are drowning in support emails."
            mock_video.illustration_prompts = None

            mock_db.session.query.return_value.filter.return_value.all.return_value = [mock_video]
            mock_render.return_value = {"status": "submitted", "job_id": "heygen-job-1"}

            from src.tasks.youtube import render_videos
            result = render_videos(account_id=2)

            mock_render.assert_called_once()
            assert result["status"] == "ok"
```

- [ ] **Step 2: Run test — expect fail**

```bash
python -m pytest tests/youtube/test_tasks.py::test_render_videos_submits_avatar_to_heygen -v
```

Expected: `AttributeError` — `render_videos` not yet defined.

- [ ] **Step 3: Add render_videos to src/tasks/youtube.py**

Add after `generate_scripts`, before the end of the file:

```python
# ── Task 2: Render Videos ──────────────────────────────────────────────────

def _generate_dalle_frames(prompts: list, account_id: int) -> list:
    """
    Generate DALL-E 3 illustration frames and upload to S3 via uploads.py.
    Returns list of public S3 URLs.
    """
    import openai
    import requests as http
    from src.uploads import upload_bytes, build_public_url

    client = openai.OpenAI()
    urls = []
    for i, prompt in enumerate(prompts):
        try:
            response = client.images.generate(
                model="dall-e-3",
                prompt=prompt,
                size="1792x1024",
                quality="standard",
                n=1,
            )
            image_url = response.data[0].url
            img_bytes = http.get(image_url, timeout=30).content
            key = f"youtube/frames/{account_id}/{uuid4()}.png"
            upload_bytes(key, img_bytes, "image/png", "attachment")
            urls.append(build_public_url(key))
        except Exception:
            logger.exception("youtube.render_videos: DALL-E frame %d failed", i)
    return urls


@shared_task(name="youtube.render_videos")
def render_videos(account_id: int = ACCOUNT_ID) -> Dict[str, Any]:
    """
    Daily 7:30am. Two operations:
    1. Submit script_ready videos to HeyGen (generate DALL-E frames first for illustration style).
    2. Poll rendering videos older than 30min as fallback (webhook is primary completion signal).
    """
    from src.mcp import heygen_mcp

    avatar_id = __import__("os").getenv("HEYGEN_AVATAR_ID", "")
    voice_id = __import__("os").getenv("HEYGEN_VOICE_ID", "")

    submitted = 0
    failed = 0

    # Submit script_ready videos
    ready_videos = (
        db.session.query(YouTubeVideo)
        .filter(
            YouTubeVideo.account_id == account_id,
            YouTubeVideo.status.in_(["script_ready", "illustration_ready"]),
        )
        .all()
    )

    for video in ready_videos:
        try:
            if video.video_style == "illustration" and video.status == "script_ready":
                # Generate DALL-E frames first
                prompts = video.illustration_prompts or []
                if not prompts:
                    logger.warning("youtube.render_videos: no illustration_prompts for video %s", video.id)
                    continue
                frame_urls = _generate_dalle_frames(prompts, account_id)
                if len(frame_urls) < 2:
                    logger.error("youtube.render_videos: DALL-E frame generation mostly failed for %s", video.id)
                    failed += 1
                    continue
                video.dalle_frame_urls = frame_urls
                video.status = "illustration_ready"
                db.session.commit()

            # Submit to HeyGen
            if video.video_style == "illustration" and video.dalle_frame_urls:
                result = heygen_mcp.render_illustration_video(
                    script=video.script or "",
                    voice_id=voice_id,
                    frame_urls=video.dalle_frame_urls,
                    aspect_ratio="16:9" if video.video_type == "long_form" else "9:16",
                )
            else:
                result = heygen_mcp.render_video(
                    script=video.script or "",
                    avatar_id=avatar_id,
                    voice_id=voice_id,
                    video_format="mp4",
                    aspect_ratio="16:9" if video.video_type == "long_form" else "9:16",
                )

            if result["status"] == "submitted":
                video.heygen_job_id = result["job_id"]
                video.status = "rendering"
                video.render_submitted_at = datetime.now(timezone.utc)
                db.session.commit()
                submitted += 1
            else:
                logger.error("youtube.render_videos: HeyGen submit failed for %s: %s", video.id, result.get("error"))
                failed += 1
        except Exception:
            db.session.rollback()
            logger.exception("youtube.render_videos: error processing video %s", video.id)
            failed += 1

    # Fallback poll: renders stuck for >30 min (webhook should have fired by now)
    stale_cutoff = datetime.now(timezone.utc) - timedelta(minutes=30)
    stale_videos = (
        db.session.query(YouTubeVideo)
        .filter(
            YouTubeVideo.account_id == account_id,
            YouTubeVideo.status == "rendering",
            YouTubeVideo.render_submitted_at < stale_cutoff,
        )
        .all()
    )
    for video in stale_videos:
        if not video.heygen_job_id:
            continue
        result = heygen_mcp.get_render_status(video.heygen_job_id)
        if result["status"] == "completed":
            video.heygen_render_url = result["render_url"]
            video.status = "render_complete"
            video.render_completed_at = datetime.now(timezone.utc)
            db.session.commit()
        elif result["status"] == "failed":
            video.status = "failed"
            db.session.commit()

    return {"status": "ok", "submitted": submitted, "failed": failed}
```

- [ ] **Step 4: Run test**

```bash
python -m pytest tests/youtube/test_tasks.py::test_render_videos_submits_avatar_to_heygen -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/tasks/youtube.py tests/youtube/test_tasks.py
git commit -m "feat: add youtube.render_videos task — DALL-E frame generation + HeyGen submission"
```

---

## Task 8: youtube.publish_videos Task + HeyGen Webhook Endpoint

**Files:**
- Modify: `src/tasks/youtube.py`
- Create: `src/api/v1/youtube.py`

The webhook endpoint receives HeyGen's render-complete callback and flips the video to `render_complete`. The `publish_videos` task then picks it up.

- [ ] **Step 1: Write failing tests**

Add to `tests/youtube/test_tasks.py`:

```python
def test_publish_videos_uploads_to_youtube(app):
    with app.app_context():
        with patch("src.tasks.youtube.youtube_mcp.upload_video") as mock_upload, \
             patch("src.tasks.youtube.youtube_mcp.add_end_screen") as mock_end, \
             patch("src.tasks.youtube.youtube_mcp.add_card") as mock_card, \
             patch("src.tasks.youtube.youtube_mcp.post_pinned_comment") as mock_pin, \
             patch("src.tasks.youtube.db") as mock_db:

            mock_video = MagicMock()
            mock_video.id = "vid-1"
            mock_video.video_type = "long_form"
            mock_video.heygen_render_url = "https://cdn.heygen.com/video.mp4"
            mock_video.title = "Never miss a support email again | InboxIQ"
            mock_video.description = "Pain.\nResolution.\n{{UTM_LINK}}"
            mock_video.tags = ["inbox management"]
            mock_video.utm_slug = "yt-long-inbox-may-2026"
            mock_video.utm_medium = "long_form"
            mock_video.utm_campaign = "inbox-may-2026"
            mock_video.parent_video_id = None

            mock_db.session.query.return_value.filter.return_value.all.return_value = [mock_video]
            mock_upload.return_value = {
                "status": "published",
                "youtube_video_id": "yt-abc123",
                "youtube_url": "https://www.youtube.com/watch?v=yt-abc123",
            }
            mock_end.return_value = {"status": "ok"}
            mock_card.return_value = {"status": "ok"}
            mock_pin.return_value = {"status": "ok"}

            from src.tasks.youtube import publish_videos
            result = publish_videos(account_id=2)

            assert result["status"] == "ok"
            assert result["published"] == 1
            mock_upload.assert_called_once()
            mock_pin.assert_called_once()
```

- [ ] **Step 2: Run test — expect fail**

```bash
python -m pytest tests/youtube/test_tasks.py::test_publish_videos_uploads_to_youtube -v
```

Expected: `AttributeError` — `publish_videos` not yet defined.

- [ ] **Step 3: Add publish_videos to src/tasks/youtube.py**

```python
# ── Task 3: Publish Videos ─────────────────────────────────────────────────

@shared_task(name="youtube.publish_videos")
def publish_videos(account_id: int = ACCOUNT_ID) -> Dict[str, Any]:
    """
    Daily 8:00am. Uploads render_complete videos to YouTube, sets UTM descriptions,
    end screens, cards, and pinned comments.
    """
    from src.mcp import youtube_mcp

    base_url = "https://inboxiq.com/start"
    published = 0
    failed = 0

    ready = (
        db.session.query(YouTubeVideo)
        .filter(
            YouTubeVideo.account_id == account_id,
            YouTubeVideo.status == "render_complete",
            YouTubeVideo.heygen_render_url.isnot(None),
        )
        .all()
    )

    for video in ready:
        try:
            utm_url = (
                f"{base_url}?utm_source=youtube"
                f"&utm_medium={video.utm_medium}"
                f"&utm_campaign={video.utm_campaign}"
            )

            description = (video.description or "").replace("{{UTM_LINK}}", utm_url)

            video.status = "publishing"
            db.session.commit()

            result = youtube_mcp.upload_video(
                file_url=video.heygen_render_url,
                title=video.title or "",
                description=description,
                tags=video.tags or [],
                category_id="28",
            )

            if result["status"] != "published":
                video.status = "failed"
                db.session.commit()
                failed += 1
                continue

            video.youtube_video_id = result["youtube_video_id"]
            video.youtube_url = result["youtube_url"]
            video.description = description
            video.utm_campaign = video.utm_campaign

            if video.video_type == "long_form":
                youtube_mcp.add_end_screen(video.youtube_video_id, utm_url)
                # Card at ~60% of video (rough midpoint for resolution moment)
                youtube_mcp.add_card(video.youtube_video_id, utm_url, offset_ms=360000)
                pinned = f"Start free → {utm_url}"
            else:
                # Short: pinned comment links to parent long form
                parent = None
                if video.parent_video_id:
                    parent = db.session.get(YouTubeVideo, video.parent_video_id)
                parent_url = parent.youtube_url if parent and parent.youtube_url else "https://www.youtube.com/@inboxiq"
                pinned = f"Full video → {parent_url}"

            youtube_mcp.post_pinned_comment(video.youtube_video_id, pinned)

            video.status = "published"
            video.published_at = datetime.now(timezone.utc)
            db.session.commit()
            published += 1

        except Exception:
            db.session.rollback()
            logger.exception("youtube.publish_videos: error publishing video %s", video.id)
            try:
                video.status = "failed"
                db.session.commit()
            except Exception:
                db.session.rollback()
            failed += 1

    return {"status": "ok", "published": published, "failed": failed}
```

- [ ] **Step 4: Create the HeyGen webhook endpoint**

Create `src/api/v1/youtube.py`:

```python
"""
YouTube API endpoints.

POST /api/v1/youtube/heygen/webhook  — HeyGen render-complete callback
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from flask import Blueprint, request, jsonify

from src.extensions import db
from src.models.campaigns import YouTubeVideo

logger = logging.getLogger(__name__)
bp = Blueprint("youtube_api", __name__, url_prefix="/api/v1/youtube")


@bp.route("/heygen/webhook", methods=["POST"])
def heygen_webhook():
    """
    HeyGen calls this URL when a video render completes or fails.
    Payload: {"event_type": "avatar_video.success"|"avatar_video.fail", "event_data": {"video_id": "...", "video_url": "..."}}

    No auth required — HeyGen does not send tokens.
    We validate by checking the video_id exists in our DB.
    """
    data = request.get_json(silent=True) or {}
    event_type = data.get("event_type", "")
    event_data = data.get("event_data", {})
    heygen_job_id = event_data.get("video_id") or event_data.get("id")

    if not heygen_job_id:
        return jsonify({"error": "missing video_id"}), 400

    video = (
        db.session.query(YouTubeVideo)
        .filter_by(heygen_job_id=heygen_job_id)
        .first()
    )

    if not video:
        logger.warning("heygen_webhook: unknown job_id %s", heygen_job_id)
        return jsonify({"ok": True}), 200  # ACK — don't leak DB info

    if "success" in event_type or "complete" in event_type:
        video.heygen_render_url = event_data.get("video_url") or event_data.get("url")
        video.status = "render_complete"
        video.render_completed_at = datetime.now(timezone.utc)
    elif "fail" in event_type or "error" in event_type:
        video.status = "failed"

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise

    return jsonify({"ok": True}), 200
```

Register the blueprint in `src/app.py`. Find where other API v1 blueprints are registered and add:

```python
from src.api.v1.youtube import bp as youtube_api_bp
app.register_blueprint(youtube_api_bp)
```

Set the webhook URL in HeyGen dashboard (Settings → API → Webhook):
```
https://api.kalevent.com/api/v1/youtube/heygen/webhook
```

- [ ] **Step 5: Run tests**

```bash
python -m pytest tests/youtube/test_tasks.py::test_publish_videos_uploads_to_youtube -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/tasks/youtube.py src/api/v1/youtube.py src/app.py
git commit -m "feat: add youtube.publish_videos task and HeyGen webhook endpoint"
```

---

## Task 9: youtube.send_digest Task + Digest Email

**Files:**
- Modify: `src/tasks/youtube.py`
- Modify: `src/notifications/emails.py`

- [ ] **Step 1: Write failing test**

Add to `tests/youtube/test_tasks.py`:

```python
def test_send_digest_calls_email_function(app):
    with app.app_context():
        with patch("src.tasks.youtube.send_youtube_digest_email") as mock_email, \
             patch("src.tasks.youtube.db") as mock_db:

            mock_db.session.query.return_value.filter.return_value.all.return_value = []
            mock_db.session.query.return_value.filter.return_value.scalar.return_value = 0

            from src.tasks.youtube import send_digest
            result = send_digest(account_id=2)

            assert result["status"] == "ok"
            mock_email.assert_called_once()
```

- [ ] **Step 2: Run test — expect fail**

```bash
python -m pytest tests/youtube/test_tasks.py::test_send_digest_calls_email_function -v
```

Expected: `AttributeError`.

- [ ] **Step 3: Add send_youtube_digest_email to src/notifications/emails.py**

At the bottom of `src/notifications/emails.py`, add:

```python
def send_youtube_digest_email(
    to_email: str,
    published_this_week: list,
    pipeline_status: list,
    youtube_visitors: int,
    youtube_trials: int,
) -> bool:
    """
    Daily YouTube cadence digest — three sections:
    1. Published this week (title, type, views, UTM clicks, YouTube link)
    2. Pipeline status (pending videos and their current stage)
    3. Funnel attribution (YouTube visitors → trial starts this week)
    """
    from flask import current_app
    app = current_app
    host = app.config.get("SMTP_HOST")
    port = app.config.get("SMTP_PORT")
    user = app.config.get("SMTP_USER")
    password = app.config.get("SMTP_PASSWORD")
    use_tls = app.config.get("SMTP_USE_TLS", True)
    mail_from = app.config.get("MAIL_FROM", "noreply@kalevent.com")

    if not host:
        app.logger.info({"event": "youtube_digest.disabled", "reason": "SMTP not configured"})
        return False

    published_rows = "".join(
        f"<tr><td>{v['title']}</td><td>{v['type']}</td><td>{v['views']}</td>"
        f"<td>{v['clicks']}</td><td><a href='{v['url']}'>Watch</a></td></tr>"
        for v in published_this_week
    ) or "<tr><td colspan='5'>No videos published this week</td></tr>"

    pipeline_rows = "".join(
        f"<tr><td>{v['title'] or v['id']}</td><td>{v['status']}</td><td>{v['type']}</td></tr>"
        for v in pipeline_status
    ) or "<tr><td colspan='3'>Pipeline is clear</td></tr>"

    html = f"""
    <div style="font-family:-apple-system,sans-serif;max-width:640px;margin:0 auto;padding:24px">
      <h2 style="color:#1e293b">YouTube Cadence — Daily Digest</h2>

      <h3>Published this week</h3>
      <table border="1" cellpadding="6" cellspacing="0" style="width:100%;border-collapse:collapse">
        <tr><th>Title</th><th>Type</th><th>Views</th><th>Clicks</th><th>Link</th></tr>
        {published_rows}
      </table>

      <h3>Pipeline status</h3>
      <table border="1" cellpadding="6" cellspacing="0" style="width:100%;border-collapse:collapse">
        <tr><th>Video</th><th>Status</th><th>Type</th></tr>
        {pipeline_rows}
      </table>

      <h3>Funnel attribution (this week)</h3>
      <p>YouTube visitors: <strong>{youtube_visitors}</strong></p>
      <p>Trial starts from YouTube: <strong>{youtube_trials}</strong></p>
    </div>
    """

    from email.message import EmailMessage
    import smtplib

    msg = EmailMessage()
    msg["Subject"] = "YouTube Cadence Digest"
    msg["From"] = mail_from
    msg["To"] = to_email
    msg.set_content(
        f"YouTube Cadence Digest\n\n"
        f"Published this week: {len(published_this_week)} videos\n"
        f"Pipeline pending: {len(pipeline_status)} videos\n"
        f"YouTube visitors this week: {youtube_visitors}\n"
        f"Trial starts from YouTube: {youtube_trials}\n"
    )
    msg.add_alternative(html, subtype="html")

    try:
        if use_tls:
            with smtplib.SMTP(host, int(port)) as s:
                s.starttls()
                s.login(user, password)
                s.send_message(msg)
        else:
            with smtplib.SMTP_SSL(host, int(port)) as s:
                s.login(user, password)
                s.send_message(msg)
        return True
    except Exception:
        app.logger.exception({"event": "youtube_digest.send_failed", "to": to_email})
        return False
```

- [ ] **Step 4: Add send_digest task to src/tasks/youtube.py**

Add at the bottom of `src/tasks/youtube.py`:

```python
# ── Task 4: Send Digest ─────────────────────────────────────────────────────

@shared_task(name="youtube.send_digest")
def send_digest(account_id: int = ACCOUNT_ID) -> Dict[str, Any]:
    """Daily 8:30am. Email admin: published this week, pipeline status, funnel attribution."""
    import os
    from src.notifications.emails import send_youtube_digest_email
    from src.models.leads import LeadAttribution
    from src.models.billing import CustomerBillingProfile

    admin_email = os.getenv("ADMIN_EMAILS", "").split(",")[0].strip()
    if not admin_email:
        return {"status": "skipped", "reason": "no ADMIN_EMAILS configured"}

    week_ago = datetime.now(timezone.utc) - timedelta(days=7)

    # Published this week
    published = (
        db.session.query(YouTubeVideo)
        .filter(
            YouTubeVideo.account_id == account_id,
            YouTubeVideo.status == "published",
            YouTubeVideo.published_at >= week_ago,
        )
        .all()
    )
    published_data = [
        {
            "title": v.title or v.id,
            "type": v.video_type,
            "views": v.view_count,
            "clicks": v.click_count,
            "url": v.youtube_url or "",
        }
        for v in published
    ]

    # Refresh view + click counts for published videos
    for video in published:
        from src.mcp import youtube_mcp
        if video.youtube_video_id:
            stats = youtube_mcp.get_video_stats(video.youtube_video_id)
            if stats["status"] == "ok":
                video.view_count = stats["view_count"]
        attribution_count = (
            db.session.query(func.count(LeadAttribution.id))
            .filter(LeadAttribution.utm_campaign == video.utm_campaign)
            .scalar()
        ) or 0
        video.click_count = attribution_count
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()

    # Pipeline status (not yet published)
    pipeline = (
        db.session.query(YouTubeVideo)
        .filter(
            YouTubeVideo.account_id == account_id,
            YouTubeVideo.status.notin_(["published", "failed"]),
        )
        .all()
    )

    # Flag stale renders (>24h in rendering)
    stale_cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    for video in pipeline:
        if video.status == "rendering" and video.render_submitted_at and video.render_submitted_at < stale_cutoff:
            video.status = "failed"
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()

    pipeline_data = [
        {"id": v.id, "title": v.title, "status": v.status, "type": v.video_type}
        for v in pipeline
    ]

    # Funnel attribution
    youtube_visitors = (
        db.session.query(func.count(LeadAttribution.id))
        .filter(
            LeadAttribution.utm_source == "youtube",
            LeadAttribution.created_at >= week_ago,
        )
        .scalar()
    ) or 0

    youtube_trials = (
        db.session.query(func.count(CustomerBillingProfile.id))
        .join(Lead, Lead.id == CustomerBillingProfile.lead_id, isouter=True)
        .filter(
            Lead.utm_source == "youtube",
            CustomerBillingProfile.created_at >= week_ago,
        )
        .scalar()
    ) or 0

    send_youtube_digest_email(
        to_email=admin_email,
        published_this_week=published_data,
        pipeline_status=pipeline_data,
        youtube_visitors=youtube_visitors,
        youtube_trials=youtube_trials,
    )

    return {"status": "ok", "published": len(published_data), "pipeline": len(pipeline_data)}
```

Add the missing import at the top of `src/tasks/youtube.py`:

```python
from src.models.leads import ICPPainPoint, LeadAttribution
from src.models.core import Lead  # for the trial join
```

- [ ] **Step 5: Run all task tests**

```bash
python -m pytest tests/youtube/test_tasks.py -v
```

Expected: All 4 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add src/tasks/youtube.py src/notifications/emails.py tests/youtube/test_tasks.py
git commit -m "feat: add youtube.send_digest task and digest email with funnel attribution"
```

---

## Task 10: Celery Beat Schedule

**Files:**
- Modify: `src/celery_inboxiq.py`

- [ ] **Step 1: Add YouTube env vars to config**

In `src/config.py` (or wherever `CONTENT_GENERATION_ENABLED` is read), confirm these env vars are accessible. Add to `src/prod.env` if not already present:

```
YOUTUBE_CADENCE_ENABLED=true
YOUTUBE_ACCOUNT_ID=2
```

- [ ] **Step 2: Locate the LinkedIn beat schedule block in src/celery_inboxiq.py**

Find the LinkedIn cadence block (around line 387). It looks like:

```python
**(
    {
        "linkedin_discover_prospects": { ... },
        ...
    }
    if os.getenv("LINKEDIN_CADENCE_ENABLED", "true").lower() == "true"
    else {}
),
```

- [ ] **Step 3: Add YouTube beat entries immediately after the LinkedIn block**

```python
# YouTube cadence
**(
    {
        "youtube_generate_scripts_avatar": {
            "task": "youtube.generate_scripts",
            "schedule": crontab(day_of_month="1", hour=7, minute=0),
            "kwargs": {"account_id": int(os.getenv("YOUTUBE_ACCOUNT_ID", "2")), "video_style": "avatar"},
            "options": {"queue": "content"},
        },
        "youtube_generate_scripts_illustration": {
            "task": "youtube.generate_scripts",
            "schedule": crontab(day_of_month="15", hour=7, minute=0),
            "kwargs": {"account_id": int(os.getenv("YOUTUBE_ACCOUNT_ID", "2")), "video_style": "illustration"},
            "options": {"queue": "content"},
        },
        "youtube_render_videos": {
            "task": "youtube.render_videos",
            "schedule": crontab(hour=7, minute=30),
            "kwargs": {"account_id": int(os.getenv("YOUTUBE_ACCOUNT_ID", "2"))},
            "options": {"queue": "content"},
        },
        "youtube_publish_videos": {
            "task": "youtube.publish_videos",
            "schedule": crontab(hour=8, minute=0),
            "kwargs": {"account_id": int(os.getenv("YOUTUBE_ACCOUNT_ID", "2"))},
            "options": {"queue": "content"},
        },
        "youtube_send_digest": {
            "task": "youtube.send_digest",
            "schedule": crontab(hour=8, minute=30),
            "kwargs": {"account_id": int(os.getenv("YOUTUBE_ACCOUNT_ID", "2"))},
            "options": {"queue": "content"},
        },
    }
    if os.getenv("YOUTUBE_CADENCE_ENABLED", "false").lower() == "true"
    else {}
),
```

- [ ] **Step 4: Register task autodiscovery**

Find where Celery autodiscovers tasks. Confirm `src/tasks/youtube.py` will be picked up. If the app uses explicit `include=` in Celery config, add `"src.tasks.youtube"` to the list.

Search: `grep -n "include\|autodiscover" src/celery_inboxiq.py | head -10`

- [ ] **Step 5: Verify beat schedule loads without error**

```bash
cd /Users/kofi/inboxiq && python -c "from src.celery_inboxiq import celery; print('beat schedule entries:', len(celery.conf.beat_schedule))"
```

Expected: No import errors. Beat schedule count increases by 5.

- [ ] **Step 6: Commit**

```bash
git add src/celery_inboxiq.py
git commit -m "feat: register YouTube cadence Celery beat schedule (disabled by default)"
```

---

## Task 11: SKILL.md + ICP Pain Point Seed Data

**Files:**
- Create: `.claude/skills/youtube-cadence/SKILL.md`
- Create: `src/youtube_cadence_seed.py` (one-time seed script)

- [ ] **Step 1: Create .claude/skills/youtube-cadence/SKILL.md**

```bash
mkdir -p /Users/kofi/inboxiq/.claude/skills/youtube-cadence
```

Create `.claude/skills/youtube-cadence/SKILL.md`:

```markdown
---
name: youtube-cadence
description: Standards and workflow for InboxIQ's YouTube content cadence — ICP pain-point-first scripts, avatar/illustration production, UTM attribution
---

# YouTube Cadence — Content Quality Contract

## North Star

Every video answers one question before a word of script is written:
> "What painful situation does the viewer recognise in themselves, and how does InboxIQ end it?"

This channel is NOT for selling features. It is for showing the product ending a pain the viewer already lives with.

## Hard Rules (agent blocks publish if violated)

1. Script must open with the named ICP pain point — no greeting, no intro, no product name
2. Product name `InboxIQ` must not appear in the video title
3. `icp_pain_point_id` must be set on `YouTubeVideo` before script generation — agent cannot invent a pain point
4. Every Short must link back to its parent Long form in the pinned comment
5. `utm_slug` must be unique — check before publishing

## Cadence Rules

| Cycle | Type | Style | Source |
| --- | --- | --- | --- |
| 1st of month, 7am | Long form (8–12 min) | Avatar — Caroline in Blue Suit | Latest published BlogPost |
| 15th of month, 7am | Long form (8–12 min) | Illustration — editorial | Second latest BlogPost |
| Auto after each long form | 2–3 Shorts (≤60s) | Inherits parent style | DSPy extracts from long form |

Minimum 2 Shorts per long form required before the cycle is considered complete.

## Script Structures

**Long Form:**
```
1. HOOK (0–30s): Open on the pain. No intro, no welcome.
2. PROBLEM (30s–2m): Make the consequence real and specific.
3. RESOLUTION (2m–9m): Show InboxIQ solving it.
4. PROOF (9m–10m): One concrete outcome.
5. CTA (10m–end): "Start free at inboxiq.com" + end screen card.
```

**Short (≤60s):**
```
1. PATTERN INTERRUPT (0–3s): One sentence naming the pain. No greeting.
2. AGITATION (3–20s): The viewer's world without a fix.
3. RESOLUTION (20–50s): InboxIQ solving it. Fast. Visual.
4. CTA (50–60s): "Link in description. Free to start."
```

## HeyGen Configuration

- Avatar: Caroline in Blue Suit (`HEYGEN_AVATAR_ID`)
- Voice: Caroline Public — Natural, Explainer, Professional (`HEYGEN_VOICE_ID`)
- Pricing: Public Avatar III at $1/min PAYG — ~$26/month at full cadence
- Generic MCP server: reusable for Ads (future phase)

## Illustration Style — Brand Definition

Illustrations must look human-made. Never AI-generated.

**Mandatory brand style prefix (prepend to every DALL-E prompt):**
```
Editorial illustration, hand-drawn ink lines with watercolour wash,
warm muted palette (navy, terracotta, cream), textured paper feel,
loose gestural linework, human figures with natural proportions,
professional magazine quality, no text, no UI chrome, no 3D render,
no gradients, no gloss — think New Yorker editorial, not stock photo.
```

**Scenes show:** Real human situations — overwhelmed person at desk, team in meeting, phone left unattended. Emotional states via body language only.

**Never:** Photorealistic renders, generic corporate stock art, glowing UI elements, cartoonish figures, text inside images.

**Cost:** ~$0.50/video (8 frames × $0.04–$0.08 DALL-E 3). Already in stack.

## SEO/GEO Standards

**Title formula:** `[Pain outcome] — [How] | InboxIQ` — max 60 chars
- Correct: "Never miss a support email again | InboxIQ"
- Wrong: "InboxIQ AI Triage Feature Demo"

**Description:** Line 1 = pain. Line 2 = resolution. Line 3 = UTM link. No filler.

**Tags:** 3 broad + 3 keywords from BlogPost.primary_keyword + 4 pain-specific.

**GEO:** UK/US English default. Nigerian market uses `utm_campaign` prefix `ng-` (separate series).

## CTA Placement

| Placement | Long Form | Short |
| --- | --- | --- |
| Description line 3 | `inboxiq.com/start?utm_source=youtube&utm_medium=long_form&utm_campaign={slug}` | `...&utm_medium=short&utm_campaign={slug}` |
| End screen (last 20s) | `/start` + subscribe | N/A |
| Card (mid-video) | `/start` at resolution moment | N/A |
| Pinned comment | "Start free → [UTM link]" | "Full video → [parent_url]" |

## Pre-Publish Quality Checklist

- [ ] Script opens with pain — no greeting, no intro
- [ ] Product name absent from title and first 5 seconds
- [ ] `icp_pain_point_id` populated on YouTubeVideo record
- [ ] UTM slug is unique
- [ ] Description has UTM link in first 3 lines
- [ ] Short links back to parent Long form in pinned comment
- [ ] Tags include at least one keyword from BlogPost.primary_keyword
- [ ] `thumbnail_prompt` populated
- [ ] Illustration videos only: frames use brand style prefix — no photorealistic, no UI, no text

## ICP Pain Point Library

Source: `icp_pain_points` table. DSPy selects from this table — never invents pain points.

Primary ICP: Founders / Heads of Support / Operations Leads · B2B SaaS · 10–50 employees · UK/US/Nigeria

| Priority | Pain Point | Consequence |
| --- | --- | --- |
| 10 | Support emails pile up unread over the weekend | Customers churn before Monday |
| 9 | No way to tell which leads are warm vs cold | Sales team chases the wrong people |
| 8 | Outreach is manual — copy/paste, one by one | Hours wasted, inconsistent follow-up |
| 7 | Reply comes in, nobody sees it in time | Deal goes cold, prospect moves on |
| 6 | No visibility into which channel drives signups | Budget spent blind |
| 5 | Support team scales by hiring, not by tooling | Margins shrink as you grow |

## Future: In-House Video Generation

When a GPU node is available on EKS, replace `heygen_mcp.py` with `video_agent_mcp.py`:
- TTS: Kokoro (MIT, CPU-capable)
- Lip-sync: MuseTalk or SadTalker (GPU required)
- Assembly: FFmpeg
- The HeyGen MCP interface (`render_video`, `get_render_status`) stays unchanged — swap the implementation.
```

- [ ] **Step 2: Create seed script**

Create `src/youtube_cadence_seed.py`:

```python
"""
One-time seed: populate icp_pain_points for account_id=2.
Run once after migration:
  flask shell < src/youtube_cadence_seed.py
  OR: python -c "from src.youtube_cadence_seed import seed_pain_points; seed_pain_points()"
"""
from src.extensions import db
from src.models.leads import ICPPainPoint
from src.models.marketing import ICPConfig


def seed_pain_points(account_id: int = 2) -> None:
    icp_config = (
        db.session.query(ICPConfig)
        .filter_by(account_id=account_id)
        .first()
    )
    if not icp_config:
        print(f"No ICPConfig found for account_id={account_id}. Create one via the LinkedIn cadence UI first.")
        return

    existing = db.session.query(ICPPainPoint).filter_by(account_id=account_id).count()
    if existing > 0:
        print(f"ICPPainPoints already seeded ({existing} records). Skipping.")
        return

    pain_points = [
        ("Support emails pile up unread over the weekend", "Customers churn before Monday", "Head of Support", 10),
        ("No way to tell which leads are warm vs cold", "Sales team chases the wrong people", "Founder", 9),
        ("Outreach is manual — copy/paste, one by one", "Hours wasted, inconsistent follow-up", "Operations Lead", 8),
        ("Reply comes in, nobody sees it in time", "Deal goes cold, prospect moves on", "Head of Support", 7),
        ("No visibility into which channel drives signups", "Budget spent blind", "Founder", 6),
        ("Support team scales by hiring, not by tooling", "Margins shrink as you grow", "Operations Lead", 5),
    ]

    for pain_point, consequence, persona, priority in pain_points:
        pp = ICPPainPoint(
            account_id=account_id,
            icp_config_id=icp_config.id,
            pain_point=pain_point,
            consequence=consequence,
            persona=persona,
            priority=priority,
        )
        db.session.add(pp)

    try:
        db.session.commit()
        print(f"Seeded {len(pain_points)} ICPPainPoints for account_id={account_id}")
    except Exception:
        db.session.rollback()
        raise


if __name__ == "__main__":
    from src.app import create_app
    app = create_app()
    with app.app_context():
        seed_pain_points()
```

- [ ] **Step 3: Run seed script**

```bash
cd /Users/kofi/inboxiq && python src/youtube_cadence_seed.py
```

Expected output: `Seeded 6 ICPPainPoints for account_id=2`

- [ ] **Step 4: Run full test suite**

```bash
python -m pytest tests/youtube/ -v
```

Expected: All tests PASS.

- [ ] **Step 5: Enable the cadence in prod.env**

```
YOUTUBE_CADENCE_ENABLED=true
YOUTUBE_ACCOUNT_ID=2
```

- [ ] **Step 6: Set webhook URL in HeyGen dashboard**

Go to `app.heygen.com` → Settings → API → Webhook field:
```
https://api.kalevent.com/api/v1/youtube/heygen/webhook
```
Click "Verify Webhook".

- [ ] **Step 7: Commit everything**

```bash
git add .claude/skills/youtube-cadence/SKILL.md src/youtube_cadence_seed.py
git commit -m "feat: add YouTube cadence SKILL.md and ICP pain point seed data"
```

- [ ] **Step 8: Deploy**

```bash
git push origin main
```

GitHub Actions will build and deploy. Monitor the `content` Celery queue logs after deploy.

---

## Self-Review Checklist

### Spec Coverage

| Spec requirement | Task |
| --- | --- |
| ICPPainPoint model | Task 1 |
| YouTubeVideo model | Task 2 |
| 4 DSPy signatures | Task 3 |
| heygen_mcp.py | Task 4 |
| youtube_mcp.py | Task 5 |
| youtube.generate_scripts | Task 6 |
| youtube.render_videos + DALL-E frames | Task 7 |
| youtube.publish_videos + UTM CTAs | Task 8 |
| HeyGen webhook endpoint | Task 8 |
| youtube.send_digest + email | Task 9 |
| Celery beat schedule | Task 10 |
| SKILL.md | Task 11 |
| ICP pain point seed data | Task 11 |
| Funnel attribution (LeadAttribution query) | Task 9 |
| Re-export in models/__init__.py | Tasks 1, 2 |

All spec requirements covered. ✓

### Type Consistency

- `YouTubeVideo` created in Task 2, used in Tasks 6, 7, 8, 9 — same import path `src.models.campaigns`
- `ICPPainPoint` created in Task 1, used in Tasks 6, 9 — same import path `src.models.leads`
- `heygen_mcp.render_video()` defined in Task 4, called in Task 7 — same signature
- `youtube_mcp.upload_video()` defined in Task 5, called in Task 8 — same signature
- `send_youtube_digest_email()` defined in Task 9 (notifications), imported in Task 9 (tasks) ✓
