# Social Distribution Queue — Design Spec

**Status:** approved (brainstorming) — pending implementation
**Date:** 2026-05-09
**Author:** Kofi + Claude

## Goal

Drive traffic to kalevent.com by automatically sharing every published blog post and YouTube video to LinkedIn, Twitter/X, and Facebook on a steady, non-spammy daily cadence — sourced from a single per-platform queue that backfills the existing inventory of 33 published blog posts and 9 published YouTube videos.

## Problem

Two distinct gaps:

1. **Blog distribution is wired but never fires.** `publish_blog_post` chains to `distribute_to_social`, but it depends on `BlogPost.status='ready'` — a state nothing in the codebase ever sets. All 33 published posts went `draft → published` directly via the admin UI, bypassing the orchestrator. `auto_publish_ready_posts` runs daily at 10am and reports "no posts" every time.
2. **Video → social does not exist.** After `youtube.publish_videos` uploads to YouTube, no follow-on task shares the YouTube link anywhere else.

A spammy fire-on-publish approach (3 LinkedIn posts in one minute when 3 Shorts publish at 8am) is rejected. We need predictable, paced, observable distribution.

## Non-goals (v1)

- **Instagram** — deferred to v2. Requires Business account linked to FB Page, image generation for every post, and link-in-bio rotation.
- **Per-customer multi-tenant rollout.** Schema is multi-tenant-ready and runtime discovers tenants from data, but customer-facing distribution is a separate product feature.
- **Smart per-platform best-time slots** — daily 11am UTC is fine.
- **Engagement/reply tracking** — separate feature.
- **Re-share cadence for old content** — separate feature.

## Architecture

A single per-platform queue table. Content (blog or video) enqueues one row per platform at publish time. A daily Celery task pulls one row per `(account, platform)` and posts it. Backfill is a one-shot task that enqueues every already-published item.

### Why a queue table

| Alternative | Why not |
|---|---|
| Fire-on-publish + Celery rate limit | Per-worker rate limits don't enforce "1 per platform per day"; no audit trail |
| Boolean flags `linkedin_posted_at`, `twitter_posted_at`, … on `BlogPost`/`YouTubeVideo` | Column count balloons; can't add new platforms without schema change; can't track failure/retry per platform |
| Reusing existing `distribute_to_social` task | The whole point of the redesign is to fix that pipeline's problems (lifecycle gap, fire-on-publish bursts, no per-platform observability) |

The queue table gives one row per `(content × platform)` — clean retries, clean audit, clean per-platform pacing.

### Data model

**New table `social_distribution_queue`:**

| column | type | notes |
|---|---|---|
| `id` | String(64) PK | uuid |
| `account_id` | Integer FK accounts | tenant scope; set from content's own account_id |
| `content_type` | String(16) | `'blog'` \| `'video'` |
| `content_id` | String(64) | FK by convention to `blog_posts.id` or `youtube_videos.id` |
| `platform` | String(16) | `'linkedin'` \| `'twitter'` \| `'facebook'` |
| `status` | String(16) | `'pending'` \| `'posted'` \| `'failed'` \| `'skipped'` |
| `caption` | Text | DSPy-generated, frozen at enqueue time so it's reviewable |
| `target_url` | Text | blog canonical URL or YouTube watch URL — what the post links to |
| `posted_url` | Text | LinkedIn/Twitter/Facebook URL of the resulting post |
| `error` | Text | last error if `failed` (truncated to 1024 chars) |
| `attempts` | SmallInt default 0 | retry counter |
| `posted_at` | DateTime tz | success timestamp |
| `created_at` | DateTime tz | row insert |

**Indexes:**
- `(account_id, platform, status, created_at)` — daily picker
- Unique `(content_type, content_id, platform)` — idempotent backfill

**No `BlogPost.status='ready'` step.** Posts go `draft → published` directly (status quo). The queue is the source of truth for what has been distributed; `BlogPost.distributed_at` becomes redundant and is dropped.

### Tenant scoping — derived from data, not configured

No hardcoded account_id anywhere. The daily picker discovers which accounts to process by querying for connected social providers:

```python
distributing_accounts = (
    db.session.query(InboxConnection.account_id)
    .filter(
        InboxConnection.provider.in_(("linkedin_social", "twitter_social", "facebook_social")),
        InboxConnection.status == "connected",
    )
    .distinct()
)
```

Today this returns one row (Kalevent, account_id=2). When a second account connects a social provider, distribution starts targeting them automatically with no code change.

`_get_social_token` is fixed to take an explicit `account_id` parameter (it currently picks "the first connected" connection of a given provider — a cross-tenant bug per the existing `feedback_inbox_connection_query` memory rule). Per-account `LINKEDIN_ORG_ID` moves from env var to `InboxConnection.metadata_json['org_id']` set during the OAuth connect flow.

### Daily picker — `marketing.run_social_distribution_queue`

Scheduled via Celery beat at `SOCIAL_DISTRIBUTION_HOUR` (default 11 UTC).

```
for account_id in distributing_accounts:
    for platform in ("linkedin", "twitter", "facebook"):
        item = pending_items_for(account_id, platform).oldest_first().first()
        if not item: continue
        result = _post_queue_item(item)
        if result['status'] == 'ok':
            item.status = 'posted'
            item.posted_url = result['post_url']
            item.posted_at = now()
        else:
            item.attempts += 1
            item.status = 'failed' if item.attempts >= 3 else 'pending'
            item.error  = (result.get('error') or '')[:1024]
        commit
```

**One item per (account, platform) per day.** No batching, no smart timing.

### Caption generation — at enqueue time

Captions are generated once when the row is inserted, not at post time, so they are observable and editable before going out.

- **Blog** → call existing `_generate_social_content(post)` in [src/marketing/content_distribution.py](src/marketing/content_distribution.py) once per blog post; it returns a `{linkedin: {...}, twitter: {...}, facebook: {...}}` dict; the enqueue helper splits that into three queue rows, one per platform, with `caption` = `text + hashtags` for that platform.
- **Video** → new DSPy signature `YouTubeVideoSocialCaption` in [src/dspy/signatures.py](src/dspy/signatures.py), called once per platform per video.
  - Inputs: `title, video_type, pain_point_text, youtube_url, platform`
  - Outputs: `caption_text, hashtags`
  - Per-platform length limits enforced in the signature prompt (LinkedIn 3000, Twitter 280-thread, Facebook 5000).

DSPy is mandatory per existing `feedback_dspy_for_all_prompts` rule.

### Per-platform poster helpers — refactored

`_post_to_linkedin`, `_post_to_twitter`, `_post_to_facebook` in [src/marketing/content_distribution.py](src/marketing/content_distribution.py) currently take a `BlogPost` object. They are refactored to take a `SocialDistributionQueueItem` and an `account_id`:

```python
def _post_to_linkedin(item: SocialDistributionQueueItem) -> Dict[str, Any]:
    token = _get_social_token("linkedin_social", item.account_id)
    org_id = _get_linkedin_org_id(item.account_id)        # from InboxConnection.metadata_json
    ...
    body = {
        "author": f"urn:li:organization:{org_id}",
        ...
        "shareCommentary": {"text": item.caption},
        "shareMediaCategory": "ARTICLE",
        "media": [{"originalUrl": item.target_url, ...}],
    }
```

This makes the helpers content-agnostic (blog vs. video) — they just post a caption with a target URL.

### Enqueue points

**Blog publish** ([src/marketing/content_distribution.py](src/marketing/content_distribution.py) `publish_blog_post`): replace the fire-on-publish call to `distribute_to_social.delay(...)` with three queue inserts (one per platform), each with a DSPy-generated caption. Drop the `funnel_stage in ['VISITS','DISCOVERY']` filter — every published post enters the queue; the user can mark items `skipped` manually if needed.

**Video publish** ([src/tasks/youtube.py](src/tasks/youtube.py) `publish_videos`): immediately after `video.status = "published"` and before the final commit, insert three queue rows.

Both enqueues use the content's own `account_id` — no fallback, no env var.

### Backfill — one-shot task

New Celery task `marketing.backfill_social_distribution`. Algorithm:

1. For every `BlogPost` where `status='published'`: insert 3 queue rows ordered by `published_at ASC`.
2. For every `YouTubeVideo` where `status='published' AND youtube_url IS NOT NULL`: insert 3 queue rows ordered by `published_at ASC`.
3. Idempotent via the `(content_type, content_id, platform)` unique index — re-running is safe.

Volume: 33 blogs × 3 + 9 videos × 3 = **126 queue items**, drained at 3/day = **~42 days of organic shares from existing inventory**.

Run once after deploy via `kubectl exec deploy/inboxiq -- python -c "from src.celery_inboxiq import celery; celery.send_task('marketing.backfill_social_distribution')"`.

### Failure handling

- Up to 3 retry attempts before final `status='failed'`. Retries happen on subsequent days because failed→pending until the attempt counter hits 3.
- OAuth token expiry is the main expected failure → emit a `crash_report` so the existing email alert fires when a connection needs reconnecting.
- A `failed` item is left in place for forensic review; an admin can flip it back to `pending` after fixing the underlying issue.

### Dead code removal

| File | Remove |
|---|---|
| [src/marketing/content_distribution.py](src/marketing/content_distribution.py) | `auto_publish_ready_posts` task — depended on never-set `status='ready'`, never fired anything |
| [src/marketing/content_distribution.py](src/marketing/content_distribution.py) | `distribute_to_social` Celery task — replaced by the queue picker; the `_post_to_*` helpers stay (refactored) |
| [src/marketing/content_distribution.py](src/marketing/content_distribution.py) | The fire-on-publish call inside `publish_blog_post` (lines 73–79); replaced with queue inserts |
| [src/celery_inboxiq.py](src/celery_inboxiq.py) | Beat schedule entry for `marketing.auto_publish_ready_posts` and the env trio `CONTENT_DISTRIBUTION_ENABLED/HOUR/MAX_POSTS` |
| [src/models/content.py](src/models/content.py) | `BlogPost.distributed_at` column (queue is the source of truth now) — schema migration drops it **only if the pre-impl audit confirms no readers**; otherwise leave the column and stop writing to it |

**Audit step before the delete commit:** grep for any caller of `auto_publish_ready_posts`, `distribute_to_social`, `BlogPost.status == "ready"`, `BlogPost.distributed_at`. Migrate or delete in the same PR.

### Rollout sequence

1. Migration: create `social_distribution_queue` + indexes; drop `BlogPost.distributed_at`
2. Deploy: new task + refactored helpers + dead code removed
3. CI/CD "Force run migrations"
4. Run one-shot backfill: `kubectl exec ... celery.send_task('marketing.backfill_social_distribution')`
5. Beat picks up `marketing.run_social_distribution_queue` at 11 UTC the next day → 3 posts/day go live
6. Watch the queue: `SELECT platform, status, count(*) FROM social_distribution_queue GROUP BY 1,2;`

### Observability

- Queue rows are the audit trail. Status counts and recent failures are inspectable via SQL.
- An admin page `/admin/social-queue` (view/edit/skip pending items) is **out of scope for v1** — manual SQL is fine while volume is low.

## Open questions

None at design time.

## File touchpoints summary

- `src/models/campaigns.py` — new `SocialDistributionQueueItem` model
- `src/migrations/versions/<new>.py` — create table; drop `BlogPost.distributed_at`
- `src/marketing/content_distribution.py` — refactor poster helpers to accept queue items + account_id; remove dead `auto_publish_ready_posts` and `distribute_to_social`; replace fire-on-publish with queue inserts
- `src/marketing/social_distribution.py` — **new** module containing `run_social_distribution_queue` and `backfill_social_distribution` Celery tasks
- `src/dspy/signatures.py` — new `YouTubeVideoSocialCaption` signature
- `src/tasks/youtube.py` — enqueue queue rows after `video.status="published"`
- `src/celery_inboxiq.py` — register new beat schedule for `marketing.run_social_distribution_queue`; remove old `auto_publish_ready_posts` schedule and env vars
- `src/social_auth/` — store per-account `linkedin_org_id` in `InboxConnection.metadata_json` during the OAuth connect flow
