# YouTube Cadence UI Design

**Date:** 2026-05-03
**Status:** Approved — ready for implementation planning

---

## Purpose

Add a YouTube section to the marketing ops dashboard (`/marketing/youtube`) so the cadence pipeline can be monitored and controlled without touching the database or CLI. Modelled exactly on the LinkedIn outreach section.

---

## Design Decisions

- **Layout:** Pipeline table full-width, no separate stats cards — views and clicks live as columns in the table
- **Columns (8):** Title, Type, Style, Status, Pain Point, Views, Clicks, Published
- **Settings:** Single card below the table with two tabs — Pain Points and Triggers
- **Performance first:** Single DB query per load, `.limit(100)`, indexed by `(account_id, status)`

---

## Architecture

### New / Modified Files

| File | Change |
|---|---|
| `src/api/v1/youtube.py` | Add 4 new routes to existing `bp` blueprint |
| `src/marketing_ops/routes.py` | Add `"youtube"` to `_VALID_SECTIONS` |
| `src/templates/marketing_ops.html` | Add YouTube nav link in sidebar + include section template |
| `src/templates/admin/section_youtube.html` | New section template (~260 lines, mirrors section_linkedin.html) |

No new blueprints. No new models. No migrations.

---

## API Routes

All added to the existing `bp = Blueprint("youtube_api", __name__, url_prefix="/api/v1/youtube")` in `src/api/v1/youtube.py`. All use `@login_required_settings` and scope by `g.current_account_id`.

### `GET /api/v1/youtube/videos`

Query params: `status` (optional), `type` (optional — `long_form` or `short`)

```python
q = YouTubeVideo.query.filter_by(account_id=account_id)
if status_filter:
    q = q.filter(YouTubeVideo.status == status_filter)
if type_filter:
    q = q.filter(YouTubeVideo.video_type == type_filter)
videos = q.order_by(YouTubeVideo.created_at.desc()).limit(100).all()
```

Response shape per item:
```json
{
  "id": "...",
  "title": "Never miss a support email again",
  "video_type": "long_form",
  "video_style": "avatar",
  "status": "published",
  "pain_point": "Support emails pile up unread",
  "view_count": 847,
  "click_count": 22,
  "youtube_url": "https://www.youtube.com/watch?v=...",
  "published_at": "2026-05-01T07:00:00+00:00",
  "created_at": "2026-04-30T07:00:00+00:00"
}
```

`pain_point` is resolved via a join to `ICPPainPoint.pain_point` — fetched in the same query using `joinedload`.

### `GET /api/v1/youtube/pain_points`

Returns all active `ICPPainPoint` rows for the account, ordered by `priority desc`.

```json
[
  {
    "id": "...",
    "pain_point": "Support emails pile up unread over the weekend",
    "consequence": "Customers churn before Monday",
    "persona": "Head of Support",
    "priority": 10,
    "active": true
  }
]
```

### `POST /api/v1/youtube/pain_points`

Creates a new `ICPPainPoint`. Requires `icp_config_id` resolved from the account's existing `ICPConfig`.

Body:
```json
{
  "pain_point": "...",
  "consequence": "...",
  "persona": "...",
  "priority": 5
}
```

Returns `{"status": "ok", "id": "..."}` or `{"status": "error", "error": "..."}`.

### `POST /api/v1/youtube/trigger/<task>`

`task` must be one of: `generate_scripts`, `render_videos`, `publish_videos`.

Calls the corresponding Celery task via `.delay(account_id=account_id)`. Returns `{"status": "queued", "task": "..."}`.

Returns 400 for unknown task names.

---

## Template — `src/templates/admin/section_youtube.html`

### Structure

```
section#section-youtube
  ├── header row (title + subtitle)
  ├── div.pipeline-card
  │   ├── filter bar (status dropdown + type dropdown)
  │   └── table#yt-table (8 columns)
  └── div.settings-card
      ├── tab bar (Pain Points | Triggers)
      ├── div#yt-tab-pain-points (pain points list + Add button)
      └── div#yt-tab-triggers (3 trigger buttons, hidden by default)
```

