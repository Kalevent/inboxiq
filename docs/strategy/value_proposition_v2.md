# Value Proposition v2

> Status: Draft — revised April 2026
> Supersedes: value_proposition.md
> Based on: ICP sharpening analysis + 3-month post-launch acquisition review

---

## What changed and why

The original value proposition was directionally right but too broad.
After three months in production, the evidence is clear: we are describing a real product for a real pain, but marketing to a market slice that is too wide and not pain-activated enough.

The shift in v2:

- **One dominant buying reason** — not a list of features
- **Narrower, more operationally specific ICP** — defined by pain intensity and trigger moment, not company size and industry
- **Three beachhead wedges** to test in the next 30 days
- **Exclusion criteria** — knowing who is not our customer matters as much as knowing who is

---

## The sharpened ICP

### Primary ICP (recommended)

**Founder-led B2B SaaS companies with 5–25 employees, 1–3 customer-facing Gmail or Outlook inboxes, 30–300 inbound emails per week, no dedicated support team, and a desire to delay their first support hire.**

This is more actionable than "10–50 employee B2B SaaS." It is defined by:

- Pain intensity (30–300 emails/week is enough to hurt, not enough to justify a hire)
- Existing workflow (Gmail or Outlook — no tool switch required)
- Trigger moment ("We're answering the same stuff every day")
- Buying motivation ("I don't want to hire support yet")

### Exclusion criteria (for now)

Do not spend time on:

- Teams already deeply using Zendesk / Intercom / Front workflows
- Companies with 5+ dedicated support reps
- Very low-volume inboxes (fewer than 30 emails/week)
- Highly regulated support environments
- Companies that require ticketing-first workflows rather than email-first

This matters. ICP sharpens when you get good at saying no.

---

## The one-sentence pitch (revised)

> **InboxIQ drafts repetitive customer emails inside Gmail so you can delay hiring support.**

This replaces the previous pitch which described too many benefits at once. One sentence. One reason to buy.

Supporting variations by wedge:

- "Still doing support from Gmail? InboxIQ handles the repetitive replies so you don't have to."
- "Your first AI support teammate — without Zendesk, Intercom, or another dashboard."
- "Connect support@, sales@, and founder inboxes. AI triage and draft replies directly inside Gmail."

---

## The pain points we solve

These must be felt, not hypothetical. Oliver has to say "yes, that is exactly my problem."

### 1. The same questions, every single day *(primary pain)*

Every SaaS company has a set of questions that arrive constantly: password resets, billing queries, onboarding help, "how does feature X work." These take 3–5 minutes each. At 30 per day across a small team, that is 1.5–2.5 hours every day — on questions already answered hundreds of times.

**What InboxIQ does**: Classifies incoming emails, matches them to known query types, drafts replies using the existing knowledge base and past answers. Oliver opens Gmail, sees a draft already in the thread, reviews it, and sends. He does not compose from scratch.

### 2. Support volume outgrowing the team before revenue justifies a hire *(primary ROI driver)*

Growing from 200 to 500 customers doubles support load. A support hire costs £35K–£50K per year plus management overhead. The maths does not work until a certain revenue threshold.

**What InboxIQ does**: Handles volume growth without headcount growth. Priced at a fraction of a hire. The headline message: **delay your first support hire**.

### 3. Customers waiting hours — or days — for a reply

Oliver's team works business hours. Customers email at 9pm. They see a reply the next morning, or after the weekend. Slow responses lose customers and deals.

**What InboxIQ does**: Drafts a reply the moment an email arrives — including at 11pm on a Friday. The draft appears in the Gmail thread waiting for Oliver. High-confidence emails can be configured to send automatically; everything else goes through Oliver first.

### 4. Support spread across multiple inboxes, none of them connected

Support emails arrive in three places: Oliver's Gmail, the `support@` alias, the `sales@` address. Each inbox is a silo. No unified picture. No shared intelligence.

**What InboxIQ does**: One account connects as many inboxes as the team manages. Oliver sends a one-click invite link — his team member authorises her Gmail in her own browser, and her inbox is connected. No InboxIQ login required for her. No password sharing. Labels appear inside each person's Gmail independently. The intelligence is shared; the inboxes stay separate.

### 5. No visibility into what customers are actually asking about

Oliver handles support reactively. He has no view of the patterns. He does not know that 40% of this month's volume is about the same onboarding step, or that billing questions doubled after a pricing change. Without that visibility, he keeps answering the same questions forever.

