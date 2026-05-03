# Onboarding Video Programme — Design Spec

**Date:** 2026-05-04
**Status:** Approved

---

## Goal

Send every new InboxIQ customer a personalised welcome video within ~30 minutes of connecting their inbox. The video covers three beats: a personalised welcome, what InboxIQ is doing behind the scenes, and what they can expect. Delivered by email and surfaced in-app via a dismissible banner and dashboard card.

---

## Trigger

The programme fires exactly once per account, on first `InboxConnection` creation.

When a user successfully connects Gmail or Outlook, the OAuth callback queues `queue_onboarding_video(account_id, user_id)`. A guard inside the task checks that no `OnboardingVideo` already exists for the account before proceeding — making it safe to call more than once without creating duplicates.

---

## Personalisation Inputs

| Field | Source |
|---|---|
| `recipient_name` | `User.name` |
| `recipient_company` | `Account.name` |
| `referral_source` | `Account.referral_source` (how they heard about InboxIQ) |

---

## DSPy Signature

A new `OnboardingVideoScript` signature added to `src/dspy/signatures.py`:

**Inputs:** `recipient_name`, `recipient_company`, `referral_source`

**Outputs:** `script`, `hook_line`, `cta_line`

The script covers three beats:
1. Personalised welcome — addresses the recipient by name and company
2. What's happening now — explains what InboxIQ is doing with their connected inbox (triaging, categorising, drafting replies)
3. What to expect — sets expectations for day 1: automated triage, draft replies ready, automation rules available

The compiled module is persisted to `dspy_artifacts/onboarding_video_script.json` with HMAC signing, following the existing `dspy_artifacts/` pattern. First run compiles and saves; subsequent runs load from disk.

---

## Task Architecture

### Task 1: `queue_onboarding_video` (event-driven)

**File:** `src/tasks/onboarding_video.py`
**Triggered by:** OAuth callback on first `InboxConnection` creation

Steps:
1. Guard: if `OnboardingVideo` already exists for `account_id`, return early
2. Create `VideoRender` — `programme="onboarding"`, `video_style="avatar"`, `aspect_ratio="16:9"`
3. Create `OnboardingVideo` — `recipient_name`, `recipient_company`, `video_render_id`
4. Run `OnboardingVideoScript` DSPy signature — inputs: name, company, referral_source
5. Set `render.script` to generated script
6. Submit to HeyGen via `heygen_mcp.render_video(script, avatar_id, voice_id, video_format="mp4", aspect_ratio="16:9")`
7. Set `render.heygen_job_id`, `render.status = "rendering"`, `render.render_submitted_at`
8. Commit

The generic `/api/v1/heygen/webhook` (already live from Plan 1) handles the HeyGen callback and sets `render.status = "render_complete"` automatically — no additional webhook code needed.

### Task 2: `deliver_onboarding_videos` (daily beat)

**File:** `src/tasks/onboarding_video.py`
**Schedule:** Daily 9:00am, queue: `"content"`
**Env var guard:** `ONBOARDING_VIDEO_ENABLED`

Steps:
1. Query `OnboardingVideo JOIN VideoRender` where `render.status = "render_complete"` and `onboarding_video.email_sent_at IS NULL`
2. For each row: call `send_onboarding_video_email(to_email, recipient_name, video_url)`
3. Set `onboarding_video.email_sent_at = now()`
4. Commit with try/except rollback

---

## Email

**New function:** `send_onboarding_video_email(to_email, recipient_name, video_url)` in `src/notifications/emails.py`

Subject: `[First name], your personalised InboxIQ walkthrough is ready`

Body: brief text introducing the video, a prominent CTA button ("Watch your walkthrough →") linking to `render.heygen_render_url` (opens in new tab), and a plain-text fallback URL.

---

## In-App Components

### Model change

`OnboardingVideo` gains one new nullable column:
- `banner_dismissed_at` (DateTime, timezone=True, nullable=True)

### Dashboard route

The dashboard route (`src/settings/routes.py` or equivalent) queries:
```python
OnboardingVideo.query.filter_by(account_id=current_account_id).first()
```
and passes the result to the dashboard template as `onboarding_video`. The template renders the banner and card only when:
- `onboarding_video` is not None
- `onboarding_video.email_sent_at` is not None (video is delivered)
- `onboarding_video.banner_dismissed_at` is None (not yet dismissed)

### Banner

A dismissible strip at the top of the dashboard. Shows:
- "Your personalised InboxIQ walkthrough is ready"
- "Watch now →" link (opens `render.heygen_render_url` in new tab)
- "×" dismiss button

### Dashboard card

A "Your personalised walkthrough" card in the dashboard body. Shows the recipient's name and a play-button link to the video URL. Disappears once dismissed.

### Dismiss endpoint

**New blueprint:** `src/api/v1/onboarding.py`

```
POST /api/v1/onboarding/dismiss-video-banner
Auth: @jwt_required()
```

Sets `OnboardingVideo.banner_dismissed_at = now()` for the current account. Returns `{"ok": true}`. Called by a small JS click handler on the dismiss button.

---

## File Structure

| File | Change |
|---|---|
| `src/tasks/onboarding_video.py` | New — `queue_onboarding_video`, `deliver_onboarding_videos` |
| `src/dspy/signatures.py` | Add `OnboardingVideoScript` signature + `build_onboarding_signatures()` |
| `src/notifications/emails.py` | Add `send_onboarding_video_email()` |
| `src/api/v1/onboarding.py` | New — dismiss banner endpoint |
| `src/app.py` | Register `onboarding_api_bp` |
| `src/models/campaigns.py` | Add `banner_dismissed_at` to `OnboardingVideo` |
| `src/celery_inboxiq.py` | Add `deliver_onboarding_videos` to beat schedule |
| Dashboard template | Add banner + card (conditional on `onboarding_video`) |
| Inbox OAuth callback | Queue `queue_onboarding_video` on first connection |

---

## Migration

After merging to main:
```bash
flask db migrate -m "add banner_dismissed_at to onboarding_videos"
flask db upgrade
```

---

## Environment Variables

| Variable | Purpose |
|---|---|
| `ONBOARDING_VIDEO_ENABLED` | Feature flag — gates the beat task |
| `HEYGEN_AVATAR_ID` | Already set (shared with YouTube) |
| `HEYGEN_VOICE_ID` | Already set (shared with YouTube) |

---

## What's Explicitly Out of Scope

- Multiple videos per account (one per account, guarded)
- Re-sending on re-connect (guard prevents duplicates)
- Video thumbnail generation (link only, no custom thumbnail)
- In-app video player / embedding (CDN link opens in new tab)
