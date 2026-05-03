# HeyGen Video Pipeline Design

**Date:** 2026-05-03
**Status:** Approved — ready for implementation planning

---

## Purpose

Replace the YouTube-specific HeyGen tracking with a shared `VideoRender` layer that powers three video programmes:

- **YouTube cadence** — pain-point-driven awareness videos, published to YouTube (existing, migrated)
- **Onboarding videos** — personalised welcome video sent by email when a customer signs up
- **Personalised outreach** — per-lead video generated at ENRICHED stage, delivered by email + LinkedIn DM simultaneously

Ads and Training Content are confirmed future programmes, deferred to avoid scope creep.

---

## Architecture

**Approach: `VideoRender` as the central render table.**

A single `VideoRender` table owns all HeyGen state. Each programme has its own table with a `video_render_id` FK. The webhook looks up `VideoRender` by `heygen_job_id` — one place, programme-agnostic. Programme tasks handle their own delivery by polling `VideoRender.status`.

---

## Data Model

### New table — `VideoRender` (`src/models/campaigns.py`)

| Column | Type | Nullable | Notes |
|---|---|---|---|
| `id` | String(64) | NOT NULL | UUID PK |
| `account_id` | Integer FK | NOT NULL | Scoped to account |
| `programme` | String(20) | NOT NULL | `youtube`, `onboarding`, `outreach` |
| `video_style` | String(20) | NOT NULL | `avatar` or `illustration` |
| `aspect_ratio` | String(5) | NOT NULL | `16:9` or `9:16` |
| `script` | Text | NULL | Final script submitted to HeyGen |
| `illustration_prompts` | JSON | NULL | Null unless `video_style = illustration` |
| `dalle_frame_urls` | JSON | NULL | Null unless `video_style = illustration` |
| `heygen_job_id` | String(128) | NULL | Set when submitted to HeyGen |
| `heygen_render_url` | String(512) | NULL | Set by webhook on completion |
| `status` | String(32) | NOT NULL | `pending` → `rendering` → `render_complete` → `delivered` → `failed` |
| `render_submitted_at` | DateTime(tz) | NULL | |
| `render_completed_at` | DateTime(tz) | NULL | |
| `created_at` | DateTime(tz) | NOT NULL | |

Index: `(account_id, programme, status)` for delivery polling queries.

---

### Modified table — `YouTubeVideo`

**Add:**
- `video_render_id` String(64) FK → `VideoRender.id` (nullable during migration, NOT NULL after backfill)

**Remove** (moved to `VideoRender`):
- `heygen_job_id`
- `heygen_render_url`
- `illustration_prompts`
- `dalle_frame_urls`
- `render_submitted_at`
- `render_completed_at`

**Keep unchanged:**
- `icp_pain_point_id` NOT NULL — ICP emotional connection is core to YouTube cadence
- `blog_post_id`, `parent_video_id`
- `video_type`, `video_style`
- `script`, `title`, `description`, `tags`, `thumbnail_prompt`
- `youtube_video_id`, `youtube_url`
- `utm_slug`, `utm_source`, `utm_medium`, `utm_campaign`
- `status` — YouTube's own lifecycle (`script_pending` → `published`) stays here
- `view_count`, `click_count`
- `script_generated_at`, `published_at`

---

### New table — `OnboardingVideo` (`src/models/campaigns.py`)

| Column | Type | Nullable | Notes |
|---|---|---|---|
| `id` | String(64) | NOT NULL | UUID PK |
| `account_id` | Integer FK | NOT NULL | The InboxIQ operator account |
| `video_render_id` | String(64) FK | NOT NULL | → `VideoRender.id` |
| `recipient_user_id` | Integer FK | NOT NULL | The new customer (`User.id`) |
| `recipient_name` | String(128) | NOT NULL | Captured at generation time |
| `recipient_company` | String(128) | NULL | Captured at generation time |
| `email_sent_at` | DateTime(tz) | NULL | Null until delivered |
| `created_at` | DateTime(tz) | NOT NULL | |

---

### New table — `OutreachVideo` (`src/models/campaigns.py`)