**What InboxIQ does**: Surfaces top topics customers are contacting him about — this week, this month, trending up or down. Oliver sees "onboarding — 38 emails this month, up 60%" and immediately knows where the documentation gap is. Automation Studio opens pre-filled with the topic as the trigger — action one click away.

### 6. Manual routing rules that cannot use AI context

Gmail filters run before any AI classification. They can match sender address or subject keyword, nothing more. Bug reports cannot be forwarded to engineering. Billing emails cannot be routed intelligently.

**What InboxIQ does**: Automation Studio fires after triage, with full AI context available as conditions. No code, no IT ticket. `label = Support AND intent = bug_report` → forward to engineering. `category = Billing` → move to Billing folder. Runs silently across all connected inboxes.

### 7. Context lost in long email threads

A customer emails Monday with a problem. Oliver asks for their account number Tuesday. The customer replies Thursday. By then the context is buried — Oliver has to re-read the thread before replying.

**What InboxIQ does**: Reads the full prior conversation — not just the latest message — before drafting a reply. It knows this is a follow-up, what was already asked, and what was said before. The draft references thread context.

### 8. Meeting scheduling is still manual and creates back-and-forth

A prospect emails asking for a demo. A customer asks for a call to discuss their account. Oliver or a team member has to check their calendar, find a time, write it out, send it, wait for a reply, confirm. This loop takes 3–6 emails and days of elapsed time. Calendly links help but require the sender to visit a separate URL.

**What InboxIQ does**: When an inbound email contains a meeting or scheduling request — *"can we book a demo?"*, *"when are you available?"*, *"let's get on a call"* — the AI detects the intent and the draft reply automatically includes available time slots pulled directly from the connected calendar. No Calendly link. No separate tool. The slots appear in the draft, ready to send.

Supports both Google Calendar and Microsoft Outlook Calendar — Oliver connects whichever he already uses via Settings → Integrations. The AI reads his real availability and surfaces it inline.

---

## The 3 reasons people will say no

### Objection 1: "I do not trust AI to reply to my customers"

**Answer**:
- InboxIQ does not send anything without a confidence threshold you set
- Default mode is draft-only: AI drafts everything, Oliver sends it — he sees quality before trusting it to send autonomously
- The AI is trained on his own knowledge base and past replies — not making things up from the internet
- Every correction he makes trains the model to do better next time

### Objection 2: "We already have a system for this"

**Answer**:
- InboxIQ connects to existing Gmail or Outlook — it does not replace it
- Oliver stays in Gmail. Every email gets a label applied automatically and a draft reply appears in the thread
- He never opens a separate dashboard to get value day-to-day
- If he decides it is not for him, he disconnects and his inbox goes back to normal — nothing migrated, nothing lost

### Objection 3: "It will not understand my specific product or business"

**Answer**:
- InboxIQ reads the full email thread before drafting — it knows what has already been said
- It ingests existing knowledge base, help centre, and past email replies
- It learns what the team actually says to customers, not a generic script
- Every correction improves the next response
- Settings → Knowledge Base supports file upload (.md, .txt, .html, .pdf) and URL-based sources. Pre-configured shortcuts for Zendesk, Intercom, Notion, GitBook, HelpScout, Confluence, and any custom URL

---

## Return on investment

### Time saved

- Average repetitive email: 4 minutes to read and reply
- Oliver's team handles: 80 repetitive emails per week
- Time cost per week: 320 minutes = 5.3 hours
- Time cost per month: ~21 hours
- At a loaded cost of £25/hour for a junior hire: £525/month in labour

InboxIQ at £99/month saves £425/month net while also improving response speed and consistency.

### The "cost of a hire" comparison *(lead with this)*

A support hire at £35,000/year = £2,917/month. InboxIQ handles the volume increase that would have triggered that hire. The ROI is not £99 vs £525 in saved time — it is **£99 vs £2,917 in deferred headcount**.

**Lead with**: "handles the workload that would justify a support hire, at 3% of the cost" — not "saves you hours."

### Unit economics confirmed

Actual LLM cost per email processed: ~$0.001 (4 AI calls per email on gpt-4o-mini, from production telemetry). At 300 emails/week, that is ~$1.20/month in AI costs per customer. Margin at £99/month is healthy — confirmed from live instrumentation, not an estimate.

---

## The three beachhead wedges to test (next 30 days)

### Wedge A — "Delay your first support hire"

**Message**: "Still doing support from Gmail? InboxIQ drafts repetitive customer emails for you so you can delay hiring support."

**Target**: Founder-led SaaS, 5–25 employees, founder still in the inbox