### JavaScript Functions

| Function | Trigger | Action |
|---|---|---|
| `loadYouTubeVideos()` | `sectionChange` event, filter change | GET `/api/v1/youtube/videos` → rebuild table |
| `loadPainPoints()` | `sectionChange` event | GET `/api/v1/youtube/pain_points` → rebuild list |
| `switchYtTab(tab)` | Tab button click | Toggle `hidden` on tab panels, update active border |
| `submitAddPainPoint(e)` | Add form submit | POST `/api/v1/youtube/pain_points` → reload list |
| `triggerTask(task)` | Trigger button click | POST `/api/v1/youtube/trigger/<task>` → flash confirmation |
| `_ytHeaders()` | Called by all fetch calls | Returns `{Content-Type, X-CSRF-TOKEN}` from `csrf_access_token` cookie |

### Section Init Pattern (mirrors LinkedIn exactly)

```javascript
document.addEventListener('sectionChange', (e) => {
  if (e.detail === 'youtube') {
    loadYouTubeVideos();
    loadPainPoints();
  }
});
```

### Status Badge Colours

| Status | Background | Text |
|---|---|---|
| `script_pending` | `bg-slate-700` | `text-slate-300` |
| `script_ready` | `bg-violet-900` | `text-violet-300` |
| `illustrating` | `bg-violet-900` | `text-violet-300` |
| `illustration_ready` | `bg-violet-800` | `text-violet-200` |
| `rendering` | `bg-orange-900` | `text-orange-300` |
| `render_complete` | `bg-blue-900` | `text-blue-300` |
| `publishing` | `bg-blue-800` | `text-blue-200` |
| `published` | `bg-emerald-900` | `text-emerald-400` |
| `failed` | `bg-red-900` | `text-red-400` |

### Type / Style Badges

| Value | Background | Text |
|---|---|---|
| `long_form` | `bg-indigo-900` | `text-indigo-300` — label: "Long" |
| `short` | `bg-sky-900` | `text-sky-300` — label: "Short" |
| `avatar` | `bg-sky-900` | `text-sky-300` — label: "Avatar" |
| `illustration` | `bg-violet-900` | `text-violet-300` — label: "Illus." |

### Title Column

- If `status == "published"` and `youtube_url` is set: render as `<a href="{youtube_url}" target="_blank">`
- Otherwise: plain `<span>`

### Triggers Tab

Three buttons, each calls `triggerTask(name)`:
- `generate_scripts` — "Generate Scripts now"
- `render_videos` — "Submit pending renders"
- `publish_videos` — "Publish render_complete videos"

On success: button text flashes "Queued ✓" for 2 seconds then reverts. On error: show error text below button.

### Add Pain Point

Inline form (no modal — simpler than LinkedIn's modal since pain points are short text):
- `pain_point` text input (required)
- `consequence` text input (required)
- `persona` text input (optional)
- `priority` number input (default 5)
- Submit button

---

## `src/marketing_ops/routes.py` Changes

```python
_VALID_SECTIONS = {"funnel", "content", "marketing", "campaigns", "linkedin", "youtube"}
```

`"youtube"` requires no additional access gate — same `owner`/`admin` check as LinkedIn.

---

## `src/templates/marketing_ops.html` Changes

1. Add YouTube nav link in the sidebar alongside LinkedIn:
```html
<button data-section="youtube" ...>YouTube</button>
```

2. Include the section template in the section container:
```html
{% include "admin/section_youtube.html" %}
```

---

## Performance Notes

- Single query per table load: `joinedload(YouTubeVideo.icp_pain_point)` avoids N+1 on pain_point text
- `.limit(100)` — videos accumulate slowly (4/month), 100 is 2 years of content
- `idx_youtube_videos_account_status` index already exists from migration
- No polling — section loads once on `sectionChange`, user refreshes manually via filter change

---

## Out of Scope

- Editing existing videos (title, description, tags)
- Deactivating / toggling pain points (add only for now)
- Inline script preview
- Pagination UI (limit 100 is sufficient)
