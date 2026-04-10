# InboxIQ Growth PRD

> Status: Draft — April 2026
> Author: Kofi
> This is a living document. Update it when decisions are made or assumptions are invalidated.

---

## 1. Why This Document Exists

InboxIQ has a working product. The pipeline runs. The ICP is sharpened. The value proposition is clear. The question is no longer "does this work?" — it is "how do we grow?"

Growth is not a marketing problem. It is a product problem. Users do not convert because the product does not deliver its promise fast enough, reliably enough, or visibly enough. This document is the plan to fix that — systematically, in the right order.

**The growth frame for everything in this document:**

Every feature, every architectural decision, every piece of work is evaluated against one question: *does this help more Olivers get to the moment they say "this is exactly what I needed"?*

---

## 2. The Growth Model

InboxIQ grows through a five-stage loop. Each stage has a specific drop-off risk. Growth work means reducing drop-off at the earliest stages first.

```text
Acquisition → Activation → Retention → Expansion → Revenue
```

### Acquisition

Oliver finds InboxIQ via Product Hunt, a LinkedIn post, Hacker News, or a founder community. He reads the homepage. The message either speaks to his exact pain or it does not. He signs up or he does not.

**Current state (April 2026):** Funnel shows 390 in VISITS, 12 in TRIAL, 2 in CONSIDERATION, 1 in DISCOVERY. 11 total accounts. 2 new sign-ups in the last 7 days. Visits-to-trial conversion is happening but the rate is unmeasured — we do not know what percentage of visitors are starting trials or where the rest are dropping off.

**The barrier:** Oliver cannot tell from the homepage whether InboxIQ will work inside *his* Gmail, with *his* kind of emails, without switching tools. The product promise is abstract until he sees it working.

### Activation

Oliver signs up, connects his Gmail, and — within his first session — sees an AI label applied and a draft reply appear in his own Gmail thread, for a real email from his own inbox.

That moment is the product. Everything before it is onboarding cost. Everything after it is retention.

**Current state:** Trial is 7 days. Inbox connect rate in trial is unknown (not instrumented). Time to first draft is unknown.

**The barrier:** The path from signup to first draft in Gmail has too many steps with no visible progress. Oliver does not know if the system is working until it works.

### Retention

Oliver comes back after the first week because InboxIQ is doing useful work for him every day — drafts waiting in his threads, labels correctly applied, sender patterns learned — without him having to open InboxIQ to get that value.

**Current state:** Draft acceptance rate, return rate, and weekly active sessions are not tracked.

**The barrier:** If activation fails (no first accepted draft), retention never starts. Retention also breaks if the draft quality degrades — Oliver deletes more drafts than he accepts.

### Expansion

Oliver adds a second inbox — the support@ alias, or a team member's Gmail via invite link. Each additional inbox is an expansion event: it increases the value InboxIQ delivers and increases the revenue per account.

**Current state:** Multi-inbox and invite flow are built. Whether customers are using them is unknown.

**The barrier:** Oliver does not know multi-inbox is available or how to use it until he is actively looking in settings. There is no in-product nudge toward expansion at the right moment.

### Revenue

Oliver converts from trial to paid. He upgrades when he needs more inboxes or advanced automation.

**Current state:** 7-day trial. Billing infra exists. Trial-to-paid conversion rate is unknown.

**The barrier:** The upgrade prompt is not tied to a moment of demonstrated value. Oliver is asked to pay before the product has proved itself.

---

## 3. North Star Metric

> **Number of accounts with at least one accepted draft reply per week.**

This metric is not vanity. It measures:

- That Oliver connected an inbox (activation)
- That the AI classified an email correctly (triage working)
- That the draft was good enough to use (quality working)
- That Oliver came back this week (retention)
- That InboxIQ is doing real work for real customers (revenue justified)

Every other metric in this document is either a leading indicator of this number or a lagging indicator of its health.

---

## 4. What Is Working

Knowing what to protect is as important as knowing what to fix.

