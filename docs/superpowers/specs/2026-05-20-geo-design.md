# GEO (Generative Engine Optimisation) Design

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Get InboxIQ surfaced by name and kalevent.com cited as a source when people ask ChatGPT, Gemini, Claude, and Perplexity about AI inbox tools, email triage software, and alternatives to Zendesk/Freshdesk/Intercom/Front/Help Scout/Groove.

**Approach:** Three sequential phases — (1) on-site technical structured data + comparison pages shipped together, (2) blog enrichment via DSPy, (3) off-site directory submissions in priority order.

**Tech Stack:** Flask + Jinja2, SQLAlchemy, DSPy, Celery, Tailwind CSS, JSON-LD (schema.org)

---

## Phase 1: Technical foundation + comparison pages

### Structured data (JSON-LD)

Every schema block is injected via `<script type="application/ld+json">` in the relevant template's `<head>`. No external library needed — plain JSON in Jinja2 blocks.

#### Homepage (`src/templates/index.html`)
- `SoftwareApplication` — name, description, applicationCategory ("BusinessApplication"), operatingSystem ("Web, Chrome Extension"), offers (Starter £9, Pro £29, Business £49), aggregateRating (seeded from G2/Capterra scores once available)
- `FAQPage` — 6 Q&A pairs covering: what InboxIQ does, how it differs from helpdesks, Gmail/Outlook compatibility, pricing model (inboxes not seats), security/data handling, free trial
- `Organization` — upgrade existing block in `marketing/base.html` to add `sameAs` array (G2, Capterra, Product Hunt, LinkedIn, Twitter/X URLs)

#### Pricing page (`src/templates/marketing/pricing.html`)
- `FAQPage` — 5 Q&A pairs: what counts as an inbox, overage pricing, cancellation, trial length, enterprise pricing
- `Offer` per plan inline in `SoftwareApplication` (linked from homepage schema)

#### Features page (`src/templates/marketing/features.html`)
- `FAQPage` — 5 Q&A pairs covering core features
- `HowTo` — "How to set up AI email triage with InboxIQ" (3-step: connect inbox, configure rules, review AI drafts)

#### Use case pages (healthcare, HR, finance, claims, ecommerce, sales, support)
- `HowTo` — vertical-specific setup steps
- `FAQPage` — 4 Q&A pairs per page, vertical-specific (e.g. healthcare: HIPAA, referral workflows)

#### Blog post template (`src/templates/blog_post.html`)
- `Article` — headline, description, datePublished, dateModified, author (Organization), image (hero_image_url)
- `FAQPage` — generated from `## Frequently Asked Questions` section in post markdown
- `speakable` — marks intro paragraph and FAQ section

#### Comparison pages (`src/templates/marketing/comparison.html` — new shared template)
- `WebPage` — name, description, url
- `FAQPage` — 5 Q&A pairs per comparison

---

### Comparison pages

**Route:** `GET /vs/<competitor>` — single Flask route in `src/marketing/routes.py`, renders `marketing/comparison.html` with competitor-specific context dict.

**Six competitors:**

| Slug | Competitor | Buyer journey |
|---|---|---|
| `zendesk` | Zendesk | Replacing traditional helpdesk, cost-driven |
| `freshdesk` | Freshdesk | Replacing traditional helpdesk, SMB-focused |
| `intercom` | Intercom | Replacing chat-first support tool |
| `front` | Front | Inbox-native, team email workflow |
| `helpscout` | Help Scout | Inbox-native, simplicity-focused |
| `groove` | Groove | Inbox-native, small team |

**Each page structure:**
1. Hero — "InboxIQ vs [Competitor]: which is right for your support team?"
2. One-line verdict — clear, opinionated, honest
3. Comparison table — 8 dimensions: works inside Gmail/Outlook, AI triage, pricing model (seats vs inboxes), setup time, helpdesk replacement, meeting scheduling, free trial, self-hosted option
4. Where [competitor] wins — 2–3 honest points (builds trust with AI models and humans)
5. Where InboxIQ wins — 4–5 points tied to InboxIQ's core differentiators
6. FAQ section — 5 Q&A pairs with `FAQPage` schema
7. CTA — "Start your free 7-day trial · No credit card required"

**GEO copy rule:** Every comparison page description and FAQ answers must include the exact phrases:
- *"AI email triage"*
- *"works inside Gmail and Outlook"*
- *"no new dashboard"*

These are the query fragments AI models match when answering inbox automation queries.

**Competitor data:** Stored as a Python dict in `src/marketing/competitors.py` — one entry per competitor with all table values, FAQ content, and honest pros/cons. Keeps the template logic clean and content easy to update.

---

## Phase 2: Blog post enrichment

### DSPy pipeline change

Add a mandatory `## Frequently Asked Questions` section to the `ContentWriterModule` prompt in `src/dspy/content.py`. Every new post must end with 4–5 Q&A pairs directly relevant to the post topic. This is the primary surface AI models pull from verbatim.

