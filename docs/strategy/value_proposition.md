# Value Proposition

> Status: Draft — for discussion at next innovation meeting
> Last updated: 11 Mar 2026

Anchored to the primary ICP: founder or head of ops at a B2B SaaS company, 10–50 employees.
See [ICP.md](ICP.md) first.

---

## The one-sentence pitch

InboxIQ is the AI layer that sits under your Gmail or Outlook — it reads every email, drafts the reply, and routes anything that needs action. Your team never opens another tool.

---

## The pain points we solve

These must be felt, not hypothetical. Oliver has to say "yes, that is exactly my problem" when he hears these.

### 1. The same questions, every single day

Every SaaS company has a set of questions that arrive constantly: "How do I reset my password?", "I was charged twice", "Can you explain how feature X works?", "We want to add a user." These take 3–5 minutes each to reply to. At 30 per day across a small team, that is 1.5–2.5 hours per day — every day — on questions that have already been answered hundreds of times.

**What InboxIQ does**: Classifies incoming emails, matches them to known query types, drafts replies using your existing knowledge base and past answers. Oliver opens Gmail, sees a draft already in the thread, reviews it, and sends. He does not compose from scratch.

### 2. Customers waiting hours (or days) for a reply

Oliver's team works business hours. Customers email at 9pm. They see a reply the next morning, or after the weekend. In a world where competitors offer live chat, slow responses lose customers and deals.

**What InboxIQ does**: Drafts a reply the moment an email arrives — including at 11pm on a Friday. The draft appears in the Gmail thread waiting for Oliver when he opens his inbox in the morning. High-confidence, low-risk emails can be configured to send automatically; everything else goes through Oliver first.

### 3. Support volume outgrowing the team faster than revenue justifies a hire

Growing from 200 to 500 customers doubles the support load. Hiring a support person costs £35K–£50K per year plus management overhead. The maths does not work until you hit a certain revenue threshold.

**What InboxIQ does**: Handles the volume growth without headcount growth. Priced at a fraction of a hire.

### 4. Support is spread across multiple inboxes — none of them connected

Oliver's support emails arrive in three places: his own Gmail, the `support@company.com` alias managed by a team member, and the `sales@company.com` address another colleague handles. Each inbox operates in isolation. The team member answers support emails without AI assistance. The sales alias has no drafts. Oliver cannot see a unified picture of what is coming in across all of them.

In an enterprise setting the same problem scales: a team of five has five separate inboxes, each one a silo. Knowledge stays personal. Response consistency is zero.

**What InboxIQ does**: One account connects as many inboxes as the team manages. Oliver sends a one-click invite link to his team member — she clicks, authorizes her Gmail in her own browser, and her inbox is connected. No InboxIQ login required for her. No password sharing. No IT involvement. From that point, InboxIQ applies the same triage intelligence, the same KB-grounded draft replies, and the same automation rules to every connected inbox. Labels appear inside each person's Gmail independently. The intelligence is shared; the inboxes stay separate.

The billing unit is the inbox connection, not the seat — because a team member whose inbox is connected consumes the same AI resources as Oliver's, regardless of whether she ever logs into InboxIQ. More inboxes connected means more value delivered, and the pricing reflects that.

---

### 5. No visibility into what customers are actually asking about

Oliver handles support reactively — he replies to emails one by one but has no view of the patterns. He does not know that 40% of his support volume this month is about the same onboarding step, or that billing questions have doubled since the pricing change. Without that visibility, he cannot fix the root cause and keeps answering the same questions forever.

**What InboxIQ does**: Surfaces the top topics customers are contacting him about — this week, this month, trending up or down. Oliver sees "onboarding — 38 emails this month, up 60% from last month" and immediately knows there is a documentation gap or a product bug to fix. And if he wants InboxIQ to handle that topic automatically, he flips a toggle on the same screen — Automation Studio opens pre-filled with the topic as the trigger, no context-switching required. The dashboard turns reactive inbox management into proactive product intelligence, with action one click away.

---

### 6. Manual routing rules that cannot use AI context

Oliver wants bug reports forwarded to engineering. He wants billing emails to move to a folder. He wants automated senders tagged and archived. Gmail filters and Outlook rules cannot do any of this — they run at message delivery time, before any AI classification has happened. They can match on sender address or subject keyword, nothing more.

