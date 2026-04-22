# AI Meeting Scheduling — Marketing Section & KB Article

**Date:** 2026-04-22  
**Scope:** Two deliverables — a new landing page section on `index.html` selling the booking feature, and a KB help article teaching users how it works.

---

## Deliverable 1 — Landing Page Section (`src/templates/index.html`)

### Position
Insert immediately after the `id="how-it-works"` section ("What InboxIQ does automatically"), before the "More than an email assistant" section.

### Layout
Two-column section matching the existing "More than an email assistant" pattern:
- Background: `bg-slate-100/70` (light, alternates with white section above)
- Grid: `grid items-center gap-8 lg:grid-cols-2 lg:gap-12`
- Full-width border-bottom separator: `border-b border-slate-200`
- Custom class: `dm-section-light`

### Left Column — Copy

**Headline:**
> Stop the scheduling back-and-forth. Your AI already handled it.

**Sub-copy:**
> When InboxIQ detects a meeting request, it drops a personal booking link straight into the draft reply. Your contact picks a slot, a calendar event is created, and a confirmation lands in their inbox — all without touching your calendar.

**Three feature checkmarks** (matching existing `dm-card rounded-2xl border border-slate-200 bg-white p-5 shadow-sm` card style):
1. Detects meeting requests automatically
2. Booking link in every draft reply
3. Confirms to calendar — no back-and-forth

**CTA link** (`dm-accent text-indigo-600 underline underline-offset-4`):
> See how scheduling works → `/features#scheduling`

### Right Column — Video Placeholder

A `rounded-2xl border border-slate-200 bg-slate-900 shadow-sm aspect-video` container structured as a placeholder `<div>` with:
- Centred `▶` play icon in white (`text-white text-5xl`)
- Label below: *"See it in action"* (`text-slate-400 text-sm mt-3`)
- `data-video-src=""` attribute on the container so a YouTube/Vimeo `<iframe>` can be swapped in later with a single attribute change — no structural edit needed

### No JavaScript Required
The placeholder is pure HTML/CSS. When a video URL is ready, replace the `<div>` with an `<iframe>` using the same container classes.

---

## Deliverable 2 — KB Help Article

### File Path
`src/kb/articles/getting-started/ai-meeting-scheduling.md`

### Category
`getting-started` — the feature requires calendar setup before use, making it a natural onboarding topic.

### Article Structure

**Title:** `# AI meeting scheduling`

**Intro paragraph** — one sentence explaining what the feature does and why it exists.

**## How it works**  
AI detects meeting-request intent in an incoming email. A booking link is automatically inserted into the draft reply. The link is unique per email thread and expires after 7 days.

**## What your contact sees**  
The booking page shows available slots pulled live from your connected calendar. The contact selects a slot and confirms. No account or login required.

**## What happens after booking**  
- A calendar event is created on your Google or Outlook calendar with a Google Meet or Teams link included  
- A confirmation email is sent to the contact with the meeting time and join link  
- The ticket is updated to *Meeting scheduled* status  
- A note is added to the ticket with booking details

**## Setup checklist**  
Before booking links appear in draft replies, connect your calendar:
1. Go to **Settings → Integrations → Calendar**
2. Connect Google Calendar or Outlook Calendar
3. That's it — InboxIQ will detect meeting requests and add booking links automatically

**## Related articles**  
- Link to calendar integration setup article  
- Link to draft replies article  
- Link to triage and AI article

### Style
- ~280 words, matching existing KB article length
- Bold for all UI element names and navigation paths
- Numbered lists for steps, bullet lists for outcomes
- No frontmatter

---

## What Is Not Changing

- No existing sections on `index.html` are removed or modified
- No existing KB articles are changed
- The `/features` page already has the scheduling section from the prior spec — no changes needed there
- No backend changes — this is purely frontend HTML and a Markdown file
