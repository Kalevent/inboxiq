# AI Meeting Scheduling — Marketing Section & KB Article Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a two-column landing page section selling the AI meeting scheduling feature to `index.html`, and create a KB help article at `kalevent.com/kb` explaining how it works to users.

**Architecture:** Two independent content changes — one HTML insertion into the existing landing page, one new Markdown file in the KB articles directory. No backend changes, no new routes, no migrations. The landing page edit inserts a new section between existing sections using the comment line as the anchor (safe pattern for this codebase). The KB article follows the existing Markdown conventions exactly.

**Tech Stack:** Jinja2 HTML templates, Tailwind CSS (pre-compiled), Markdown (no frontmatter)

---

## ⚠️ Critical constraint — `index.html` editing rule

**Never use the Edit tool on `index.html` lines that contain Tailwind CSS classes.** This introduces trailing whitespace that silently breaks CSS rendering. The only safe pattern is:

- Use the Edit tool with an `old_string` that is **a comment line only** (HTML comments contain no Tailwind classes)
- The new section HTML you insert is new content — that is fine. The risk is modifying *existing* lines with classes on them.
- If styling breaks after the edit: `git checkout HEAD -- src/templates/index.html` is the only reliable fix.

---

## Files

| Action | Path | Purpose |
|--------|------|---------|
| Modify | `src/templates/index.html` | Insert scheduling section after `id="how-it-works"` |
| Create | `src/kb/articles/getting-started/ai-meeting-scheduling.md` | KB help article for the booking feature |

---

## Task 1 — KB Help Article

**Files:**
- Create: `src/kb/articles/getting-started/ai-meeting-scheduling.md`

- [ ] **Step 1: Create the article file**

Create `src/kb/articles/getting-started/ai-meeting-scheduling.md` with this exact content:

```markdown
# AI meeting scheduling

InboxIQ detects meeting requests in incoming emails and adds a personal booking link to the draft reply — so your contact can book a time without any back-and-forth.

## How it works

When an incoming email contains a meeting request, InboxIQ's AI pipeline detects the intent and automatically inserts a booking link into the draft reply it generates. The link is unique to that email thread and expires after 7 days.

## What your contact sees

Clicking the booking link opens a public page — no account or login required. The page shows your available time slots pulled live from your connected calendar. Your contact selects a slot and confirms with their name and email address.

## What happens after booking

- A calendar event is created on your Google or Outlook calendar, with a Google Meet or Microsoft Teams link included
- A confirmation email is sent to your contact with the meeting time and a join link
- The ticket in InboxIQ is updated to **Meeting scheduled** status
- A note is added to the ticket recording the booking details

## Setup

Before booking links appear in draft replies, connect your calendar:

1. Go to **Settings → Integrations → Calendar**
2. Click **Connect Google Calendar** or **Connect Outlook Calendar**
3. Complete the authorisation flow
4. Booking links will now appear automatically in draft replies whenever InboxIQ detects a meeting request

## Related articles

- [Connect your Gmail inbox](/kb/getting-started/connect-gmail)
- [Connect your Outlook inbox](/kb/getting-started/connect-outlook)
- [How InboxIQ works](/kb/getting-started/how-inboxiq-works)
```

- [ ] **Step 2: Verify the article is discoverable by the KB route**

The KB routes file at `src/kb/routes.py` serves articles from the `src/kb/articles/` directory by mapping URL path to file path. Confirm the file is in the correct location:

```bash
ls src/kb/articles/getting-started/
```

Expected output includes `ai-meeting-scheduling.md`.

- [ ] **Step 3: Verify the article renders**

Start the dev server if not already running, then open:

```
http://localhost:5000/kb/getting-started/ai-meeting-scheduling
```

Expected: Article renders with correct heading "AI meeting scheduling", all sections visible, related article links clickable.

- [ ] **Step 4: Commit**

```bash
git add src/kb/articles/getting-started/ai-meeting-scheduling.md
git commit -m "feat: add KB article for AI meeting scheduling feature"
```

---

## Task 2 — Landing Page Section

**Files:**
- Modify: `src/templates/index.html` (insert between line 457 `</section>` and line 459 `<!-- ── More than an email assistant`)

- [ ] **Step 1: Confirm the insertion anchor**

Read lines 455–462 of `src/templates/index.html` and verify the exact text of the comment line you will use as the Edit anchor:

```bash
sed -n '455,462p' src/templates/index.html
```

Expected output includes this exact line (the anchor for the Edit):
```
      <!-- ── More than an email assistant ───────────────────────────────── -->
```

- [ ] **Step 2: Insert the new section**