| Column | Type | Nullable | Notes |
|---|---|---|---|
| `id` | String(64) | NOT NULL | UUID PK |
| `account_id` | Integer FK | NOT NULL | |
| `video_render_id` | String(64) FK | NOT NULL | → `VideoRender.id` |
| `lead_id` | String(64) FK | NOT NULL | → `Lead.id` |
| `delivered_email_at` | DateTime(tz) | NULL | Null until email sent |
| `delivered_linkedin_at` | DateTime(tz) | NULL | Null until LinkedIn DM sent |
| `created_at` | DateTime(tz) | NOT NULL | |

---

## Webhook

### New endpoint

**File:** `src/api/v1/heygen.py` — new blueprint `heygen_api`, prefix `/api/v1/heygen`

**Route:** `POST /api/v1/heygen/webhook`

**Production URL (update in HeyGen dashboard):**
```
https://api.kalevent.com/api/v1/heygen/webhook
```

The old `/api/v1/youtube/heygen/webhook` route is removed from `src/api/v1/youtube.py`.

**Webhook logic:**
```python
data = request.get_json(silent=True) or {}
event_data = data.get("event_data") or {}
if not isinstance(event_data, dict):
    return jsonify({"error": "invalid event_data"}), 400

heygen_job_id = event_data.get("video_id") or event_data.get("id")
if not heygen_job_id:
    return jsonify({"error": "missing video_id"}), 400

render = VideoRender.query.filter_by(heygen_job_id=heygen_job_id).first()
if not render:
    return jsonify({"ok": True}), 200  # unknown job — ACK silently

event_type = data.get("event_type", "")
if "success" in event_type or "complete" in event_type:
    render.heygen_render_url = event_data.get("video_url") or event_data.get("url")
    render.status = "render_complete"
    render.render_completed_at = datetime.now(timezone.utc)
elif "fail" in event_type or "error" in event_type:
    render.status = "failed"

db.session.commit()  # with rollback on exception
return jsonify({"ok": True}), 200
```

No auth on the webhook — validated by `heygen_job_id` lookup (no valid job ID = no state change).

---

## Programme Tasks

### YouTube (`src/tasks/youtube.py`) — updated

All four tasks continue to exist. Changes are surgical:

**`generate_scripts`:**
- Creates `VideoRender(programme="youtube", ...)` first
- Creates `YouTubeVideo(video_render_id=render.id, ...)`
- Moves `script`, `illustration_prompts` fields to `VideoRender`

**`render_videos`:**
- Queries `YouTubeVideo` joined to `VideoRender` via `video_render_id`
- DALL-E frames stored in `VideoRender.dalle_frame_urls`
- HeyGen submission sets `VideoRender.heygen_job_id`, `VideoRender.status = "rendering"`
- Stale polling checks `VideoRender.status = "rendering"` and `render_submitted_at`

**`publish_videos`:**
- Queries `YouTubeVideo JOIN VideoRender` where `VideoRender.status = "render_complete"`
- Uses `VideoRender.heygen_render_url` to download and upload to YouTube
- Sets `VideoRender.status = "delivered"` after successful YouTube publish

**`send_digest`:**
- Joins `VideoRender` for `heygen_render_url` — logic otherwise unchanged

---

### Onboarding (`src/tasks/onboarding_video.py`) — new

**`onboarding_video.generate_and_send(account_id, user_id, recipient_name, recipient_company)`**

Called from the trial/signup flow (wherever `CustomerBillingProfile` is created on signup).

```
1. Generate script via DSPy: OnboardingVideoScript(name, company) → script
2. Create VideoRender(programme="onboarding", video_style="avatar", aspect_ratio="16:9", status="pending")
3. Create OnboardingVideo(video_render_id, recipient_user_id, recipient_name, recipient_company)
4. Submit to HeyGen via heygen_mcp.render_video(script, avatar_id, voice_id, aspect_ratio="16:9")
5. Set VideoRender.heygen_job_id, status="rendering", render_submitted_at
6. Commit
```

**`onboarding_video.deliver_completed`** — beat schedule: daily at 9:00am