| What works | Evidence |
|---|---|
| Core triage pipeline | DSPy `DecisionProgram` running in production — category, priority, draft |
| Gmail label writeback | Labels appearing in user inboxes post-triage |
| Sender learning | `SenderProfile` routing — high-confidence senders bypass DSPy |
| Knowledge base integration | KB-grounded drafts from file upload and URL sources |
| Multi-inbox + invite | Built and deployed — Oliver can connect multiple inboxes and invite others |
| Calendar OAuth | Google Calendar and Outlook Calendar connected |
| Trial infrastructure | 7-day trial, billing profiles created on signup |
| Blog / SEO pipeline | Published posts indexed, content agent generating new posts |

---

## 5. What Blocks Growth (By Stage)

### Blocking Acquisition

**B-ACQ-1 — The homepage does not show the product**
Oliver cannot see what InboxIQ looks like inside Gmail from the marketing page. He reads features, not proof. The real selling event — a label applied and draft in Gmail — is never shown.

**B-ACQ-2 — No referral or word-of-mouth loop**
There is no mechanism for Oliver to share InboxIQ with another founder in a way that benefits him. Expansion (adding inboxes) is individual. Growth from existing users is not structured.

**B-ACQ-3 — Funnel is not instrumented**
The path from homepage visit → signup → inbox connect is not measured. We do not know where Olivers are dropping off, so we cannot fix it.

---

### Blocking Activation

**B-ACT-1 — No visible onboarding progress**
After signup, Oliver does not know how many steps remain before InboxIQ starts working. There is no progress indicator. The system processing emails in the background is invisible until the first label appears.

**B-ACT-2 — Time to first draft is unknown and likely too long**
If Oliver connects his inbox and nothing visible happens in his Gmail within 10 minutes, he assumes it is broken. The poll cycle, triage, and writeback must happen within a visible window during the first session.

**B-ACT-3 — No fallback if inbox has no recent email**
If Oliver signs up on a Saturday and his inbox had no activity for 24 hours, the first poll returns nothing and he sees no proof that InboxIQ works. There is no demo email injection or simulated first run.

**B-ACT-4 — KB setup is optional but draft quality depends on it**
Oliver can skip KB setup and still see drafts — but those drafts will be lower quality, and he will delete them. The connection between KB setup and draft quality is not explained during onboarding.

---

### Blocking Retention

**B-RET-1 — Draft quality degrades on unknown KB topics**
When a customer emails about something not covered in the KB, the draft is generic. Oliver deletes it. If this happens often enough, he stops trusting the drafts entirely. There is no signal to Oliver that the KB has a gap — and no dashboard nudge to fill it.

**B-RET-2 — No weekly value summary**
Oliver never gets a message saying "this week, InboxIQ processed 47 emails, drafted 31 replies, and saved you an estimated 3.4 hours." He forgets the product is working because the value is invisible.

**B-RET-3 — The dashboard is underused**
The dashboard shows topic trends, accuracy metrics, and hours saved — but Oliver is not returning to it. It is not surfacing anything that prompts action. It is a reporting screen, not a decision screen.

---

### Blocking Expansion

**B-EXP-1 — Multi-inbox is hidden**
Oliver does not know he can connect a support@ alias or invite a team member until he navigates to Settings → Inboxes. There is no in-product moment that surfaces this when the timing is right (e.g. after his first 10 emails processed).

**B-EXP-2 — Automation Studio is not self-discoverable**
Automation Studio is a powerful retention and expansion driver — it makes InboxIQ indispensable. But Oliver must navigate there deliberately. There is no pathway from "I just saw a spike in billing emails" to "let me automate that" without knowing where Automation Studio is.

---

### Blocking Revenue

**B-REV-1 — Trial conversion is not tied to a value moment**
The upgrade prompt appears at trial expiry, not at the moment of demonstrated value. If Oliver has not had an accepted draft in his first 7 days, the upgrade ask is premature. If he has had 20, it is too late — he is already sold.

