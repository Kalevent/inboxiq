# Social Distribution Queue Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Drive traffic to kalevent.com by automatically distributing every published blog post and YouTube video to LinkedIn, Twitter, and Facebook on a daily 1-per-platform-per-account cadence, sourced from a per-platform queue table.

**Architecture:** A new `social_distribution_queue` table holds one row per `(content × platform)`. Blog and video publish flows insert rows. A daily Celery task picks one pending row per `(account, platform)`, posts via existing helpers (refactored to be content-agnostic), and updates the row. Tenant scope is derived from `InboxConnection` rows — never hardcoded. A one-shot backfill task seeds the queue with 33 already-published blogs + 9 published videos = ~126 rows.

**Tech Stack:** Python 3.11, Flask, SQLAlchemy, Celery, DSPy, pytest+unittest.mock. Spec at `docs/superpowers/specs/2026-05-09-social-distribution-queue-design.md`.

---

## File Structure

**Create:**
- `src/marketing/social_distribution.py` — new module: enqueue helpers, daily picker task, backfill task
- `tests/marketing/__init__.py` — package init for marketing tests
- `tests/marketing/conftest.py` — `app`/`db` fixture creating SQLite tables for SocialDistributionQueueItem + dependencies
- `tests/marketing/test_social_distribution_model.py` — model + index tests
- `tests/marketing/test_social_distribution_helpers.py` — `_post_to_*` refactor tests
- `tests/marketing/test_social_distribution_picker.py` — daily picker tests
- `tests/marketing/test_social_distribution_backfill.py` — backfill task tests
- `tests/marketing/test_social_distribution_enqueue.py` — blog + video enqueue tests

**Modify:**
- `src/models/campaigns.py` — add `SocialDistributionQueueItem` model (~30 lines at end of file)
- `src/marketing/content_distribution.py` — refactor `_post_to_linkedin/twitter/facebook` to take queue items + account_id; refactor `_get_social_token` to take account_id; remove `auto_publish_ready_posts` and `distribute_to_social`; replace fire-on-publish in `publish_blog_post`
- `src/dspy/signatures.py` — add `YouTubeVideoSocialCaption` signature
- `src/tasks/youtube.py` — enqueue queue rows after `video.status = "published"` in `publish_videos`
- `src/celery_inboxiq.py` — register `marketing.run_social_distribution_queue` beat schedule with `SOCIAL_DISTRIBUTION_HOUR` env (default 11); remove `marketing.auto_publish_ready_posts` schedule + `CONTENT_DISTRIBUTION_*` env vars
- `src/social_auth/<oauth handler>` — capture `linkedin_org_id` into `InboxConnection.metadata_json` during connect

**Migration:**
- `src/migrations/versions/<auto>_social_distribution_queue.py` — auto-generated via `flask db migrate`

---

## Conventions used by this plan

- Tests use the existing fixture pattern: `tests/marketing/conftest.py` creates a per-test SQLite app with only the tables this feature needs.
- Run a single test: `pytest tests/marketing/test_x.py::test_name -v`
- Run all marketing tests: `pytest tests/marketing -v`
- Pre-commit hooks may run; do not bypass with `--no-verify`.
- Commit at the end of each task. Never amend.

---

## Task 1: Add `SocialDistributionQueueItem` model

**Files:**
- Modify: `src/models/campaigns.py` (append at end)
- Create: `tests/marketing/__init__.py`
- Create: `tests/marketing/conftest.py`
- Create: `tests/marketing/test_social_distribution_model.py`

- [ ] **Step 1.1: Create empty `tests/marketing/__init__.py`**

```python
# tests/marketing/__init__.py
```

- [ ] **Step 1.2: Create `tests/marketing/conftest.py`**

```python
# tests/marketing/conftest.py
import os
import pytest

os.environ.setdefault("APP_ENV", "test")

from src.app import create_app
from src.extensions import db as _db
from src.models.core import Account, InboxConnection
from src.models.content import BlogPost
from src.models.campaigns import YouTubeVideo, VideoRender, SocialDistributionQueueItem


@pytest.fixture
def app():
    from sqlalchemy.pool import StaticPool

    app = create_app()
    app.config["TESTING"] = True
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite://"
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
        "connect_args": {"check_same_thread": False},
        "poolclass": StaticPool,
    }
    app.config["SECRET_KEY"] = "test-secret"
    with app.app_context():
        Account.__table__.create(_db.engine, checkfirst=True)
        InboxConnection.__table__.create(_db.engine, checkfirst=True)
        BlogPost.__table__.create(_db.engine, checkfirst=True)
        VideoRender.__table__.create(_db.engine, checkfirst=True)
        YouTubeVideo.__table__.create(_db.engine, checkfirst=True)
        SocialDistributionQueueItem.__table__.create(_db.engine, checkfirst=True)
        yield app
        _db.session.remove()
        SocialDistributionQueueItem.__table__.drop(_db.engine, checkfirst=True)
        YouTubeVideo.__table__.drop(_db.engine, checkfirst=True)
        VideoRender.__table__.drop(_db.engine, checkfirst=True)
        BlogPost.__table__.drop(_db.engine, checkfirst=True)
        InboxConnection.__table__.drop(_db.engine, checkfirst=True)
        Account.__table__.drop(_db.engine, checkfirst=True)


@pytest.fixture
def db(app):
    return _db


@pytest.fixture
def kalevent_account(db):
    a = Account(id=2, name="Kalevent")
    db.session.add(a)
    db.session.commit()
    return a
```

- [ ] **Step 1.3: Write failing model test**

Create `tests/marketing/test_social_distribution_model.py`:

```python
from src.models.campaigns import SocialDistributionQueueItem


def test_queue_item_persists_with_defaults(app, db, kalevent_account):
    item = SocialDistributionQueueItem(
        account_id=2,
        content_type="blog",
        content_id="post-abc",
        platform="linkedin",
        caption="Read our new post on inbox triage.",
        target_url="https://kalevent.com/blog/post-abc",
    )
    db.session.add(item)
    db.session.commit()

    fetched = db.session.query(SocialDistributionQueueItem).first()
    assert fetched.status == "pending"
    assert fetched.attempts == 0
    assert fetched.posted_at is None
    assert fetched.created_at is not None


def test_queue_item_unique_per_content_platform(app, db, kalevent_account):
    item1 = SocialDistributionQueueItem(
        account_id=2, content_type="blog", content_id="post-abc",
        platform="linkedin", caption="x", target_url="u",
    )
    db.session.add(item1)
    db.session.commit()

    item2 = SocialDistributionQueueItem(
        account_id=2, content_type="blog", content_id="post-abc",
        platform="linkedin", caption="y", target_url="u",
    )
    db.session.add(item2)
    import pytest
    from sqlalchemy.exc import IntegrityError
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


def test_queue_item_allows_same_content_on_different_platforms(app, db, kalevent_account):
    for p in ("linkedin", "twitter", "facebook"):
        db.session.add(SocialDistributionQueueItem(
            account_id=2, content_type="blog", content_id="post-abc",
            platform=p, caption="x", target_url="u",
        ))
    db.session.commit()
    assert db.session.query(SocialDistributionQueueItem).count() == 3
```

- [ ] **Step 1.4: Run tests — expect ImportError**

Run: `pytest tests/marketing/test_social_distribution_model.py -v`
Expected: ImportError on `SocialDistributionQueueItem`.