Use the Edit tool on `src/templates/index.html`. The `old_string` must be **only the comment line** (no Tailwind classes — safe per codebase constraint). Replace it with the new section followed by the original comment.

`old_string`:
```
      <!-- ── More than an email assistant ───────────────────────────────── -->
```

`new_string`:
```
      <!-- ── AI meeting scheduling ─────────────────────────────────────── -->
      <section class="dm-section-light border-b border-slate-200 bg-slate-100/70">
        <div class="mx-auto max-w-7xl px-6 py-16 lg:px-8 lg:py-20">
          <div class="grid items-center gap-8 lg:grid-cols-2 lg:gap-12">
            <div>
              <h2 class="dm-heading text-3xl font-bold tracking-tight text-slate-950 sm:text-4xl">Stop the scheduling back-and-forth. Your AI already handled it.</h2>
              <p class="dm-body mt-4 text-lg leading-8 text-slate-600">When InboxIQ detects a meeting request, it drops a personal booking link straight into the draft reply. Your contact picks a slot, a calendar event is created, and a confirmation lands in their inbox — all without touching your calendar.</p>
              <div class="mt-6 grid gap-3">
                <div class="dm-card rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
                  <span class="mr-2 text-emerald-600">✓</span>
                  <span class="dm-heading font-medium text-slate-900">Detects meeting requests automatically</span>
                </div>
                <div class="dm-card rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
                  <span class="mr-2 text-emerald-600">✓</span>
                  <span class="dm-heading font-medium text-slate-900">Booking link in every draft reply</span>
                </div>
                <div class="dm-card rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
                  <span class="mr-2 text-emerald-600">✓</span>
                  <span class="dm-heading font-medium text-slate-900">Confirms to calendar — no back-and-forth</span>
                </div>
              </div>
              <div class="mt-6 text-sm">
                <a href="/features#scheduling" class="dm-accent text-indigo-600 underline underline-offset-4 hover:text-indigo-700">See how scheduling works →</a>
              </div>
            </div>
            <div class="dm-card flex flex-col items-center justify-center rounded-2xl border border-slate-200 bg-slate-900 p-8 shadow-sm" style="aspect-ratio:16/9" data-video-src="">
              <div class="text-5xl text-white">▶</div>
              <p class="dm-body mt-3 text-sm text-slate-400">See it in action</p>
            </div>
          </div>
        </div>
      </section>

      <!-- ── More than an email assistant ───────────────────────────────── -->
```

- [ ] **Step 3: Verify the edit was applied cleanly**

```bash
grep -n "scheduling back-and-forth\|More than an email\|how-it-works" src/templates/index.html
```

Expected output (three lines, in this order):
1. Line with `id="how-it-works"` 
2. Line with `Stop the scheduling back-and-forth`
3. Line with `More than an email assistant`

- [ ] **Step 4: Check for trailing whitespace on modified lines**

```bash
grep -Pn " $" src/templates/index.html | head -5
```

Expected: no output. If any lines appear, the Edit tool introduced trailing whitespace — run `git checkout HEAD -- src/templates/index.html` and redo the edit manually using the Write tool with the full file content.

- [ ] **Step 5: Visual verification**

Open `http://localhost:5000` in a browser and scroll past the "What InboxIQ does automatically" section. Verify:

- New section appears with headline "Stop the scheduling back-and-forth. Your AI already handled it."
- Three green checkmark cards visible on the left
- Dark video placeholder with ▶ and "See it in action" on the right
- "See how scheduling works →" link present
- Section does not disturb the sections above or below it
- Check dark mode toggle — section background should switch to dark correctly

- [ ] **Step 6: Commit**

```bash
git add src/templates/index.html
git commit -m "feat: add AI meeting scheduling section to landing page"
```

---

## Swapping in the Video Later

When a demo video is ready, replace the placeholder `<div>` in `index.html` with an `<iframe>`. The container classes stay identical:

```html
<!-- Replace this placeholder div: -->
<div class="dm-card flex flex-col items-center justify-center rounded-2xl border border-slate-200 bg-slate-900 p-8 shadow-sm" style="aspect-ratio:16/9" data-video-src="">
  <div class="text-5xl text-white">▶</div>
  <p class="dm-body mt-3 text-sm text-slate-400">See it in action</p>
</div>

<!-- With this iframe (YouTube example): -->
<iframe class="dm-card rounded-2xl border border-slate-200 shadow-sm w-full" style="aspect-ratio:16/9" src="https://www.youtube.com/embed/VIDEO_ID" title="AI meeting scheduling demo" frameborder="0" allowfullscreen></iframe>
```