**B-REV-2 — Pricing is not anchored to the value metric**
InboxIQ saves Oliver time and defers a £35K hire. The pricing page does not make this comparison vivid and specific. "£99/month" next to a feature list is the weakest possible framing.

---

## 6. The Architecture Contract

Every requirement in the next section is built on this model. Understanding it determines what is cheap to add, what is expensive, and what would break the product if done wrong.

> **Agents orchestrate, skills guide reasoning, DSPy structures prompts, and MCP servers execute capabilities.**

| Layer | Responsibility | Growth implication |
| --- | --- | --- |
| **Agents** | Orchestrate — know the sequence, not the domain | Safe to add new capabilities without touching core logic |
| **Skills** | Guide reasoning — encode what "good" looks like per domain | Draft quality and accuracy improve without retraining models |
| **DSPy** | Structure prompts — typed, optimizable, traceable LLM calls | Every accepted draft and correction compounds into better outputs |
| **MCP servers** | Execute capabilities — typed tools for external APIs | New integrations (CRM, calendar, Slack) are additive, not invasive |

**The constraint this creates:** No requirement is allowed to bypass this model. A feature that calls the Gmail API directly from a Flask route — instead of through an MCP tool — is a violation regardless of how fast it ships. Short-term speed is paid back in long-term brittleness.

**The freedom this creates:** Any new capability that fits the model — a new MCP tool, a new skill, a new agent — can be added without touching existing behaviour. That is what makes growth safe to ship quickly.

---

## 7. Growth Requirements

Requirements are ordered by growth stage impact. Each has a clear definition of done and the metric it moves.

---

### Acquisition Requirements

> **Architecture:** These are product and UX changes. No new architectural layer is required — they operate above the pipeline.

**ACQ-1 — Homepage shows the product in Gmail**
The hero section must include a screenshot or short animation of InboxIQ labels appearing in a real Gmail thread, with a draft already in the reply area. Text: "Drafts appear in your Gmail. You review, edit, send." No abstract illustrations.

**ACQ-2 — Trial landing page with a specific promise**
A standalone trial page: "Connect your Gmail. In 20 minutes, InboxIQ will have classified your last 50 emails and drafted replies for the repetitive ones. No credit card." This is the specific promise. It is either true or we fix the product until it is.

**ACQ-3 — Funnel instrumentation from first visit**
Track: page visit → signup started → signup completed → inbox connected → first triage event → first draft → first accepted draft. This is the acquisition-to-activation funnel. Every stage must be visible in a dashboard.

**Metric moved:** Visit → signup conversion rate

---

### Activation Requirements

> **Architecture:** ACQ-5 requires the inbox connection event to immediately trigger the Triage Agent pipeline — not wait for the next Celery beat. ACQ-7 requires the Enrichment Agent to be wired to the `kb_search` MCP tool and report grounding coverage.

**ACQ-4 — Onboarding checklist with visible progress**
After signup, Oliver sees a 3-step checklist: (1) Connect inbox ✓ (2) First email processed ◌ (3) First draft ready ◌. Each step checks off automatically as the event fires. Oliver knows InboxIQ is working before he opens Gmail.

**ACQ-5 — First poll within 5 minutes of inbox connect**
The initial poll for a newly connected inbox must run immediately on connection — not wait for the next Celery beat cycle. Oliver should see labels in Gmail within 5 minutes of completing OAuth.

**ACQ-6 — Demo mode if no recent inbox email**
If the first poll returns no emails from the last 48 hours, inject a set of realistic demo emails that get triaged and drafted — clearly marked as demo. Oliver sees the product working even with an empty inbox. When his first real email arrives, the demo labels disappear.

**ACQ-7 — KB gap explained during onboarding**
After the first triage run, show Oliver how many of the drafted emails were grounded in his KB vs. how many used general knowledge. "3 of 12 drafts were grounded in your KB. Connect your knowledge base to improve draft quality for the other 9." This makes the KB setup feel worth doing.

**Metric moved:** Inbox connect rate, time to first accepted draft

