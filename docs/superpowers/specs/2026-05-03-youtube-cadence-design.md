# YouTube Cadence Design

**Date:** 2026-05-03
**Status:** Approved — ready for implementation planning

---

## Purpose

Build a content-driven YouTube funnel that showcases how InboxIQ resolves real ICP pain points — not to sell features, but to show the product ending a problem the viewer already lives with. YouTube is used as a free channel to drive organic traffic to `inboxiq.com` while paid Ads are not yet running.

**North star:** Every video answers one question before a word of script is written:
> *"What painful situation does the viewer recognise in themselves, and how does InboxIQ end it?"*

---

## Architecture — Approach B: Agent-Driven Staged Pipeline

### New MCP Servers

**`src/mcp/heygen_mcp.py`**
Wraps the HeyGen REST API. Designed generically — no YouTube coupling — so it is reusable for Ads production in a future phase.

Tools:
- `render_video(script, avatar_id, voice_id, format, aspect_ratio)` — submits a render job, returns `job_id`
- `get_render_status(job_id)` — returns status + `render_url` when complete

**`src/mcp/youtube_mcp.py`**
Wraps the YouTube Data API v3.

Tools:
- `upload_video(file_url, title, description, tags, category)` — uploads MP4, returns `youtube_video_id`
- `add_end_screen(video_id, cta_url)` — adds end screen card in final 20 seconds
- `add_card(video_id, cta_url, offset_ms)` — adds mid-video card at resolution moment
- `get_video_stats(video_id)` — returns view count, click-through rate

### Celery Beat Tasks — `src/tasks/youtube.py`

| Task | Schedule | Responsibility |
|---|---|---|
| `youtube.generate_scripts` | 1st + 15th of month, 7:00am | DSPy generates 1 long form script + 3 short scripts from latest BlogPost + ICPPainPoint |
| `youtube.render_videos` | Daily 7:30am | Submits pending scripts to HeyGen; polls in-progress renders |
| `youtube.publish_videos` | Daily 8:00am | Uploads completed renders to YouTube; sets UTM descriptions, end screens, cards, pinned comment |
| `youtube.send_digest` | Daily 8:30am | Emails admin: published this week, pipeline status, funnel attribution snapshot |

### DSPy Signatures — `src/dspy/signatures.py`

**`YouTubeLongFormScript`**
```
Inputs:  blog_post_content, icp_persona, pain_point, consequence
Outputs: script, hook_line (first spoken sentence — must name the pain),
         chapter_markers, cta_line
```

**`YouTubeShortScript`**
```
Inputs:  long_form_script, pain_point, parent_youtube_url
Outputs: short_script (≤60s), pattern_interrupt_line (0–3s), cta_line
```

**`YouTubeSEOMetadata`**
```
Inputs:  script, pain_point, blog_post_primary_keyword, video_type
Outputs: title (≤60 chars, pain-outcome format), description (UTM link in line 3),
         tags (10 max), thumbnail_prompt
```

Rule enforced at signature level: product name may not appear in `title` or within the first 5 seconds of any script.

---

## Data Models

### `ICPPainPoint` — `src/models/leads.py`

One row per named ICP pain point. Shared across YouTube, LinkedIn cadence, and blog post pipeline — single source of truth.

**Dependency:** References `icp_configs` table — created by the LinkedIn cadence implementation. Not a new table.

```python
class ICPPainPoint(db.Model):
    __tablename__ = "icp_pain_points"

    id             = db.Column(db.String, primary_key=True, default=lambda: str(uuid.uuid4()))
    account_id     = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=False)
    icp_config_id  = db.Column(db.String, db.ForeignKey("icp_configs.id"), nullable=False)

    pain_point     = db.Column(db.Text, nullable=False)   # "Support emails pile up unread"
    consequence    = db.Column(db.Text, nullable=False)   # "Customers churn before Monday"
    persona        = db.Column(db.String)                 # "Head of Support"
    priority       = db.Column(db.Integer, default=0)     # higher = used first by DSPy
    active         = db.Column(db.Boolean, default=True)

    created_at     = db.Column(db.DateTime, default=datetime.utcnow)
```

**Seed data for primary ICP** (Founders / Heads of Support / Operations Leads · B2B SaaS · 10–50 employees · UK/US/Nigeria):