```
1. Query OnboardingVideo JOIN VideoRender
   WHERE VideoRender.status = "render_complete"
   AND OnboardingVideo.email_sent_at IS NULL
2. For each: send email with VideoRender.heygen_render_url (video link)
3. Set OnboardingVideo.email_sent_at, VideoRender.status = "delivered"
```

---

### Outreach (`src/tasks/outreach_video.py`) — new

**`outreach_video.generate(account_id, lead_id)`**

Called via `.delay()` from within the lead enrichment task (`src/tasks/`) when a lead transitions to `ENRICHED` stage and has name, company, and role populated.

```
1. Fetch Lead — requires: lead_name, company, role. Pain point optional.
2. Generate script via DSPy: OutreachVideoScript(lead_name, company, role, pain_point) → script
3. Create VideoRender(programme="outreach", video_style="avatar", aspect_ratio="16:9", status="pending")
4. Create OutreachVideo(video_render_id, lead_id)
5. Submit to HeyGen via heygen_mcp.render_video(script, avatar_id, voice_id, aspect_ratio="16:9")
6. Set VideoRender.heygen_job_id, status="rendering", render_submitted_at
7. Commit
```

**`outreach_video.deliver_completed`** — beat schedule: daily at 9:30am

```
1. Query OutreachVideo JOIN VideoRender
   WHERE VideoRender.status = "render_complete"
   AND delivered_email_at IS NULL
   AND delivered_linkedin_at IS NULL
2. For each, fire simultaneously:
   - Send email via existing outreach email flow with video link
   - Queue LinkedIn DM with video link
3. Set delivered_email_at, delivered_linkedin_at, VideoRender.status = "delivered"
```

---

## DSPy Signatures (`src/dspy/signatures.py`)

Two new signatures:

**`OnboardingVideoScript`**
```python
class OnboardingVideoScript(dspy.Signature):
    """Generate a 60-second welcome avatar video script personalised by name and company."""
    name: str = dspy.InputField()
    company: str = dspy.InputField()
    script: str = dspy.OutputField()
```

**`OutreachVideoScript`**
```python
class OutreachVideoScript(dspy.Signature):
    """Generate a 90-second personalised outreach avatar video script for a prospect."""
    lead_name: str = dspy.InputField()
    company: str = dspy.InputField()
    role: str = dspy.InputField()
    pain_point: str = dspy.InputField(desc="Optional — empty string if unknown")
    script: str = dspy.OutputField()
```

---

## Files Changed / Created

| File | Change |
|---|---|
| `src/models/campaigns.py` | Add `VideoRender`, `OnboardingVideo`, `OutreachVideo`; modify `YouTubeVideo` |
| `src/api/v1/heygen.py` | New — generic webhook blueprint |
| `src/api/v1/youtube.py` | Remove `/heygen/webhook` route |
| `src/app.py` | Register `heygen_bp` |
| `src/tasks/youtube.py` | Update 4 tasks to use `VideoRender` |
| `src/tasks/onboarding_video.py` | New — 2 tasks |
| `src/tasks/outreach_video.py` | New — 2 tasks |
| `src/celery_inboxiq.py` | Register new task modules + add 2 beat entries |
| `src/dspy/signatures.py` | Add 2 new signatures |

No new blueprints beyond `heygen_bp`. No new MCP servers.

---

## Migration Notes

- `YouTubeVideo.video_render_id` starts nullable; backfill creates a `VideoRender` record for each existing `YouTubeVideo` row, then column becomes NOT NULL
- The 6 removed columns from `YouTubeVideo` are dropped after backfill
- Existing `YouTubeVideo` rows with `heygen_job_id` set should have `VideoRender.status = "render_complete"` (or `"delivered"` if `youtube_video_id` is set)
- Run `flask db migrate` after model changes; do NOT create migration files manually

---

## Out of Scope

- Ads video programme — confirmed future work, not forgotten
- Training Content video programme — confirmed future work, not forgotten
- Admin UI for OnboardingVideo / OutreachVideo pipeline (can be added later)
- Illustration style for onboarding or outreach (avatar only for now)