**Why strong**: "Delay your first support hire" is a much sharper buying reason than "AI email assistant." It speaks directly to the trigger moment.

### Wedge B — "Shared inbox without leaving Gmail"

**Message**: "Connect support@, sales@, and founder inboxes. AI triage and draft replies directly inside Gmail."

**Target**: Lean ops / founder / Head of Ops managing multiple inboxes

**Why strong**: The multi-inbox angle is a genuine product differentiator. No competitor does this inside Gmail without a new tool.

### Wedge C — "For bootstrapped SaaS founders"

**Message**: "Your first AI support teammate — without Zendesk, Intercom, or another dashboard."

**Target**: Indie Hackers, bootstrapped founders, micro-SaaS operators

**Why strong**: These buyers feel the pain personally, can decide quickly, and are active in communities where we can reach them cheaply (X, Indie Hackers, Reddit). Lower ACV but faster learning.

---

## The real selling event

The product's real selling moment is not the homepage. It is not the demo. It is:

> **The AI label and draft appearing correctly in the user's Gmail thread.**

Everything before that is activation cost. Everything after that is retention.

Acquisition should revolve around getting someone to:

1. Connect one inbox
2. See one amazing draft
3. Confirm it handled a real repetitive email well

Not "explaining the platform."

**What this means for GTM**:
- Trial onboarding must get Oliver to a working draft in Gmail within 20 minutes
- Outreach should lead with the inbox-native proof, not the feature list
- Paid ads / landing pages should show the label and draft in an actual Gmail screenshot — not an abstract product illustration

---

## What "good ICP signal" looks like

The strongest ICP signal is not traffic or signups. It is when someone says:

> "This is exactly our problem."
> "We need this."
> "Can this connect to our support@ inbox?"

Weak signal: "Interesting." "Cool." "I should try this someday."

Optimise for the strong signal, not the volume signal.

---

## Behaviour change required (honest)

| What changes | Effort level |
|---|---|
| Sign up with Google (2 minutes, no IT involvement) | Very low |
| Connect Gmail or Outlook (OAuth, 2 minutes) | Low |
| Upload or link knowledge base articles | Medium — 1–2 hours first time |
| Review and approve AI drafts for first 2 weeks | Low — replaces composing from scratch |
| Adjust confidence thresholds based on results | Low — occasional |
| Retrain support team on new queue workflow | Low — team still works in Gmail |

The honest message: setup takes about 2 hours. After that, the daily workflow is lighter than before, and it happens inside Gmail.

---

## What InboxIQ replaces or reduces

| Current tool | What changes |
|---|---|
| Shared Gmail / Outlook inbox | Stays — InboxIQ layers on top, adds labels and drafts |
| Help Scout (AI Assist) / Front / Superhuman | May replace for teams using only basic shared inbox features |
| Zendesk (AI features, basic tier) | May replace for teams using Zendesk as a shared inbox without ticketing workflows |
| Freshdesk (Freddy AI) | May replace for teams who adopted Freshdesk for simplicity but don't use its full suite |
| Intercom (Fin AI) | Not a direct replacement — Intercom is chat-first and priced for larger teams |
| Copy-paste reply templates | Replaced — AI generates contextual drafts using full thread history |
| Calendly / cal.com | Replaced — AI detects meeting requests and includes available slots directly in the draft reply; no separate scheduling link required |
| Junior support hire (planned) | Deferred — handle the same volume with existing team |

InboxIQ is not trying to replace Zendesk for a 10-person support team. It is the tool for the company that is not there yet.

---

## One-paragraph narrative for Oliver

> You are handling customer emails that have already been answered dozens of times. You cannot afford enterprise support tools. You cannot justify a hire yet. You cannot afford to have yourself or a senior person buried in the inbox all day. InboxIQ connects to your existing Gmail or Outlook, reads every incoming email in full thread context, classifies it, and places a draft reply directly in the Gmail thread — ready for you to review and send without composing from scratch. You never open a separate dashboard. Response times drop from hours to minutes. Volume grows without headcount growing. You can sign up in under 2 minutes, connect your inbox in another 2 minutes, and see draft replies appearing in your own Gmail threads within 20 minutes of signing up.

---

## Next actions

1. Pick one of the three beachhead wedges and run it for 2 weeks before switching
2. Rewrite the kalevent.com homepage hero to lead with the winning wedge message
3. Track: signup conversion, inbox connection rate, first successful draft rate, return rate after first connection
4. Measure who says "this is exactly our problem" — that is the real ICP signal
5. Update ICP.md once a wedge shows clear pull