| Priority | Pain Point | Consequence |
|---|---|---|
| 10 | Support emails pile up unread over the weekend | Customers churn before Monday |
| 9 | No way to tell which leads are warm vs cold | Sales team chases the wrong people |
| 8 | Outreach is manual — copy/paste, one by one | Hours wasted, inconsistent follow-up |
| 7 | Reply comes in, nobody sees it in time | Deal goes cold, prospect moves on |
| 6 | No visibility into which channel drives signups | Budget spent blind |
| 5 | Support team scales by hiring, not by tooling | Margins shrink as you grow |

### `YouTubeVideo` — `src/models/campaigns.py`

One row per video (long form or short). Shorts link back to their parent long form via `parent_video_id`.

```python
class YouTubeVideo(db.Model):
    __tablename__ = "youtube_videos"

    id                   = db.Column(db.String, primary_key=True, default=lambda: str(uuid.uuid4()))
    account_id           = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=False)
    blog_post_id         = db.Column(db.String, db.ForeignKey("blog_posts.id"), nullable=True)
    icp_pain_point_id    = db.Column(db.String, db.ForeignKey("icp_pain_points.id"), nullable=False)
    parent_video_id      = db.Column(db.String, db.ForeignKey("youtube_videos.id"), nullable=True)

    # Content
    video_type           = db.Column(db.String, nullable=False)  # "long_form" | "short"
    script               = db.Column(db.Text)
    title                = db.Column(db.String(100))
    description          = db.Column(db.Text)                    # includes UTM-tagged CTA link
    tags                 = db.Column(db.JSON)
    thumbnail_prompt     = db.Column(db.Text)

    # HeyGen
    heygen_job_id        = db.Column(db.String)
    heygen_render_url    = db.Column(db.String)                  # MP4 URL when render complete

    # YouTube
    youtube_video_id     = db.Column(db.String)
    youtube_url          = db.Column(db.String)

    # UTM / funnel tracking
    utm_slug             = db.Column(db.String, unique=True)     # e.g. "yt-long-inbox-chaos-may-2026"
    utm_source           = db.Column(db.String, default="youtube")
    utm_medium           = db.Column(db.String)                  # "long_form" | "short"
    utm_campaign         = db.Column(db.String)

    # Status + timing
    status               = db.Column(db.String, default="script_pending")
    script_generated_at  = db.Column(db.DateTime)
    render_submitted_at  = db.Column(db.DateTime)
    render_completed_at  = db.Column(db.DateTime)
    published_at         = db.Column(db.DateTime)

    # Performance (refreshed daily by digest task)
    view_count           = db.Column(db.Integer, default=0)
    click_count          = db.Column(db.Integer, default=0)      # from LeadAttribution

    created_at           = db.Column(db.DateTime, default=datetime.utcnow)
```

**Status flow:**
```
script_pending → script_ready → rendering → render_complete → publishing → published → failed
```

---

## SKILL.md — Content Consistency Contract

The SKILL.md file lives at `.claude/skills/youtube-cadence/SKILL.md`. It governs quality at every stage.

### Hard Rules (agent blocks publish if violated)

1. Script must open with the named pain point — no greeting, no intro, no product name
2. Product name (`InboxIQ`) may not appear in the video title
3. `icp_pain_point_id` must be set before script generation begins — agent cannot invent a pain point
4. Every Short must link back to its parent Long form in the pinned comment
5. `utm_slug` must be unique — agent checks before publishing

### Cadence Rules

| Cycle | Type | Source |
|---|---|---|
| 1st of month, 7am | Long form (8–12 min) | Latest published `BlogPost` |
| 15th of month, 7am | Long form (8–12 min) | Second latest `BlogPost` |
| Auto, after each long form | 2–3 Shorts (≤60s) | DSPy extracts up to 3 clips from the long form script; minimum 2 required before pipeline advances |

### Script Structure

**Long Form:**
```
1. HOOK        (0–30s)    Open on the pain. No intro, no welcome.
2. PROBLEM     (30s–2m)   Make the consequence real and specific.
3. RESOLUTION  (2m–9m)    Show InboxIQ solving it. Screen demo or avatar walkthrough.
4. PROOF       (9m–10m)   One concrete outcome (time saved, emails handled, leads recovered).
5. CTA         (10m–end)  One ask only: "Start free at inboxiq.com" + end screen card.
```

**Short (≤60s):**
```
1. PATTERN INTERRUPT  (0–3s)   One sentence naming the pain. No greeting.
2. AGITATION          (3–20s)  The viewer's world without a fix.
3. RESOLUTION         (20–50s) InboxIQ solving it. Fast. Visual.
4. CTA                (50–60s) "Link in description. Free to start."
```

### SEO / GEO Standards