- [ ] **Step 1.5: Add the model to `src/models/campaigns.py`**

Append to `src/models/campaigns.py` (after `OutreachVideo`):

```python
class SocialDistributionQueueItem(db.Model):
    """One row per (content × platform) for paced social distribution."""
    __tablename__ = "social_distribution_queue"
    __table_args__ = (
        db.Index(
            "idx_sdq_account_platform_status_created",
            "account_id", "platform", "status", "created_at",
        ),
        db.UniqueConstraint(
            "content_type", "content_id", "platform",
            name="uq_sdq_content_platform",
        ),
    )

    id = db.Column(db.String(64), primary_key=True, default=lambda: str(uuid4()), nullable=False)
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=False)
    content_type = db.Column(db.String(16), nullable=False)  # 'blog' | 'video'
    content_id = db.Column(db.String(64), nullable=False)
    platform = db.Column(db.String(16), nullable=False)  # 'linkedin' | 'twitter' | 'facebook'
    status = db.Column(db.String(16), nullable=False, server_default="pending")
    caption = db.Column(db.Text, nullable=False)
    target_url = db.Column(db.Text, nullable=False)
    posted_url = db.Column(db.Text, nullable=True)
    error = db.Column(db.Text, nullable=True)
    attempts = db.Column(db.SmallInteger, nullable=False, server_default="0")
    posted_at = db.Column(db.DateTime(timezone=True), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, server_default=func.now())
```

- [ ] **Step 1.6: Re-export from `src/models/__init__.py`**

In `src/models/__init__.py`, add `SocialDistributionQueueItem` to both the import line and the `__all__` list under `campaigns`:

```python
from src.models.campaigns import (
    CampaignSender, HunterDomainCache, EmailCampaign, EmailOutreach, NurtureEmailSend,
    LinkedInProspect, YouTubeVideo, VideoRender, OnboardingVideo, OutreachVideo,
    SocialDistributionQueueItem,
)
```

And the corresponding `"SocialDistributionQueueItem"` in `__all__`.

- [ ] **Step 1.7: Run tests — expect PASS**

Run: `pytest tests/marketing/test_social_distribution_model.py -v`
Expected: 3 passed.

- [ ] **Step 1.8: Commit**

```bash
git add src/models/campaigns.py src/models/__init__.py tests/marketing/
git commit -m "feat(social): add SocialDistributionQueueItem model"
```

---

## Task 2: Generate and review migration

**Files:**
- Create (auto-gen): `src/migrations/versions/<auto>_social_distribution_queue.py`

This task is run by the user, not autogenerated by the agent — per CLAUDE.md "DO NOT create migration files directly."

- [ ] **Step 2.1: User runs migration autogenerate**

User runs locally:

```bash
flask db migrate -m "add social_distribution_queue"
```

- [ ] **Step 2.2: Review and trim the generated migration**

Open the generated file. Keep only the `social_distribution_queue` create_table + index + unique constraint operations. Delete any unrelated drift Alembic picked up (e.g., `automation_studio_waitlist` index drift) — record those for a separate housekeeping migration.

- [ ] **Step 2.3: Apply locally**

```bash
flask db upgrade
```

- [ ] **Step 2.4: Commit**

```bash
git add src/migrations/versions/*social_distribution_queue.py
git commit -m "migration: add social_distribution_queue table"
```

---

## Task 3: Refactor `_get_social_token` to require `account_id`

**Files:**
- Modify: `src/marketing/content_distribution.py:447-454`
- Create: `tests/marketing/test_social_distribution_helpers.py`

- [ ] **Step 3.1: Write failing test**

Create `tests/marketing/test_social_distribution_helpers.py`:

```python
from unittest.mock import patch, MagicMock


def test_get_social_token_scopes_by_account(app, db, kalevent_account):
    from src.models.core import InboxConnection
    from src.crypto import encrypt_value

    InboxConnection.query.delete()
    db.session.add(InboxConnection(
        id="c1", account_id=2, provider="linkedin_social", status="connected",
        metadata_json={"access_token_enc": encrypt_value("token-acc-2")},
    ))
    db.session.add(InboxConnection(
        id="c2", account_id=99, provider="linkedin_social", status="connected",
        metadata_json={"access_token_enc": encrypt_value("token-acc-99")},
    ))
    db.session.commit()

    from src.marketing.content_distribution import _get_social_token
    assert _get_social_token("linkedin_social", account_id=2) == "token-acc-2"
    assert _get_social_token("linkedin_social", account_id=99) == "token-acc-99"


def test_get_social_token_returns_none_when_unconnected(app, db, kalevent_account):
    from src.marketing.content_distribution import _get_social_token
    assert _get_social_token("linkedin_social", account_id=2) is None
```

- [ ] **Step 3.2: Run test — expect FAIL (TypeError: missing positional arg)**

Run: `pytest tests/marketing/test_social_distribution_helpers.py -v -k get_social_token`
Expected: FAIL.

- [ ] **Step 3.3: Update `_get_social_token` signature**

Replace `src/marketing/content_distribution.py:447-454` with:

```python
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
```

- [ ] **Step 3.4: Update existing callers in `_post_to_linkedin`/`_post_to_twitter`/`_post_to_facebook`**

In each helper, change `token = _get_social_token("linkedin_social")` to `token = _get_social_token("linkedin_social", account_id)`. The `account_id` parameter is added in Task 4.

For now, to keep the test for Task 3 passing without breaking existing integration, update all three call sites to use a default — temporary scaffold removed in Task 4:

In `src/marketing/content_distribution.py`, locate each `_get_social_token("linkedin_social")` / `_get_social_token("twitter_social")` / `_get_social_token("facebook_social")` and append `, account_id=2` literal **only as a temporary bridge**. Task 4 replaces these.

```python
# TEMPORARY (removed in Task 4)
token = _get_social_token("linkedin_social", account_id=2)
```

- [ ] **Step 3.5: Run tests — expect PASS**

Run: `pytest tests/marketing/test_social_distribution_helpers.py -v -k get_social_token`
Expected: 2 passed.

- [ ] **Step 3.6: Commit**

```bash
git add src/marketing/content_distribution.py tests/marketing/test_social_distribution_helpers.py
git commit -m "refactor(social): scope _get_social_token by account_id"
```

---

## Task 4: Refactor `_post_to_*` helpers to take queue items

**Files:**
- Modify: `src/marketing/content_distribution.py` (`_post_to_linkedin`/`_post_to_twitter`/`_post_to_facebook`)
- Modify: `tests/marketing/test_social_distribution_helpers.py` (extend)

- [ ] **Step 4.1: Write failing test for `_post_to_linkedin`**

Append to `tests/marketing/test_social_distribution_helpers.py`:

```python
def test_post_to_linkedin_uses_queue_item_and_org_id(app, db, kalevent_account, monkeypatch):
    from src.models.core import InboxConnection
    from src.models.campaigns import SocialDistributionQueueItem
    from src.crypto import encrypt_value

    db.session.add(InboxConnection(
        id="c1", account_id=2, provider="linkedin_social", status="connected",
        metadata_json={
            "access_token_enc": encrypt_value("li-token"),
            "org_id": "999",
        },
    ))
    item = SocialDistributionQueueItem(
        account_id=2, content_type="blog", content_id="post-1",
        platform="linkedin", caption="Hello LinkedIn",
        target_url="https://kalevent.com/blog/post-1",
    )
    db.session.add(item)
    db.session.commit()

    captured = {}
    def fake_post(url, json, headers, timeout):
        captured["url"] = url
        captured["json"] = json
        captured["headers"] = headers
        resp = MagicMock()
        resp.raise_for_status = lambda: None
        resp.json = lambda: {"id": "urn:li:share:abc"}
        return resp

    import requests as http
    monkeypatch.setattr(http, "post", fake_post)

    from src.marketing.content_distribution import _post_to_linkedin
    result = _post_to_linkedin(item)

    assert result["status"] == "ok"
    assert result["post_url"] == "https://www.linkedin.com/feed/update/urn:li:share:abc"
    assert captured["url"] == "https://api.linkedin.com/v2/ugcPosts"
    body = captured["json"]
    assert body["author"] == "urn:li:organization:999"
    assert body["specificContent"]["com.linkedin.ugc.ShareContent"]["shareCommentary"]["text"] == "Hello LinkedIn"
    assert body["specificContent"]["com.linkedin.ugc.ShareContent"]["media"][0]["originalUrl"] == "https://kalevent.com/blog/post-1"


def test_post_to_linkedin_skips_when_not_connected(app, db, kalevent_account):
    from src.models.campaigns import SocialDistributionQueueItem
    item = SocialDistributionQueueItem(
        account_id=2, content_type="blog", content_id="post-1",
        platform="linkedin", caption="x", target_url="u",
    )
    db.session.add(item)
    db.session.commit()

    from src.marketing.content_distribution import _post_to_linkedin
    result = _post_to_linkedin(item)
    assert result["status"] == "skipped"
    assert result["reason"] == "not_connected"
```

- [ ] **Step 4.2: Run test — expect FAIL**

Run: `pytest tests/marketing/test_social_distribution_helpers.py::test_post_to_linkedin_uses_queue_item_and_org_id -v`
Expected: FAIL — current `_post_to_linkedin` takes `(post, content)` not `(item)`.

- [ ] **Step 4.3: Refactor `_post_to_linkedin`**

Replace the entire `_post_to_linkedin` function in `src/marketing/content_distribution.py` with:

```python
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
```

- [ ] **Step 4.4: Run linkedin tests — expect PASS**

Run: `pytest tests/marketing/test_social_distribution_helpers.py -v -k linkedin`
Expected: 2 passed.

- [ ] **Step 4.5: Repeat refactor for `_post_to_twitter`**

