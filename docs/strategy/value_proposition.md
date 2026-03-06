# Value Proposition

> Status: Draft — for discussion at next innovation meeting
> Last updated: 6 Mar 2026

Anchored to the primary ICP: founder or head of ops at a B2B SaaS company, 10–50 employees.
See [ICP.md](ICP.md) first.

---

## The one-sentence pitch

**InboxIQ handles the repetitive support emails your team keeps answering manually, so you stop losing hours to your inbox every day.**

No enterprise setup. No AI hallucinations sent to customers. Works with your existing email.

---

## The pain points we solve

These must be felt, not hypothetical. Oliver has to say "yes, that is exactly my problem" when he hears these.

### 1. The same questions, every single day

Every SaaS company has a set of questions that arrive constantly: "How do I reset my password?", "I was charged twice", "Can you explain how feature X works?", "We want to add a user." These take 3–5 minutes each to reply to. At 30 per day across a small team, that is 1.5–2.5 hours per day — every day — on questions that have already been answered hundreds of times.

**What InboxIQ does**: Classifies incoming emails, matches them to known query types, drafts replies using your existing knowledge base and past answers. The team reviews or approves; they do not compose from scratch.

### 2. Customers waiting hours (or days) for a reply

Oliver's team works business hours. Customers email at 9pm. They see a reply the next morning, or after the weekend. In a world where competitors offer live chat, slow responses lose customers and deals.

**What InboxIQ does**: Can draft and optionally send responses immediately for high-confidence, low-risk query types. Human stays in control of the confidence threshold.

### 3. Support volume outgrowing the team faster than revenue justifies a hire

Growing from 200 to 500 customers doubles the support load. Hiring a support person costs £35K–£50K per year plus management overhead. The maths does not work until you hit a certain revenue threshold.

**What InboxIQ does**: Handles the volume growth without headcount growth. Priced at a fraction of a hire.

---

## The 3 reasons people will say no

These are the objections Oliver will have. We need an answer for each one before he has the conversation with himself.

### Objection 1: "I do not trust AI to reply to my customers"

This is the most common and most legitimate objection. Oliver has seen AI hallucinate. He cannot afford to have the AI tell a customer something wrong.

**Our answer**:
- InboxIQ does not send anything without a confidence threshold you set
- Low-confidence drafts go to a human review queue — the AI writes, the human approves
- You can start in draft-only mode: AI drafts everything, your team sends it. You see the quality before you trust it to send autonomously
- The AI is trained on your own knowledge base and past replies — it is not making things up from the internet

**What this requires from the product**: The confidence/approval workflow must be prominent in onboarding. Oliver needs to see "draft mode" as the default on day one, not buried in settings.

### Objection 2: "We already have a system for this"

Most companies Oliver's size are using Gmail or Outlook, maybe with a shared inbox tool (Front, Superhuman, Help Scout). Some have Zendesk but are only using 20% of it.

**Our answer**:
- InboxIQ connects to your existing inbox — it does not replace it
- If you use Gmail, you still use Gmail. InboxIQ sits on top
- You do not have to migrate anything or retrain your team
- If you decide it is not for you, you disconnect it and nothing changes

**What this requires from the product**: The Gmail/Outlook OAuth connection must be frictionless. The value must be visible inside the user's existing workflow, not in a separate dashboard they have to remember to open.

### Objection 3: "It will not understand my specific product or business"

Generic AI gives generic answers. Oliver's customers ask about his specific features, his pricing, his processes. A general-purpose chatbot will fail.

**Our answer**:
- InboxIQ ingests your existing knowledge base, help centre, and past email replies
- It learns what your team actually says to customers, not a generic script
- You can review and correct its answers — every correction makes the next response better

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

---

## Behaviour change required

Be honest about what Oliver has to do differently. Hiding this creates churn.

| What changes | Effort level |
|---|---|
| Connect Gmail or Outlook (OAuth, 2 minutes) | Low |
| Upload or link knowledge base articles | Medium — needs 1–2 hours first time |
| Review and approve AI drafts for first 2 weeks | Low — replaces composing from scratch |
| Adjust confidence thresholds based on results | Low — occasional |
| Retrain support team on new queue workflow | Medium — depends on team size |

The honest message: setup takes about 2–3 hours. After that, day-to-day use is lighter than what they do now.

---

## What systems InboxIQ replaces or reduces

| Current tool | What changes |
|---|---|
| Shared Gmail / Outlook inbox | Stays — InboxIQ layers on top |
| Help Scout / Front / Superhuman | May replace for teams that only use basic shared inbox features |
| Zendesk (basic tier) | May replace for teams using Zendesk as a shared inbox without ticketing workflows |
| Copy-paste reply templates | Replaced — AI generates contextual drafts instead |
| Junior support hire (planned) | Deferred — handle the same volume with existing team |

InboxIQ is not trying to replace Zendesk for a company with a 10-person support team. It is the tool for the company that is not there yet.

---

## One-paragraph narrative for the innovation manager

> Small SaaS companies spend a disproportionate amount of time on support emails that have been answered dozens of times before. They cannot afford enterprise support tools, cannot justify a support hire yet, and cannot afford to have the founder or a senior person buried in the inbox all day. InboxIQ connects to their existing email, reads every incoming message, classifies it, and drafts a reply using their own knowledge base and previous answers. The team approves or edits — they stop composing from scratch. Response times drop from hours to minutes. Volume grows without headcount growing. The product is designed so a founder can set it up in an afternoon without involving IT, and can see the AI working on their own emails within 20 minutes of signing up.

---

## What to do before the next meeting

1. Test the free trial signup as if you are Oliver — can you get to a working demo in under 20 minutes without connecting a real inbox?
2. Identify 3 people in your network who match the Oliver persona
3. Draft a one-page version of this document that can be shared with the innovation manager without all the commentary