**Title formula:** `[Pain outcome] — [How] | InboxIQ` — max 60 chars
- Correct: *"Never miss a support email again | InboxIQ"*
- Wrong: *"InboxIQ AI Triage Feature Demo"*

**Description:** First 2 lines (visible before "show more") must state the pain and resolution. UTM link in line 3. No filler.

**Tags:** 3 broad (inbox management, customer support, B2B SaaS) + 3 specific keywords from `BlogPost.primary_keyword`.

**GEO:** Default to UK/US English. Nigerian market addressed via dedicated video series with `utm_campaign` prefix `ng-` — not mixed into general content.

**Thumbnail prompt:** Must depict a before/after state or a visible problem — never a logo-only or text-only card.

### CTA Placement

| Placement | Long Form | Short |
|---|---|---|
| Description line 3 | `inboxiq.com/start?utm_source=youtube&utm_medium=long_form&utm_campaign={slug}` | `inboxiq.com/start?utm_source=youtube&utm_medium=short&utm_campaign={slug}` |
| End screen (last 20s) | Link to `/start` + subscribe button | N/A |
| Card (mid-video) | At resolution moment → `/start` | N/A |
| Pinned comment | "Start free → [UTM link]" | "Full video → [parent_youtube_url]" |

### Pre-Publish Quality Checklist

- [ ] Script opens with pain — no greeting, no intro
- [ ] Product name absent from title and first 5 seconds of script
- [ ] `icp_pain_point_id` populated on `YouTubeVideo` record
- [ ] UTM slug is unique — no duplicate `utm_campaign` values
- [ ] Description has UTM link in first 3 lines
- [ ] Short links back to parent Long form in pinned comment
- [ ] Tags include at least one keyword matching `BlogPost.primary_keyword`
- [ ] `thumbnail_prompt` populated (not null)

---

## Funnel Attribution Flow

No new tracking infrastructure required. The existing `LeadAttribution` model and `/funnel/dashboard` handle everything.

```
Viewer watches video
        ↓
Clicks CTA link in description or end screen
inboxiq.com/start?utm_source=youtube&utm_medium=long_form&utm_campaign=inbox-chaos-may-2026
        ↓
Landing page JS captures UTM params → POST /api/v1/leads/track
        ↓
LeadAttribution record created:
  source   = "youtube"
  medium   = "long_form"
  campaign = "inbox-chaos-may-2026"
  lead_id  = (new or matched Lead)
        ↓
Lead enters VISITS stage in funnel
        ↓
/funnel/dashboard shows YouTube as acquisition channel
        ↓
YouTubeVideo.click_count refreshed daily by digest task
(count query: LeadAttribution WHERE utm_campaign = video.utm_campaign)
```

---

## Daily Digest Email

Sent by `youtube.send_digest` at 8:30am. Three sections:

**Published this week** — title, type, pain point, view count, UTM click count, YouTube link

**Pipeline status** — every `YouTubeVideo` not yet published: current status, blocker, expected publish date. Renders stuck in `rendering` for >24h flagged as failed.

**Funnel attribution** — visitors from YouTube this week → trial starts. Source: `LeadAttribution WHERE utm_source='youtube'` joined to `CustomerBillingProfile`.

---

## What This Answers for the Business

| Question | Source |
|---|---|
| Which pain points resonate most? | View count per `ICPPainPoint` |
| Long form or Shorts convert better? | `utm_medium` split in `LeadAttribution` |
| Which blog post generates the best videos? | `blog_post_id` on `YouTubeVideo` |
| Is YouTube driving trials? | `LeadAttribution` → `CustomerBillingProfile` |

---

## Dependencies & Config

| Item | Notes |
|---|---|
| `HEYGE_API_KEY` | HeyGen REST API key — new env var |
| `HEYGE_AVATAR_ID` | Default avatar ID for InboxIQ brand voice |
| `HEYGE_VOICE_ID` | Default voice ID |
| `YOUTUBE_CLIENT_ID` | OAuth 2.0 client for YouTube Data API v3 |
| `YOUTUBE_CLIENT_SECRET` | OAuth 2.0 secret |
| `YOUTUBE_CHANNEL_ID` | Target channel for uploads |
| `YOUTUBE_REFRESH_TOKEN` | Long-lived token for programmatic upload |

---

## Out of Scope

- AI-generated thumbnail images (thumbnail prompt is text only — human creates image from prompt)
- YouTube Analytics API integration beyond basic view counts (future phase)
- Paid Ads production via HeyGen (future phase — MCP server is already generic)
- A/B title testing
- Subtitle/caption generation