---

### Retention Requirements

> **Architecture:** RET-1 and RET-2 read from existing pipeline data — no new layer required. RET-2 specifically requires the `draft_reply_skill` (Phase 2) to record KB grounding per draft so gaps can be detected. RET-3 requires a query against `AutomationRuleExecution` counts — no new layer.

**RET-1 — Weekly digest email**
Every Monday morning, Oliver receives: emails processed this week, drafts generated, drafts accepted, estimated hours saved, and one insight ("Your top topic this week was billing — 14 emails"). No link to the dashboard required to get value from this email.

**RET-2 — KB gap alert**
When the AI generates a draft with low KB coverage (no grounding found), record it. When the same topic appears 3+ times with no KB grounding, send Oliver a notification: "We drafted 3 replies about [topic] this week without KB grounding. These drafts may be lower quality — consider adding an article about [topic]."

**RET-3 — Dashboard → Automation Studio one-click path**
When a topic has ≥ 5 emails in the last 7 days, the topic row in the dashboard shows an "Automate this" button. Clicking it opens Automation Studio pre-filled with that topic as the trigger condition and a suggested action. Oliver should never have to navigate to Automation Studio cold.

**Metric moved:** Weekly active accounts, draft acceptance rate

---

### Expansion Requirements

> **Architecture:** EXP-3 requires the Action Agent to emit a notification event after a provider action MCP tool executes — depends on Phase 4 (provider action MCP tools) being live first.

**EXP-1 — Post-activation inbox expansion nudge**
After Oliver has his 10th email processed, show an in-product banner: "Managing a support@ or team inbox? Connect it here — no extra login required for your team." Triggered once, dismissible, linked to Settings → Inboxes.

**EXP-2 — Dashboard shows per-inbox breakdown**
When Oliver has 2+ inboxes connected, the dashboard shows metrics per inbox — not just aggregated. "Your Gmail: 23 emails. Support@: 47 emails." This makes the value of each inbox connection visible and creates a pull toward adding more.

**EXP-3 — Automation Studio as a retention anchor**
After Oliver's first Automation rule fires successfully (an email was archived, forwarded, or labelled via a rule), send a notification: "Your rule [name] just ran on 4 emails." This surfaces the Automation Studio value at the moment it delivers it.

**Metric moved:** Inboxes per account, Automation Studio adoption rate

---

### Revenue Requirements

> **Architecture:** No new architectural layer required. REV-1 reads from `DraftReplyFeedback`. REV-3 reads from `Ticket` counts and billing events.

**REV-1 — Value-moment triggered upgrade prompt**
When Oliver's accepted draft count crosses 10 in a single trial period, show the upgrade prompt: "InboxIQ has drafted 10 replies for you this week. At this rate, that is 40 per month. Upgrade to continue after your trial ends." The prompt is specific to his usage — not a generic "trial ending" banner.

**REV-2 — Pricing anchored to the hire comparison**
The pricing page must lead with: "InboxIQ handles the email volume that would justify a support hire, at 3% of the cost." Below that: a table comparing InboxIQ at £99/month vs. a junior support hire at £2,917/month, with the assumption made explicit (10 emails/day, 4 minutes each = 33 hours/month). No abstract feature lists leading.

**REV-3 — Downgrade protection: show what they would lose**
When an account cancels or lets a trial expire, show a summary of what InboxIQ did for them: "In your trial, InboxIQ processed 67 emails, drafted 41 replies, and saved an estimated 4.1 hours." Then ask: "Are you sure you want to stop?" This is not a dark pattern — it is making the value concrete at the exact moment it is being dismissed.

**Metric moved:** Trial-to-paid conversion rate, MRR

---

## 8. Phased Roadmap

Phases are strictly ordered by growth impact. Architecture work only ships when it directly unblocks a growth stage.

---

### Phase 1 — Activate the funnel (Weeks 1–3)

**Goal:** Know exactly where Olivers are dropping off. Fix the two biggest activation blockers.