**What InboxIQ does**: Automation Studio lets Oliver configure rules that fire after triage, with full AI context available as conditions. Rules are built in a UI — no code, no IT ticket. Conditions can combine any triage output:

- `label = InboxIQ/Support AND intent = bug_report` → forward to `engineering@company.com`
- `category = Billing` → move to Billing folder, tag email
- `is_automated = true` → tag and archive
- `sentiment = Frustrated AND action_required = true` → send webhook to Slack

Actions available today: forward (send email), tag, move to folder, send webhook, extract structured data. Rules are account-level — one set of rules applies across all connected inboxes. Oliver configures it in Settings → Automation and it runs silently after every triage.

**Why native rules cannot replicate this**: A Gmail filter on `from:stripe.com` catches every Stripe email regardless of what it is. An InboxIQ rule on `category = Billing` catches only actual billing emails — receipts, disputes, invoices — identified by AI, not by sender address guesswork.

---

### 7. No way to measure what the inbox is actually costing the business

Oliver knows support emails take time but cannot quantify it. He has no number to show a co-founder, investor, or himself when justifying the cost of a tool or a hire. He also cannot tell if response times are improving or getting worse without manually tracking it.

**What InboxIQ does**: Calculates hours saved per month, equivalent headcount ("InboxIQ handled the workload of 0.4 of a hire this month"), average first response time, and KB coverage gaps — all derived automatically from pipeline data. Oliver opens the dashboard and immediately has the business case for why InboxIQ is worth it, and what to fix to make it work even better.

---

### 6. Context lost in long email threads

A customer emails on Monday with a problem. Oliver asks for their account number on Tuesday. The customer replies on Thursday. By then the context is buried and Oliver has to re-read the thread before he can respond.

**What InboxIQ does**: Reads the full prior conversation — not just the latest message — before drafting a reply. It knows this is a follow-up, what was already asked, and what the customer said before. The draft reply references the thread context rather than treating every incoming message as a new conversation.

---

## The 3 reasons people will say no

These are the objections Oliver will have. We need an answer for each one before he has the conversation with himself.

### Objection 1: "I do not trust AI to reply to my customers"

This is the most common and most legitimate objection. Oliver has seen AI hallucinate. He cannot afford to have the AI tell a customer something wrong.

**Our answer**:

- InboxIQ does not send anything without a confidence threshold you set
- Low-confidence drafts go to a human review queue — the AI writes, the human approves
- Default mode is draft-only: AI drafts everything, Oliver sends it. He sees the quality before trusting it to send autonomously
- The AI is trained on his own knowledge base and past replies — it is not making things up from the internet
- Every correction he makes trains the model to do better next time

**What this requires from the product**: Draft mode must be the visible default on day one. The confidence threshold must be adjustable from the main settings screen, not buried.

### Objection 2: "We already have a system for this"

Most companies Oliver's size are using Gmail or Outlook, maybe with a shared inbox tool (Front, Superhuman, Help Scout with AI Assist). Some have Zendesk (with AI features) or Freshdesk (Freddy AI) but are only using 20% of what those platforms offer. A few have tried Intercom (Fin AI) and found it priced for a company twice their size.

**Our answer**:

- InboxIQ connects to your existing Gmail or Outlook — it does not replace it
- Oliver stays in Gmail. After connecting, every email gets a label applied automatically (e.g. "InboxIQ · Billing · P1") and a draft reply appears collapsed in the thread
- He never has to open a separate dashboard to get value day-to-day
- If he decides it is not for him, he disconnects and his inbox goes back to normal — nothing migrated, nothing lost

**What this requires from the product**: The write-back to Gmail must be reliable. The label and draft have to appear in the right thread, correctly formatted, every time. This is the core "proof of value" moment — Oliver sees it working in his own Gmail within minutes of connecting.

### Objection 3: "It will not understand my specific product or business"

Generic AI gives generic answers. Oliver's customers ask about his specific features, his pricing, his processes. A general-purpose chatbot will fail.

**Our answer**:

- InboxIQ reads the full email thread before drafting — it knows what has already been said and by whom
- It ingests his existing knowledge base, help centre, and past email replies
- It learns what his team actually says to customers, not a generic script
- Every correction he makes improves the next response

