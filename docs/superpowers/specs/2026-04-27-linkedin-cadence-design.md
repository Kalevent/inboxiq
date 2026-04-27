# LinkedIn Outreach Cadence — Design Spec

**Date:** 2026-04-27
**Status:** Approved
**Scope:** Phase 2 of the traffic & conversion plan — systematic LinkedIn outreach with agent-drafted messages, daily email digest, and a Marketing Ops queue UI

---

## Problem Statement

LinkedIn lead discovery is already running and surfacing qualified prospects, but outreach is ad hoc. There is no queue, no message tracking, and no consistency in follow-up. Phase 2 makes this systematic: the agent does all the thinking, the user does the sending on LinkedIn, and a daily email digest bridges the two.

---

## Design: Option A — Agent-first, Email Digest

The agent discovers prospects, drafts all three messages, selects the right blog post to share, and tracks timing. Each morning a digest email tells you exactly who to contact and what to say. A queue UI in Marketing Ops holds the full history. Status transitions are triggered by "Mark sent" actions — from email or the UI.

LinkedIn DMs are sent manually by the user. LinkedIn bans automated sending — this is non-negotiable.

---

## 1. Data Models

### 1A. `LinkedInProspect` — `src/models/campaigns.py`

New table: `linkedin_prospects`. Tracks a prospect from discovery through to qualified lead.

```text
id                  UUID string, PK
account_id          Integer, FK (scoped per account)
lead_id             String FK → leads.id (nullable — set when prospect qualifies)
name                String
company_name        String
job_title           String
industry            String
linkedin_url        String (unique per account)
source              String — "auto" | "manual"
status              Enum — see status states below
fit_score           Integer 0–10
connection_sent_at  DateTime
connected_at        DateTime (manually marked — triggers message 2 timer)
message_2_due_at    DateTime (set to connected_at + 3 days when connected_at is written)
message_2_sent_at   DateTime
message_3_due_at    DateTime (set to message_2_sent_at + 5 days when message_2_sent_at is written)
message_3_sent_at   DateTime
msg_1_draft         Text (agent-drafted connection request)
msg_2_draft         Text (agent-drafted value message)
msg_3_draft         Text (agent-drafted soft ask)
suggested_post_id   String FK → blog_posts.id (nullable)
notes               Text
created_at          DateTime
updated_at          DateTime
```

**Status states:**

```text
pending → connection_sent → connected → message_2_sent → message_3_sent → replied → qualified → disqualified
```

**New column on `Lead`:** `linkedin_url` (nullable String) — added to `src/models/leads.py` so the funnel can store LinkedIn URLs during discovery and the agent can match back to existing leads.

### 1B. `ICPConfig` — `src/models/marketing.py`

New table: `icp_configs`. One record per account. Defines who qualifies as a LinkedIn prospect. If no record exists, the discovery task uses defaults.

```text
id                  UUID string, PK
account_id          Integer, FK (unique — one per account)
titles              JSON — ["Founder", "Head of Support", "Operations Lead", "Customer Success Lead"]
industries          JSON — ["B2B SaaS", "Software"]
company_size_min    Integer — default 10
company_size_max    Integer — default 50
geographies         JSON — ["UK", "US", "Nigeria"]
created_at          DateTime
updated_at          DateTime
```

Editable from Marketing Ops → ICP Settings (`/marketing/icp`). Never hardcoded in task code.

---

## 2. Celery Tasks — `src/tasks/linkedin.py`

Three tasks, run in sequence each morning.

### Task 1: `linkedin.discover_prospects` — 7:00am daily

Loads `ICPConfig` for the account (falls back to defaults if none). Queries `Lead` records where:

- `source = "linkedin"` OR `first_attribution_source = "linkedin"`
- `fit_score >= 7`
- `linkedin_url` is set
- No `LinkedInProspect` already exists for that `linkedin_url` + `account_id`
- `outreach_unsubscribed_at` is null

Creates a `LinkedInProspect` record (status = `pending`) for each new match.

Manually-added prospects bypass this task — they enter at `pending` directly from the UI.

### Task 2: `linkedin.draft_messages` — 7:30am daily

For every `pending` prospect with no drafts:

1. Calls `MessageDrafterModule` (DSPy) — generates all 3 messages in one `ChainOfThought` call
2. Calls `BlogPostMatcherModule` (DSPy) — selects the best published blog post for message 2
3. Saves `msg_1_draft`, `msg_2_draft`, `msg_3_draft`, `suggested_post_id` to the record

### Task 3: `linkedin.send_digest` — 8:00am daily

Collects all prospects due for action today:

- Status `pending` — connection request ready
- Status `connected` and `message_2_due_at <= now`
- Status `message_2_sent` and `message_3_due_at <= now`
- Status `replied` — needs qualify/disqualify decision

Sends one digest email via `src/notifications/emails.py`. No prospects due = no email sent.

---

## 3. DSPy Scripts — `skills/linkedin_cadence/scripts/`

### `draft_messages.py` — `MessageDrafterModule`

**Signature inputs:** `prospect_name`, `job_title`, `company_name`, `industry`, `product_name`

**Signature outputs:**

- `msg_1` — connection request, ≤300 chars, no pitch, no product mention
- `msg_2` — value share, ≤500 chars, references the blog post, no ask
- `msg_3` — soft ask, ≤400 chars, one CTA: "would a 15-min call make sense?"

All three drafted in one `ChainOfThought` call — not three separate requests.

### `match_post.py` — `BlogPostMatcherModule`

**Signature inputs:** `prospect_industry`, `job_title`, `posts_json` (array of `{slug, title, primary_keyword}` for all published posts)

**Signature outputs:**

- `selected_slug` — slug of the best matching post
- `reason` — one sentence explaining the match (shown in the digest email)

No embeddings or vector search — post list is short enough to pass in context.

---

## 4. Email Digest

**Subject:** `LinkedIn Outreach — {n} actions ready ({Day DD Mon})`

One section per prospect, ordered by urgency (message 3 first, then message 2, then connection requests). Each section shows:

- Name, job title, company, LinkedIn URL
- Action label: "Send connection request" / "Send message 2 (connected X days ago)" / "Send message 3" / "Follow up — replied"
- For message 2: blog post title + reason it was chosen
- Full drafted message text (copy-paste ready)
- "Mark as sent" link — hits an authenticated endpoint that advances status and sets timestamp

No email sent on days with no due actions.

---

## 5. Queue UI — Marketing Ops

**Route:** `/marketing/linkedin`

### Top section — Today's Actions

Compact cards for prospects due today. Same content as the digest. "Mark sent" button per card.

### Bottom section — Full Queue

Table view:

| Column | Notes |
| --- | --- |
| Name + Company | Linked to LinkedIn URL |
| Job Title | |
| Status | Colour-coded badge |
| Fit Score | 0–10 |
| Days in stage | How long at current status |
| Next action | Date of next due action |
| Actions | View drafts, Mark sent, Mark connected, Add note, Disqualify |

Filter bar: status, source (auto/manual), industry.

"Add prospect manually" button — opens a form:

- LinkedIn URL (required, validated as linkedin.com URL)
- Name, Company, Job title, Industry (all required)
- Fit score (optional, 0–10)
- Notes (optional)

On submit: creates `LinkedInProspect` (source = `manual`, status = `pending`), triggers draft generation immediately via a short Celery task.

### ICP Settings — `/marketing/icp`

Simple edit form for `ICPConfig`. Fields: job titles (tag input), industries (tag input), company size min/max, geographies (tag input). Save updates the record; discovery task picks up changes on next run.

---

## 6. Skill — `skills/linkedin_cadence/skill.md`

### Scripts

| Script | Purpose |
| --- | --- |
| `scripts/draft_messages.py` | Drafts all 3 messages for a prospect in one DSPy call |
| `scripts/match_post.py` | Selects the best published blog post for message 2 |

### Cadence Rules

- **Message 1:** Connection request only — no pitch, no product mention, ≤300 chars
- **Message 2:** Value only — share the matched post, no ask, ≤500 chars. Never send before `connected_at` is set.
- **Message 3:** One soft ask — "would a 15-min call make sense?", ≤400 chars. Never send before message 2 is marked sent.
- **Disqualify** after 14 days with no response to message 3

### ICP

Defined in `ICPConfig` — never hardcoded. Edit via Marketing Ops → ICP Settings.

Defaults: Founder / Head of Support / Operations Lead / Customer Success Lead · B2B SaaS, Software · 10–50 employees · UK, US, Nigeria.

### Funnel Integration

| Prospect status | Lead funnel action |
| --- | --- |
| `replied` | Advance Lead to `consideration` |
| `qualified` | Advance Lead to `conversion`, flag for Hunter.io email |

---

## Success Metrics

| Metric | Target |
| --- | --- |
| Prospects entering queue per week | 5–10 |
| Connection acceptance rate | ≥ 30% |
| Message 2 reply rate | ≥ 10% |
| Qualified leads per month from LinkedIn | 3–5 |
| Time spent per day on outreach | ≤ 15 minutes |