**Architecture layer activated:** The full pipeline runs for the first time for a new user — Intake Agent → Enrichment Agent → Triage Agent (DSPy `DecisionProgram`) → Action Agent (label writeback). No new layers built; existing layers wired correctly end-to-end.

- Instrument the full funnel: visit → signup → inbox connect → first triage → first draft → first accepted draft
- Trigger first poll immediately on inbox connect (not on next Celery beat)
- Build the onboarding checklist with real-time step completion
- Implement demo mode for inboxes with no recent email

**Definition of done:** Can answer "what % of users who connect an inbox have an accepted draft within 60 minutes?" with real data.

---

### Phase 2 — Improve draft quality (Weeks 3–6)

**Goal:** Raise draft acceptance rate. This is the core retention lever.

**Architecture layer activated:** Enrichment Agent → `kb_search` MCP tool (MCP executes KB lookup before every triage). `draft_reply_skill` introduced (Skills guide DSPy on structure, tone, and KB fallback). DSPy `DecisionProgram` receives richer context from both.

- Wire Enrichment Agent to KB search before every triage — `kb_search` MCP tool
- Build KB gap detection and in-product notification
- Implement `draft_reply_skill` — encodes structure, tone, thread context, KB fallback behaviour
- Show Oliver KB coverage stats during onboarding and in the weekly digest

**Definition of done:** Draft acceptance rate measured for the first time. Target baseline ≥ 50%.

---

### Phase 3 — Retention infrastructure (Weeks 6–9)

**Goal:** Keep Olivers who activated. Surface value they cannot ignore.

**Architecture layer activated:** No new layer. Reads from data produced by Agents (Ticket counts, DraftReplyFeedback, AutomationRuleExecution). The value of the pipeline becomes visible to Oliver for the first time.

- Weekly digest email (processed, drafted, accepted, hours saved, top topic)
- KB gap alert notification
- Dashboard → Automation Studio one-click path ("Automate this" button on topic rows)
- Per-inbox breakdown in dashboard for multi-inbox accounts

**Definition of done:** Week-2 retention rate measured. Target ≥ 60% of activated accounts return in week 2.

---

### Phase 4 — Provider actions in Gmail/Outlook (Weeks 9–12)

**Goal:** Make Automation Studio indispensable. This is the primary expansion and retention anchor.

**Architecture layer activated:** Action Agent → Gmail and Outlook MCP tools (`gmail_apply_label`, `gmail_archive`, `gmail_forward`, `outlook_apply_category`, etc.). MCP servers execute capabilities directly inside Oliver's inbox. This is the first phase where all four layers are fully active end-to-end.

- Build Gmail MCP tools: `gmail_apply_label`, `gmail_archive`, `gmail_forward`, `gmail_create_draft`
- Build Outlook equivalents
- Wire `provider_action` type in Automation Studio to MCP tools
- Automation rule execution notification ("Your rule just ran on 4 emails")

**Definition of done:** Oliver creates a rule in Automation Studio and watches it execute inside his Gmail. Automation Studio adoption rate tracked.

---

### Phase 5 — Expansion and revenue triggers (Weeks 12–16)

**Goal:** Convert activated users to paid. Expand accounts with multiple inboxes.

**Architecture layer activated:** No new layer. Relies on instrumentation from Phase 1 and provider actions from Phase 4. The architecture is fully in place — this phase harvests the growth signals it produces.

- Post-activation inbox expansion nudge (after 10th processed email)
- Value-moment triggered upgrade prompt (after 10th accepted draft)
- Pricing page rewrite anchored to hire comparison
- Downgrade protection flow showing trial value summary

**Definition of done:** Trial-to-paid conversion rate measured for the first time. Inboxes-per-account average tracked.

---

### Phase 6 — Calendar slot injection (Weeks 14–18)

**Goal:** Remove a competing tool (Calendly) and add a visible value moment.

