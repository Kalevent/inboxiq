# Traffic & Conversion Growth — Design Spec

**Date:** 2026-04-24  
**Status:** Approved  
**Scope:** Three-phase plan to drive qualified traffic and improve trial-to-paid conversion

---

## Problem Statement

InboxIQ has a strong product but near-zero external traffic (24 GA4 sessions in the last 28 days, 96% direct). The blog content pipeline runs but posts never go live. The landing page has no social proof. The LinkedIn lead gen system exists but is used ad hoc. Result: 516 funnel visits, 0 paid conversions.

The fix is not one thing — it is three channels working together, in sequence.

---

## Approach: Phased Integrated Pipeline

**Phase 1 — Fix the destination** (blog publishing + landing page credibility)  
**Phase 2 — Activate outreach** (systematic LinkedIn cadence)  
**Phase 3 — Amplify with paid** (targeted LinkedIn Ads)

Phase 3 does not start until Phase 1 is live. Paying for traffic before the destination converts is wasted spend.

---

## Phase 1: Fix Blog Publishing + Landing Page Credibility

### 1A — Blog Publishing Fix

**Root cause:** `publish_blog_post` gates on `rendered_html`, but `generate_blog_post` only populates `content_html`. Posts reach `status="ready"` but silently fail the publish check because `rendered_html` is never set.

**Fix:** In `src/content/tasks.py`, after writing `content_html`, render it to `rendered_html` immediately (markdown → HTML). No schema changes required.

**Pipeline flow once fixed:**
1. `content.generate_blog_post` runs → sets `content_html` + `rendered_html` → status = `ready`
2. `marketing.auto_publish_ready_posts` finds ready posts → calls `publish_blog_post`
3. `publish_blog_post` passes the gate → sets status = `published`, sets `published_at`
4. Post appears at `/blog/<slug>`
5. Blog newsletter and social distribution fire automatically (already wired)

**Quality gate:** Before marking a post `ready`, run a DSPy quality check (new lightweight signature) that scores the post for relevance and coherence. Posts below threshold stay in `draft` for manual review. This keeps auto-publish safe without manual overhead on every post.

**DSPy signature:** `BlogQualityCheck` — inputs: `title`, `content_html`, `target_audience`. Output: `quality_score` (0–10), `publish_decision` (ready/draft), `reason`. Threshold: score ≥ 7 → status = `ready`; score < 7 → status = `draft` for manual review.

**Expected output:** 2–4 posts per week published automatically, indexed by Google within days.

### 1B — Landing Page Credibility

Three targeted additions to `src/templates/index.html`. All new sections appended as self-contained blocks. Tailwind rebuilt after (`cd src && npm run build:css`).

**1. Social proof strip** — Directly below the hero: 2–3 short quotes from beta users or early customers. If quotes are not yet available, a "Built for teams at [Industry] and [Industry]" strip with industry labels suffices as an interim signal.

**2. Pricing teaser** — A minimal pricing callout on the homepage showing the starting price and what the trial includes. Visitors currently have no idea what commitment they are considering. Surfacing this removes anxiety and increases CTA clicks.

**3. Quantified value proposition** — Supplement the current headline with a specific outcome metric. Example: *"Handle 3× the support volume without adding headcount — teams see their first AI draft in under 20 minutes."* Numbers convert better than concepts.

**Constraint:** Never edit Tailwind class lines in index.html directly — append new sections only. Rebuild Tailwind after every change.

---

## Phase 2: Systematic LinkedIn Outreach Cadence

### What gets built

**ICP targeting criteria (hardcoded):**
- Job titles: Founder, Head of Support, Operations Lead, Customer Success Lead
- Company size: 10–50 employees
- Industry: B2B SaaS, Software
- Geography: UK and US (primary), Nigeria (secondary)

**Outreach queue (Marketing Ops UI):**
- Table of LinkedIn prospects with fields: name, company, LinkedIn URL, status
- Status states: `pending → connected → messaged → replied → qualified`
- Prospects enter via existing LinkedIn lead gen discovery
- Queue surfaced in Marketing Ops so it can be worked in 15 minutes/day

**Three-message sequence (manual send, tracked in app):**
- Message 1 (connection request): one sentence on the shared context, no pitch
- Message 2 (3 days after connect): share a relevant blog post or insight, no ask
- Message 3 (5 days after message 2): soft ask — "would a 15-minute call make sense?"

**Funnel integration:**
- Prospects who reach `replied` or `qualified` status automatically advance in the Lead funnel (discovery → consideration)
- Hunter.io email outreach (25/month) is reserved exclusively for `replied`-status prospects — the warmest leads only

**Key constraint:** LinkedIn DMs are sent manually by the user. The app tracks state and surfaces who to contact today — it does not automate the sends. LinkedIn bans automation of direct messages.

---

## Phase 3: Targeted LinkedIn Ads

**Prerequisite:** Phase 1 must be live AND the blog must have at least 4–6 published posts before ads run.

### What gets built

**1. LinkedIn Insight Tag** — Added to `src/templates/index.html` (and blog templates). Builds a retargeting audience from all visitors who do not sign up. Retargeting is the most cost-efficient spend because it targets people who already showed intent.

**2. ICP-targeted campaign:**
- Targeting: job title (Founder, Head of Support, Operations Lead), company size (10–50), industry (SaaS/Software), geography (UK + US)
- Budget: £300–500/month to start
- One campaign, narrow audience — not spray-and-pray

**3. Two-step ad strategy:**
- Step 1: Ad links to a specific blog post (warm the audience with useful content)
- Step 2: Retarget blog readers with a trial CTA ad
- Cold "Start free trial" ads perform poorly — content-first converts better

**4. Measurement:**
- LinkedIn ad clicks tracked into the existing funnel (visits → discovery stage)
- Review performance at 3–4 weeks: kill underperforming ad/post combinations, double down on what works
- Success signal: cost per trial start below £50

---

## Success Metrics

| Phase | Signal | Target |
|-------|--------|--------|
| 1A (blog) | Posts published per week | 2–4 |
| 1A (blog) | Organic search sessions (GA4) | 50+/month within 60 days |
| 1B (landing page) | Visits → signup rate | >1% (from current ~0%) |
| 2 (LinkedIn) | Prospects messaged per week | 10–15 |
| 2 (LinkedIn) | Reply rate | >15% |
| 3 (ads) | Cost per trial start | <£50 |
| 3 (ads) | Trial → paid conversion | >10% |

---

## What This Does NOT Include

- Mass untargeted email outreach
- Paid ads before Phase 1 is live
- Changes to the core trial/billing flow (separate initiative)
- Healthcare-specific features (blocked on FHIR integration)