### Blog post template additions

`src/templates/blog_post.html` gets:
- `Article` JSON-LD block pulling from `post.title`, `post.meta_description`, `post.created_at`, `post.updated_at`, `post.hero_image_url`
- `FAQPage` JSON-LD block — parsed from the `## Frequently Asked Questions` section in `post.markdown`
- `speakable` property on `Article` — marks intro paragraph (first `<p>`) and FAQ section

### One-time enrichment task

New Celery task: `enrich_blog_posts_for_geo` in `src/content/tasks.py`

- Queries all `BlogPost` records with `status="published"` and `markdown` not containing `## Frequently Asked Questions`
- For each: calls a new DSPy signature `BlogFAQGenerator` (4–5 Q&A pairs from post content)
- Appends the FAQ section to `post.markdown`, regenerates `post.content_html` via `markdown` + `sanitize_html`
- Updates `post.updated_at`, commits
- Runs once via `flask shell` or a one-off Celery beat schedule — not a recurring task

Quality gate: skip posts with `dspy_quality_score < 0.5` to avoid enriching low-quality drafts.

---

## Phase 3: Off-site directory submissions

All submissions are manual — only Kofi can submit. This phase is a sequenced checklist, not a code task.

### Priority 1 — highest AI indexing weight

| Directory | Why | Submission notes |
|---|---|---|
| **Product Hunt** | Heavily cited by ChatGPT/Perplexity for "best X tool" queries. Launch generates backlinks and social signal. | Create maker account. Prepare: 60s demo GIF, tagline (≤60 chars), 5 product screenshots, first comment (founder story). Launch Tuesday–Thursday for max upvotes. |
| **AlternativeTo** | AI models cite this directly for "alternative to Zendesk/Freshdesk" queries — exact comparison page keywords. | Free self-submission at alternativeto.net. List all 6 competitors from Phase 1 as alternatives. |
| **Futurepedia** | Largest AI tool directory, explicitly indexed by ChatGPT and Claude. | Free submission form. Category: Email + Productivity + AI Assistant. Include pricing tier. |
| **There's An AI For That (TAAFT)** | ~1M monthly visitors, heavily scraped by AI training pipelines. | Free submission. Category: Email Automation / Customer Support. |

### Priority 2 — credibility and review signals

| Directory | Why | Submission notes |
|---|---|---|
| **GetApp** | Sister site to Capterra (Gartner network) — free extension of existing listing. | Login to Capterra account — GetApp listing auto-created, needs activation and category confirmation. |
| **SaaSHub** | Aggregator cited for pricing comparisons. | Free self-submission at saashub.com. |
| **Trustpilot** | AI models cite Trustpilot ratings when answering credibility questions. | Free business account. Invite existing users to review immediately after signup. |
| **G2 Stack** | Enriches existing G2 listing with integration data — increases appearance in "tools that integrate with Gmail" queries. | From existing G2 profile: add Gmail, Outlook, Google Calendar as integrations. |

### Priority 3 — longer tail

| Directory | Notes |
|---|---|
| **Slant.co** | Community comparison site, cited for niche tool queries |
| **SourceForge** | Older DA, still indexed for SMB searches |
| **Clutch.co** | B2B services directory, strong for enterprise/agency searches |
| **Reddit** | Post in r/SaaS, r/entrepreneur, r/automation — share Product Hunt launch link, genuine post not spam |

### Copy rule for all listings

Every directory description must include:
- *"AI email triage"*
- *"works inside Gmail and Outlook"*
- *"no new dashboard"*

These exact phrases must appear in every listing so AI models consistently associate InboxIQ with these queries across multiple high-authority sources.

---

## Files created / modified

**Phase 1:**
- Create: `src/templates/marketing/comparison.html`
- Create: `src/marketing/competitors.py`
- Modify: `src/marketing/routes.py` — add `/vs/<competitor>` route
- Modify: `src/templates/index.html` — add `SoftwareApplication` + `FAQPage` JSON-LD
- Modify: `src/templates/marketing/base.html` — upgrade `Organization` schema
- Modify: `src/templates/marketing/pricing.html` — add `FAQPage` JSON-LD
- Modify: `src/templates/marketing/features.html` — add `FAQPage` + `HowTo` JSON-LD
- Modify: `src/templates/marketing/use_case_*.html` (7 files) — add `HowTo` + `FAQPage` JSON-LD
- Modify: `src/templates/blog_post.html` — add `Article` + `FAQPage` + `speakable` JSON-LD

**Phase 2:**
- Modify: `src/dspy/content.py` — add FAQ requirement to `ContentWriterModule` prompt
- Modify: `src/templates/blog_post.html` — FAQ schema block (same edit as Phase 1)
- Create: `src/dspy/signatures.py` — add `BlogFAQGenerator` signature
- Modify: `src/content/tasks.py` — add `enrich_blog_posts_for_geo` task

**Phase 3:**
- No code — manual submission checklist only