**Architecture layer activated:** `meeting_scheduling_skill` (Skills guide DSPy on when and how to inject slots). Enrichment Agent → `calendar_get_slots` MCP tool (MCP fetches real availability). DSPy `ExtractEntities` extended with meeting intent signal. New capability added without touching existing triage logic.

- `calendar_get_slots` MCP tool (Google Calendar + Outlook Calendar)
- Meeting intent detection in `ExtractEntities`
- Draft reply includes available slots when meeting intent detected
- Used as an acquisition story: "InboxIQ handles meeting scheduling too"

**Definition of done:** Meeting-intent emails produce drafts with real calendar slots. Measurable in Phoenix traces.

---

### Phase 7 — Cross-account intelligence (Weeks 18–24)

**Goal:** New accounts get immediate value. Cold start eliminated.

**Architecture layer activated:** DSPy bypass layer — `SenderProfile` confidence routing now draws on global profiles (`account_id = NULL`). The compounding effect of DSPy training data across all accounts materializes here. No new agents or MCP tools; the intelligence layer deepens.

- Promote high-agreement domain classifications to global `SenderProfile` (`account_id = NULL`)
- New account warmup: ≥ 30% of known sender domains pre-classified on first poll
- Privacy: domain only, no email content, opt-in per account

**Definition of done:** New accounts have measurably shorter time to first accurate triage vs. accounts before this phase.

---

## 9. Growth Metrics

### North Star

Weekly active accounts with ≥ 1 accepted draft reply

### By growth stage

| Stage | Metric | Target |
|---|---|---|
| Acquisition | Visit → signup conversion | Baseline → 10% |
| Activation | Inbox connect rate in trial | Baseline → 70% |
| Activation | Time to first accepted draft | Baseline → ≤ 20 min |
| Retention | Week-2 return rate (activated accounts) | Baseline → 60% |
| Retention | Draft acceptance rate | Baseline → 60% |
| Expansion | Inboxes per paid account | Baseline → 1.8 |
| Expansion | Automation Studio adoption | Baseline → 40% of paid accounts |
| Revenue | Trial-to-paid conversion | Baseline → 25% |
| Revenue | MRR growth | Track monthly |

All baselines measured before Phase 1 ships.

---

## 10. What We Will Not Do to Chase Growth

These are the guardrails. Violating them in the name of "growth" destroys the thing worth growing.

- **No auto-send email without a user-set confidence threshold.** Draft-first is the default and the trust model. Auto-send is opt-in per category, with a threshold Oliver controls.
- **No new third-party services without explicit decision.** Stack is: Flask, Celery, Redis, PostgreSQL, OpenAI, Gmail API, Outlook API, Phoenix. Every addition must be justified.
- **No raw LLM calls outside DSPy.** Quality and traceability depend on this being absolute.
- **No cross-account data sharing without opt-in.** Cross-account sender learning uses domain only — never email content — and is opt-in.
- **No healthcare features until FHIR is integrated.** Do not build healthcare-specific capabilities without the compliance infrastructure.
- **Trial stays at 7 days.** Changing it breaks cohort comparisons and makes learning impossible.
- **Do not build for ICPs outside the primary.** Founder-led B2B SaaS, 5–25 employees, Gmail or Outlook. E-commerce is secondary and has not been tested. Healthcare is deferred.

---

## 11. Open Questions

Must be resolved before the relevant phase begins.

| Question | Blocks | Priority |
|---|---|---|
| What is the current visit → signup conversion rate? | Phase 1 baseline | Immediate |
| What is the current inbox connect rate in trial? | Phase 1 baseline | Immediate |
| What % of trial signups have an accepted draft by day 3? | Phase 1 baseline | Immediate |
| What is the upgrade path UX? (What does Oliver see when trial ends?) | Phase 5 | High |
| Should the weekly digest be built in-app or via email? Which gets opened? | Phase 3 | Medium |
| How does the developer API interact with agents — can partners trigger agent workflows? | Post-Phase 5 | Low |

---

*Growth is not a campaign. It is a system. This document is the plan for that system. Update it when the data changes the assumptions.*