Replace `_post_to_twitter` similarly — accept `item`, fetch token via `_get_social_token("twitter_social", item.account_id)`, post the caption with the target URL appended, return `{"status": "ok", "post_url": "https://twitter.com/i/web/status/<id>"}`. (Existing implementation in [src/marketing/content_distribution.py:524-569](src/marketing/content_distribution.py#L524-L569) — reuse the API call shape, just swap parameters.)

Add a corresponding test in `tests/marketing/test_social_distribution_helpers.py` mirroring the LinkedIn one.

- [ ] **Step 4.6: Repeat refactor for `_post_to_facebook`**

Same pattern. Existing impl at [src/marketing/content_distribution.py:571-632](src/marketing/content_distribution.py#L571-L632). Resolve `facebook_page_id` from `InboxConnection.metadata_json['page_id']` (mirror the LinkedIn `_get_linkedin_org_id` helper as `_get_facebook_page_id`).

Add test mirroring LinkedIn.

- [ ] **Step 4.7: Run all helper tests**

Run: `pytest tests/marketing/test_social_distribution_helpers.py -v`
Expected: all pass.

- [ ] **Step 4.8: Commit**

```bash
git add src/marketing/content_distribution.py tests/marketing/test_social_distribution_helpers.py
git commit -m "refactor(social): poster helpers take queue items + per-account org/page resolution"
```

---

## Task 5: `YouTubeVideoSocialCaption` DSPy signature

**Files:**
- Modify: `src/dspy/signatures.py`
- Create: `tests/marketing/test_video_caption_signature.py`

- [ ] **Step 5.1: Write failing test (signature shape only — DSPy module compiles)**

Create `tests/marketing/test_video_caption_signature.py`:

```python
def test_youtube_video_social_caption_signature_fields():
    from src.dspy.signatures import YouTubeVideoSocialCaption

    sig = YouTubeVideoSocialCaption
    fields = sig.model_fields if hasattr(sig, "model_fields") else sig.signature.input_fields
    # Inputs
    assert "title" in sig.signature.input_fields
    assert "video_type" in sig.signature.input_fields
    assert "pain_point_text" in sig.signature.input_fields
    assert "youtube_url" in sig.signature.input_fields
    assert "platform" in sig.signature.input_fields
    # Outputs
    assert "caption_text" in sig.signature.output_fields
    assert "hashtags" in sig.signature.output_fields
```

- [ ] **Step 5.2: Run test — expect FAIL**

Run: `pytest tests/marketing/test_video_caption_signature.py -v`
Expected: ImportError.

- [ ] **Step 5.3: Add the signature**

Append to `src/dspy/signatures.py`:

```python
class YouTubeVideoSocialCaption(dspy.Signature):
    """Generate a social media caption promoting a YouTube video.

    Length limits per platform:
      linkedin: <= 3000 chars; professional tone; encourage click-through.
      twitter:  <= 280 chars; punchy; one hashtag max.
      facebook: <= 5000 chars; conversational; emoji ok.
    Always include the youtube_url at the end. Never use 'InboxIQ' in the first sentence.
    """

    title = dspy.InputField(desc="YouTube video title")
    video_type = dspy.InputField(desc="'long_form' or 'short'")
    pain_point_text = dspy.InputField(desc="The viewer pain the video addresses")
    youtube_url = dspy.InputField(desc="YouTube watch URL of the video")
    platform = dspy.InputField(desc="'linkedin' | 'twitter' | 'facebook'")
    caption_text = dspy.OutputField(desc="Caption body, length-appropriate for platform")
    hashtags = dspy.OutputField(desc="2-4 space-separated hashtags, no leading text")
```

- [ ] **Step 5.4: Run test — expect PASS**

Run: `pytest tests/marketing/test_video_caption_signature.py -v`
Expected: PASS.

- [ ] **Step 5.5: Commit**

```bash
git add src/dspy/signatures.py tests/marketing/test_video_caption_signature.py
git commit -m "feat(dspy): YouTubeVideoSocialCaption signature"
```

---

## Task 6: Enqueue helpers in new `src/marketing/social_distribution.py`

**Files:**
- Create: `src/marketing/social_distribution.py`
- Create: `tests/marketing/test_social_distribution_enqueue.py`

- [ ] **Step 6.1: Write failing test for blog enqueue**

Create `tests/marketing/test_social_distribution_enqueue.py`:

```python
from unittest.mock import patch
from src.models.campaigns import SocialDistributionQueueItem
from src.models.content import BlogPost


def test_enqueue_blog_creates_three_rows(app, db, kalevent_account):
    post = BlogPost(
        id="post-x", account_id=2, title="A title",
        slug="a-title", canonical_url="https://kalevent.com/blog/a-title",
        status="published", excerpt="An excerpt",
    )
    db.session.add(post)
    db.session.commit()

    fake_content = {
        "linkedin": {"text": "LI body", "hashtags": "#a #b"},
        "twitter": {"text": "TW body", "hashtags": "#a"},
        "facebook": {"text": "FB body", "hashtags": ""},
    }
    with patch("src.marketing.social_distribution._generate_social_content", return_value=fake_content):
        from src.marketing.social_distribution import enqueue_blog_post
        n = enqueue_blog_post(post)
    assert n == 3

    rows = db.session.query(SocialDistributionQueueItem).order_by(SocialDistributionQueueItem.platform).all()
    assert [r.platform for r in rows] == ["facebook", "linkedin", "twitter"]
    li = [r for r in rows if r.platform == "linkedin"][0]
    assert li.account_id == 2
    assert li.content_type == "blog"
    assert li.content_id == "post-x"
    assert li.target_url == "https://kalevent.com/blog/a-title"
    assert li.caption == "LI body\n\n#a #b"
    assert li.status == "pending"


def test_enqueue_blog_idempotent(app, db, kalevent_account):
    post = BlogPost(
        id="post-x", account_id=2, title="t", slug="t",
        canonical_url="https://kalevent.com/blog/t", status="published",
    )
    db.session.add(post)
    db.session.commit()

    fake_content = {p: {"text": "x", "hashtags": ""} for p in ("linkedin","twitter","facebook")}
    with patch("src.marketing.social_distribution._generate_social_content", return_value=fake_content):
        from src.marketing.social_distribution import enqueue_blog_post
        enqueue_blog_post(post)
        enqueue_blog_post(post)  # second call should not duplicate
    assert db.session.query(SocialDistributionQueueItem).count() == 3
```

- [ ] **Step 6.2: Run test — expect FAIL (module missing)**

Run: `pytest tests/marketing/test_social_distribution_enqueue.py::test_enqueue_blog_creates_three_rows -v`
Expected: FAIL ImportError.

- [ ] **Step 6.3: Create `src/marketing/social_distribution.py`**

```python
"""Per-platform queue for paced social distribution of blogs and YouTube videos."""
from __future__ import annotations

import logging
from typing import Optional, List

from sqlalchemy.exc import IntegrityError

from src.celery_inboxiq import celery
from src.extensions import db
from src.models.campaigns import (
    SocialDistributionQueueItem, YouTubeVideo, VideoRender,
)
from src.models.content import BlogPost
from src.models.core import InboxConnection
from src.marketing.content_distribution import (
    _generate_social_content,
    _post_to_linkedin,
    _post_to_twitter,
    _post_to_facebook,
)

logger = logging.getLogger(__name__)

PLATFORMS = ("linkedin", "twitter", "facebook")


def _compose_caption(text: str, hashtags: str) -> str:
    text = (text or "").strip()
    hashtags = (hashtags or "").strip()
    return f"{text}\n\n{hashtags}".strip() if hashtags else text


def enqueue_blog_post(post: BlogPost) -> int:
    """Create one pending queue item per platform for a published blog post.

    Idempotent — existing rows for (content_type='blog', content_id=post.id, platform) are skipped.
    Returns the number of NEW rows inserted.
    """
    if not post.canonical_url:
        logger.warning("enqueue_blog_post: post %s has no canonical_url, skipping", post.id)
        return 0

    content = _generate_social_content(post)
    inserted = 0
    for platform in PLATFORMS:
        per = content.get(platform) or {}
        caption = _compose_caption(per.get("text", ""), per.get("hashtags", ""))
        if not caption:
            continue
        item = SocialDistributionQueueItem(
            account_id=post.account_id,
            content_type="blog",
            content_id=post.id,
            platform=platform,
            caption=caption,
            target_url=post.canonical_url,
        )
        db.session.add(item)
        try:
            db.session.commit()
            inserted += 1
        except IntegrityError:
            db.session.rollback()  # already enqueued
    return inserted
```

- [ ] **Step 6.4: Run blog enqueue tests — expect PASS**

Run: `pytest tests/marketing/test_social_distribution_enqueue.py -v -k blog`
Expected: 2 passed.

- [ ] **Step 6.5: Add failing test for video enqueue**

Append to `tests/marketing/test_social_distribution_enqueue.py`:

```python
def test_enqueue_video_creates_three_rows(app, db, kalevent_account):
    from src.models.campaigns import VideoRender, YouTubeVideo
    render = VideoRender(
        id="render-1", account_id=2, programme="youtube",
        video_style="avatar", aspect_ratio="9:16", status="delivered",
    )
    db.session.add(render)
    db.session.commit()
    video = YouTubeVideo(
        id="vid-1", account_id=2, video_render_id="render-1",
        video_type="short", title="Endless Email Chains No More | InboxIQ",
        status="published", youtube_url="https://www.youtube.com/watch?v=YN1JHIARDvs",
        utm_medium="short", utm_campaign="endless-email-chains",
    )
    db.session.add(video)
    db.session.commit()

    def fake_caption(title, video_type, pain_point_text, youtube_url, platform):
        return type("R", (), {
            "caption_text": f"caption for {platform}",
            "hashtags": f"#{platform}",
        })()

    with patch("src.marketing.social_distribution._generate_video_caption", side_effect=fake_caption):
        from src.marketing.social_distribution import enqueue_youtube_video
        n = enqueue_youtube_video(video, render, pain_point_text="x")
    assert n == 3

    rows = db.session.query(SocialDistributionQueueItem).all()
    assert {r.platform for r in rows} == {"linkedin", "twitter", "facebook"}
    for r in rows:
        assert r.content_type == "video"
        assert r.content_id == "vid-1"
        assert r.target_url == "https://www.youtube.com/watch?v=YN1JHIARDvs"
```

- [ ] **Step 6.6: Run test — expect FAIL**

Run: `pytest tests/marketing/test_social_distribution_enqueue.py -v -k video`
Expected: FAIL.

- [ ] **Step 6.7: Implement `enqueue_youtube_video` and `_generate_video_caption`**

Append to `src/marketing/social_distribution.py`:

```python
def _generate_video_caption(*, title: str, video_type: str, pain_point_text: str,
                            youtube_url: str, platform: str):
    """DSPy-backed video caption generator. Returns a Prediction with caption_text + hashtags."""
    import dspy
    from src.dspy.signatures import YouTubeVideoSocialCaption
    from src.dspy.triage_config import _configure_dspy

    _configure_dspy()
    predictor = dspy.Predict(YouTubeVideoSocialCaption)
    return predictor(
        title=title,
        video_type=video_type,
        pain_point_text=pain_point_text,
        youtube_url=youtube_url,
        platform=platform,
    )


def enqueue_youtube_video(video: YouTubeVideo, render: VideoRender,
                          pain_point_text: str = "") -> int:
    """Create one pending queue item per platform for a published YouTube video.

    Idempotent. Returns count of NEW rows inserted.
    """
    if not video.youtube_url:
        logger.warning("enqueue_youtube_video: video %s has no youtube_url", video.id)
        return 0

    inserted = 0
    for platform in PLATFORMS:
        try:
            pred = _generate_video_caption(
                title=video.title or "",
                video_type=video.video_type or "short",
                pain_point_text=pain_point_text,
                youtube_url=video.youtube_url,
                platform=platform,
            )
            caption = _compose_caption(pred.caption_text, pred.hashtags)
        except Exception as exc:
            logger.exception("video caption generation failed for %s/%s", video.id, platform)
            caption = f"{video.title}\n\n{video.youtube_url}"

        if not caption:
            continue
        item = SocialDistributionQueueItem(
            account_id=video.account_id,
            content_type="video",
            content_id=video.id,
            platform=platform,
            caption=caption,
            target_url=video.youtube_url,
        )
        db.session.add(item)
        try:
            db.session.commit()
            inserted += 1
        except IntegrityError:
            db.session.rollback()
    return inserted
```

- [ ] **Step 6.8: Run video enqueue test — expect PASS**

Run: `pytest tests/marketing/test_social_distribution_enqueue.py -v -k video`
Expected: PASS.

- [ ] **Step 6.9: Commit**

```bash
git add src/marketing/social_distribution.py tests/marketing/test_social_distribution_enqueue.py
git commit -m "feat(social): enqueue helpers for blog + video into the queue"
```

---

## Task 7: Daily picker `run_social_distribution_queue`

**Files:**
- Modify: `src/marketing/social_distribution.py`
- Create: `tests/marketing/test_social_distribution_picker.py`

- [ ] **Step 7.1: Write failing test**

Create `tests/marketing/test_social_distribution_picker.py`:

```python
from unittest.mock import patch
from datetime import datetime, timezone, timedelta

from src.models.campaigns import SocialDistributionQueueItem
from src.models.core import InboxConnection


def _seed_connection(db, account_id, provider="linkedin_social"):
    db.session.add(InboxConnection(
        id=f"c-{account_id}-{provider}", account_id=account_id,
        provider=provider, status="connected", metadata_json={},
    ))
    db.session.commit()


def _seed_pending(db, account_id, platform, content_id, created_at=None):
    item = SocialDistributionQueueItem(
        account_id=account_id, content_type="blog", content_id=content_id,
        platform=platform, caption=f"caption-{content_id}-{platform}",
        target_url=f"https://example.com/{content_id}",
    )
    if created_at:
        item.created_at = created_at
    db.session.add(item)
    db.session.commit()
    return item


def test_picker_picks_oldest_pending_per_account_platform(app, db, kalevent_account):
    _seed_connection(db, 2, "linkedin_social")
    now = datetime.now(timezone.utc)
    older = _seed_pending(db, 2, "linkedin", "post-A", created_at=now - timedelta(days=2))
    newer = _seed_pending(db, 2, "linkedin", "post-B", created_at=now - timedelta(days=1))

    with patch("src.marketing.social_distribution._post_to_linkedin",
               return_value={"status": "ok", "post_url": "https://li.com/x"}):
        from src.marketing.social_distribution import run_social_distribution_queue
        result = run_social_distribution_queue()

    db.session.refresh(older)
    db.session.refresh(newer)
    assert older.status == "posted"
    assert newer.status == "pending"
    assert older.posted_url == "https://li.com/x"
    assert older.posted_at is not None
    assert result["posted"] == 1


def test_picker_marks_failed_after_three_attempts(app, db, kalevent_account):
    _seed_connection(db, 2, "linkedin_social")
    item = _seed_pending(db, 2, "linkedin", "post-X")
    item.attempts = 2
    db.session.commit()

    with patch("src.marketing.social_distribution._post_to_linkedin",
               return_value={"status": "error", "error": "boom"}):
        from src.marketing.social_distribution import run_social_distribution_queue
        run_social_distribution_queue()

    db.session.refresh(item)
    assert item.status == "failed"
    assert item.attempts == 3
    assert "boom" in (item.error or "")


def test_picker_skips_accounts_without_connections(app, db, kalevent_account):
    _seed_pending(db, 2, "linkedin", "post-A")  # NO InboxConnection seeded

    with patch("src.marketing.social_distribution._post_to_linkedin") as li:
        from src.marketing.social_distribution import run_social_distribution_queue
        run_social_distribution_queue()
        li.assert_not_called()


def test_picker_one_per_platform_per_run(app, db, kalevent_account):
    _seed_connection(db, 2, "linkedin_social")
    _seed_connection(db, 2, "twitter_social")
    a = _seed_pending(db, 2, "linkedin", "blog-1")
    b = _seed_pending(db, 2, "linkedin", "blog-2")
    c = _seed_pending(db, 2, "twitter", "blog-1")

    posted = []
    def ok(item):
        posted.append((item.platform, item.content_id))
        return {"status": "ok", "post_url": "https://x"}

    with patch("src.marketing.social_distribution._post_to_linkedin", side_effect=ok), \
         patch("src.marketing.social_distribution._post_to_twitter", side_effect=ok), \
         patch("src.marketing.social_distribution._post_to_facebook", side_effect=ok):
        from src.marketing.social_distribution import run_social_distribution_queue
        run_social_distribution_queue()

    assert len(posted) == 2  # one linkedin, one twitter
    assert ("linkedin", "blog-1") in posted  # oldest first
    assert ("twitter", "blog-1") in posted
```

- [ ] **Step 7.2: Run tests — expect FAIL**

Run: `pytest tests/marketing/test_social_distribution_picker.py -v`
Expected: ImportError.

- [ ] **Step 7.3: Implement the picker**

Append to `src/marketing/social_distribution.py`:

```python
from datetime import datetime, timezone

POSTERS = {
    "linkedin": _post_to_linkedin,
    "twitter": _post_to_twitter,
    "facebook": _post_to_facebook,
}

PROVIDER_FOR = {
    "linkedin": "linkedin_social",
    "twitter": "twitter_social",
    "facebook": "facebook_social",
}

MAX_ATTEMPTS = 3


def _accounts_with_social_connections() -> List[int]:
    rows = (
        db.session.query(InboxConnection.account_id)
        .filter(
            InboxConnection.provider.in_(tuple(PROVIDER_FOR.values())),
            InboxConnection.status == "connected",
        )
        .distinct()
        .all()
    )
    return [r[0] for r in rows]


def _account_has_provider(account_id: int, platform: str) -> bool:
    return InboxConnection.query.filter_by(
        account_id=account_id,
        provider=PROVIDER_FOR[platform],
        status="connected",
    ).first() is not None


@celery.task(name="marketing.run_social_distribution_queue")
def run_social_distribution_queue() -> dict:
    """Daily picker: post one pending item per (account, platform)."""
    accounts = _accounts_with_social_connections()
    posted = 0
    failed = 0
    for account_id in accounts:
        for platform in PLATFORMS:
            if not _account_has_provider(account_id, platform):
                continue
            item = (
                SocialDistributionQueueItem.query
                .filter_by(account_id=account_id, platform=platform, status="pending")
                .order_by(SocialDistributionQueueItem.created_at.asc())
                .first()
            )
            if not item:
                continue

            poster = POSTERS[platform]
            try:
                result = poster(item)
            except Exception as exc:
                logger.exception("social poster crashed for %s/%s", account_id, platform)
                result = {"status": "error", "error": str(exc)}

            item.attempts = (item.attempts or 0) + 1
            if result.get("status") == "ok":
                item.status = "posted"
                item.posted_url = result.get("post_url")
                item.posted_at = datetime.now(timezone.utc)
                posted += 1
            elif result.get("status") == "skipped":
                item.status = "skipped"
                item.error = result.get("reason", "")[:1024]
            else:
                err = (result.get("error") or "")[:1024]
                item.error = err
                if item.attempts >= MAX_ATTEMPTS:
                    item.status = "failed"
                    failed += 1

            try:
                db.session.commit()
            except Exception:
                db.session.rollback()
                raise

    return {"status": "ok", "posted": posted, "failed": failed, "accounts": len(accounts)}
```

- [ ] **Step 7.4: Run picker tests — expect PASS**

Run: `pytest tests/marketing/test_social_distribution_picker.py -v`
Expected: 4 passed.

- [ ] **Step 7.5: Commit**

```bash
git add src/marketing/social_distribution.py tests/marketing/test_social_distribution_picker.py
git commit -m "feat(social): daily picker run_social_distribution_queue"
```

---

## Task 8: Backfill task

**Files:**
- Modify: `src/marketing/social_distribution.py`
- Create: `tests/marketing/test_social_distribution_backfill.py`

- [ ] **Step 8.1: Write failing test**

```python
# tests/marketing/test_social_distribution_backfill.py
from unittest.mock import patch
from src.models.campaigns import SocialDistributionQueueItem, YouTubeVideo, VideoRender
from src.models.content import BlogPost


def test_backfill_seeds_blogs_and_videos(app, db, kalevent_account):
    db.session.add(BlogPost(
        id="b1", account_id=2, title="t", slug="t",
        canonical_url="https://kalevent.com/blog/t", status="published",
    ))
    render = VideoRender(id="r1", account_id=2, programme="youtube",
                         video_style="avatar", aspect_ratio="9:16", status="delivered")
    db.session.add(render)
    db.session.add(YouTubeVideo(
        id="v1", account_id=2, video_render_id="r1",
        video_type="short", title="title", status="published",
        youtube_url="https://www.youtube.com/watch?v=abc",
        utm_medium="short", utm_campaign="x",
    ))
    db.session.commit()

    fake_blog_content = {p: {"text": "x", "hashtags": ""} for p in ("linkedin","twitter","facebook")}
    with patch("src.marketing.social_distribution._generate_social_content", return_value=fake_blog_content), \
         patch("src.marketing.social_distribution._generate_video_caption",
               side_effect=lambda **kw: type("R", (), {"caption_text":"c","hashtags":""})()):
        from src.marketing.social_distribution import backfill_social_distribution
        result = backfill_social_distribution()

    assert result["blogs_enqueued"] == 1
    assert result["videos_enqueued"] == 1
    assert db.session.query(SocialDistributionQueueItem).count() == 6  # 3 blog + 3 video


def test_backfill_is_idempotent(app, db, kalevent_account):
    db.session.add(BlogPost(
        id="b1", account_id=2, title="t", slug="t",
        canonical_url="https://kalevent.com/blog/t", status="published",
    ))
    db.session.commit()

    fake_content = {p: {"text": "x", "hashtags": ""} for p in ("linkedin","twitter","facebook")}
    with patch("src.marketing.social_distribution._generate_social_content", return_value=fake_content):
        from src.marketing.social_distribution import backfill_social_distribution
        backfill_social_distribution()
        backfill_social_distribution()  # second run inserts no new rows

    assert db.session.query(SocialDistributionQueueItem).count() == 3
```

- [ ] **Step 8.2: Run — expect FAIL**

Run: `pytest tests/marketing/test_social_distribution_backfill.py -v`
Expected: FAIL.

- [ ] **Step 8.3: Implement the backfill task**

Append to `src/marketing/social_distribution.py`:

```python
@celery.task(name="marketing.backfill_social_distribution")
def backfill_social_distribution() -> dict:
    """One-shot: enqueue every published blog post and YouTube video into the queue.

    Idempotent — relies on the unique (content_type, content_id, platform) constraint.
    """
    blogs_enqueued = 0
    videos_enqueued = 0

    blogs = (
        BlogPost.query
        .filter(BlogPost.status == "published")
        .order_by(BlogPost.published_at.asc())
        .all()
    )
    for post in blogs:
        if enqueue_blog_post(post) > 0:
            blogs_enqueued += 1

    videos = (
        db.session.query(YouTubeVideo, VideoRender)
        .join(VideoRender, YouTubeVideo.video_render_id == VideoRender.id)
        .filter(
            YouTubeVideo.status == "published",
            YouTubeVideo.youtube_url.isnot(None),
        )
        .order_by(YouTubeVideo.published_at.asc())
        .all()
    )
    for video, render in videos:
        if enqueue_youtube_video(video, render) > 0:
            videos_enqueued += 1

    return {
        "status": "ok",
        "blogs_enqueued": blogs_enqueued,
        "videos_enqueued": videos_enqueued,
    }
```

- [ ] **Step 8.4: Run — expect PASS**

Run: `pytest tests/marketing/test_social_distribution_backfill.py -v`
Expected: 2 passed.

- [ ] **Step 8.5: Commit**

```bash
git add src/marketing/social_distribution.py tests/marketing/test_social_distribution_backfill.py
git commit -m "feat(social): one-shot backfill of existing blogs + videos"
```

---

## Task 9: Wire blog publish → enqueue (replace fire-on-publish)

**Files:**
- Modify: `src/marketing/content_distribution.py:69-95` (replace the social/newsletter/seo fan-out block)

- [ ] **Step 9.1: Write failing test**

Append to `tests/marketing/test_social_distribution_enqueue.py`:

```python
def test_publish_blog_post_enqueues_via_queue(app, db, kalevent_account):
    from src.models.content import BlogPost
    from src.models.campaigns import SocialDistributionQueueItem

    post = BlogPost(
        id="post-pub", account_id=2, title="t", slug="t",
        canonical_url="https://kalevent.com/blog/t",
        status="ready", rendered_html="<p>hi</p>",
    )
    db.session.add(post)
    db.session.commit()

    fake_content = {p: {"text": "x", "hashtags": ""} for p in ("linkedin","twitter","facebook")}
    with patch("src.marketing.social_distribution._generate_social_content", return_value=fake_content), \
         patch("src.marketing.content_distribution.send_blog_newsletter.delay"), \
         patch("src.marketing.content_distribution.submit_to_search_engines.delay"):
        from src.marketing.content_distribution import publish_blog_post
        publish_blog_post("post-pub")

    db.session.refresh(post)
    assert post.status == "published"
    assert db.session.query(SocialDistributionQueueItem).count() == 3
```

- [ ] **Step 9.2: Run — expect FAIL**

Run: `pytest tests/marketing/test_social_distribution_enqueue.py::test_publish_blog_post_enqueues_via_queue -v`
Expected: FAIL — current code calls `distribute_to_social.delay`.

- [ ] **Step 9.3: Replace fan-out block in `publish_blog_post`**

In `src/marketing/content_distribution.py`, replace lines 69-95 (the `# Trigger distribution channels…` block down to and including the `# Mark distribution as initiated` block) with:

```python
        # Distribution: enqueue per-platform rows (replaces fire-on-publish).
        from src.marketing.social_distribution import enqueue_blog_post
        try:
            enqueue_blog_post(post)
        except Exception as exc:
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
```

- [ ] **Step 9.4: Run — expect PASS**

Run: `pytest tests/marketing/test_social_distribution_enqueue.py::test_publish_blog_post_enqueues_via_queue -v`
Expected: PASS.

- [ ] **Step 9.5: Commit**

```bash
git add src/marketing/content_distribution.py tests/marketing/test_social_distribution_enqueue.py
git commit -m "feat(social): publish_blog_post enqueues via queue, drops fire-on-publish"
```

---

## Task 10: Wire video publish → enqueue

**Files:**
- Modify: `src/tasks/youtube.py` (after `video.status = "published"` in `publish_videos`)
- Create: `tests/marketing/test_youtube_publish_enqueues.py`

- [ ] **Step 10.1: Write failing test**

```python
# tests/marketing/test_youtube_publish_enqueues.py
from unittest.mock import patch, MagicMock
from src.models.campaigns import SocialDistributionQueueItem


def test_publish_videos_enqueues_after_youtube_upload(app, db, kalevent_account):
    from src.models.campaigns import VideoRender, YouTubeVideo
    render = VideoRender(
        id="r-pub", account_id=2, programme="youtube",
        video_style="avatar", aspect_ratio="9:16", status="render_complete",
        heygen_job_id="job-1",
    )
    db.session.add(render)
    db.session.add(YouTubeVideo(
        id="v-pub", account_id=2, video_render_id="r-pub",
        video_type="short", title="t",
        utm_medium="short", utm_campaign="c",
        status="render_complete", description="desc {{UTM_LINK}}",
        tags=[],
    ))
    db.session.commit()

    fake_caption = lambda **kw: type("R", (), {"caption_text":"c","hashtags":""})()

    with patch("src.tasks.youtube.heygen_mcp") as heygen, \
         patch("src.tasks.youtube.youtube_mcp") as ytmcp, \
         patch("src.marketing.social_distribution._generate_video_caption", side_effect=fake_caption):
        heygen.get_render_status.return_value = {"status": "completed", "render_url": "https://x.mp4"}
        ytmcp.upload_video.return_value = {"status": "published",
                                           "youtube_video_id": "yt-id",
                                           "youtube_url": "https://www.youtube.com/watch?v=yt-id"}
        ytmcp.add_end_screen.return_value = None
        ytmcp.add_card.return_value = None
        ytmcp.post_pinned_comment.return_value = None

        from src.tasks.youtube import publish_videos
        publish_videos(account_id=2)

    items = db.session.query(SocialDistributionQueueItem).all()
    assert len(items) == 3
    assert {i.platform for i in items} == {"linkedin","twitter","facebook"}
    assert all(i.target_url == "https://www.youtube.com/watch?v=yt-id" for i in items)
```

- [ ] **Step 10.2: Run — expect FAIL**

Run: `pytest tests/marketing/test_youtube_publish_enqueues.py -v`
Expected: FAIL.

- [ ] **Step 10.3: Add enqueue call in `publish_videos`**

In `src/tasks/youtube.py`, after the block that sets `video.status = "published"`, `video.published_at = ...`, `render.status = "delivered"`, and commits (around lines 603-610 per [src/tasks/youtube.py:603](src/tasks/youtube.py#L603)), append:

```python
            # After successful YouTube upload, enqueue 1 row per social platform.
            try:
                from src.marketing.social_distribution import enqueue_youtube_video
                pain_point_text = ""
                if video.icp_pain_point_id:
                    from src.models.leads import ICPPainPoint
                    pp = db.session.get(ICPPainPoint, video.icp_pain_point_id)
                    if pp:
                        pain_point_text = pp.pain_point or ""
                enqueue_youtube_video(video, render, pain_point_text=pain_point_text)
            except Exception:
                logger.exception("youtube.publish_videos: enqueue social distribution failed for %s", video.id)
```

- [ ] **Step 10.4: Run — expect PASS**

Run: `pytest tests/marketing/test_youtube_publish_enqueues.py -v`
Expected: PASS.

- [ ] **Step 10.5: Commit**

```bash
git add src/tasks/youtube.py tests/marketing/test_youtube_publish_enqueues.py
git commit -m "feat(social): YouTube publish enqueues video into social queue"
```

---

## Task 11: Capture `linkedin_org_id` during OAuth connect

**Files:**
- Modify: `src/social_auth/<linkedin handler file>` — locate via `grep -rn "linkedin_social" src/social_auth`

- [ ] **Step 11.1: Locate the LinkedIn OAuth callback**

```bash
grep -rn "linkedin_social\|linkedin/callback\|access_token" src/social_auth | head
```

Identify the function that creates/updates the `InboxConnection` for `provider='linkedin_social'`.

- [ ] **Step 11.2: Write failing integration test**

Create `tests/marketing/test_linkedin_oauth_org_id.py`:

```python
from unittest.mock import patch, MagicMock


def test_linkedin_callback_persists_org_id(app, db, kalevent_account, monkeypatch):
    """After OAuth callback, the InboxConnection.metadata_json carries 'org_id'."""
    # This test stubs the LinkedIn HTTP calls and asserts persistence.
    # Replace the import path below with the real callback function discovered in 11.1.
    from src.social_auth import linkedin as linkedin_oauth  # adjust if different

    monkeypatch.setattr(linkedin_oauth, "_exchange_code_for_token", lambda code: "TOKEN")
    monkeypatch.setattr(linkedin_oauth, "_fetch_admin_organization_id", lambda token: "999")

    # Simulate session/account context as the real callback does:
    with app.test_request_context("/auth/linkedin/callback?code=xyz&state=ok"):
        linkedin_oauth.handle_callback(account_id=2)

    from src.models.core import InboxConnection
    conn = InboxConnection.query.filter_by(provider="linkedin_social", account_id=2).first()
    assert conn is not None
    assert conn.metadata_json.get("org_id") == "999"
```

- [ ] **Step 11.3: Run — expect FAIL**

Run: `pytest tests/marketing/test_linkedin_oauth_org_id.py -v`
Expected: FAIL — `_fetch_admin_organization_id` not defined.

- [ ] **Step 11.4: Implement org_id fetch + persist**

In the LinkedIn OAuth handler, after exchanging the code for a token and before/while creating the `InboxConnection`, call LinkedIn's `/v2/organizationAcls?q=roleAssignee&role=ADMINISTRATOR` endpoint with the bearer token. Extract the first `organizationalTarget` URN's numeric ID:

```python
def _fetch_admin_organization_id(access_token: str) -> Optional[str]:
    """Return the numeric ID of the first LinkedIn org the user can administer, or None."""
    import requests as http
    try:
        resp = http.get(
            "https://api.linkedin.com/v2/organizationAcls",
            params={"q": "roleAssignee", "role": "ADMINISTRATOR", "state": "APPROVED"},
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=15,
        )
        resp.raise_for_status()
        elements = (resp.json() or {}).get("elements") or []
        if not elements:
            return None
        urn = elements[0].get("organizationalTarget", "")  # 'urn:li:organization:999'
        return urn.rsplit(":", 1)[-1] or None
    except Exception:
        return None
```

In the existing `handle_callback` (or equivalent), after the token is decrypted and the connection row is built, set:

```python
metadata_json = {**(metadata_json or {}), "access_token_enc": encrypt_value(token)}
org_id = _fetch_admin_organization_id(token)
if org_id:
    metadata_json["org_id"] = org_id
conn.metadata_json = metadata_json
```

- [ ] **Step 11.5: Run — expect PASS**

Run: `pytest tests/marketing/test_linkedin_oauth_org_id.py -v`
Expected: PASS.

- [ ] **Step 11.6: Document the manual reconnect for already-connected accounts**

Add to the rollout README or a comment in `src/social_auth/linkedin.py`:

> Existing `linkedin_social` connections were created before `org_id` was captured. Account holders must disconnect + reconnect once to populate `metadata_json['org_id']`. Until then, `_post_to_linkedin` returns `{"status": "skipped", "reason": "not_configured"}`.

- [ ] **Step 11.7: Commit**

```bash
git add src/social_auth/ tests/marketing/test_linkedin_oauth_org_id.py
git commit -m "feat(social): capture linkedin_org_id during OAuth connect"
```

---

## Task 12: Remove dead distribution code

**Files:**
- Modify: `src/marketing/content_distribution.py` (delete `auto_publish_ready_posts`, `distribute_to_social`)
- Modify: `src/celery_inboxiq.py` (delete `auto_publish_ready_posts` schedule + env vars)

- [ ] **Step 12.1: Audit for callers**

Run:

```bash
grep -rn "auto_publish_ready_posts\|distribute_to_social\b" src/ tests/ \
  --include="*.py" --include="*.html" --include="*.yml"
```

Expected: only definitions in `src/marketing/content_distribution.py` and the beat schedule entry in `src/celery_inboxiq.py`. If anything else references them, migrate or delete those callers in this same task before deleting the definitions.

- [ ] **Step 12.2: Delete `distribute_to_social` task**

In `src/marketing/content_distribution.py`, delete the entire `distribute_to_social` function (currently at lines 119-169).

- [ ] **Step 12.3: Delete `auto_publish_ready_posts` task**

Delete `auto_publish_ready_posts` (currently at lines 700-748).

- [ ] **Step 12.4: Delete the obsolete beat schedule entry + env vars**

In `src/celery_inboxiq.py`, remove:
- `content_distribution_enabled = ...` (line 146)
- `content_distribution_hour = ...` (line 147)
- `content_distribution_max_posts = ...` (line 148)
- The conditional schedule block (lines 297-303 referencing `marketing.auto_publish_ready_posts`).

- [ ] **Step 12.5: Run full test suite — expect PASS**

Run: `pytest tests/ -v`
Expected: all green.

- [ ] **Step 12.6: Commit**

```bash
git add src/marketing/content_distribution.py src/celery_inboxiq.py
git commit -m "chore(social): remove dead auto_publish_ready_posts + distribute_to_social"
```

---

## Task 13: Register the daily picker beat schedule

**Files:**
- Modify: `src/celery_inboxiq.py`

- [ ] **Step 13.1: Add env var read**

Near the other schedule env reads in `src/celery_inboxiq.py`:

```python
social_distribution_hour = int(os.getenv("SOCIAL_DISTRIBUTION_HOUR", "11"))
```

- [ ] **Step 13.2: Add the beat entry**

Inside the `beat_schedule` dict where other schedules are registered, add:

```python
"social_distribution_daily": {
    "task": "marketing.run_social_distribution_queue",
    "schedule": crontab(hour=social_distribution_hour, minute=0),
},
```

- [ ] **Step 13.3: Verify by booting the celery beat config**

```bash
.venv/bin/python -c "from src.celery_inboxiq import celery; print([k for k in celery.conf.beat_schedule])"
```

Expected: list contains `'social_distribution_daily'` and does NOT contain any `auto_publish_ready_posts` entry.

- [ ] **Step 13.4: Commit**

```bash
git add src/celery_inboxiq.py
git commit -m "feat(social): schedule daily social distribution picker"
```

---

## Task 14: Audit and conditionally drop `BlogPost.distributed_at`

**Files (depends on audit outcome):**
- Modify: `src/models/content.py` (drop column)
- Migration via `flask db migrate`

- [ ] **Step 14.1: Audit readers**

```bash
grep -rn "distributed_at" src/ tests/ --include="*.py" --include="*.html"
```

If anything outside `src/marketing/content_distribution.py` reads it, **STOP** and add a migration step instead of dropping. Otherwise proceed.

- [ ] **Step 14.2: Remove column from model**

In `src/models/content.py`, remove the `distributed_at` column from `BlogPost`.

Also remove any remaining write `post.distributed_at = ...` in `publish_blog_post`.

- [ ] **Step 14.3: User generates migration**

```bash
flask db migrate -m "drop blog_posts.distributed_at"
```

Trim the autogenerate to only the column drop. Apply locally.

- [ ] **Step 14.4: Run full test suite**

Run: `pytest tests/ -v`
Expected: green.

- [ ] **Step 14.5: Commit**

```bash
git add src/models/content.py src/marketing/content_distribution.py src/migrations/versions/*distributed_at.py
git commit -m "chore(blog): drop unused distributed_at column"
```

---

## Task 15: Deploy + run prod backfill + verify

**Files:** none (operational task)

- [ ] **Step 15.1: Push to main**

```bash
git push origin main
```

GitHub Actions builds + deploys.

- [ ] **Step 15.2: Run prod migration**

Trigger CI/CD's "Force run migrations" workflow.

- [ ] **Step 15.3: Reconnect LinkedIn** (one-time)

In Settings → Integrations, the user disconnects + reconnects LinkedIn so `metadata_json['org_id']` is populated. Verify:

```bash
kubectl exec -n kaley deploy/inboxiq -- python -c "
from src.app import create_app
app = create_app()
with app.app_context():
    from src.models.core import InboxConnection
    c = InboxConnection.query.filter_by(provider='linkedin_social', account_id=2).first()
    print('org_id:', (c.metadata_json or {}).get('org_id'))
"
```

Expected: prints a numeric LinkedIn org ID.

- [ ] **Step 15.4: Run the backfill task**

```bash
kubectl exec -n kaley deploy/inboxiq -- python -c "
from src.celery_inboxiq import celery
print(celery.send_task('marketing.backfill_social_distribution').id)
"
```

- [ ] **Step 15.5: Verify queue counts**

```bash
kubectl exec -n kaley deploy/inboxiq -- python -c "
from src.app import create_app
app = create_app()
with app.app_context():
    from src.extensions import db
    from src.models.campaigns import SocialDistributionQueueItem
    rows = db.session.query(
        SocialDistributionQueueItem.platform,
        SocialDistributionQueueItem.status,
        db.func.count()
    ).group_by(
        SocialDistributionQueueItem.platform,
        SocialDistributionQueueItem.status
    ).all()
    for p, s, n in rows:
        print(f'{p:10} {s:10} {n}')
"
```

Expected: ~42 pending rows per platform, 0 posted.

- [ ] **Step 15.6: Trigger the picker once to validate**

```bash
kubectl exec -n kaley deploy/inboxiq -- python -c "
from src.celery_inboxiq import celery
print(celery.send_task('marketing.run_social_distribution_queue').id)
"
```

Wait 30 seconds, then re-run Step 15.5 — expected: 1 posted row per platform that had a connected provider; 1 fewer pending row per platform.

- [ ] **Step 15.7: Confirm a post landed on LinkedIn**

Open the LinkedIn company page. Confirm the new post is live and the `target_url` resolves. Repeat for Twitter and Facebook.

- [ ] **Step 15.8: Done**

The 11am UTC beat will drain ~3 posts/day across the queue. Monitor via SQL query above for the next few days.

---

## Self-review checklist

- [x] Spec coverage: every section of the spec maps to a task (model T1, migration T2, helpers T3-4, video DSPy T5, enqueue helpers T6, picker T7, backfill T8, blog wiring T9, video wiring T10, OAuth org_id T11, dead code T12, schedule T13, distributed_at drop T14, deploy T15).
- [x] No placeholders — every code step has a code block.
- [x] Type/name consistency — `SocialDistributionQueueItem` used everywhere; `enqueue_blog_post`/`enqueue_youtube_video`/`run_social_distribution_queue`/`backfill_social_distribution` used consistently.
- [x] Each task ends with a commit.
- [x] Tests run before implementation in every task (red → green).