**What this requires from the product**: Onboarding must include a knowledge base setup step that feels immediate. Oliver should be able to paste in 5 past email replies and see the AI use them within 10 minutes of signing up.

---

## Return on investment

This must be concrete and calculable, not vague.

### Time saved

- Average repetitive email: 4 minutes to read and reply
- Oliver's team handles: 80 repetitive emails per week
- Time cost per week: 320 minutes = 5.3 hours
- Time cost per month: ~21 hours
- At a loaded cost of £25/hour for a junior hire: £525/month in labour

InboxIQ at £99/month saves £425/month net while also improving response speed and consistency.

### The "cost of a hire" comparison

A support hire at £35,000/year = £2,917/month. InboxIQ handles the volume increase that would have triggered that hire. The ROI is not £99 vs £525 in saved time — it is £99 vs £2,917 in deferred headcount.

**How to use this**: On the pricing page and in any sales conversation, lead with "handles the volume of a full-time support hire at 3% of the cost" — not "saves you hours".

### Our cost to deliver

Actual LLM cost per email processed is approximately **$0.001** (4 AI calls per email on gpt-4o-mini, measured from production telemetry). At 300 emails/week (Oliver's upper volume), that is ~$1.20/month in AI costs per customer. Margin at £99/month is healthy even accounting for infrastructure. This is confirmed by live instrumentation — not an estimate.

---

## Behaviour change required

Be honest about what Oliver has to do differently. Hiding this creates churn.

| What changes | Effort level |
| --- | --- |
| Sign up with Google (2 minutes, no IT involvement) | Very low — now works without any approval blocker |
| Connect Gmail or Outlook (OAuth, 2 minutes, after sign-up) | Low |
| Upload or link knowledge base articles | Medium — needs 1–2 hours first time |
| Review and approve AI drafts for first 2 weeks | Low — replaces composing from scratch |
| Adjust confidence thresholds based on results | Low — occasional, from Settings |
| Retrain support team on new queue workflow | Low to medium — team still works in Gmail, labels change |

The honest message: setup takes about 2 hours. After that, the daily workflow is lighter than what they do now, and it happens inside Gmail rather than in a new tool.

---

## What systems InboxIQ replaces or reduces

| Current tool | What changes |
| --- | --- |
| Shared Gmail / Outlook inbox | Stays — InboxIQ layers on top, adds labels and drafts |
| Help Scout (AI Assist) / Front / Superhuman | May replace for teams that only use basic shared inbox features |
| Zendesk (AI features, basic tier) | May replace for teams using Zendesk as a shared inbox without ticketing workflows |
| Freshdesk (Freddy AI) | May replace for teams who adopted Freshdesk for simplicity but don't use its full suite |
| Intercom (Fin AI) | Not a direct replacement — Intercom is chat-first and priced for larger teams |
| Copy-paste reply templates | Replaced — AI generates contextual drafts using full thread history |
| Junior support hire (planned) | Deferred — handle the same volume with existing team |

InboxIQ is not trying to replace Zendesk for a company with a 10-person support team. It is the tool for the company that is not there yet.

---

## One-paragraph narrative for the innovation manager

> Small SaaS companies spend a disproportionate amount of time on support emails that have been answered dozens of times before. They cannot afford enterprise support tools, cannot justify a support hire yet, and cannot afford to have the founder or a senior person buried in the inbox all day. InboxIQ connects to their existing Gmail or Outlook, reads every incoming email in full thread context, classifies it, and places a draft reply directly in the Gmail thread — ready for Oliver to review and send without composing from scratch. He never opens a separate dashboard. Response times drop from hours to minutes. Volume grows without headcount growing. The product is designed so a founder can sign up in under 2 minutes without involving IT, connect their inbox in another 2 minutes, and see draft replies appearing in their own Gmail threads within 20 minutes of signing up.

---

## What to do before the next meeting

1. Test the full flow as Oliver: sign up → connect Gmail → receive a test email → confirm a label and draft appear in Gmail
2. Identify 3 people in your network who match the Oliver persona
3. Draft a one-page version of this document that can be shared with the innovation manager without all the commentary
4. Decide: is the beta user free or paying? Free removes price friction but may reduce commitment signal
