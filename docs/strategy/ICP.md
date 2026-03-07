# Ideal Customer Profile (ICP)

> Status: Draft — for discussion at next innovation meeting
> Last updated: 7 Mar 2026

---

## The problem with the current ICP

Right now InboxIQ targets "B2B SaaS, E-commerce, Healthcare" simultaneously. That is not an ICP. That is three different markets with different buyers, different objections, different workflows, and different competitors. The result is a product that does too many things with no clear narrative for any of them.

The innovation manager's observation is correct: focus on one pain point, one buyer, one use case — and get one customer.

---

## Recommended Primary ICP

### Who they are

**The founder or head of operations at a B2B SaaS company, 10–50 employees, $500K–$5M ARR.**

More specifically:
- They have a small customer support function — 1 to 3 people handling email support, or the founder is still doing it themselves
- They are receiving between 50 and 300 support emails per week
- The majority of those emails are repetitive: billing questions, password resets, onboarding help, "how do I do X" questions
- They have evaluated Intercom (Fin AI) or Zendesk (AI features) and found them too expensive or too complex for where they are now
- They make their own buying decisions — no procurement process, no IT manager sign-off needed
- They care about customer experience but cannot afford to staff it properly

### Why this segment

| Factor | Why it fits |
|---|---|
| Volume problem | 50–300 emails/week is enough to cause pain but not enough to justify a full support hire |
| Decision speed | Founder or head of ops can sign up with a card, no committee |
| Technical comfort | B2B SaaS buyers understand AI and are not afraid of it |
| Network access | Most accessible market — startup communities, Slack groups, LinkedIn |
| Willingness to pay | SaaS companies understand recurring software costs |
| Behaviour change is low | They already use email — we are not replacing their workflow, we are making it faster |

### Why NOT e-commerce or healthcare first

- **E-commerce**: High ticket volume but seasonal, price-sensitive, and dominated by Gorgias/Tidio at the SMB level. Harder to displace. A different persona (operations manager, not founder).
- **Healthcare**: Requires FHIR integration (not yet built). Regulatory friction. Longer sales cycle. Do not prioritise until FHIR is integrated.

---

## Persona: "Overwhelmed Oliver"

This is a composite of the buyer we are targeting.

**Name**: Oliver (or equivalent — founder, Head of Ops, Head of CS)
**Company**: B2B SaaS, 15–40 employees
**Role**: Founder or first CS/Ops hire
**Age**: 28–42

### A day in Oliver's life

Oliver starts the day with 47 unread support emails. He knows at least 30 of them are variations of questions he has answered before. He spends 2–3 hours per day in his inbox. His team is growing, customer queries are growing faster, and hiring another support person costs £35,000–£50,000 a year. He has looked at Zendesk (AI features) and Intercom (Fin AI) — both are built for a 20-person support team, not a 2-person startup. He has tried Freshdesk (Freddy AI) and found the AI too generic. He has tried help centre articles. Customers still email.

Critically: **Oliver does not want to log into a new dashboard.** He lives in Gmail. Any tool that requires him to open a separate app is a tool he will forget to use. The value has to appear where he already is.

### What Oliver wants

- Fewer hours in the inbox
- Fast, consistent replies — even at 11pm on a Friday
- Not to have to hire his way out of the problem
- Something he can set up himself in an afternoon, not a 3-month implementation project
- Drafts waiting for him in the same Gmail thread, ready to review and send

### What Oliver is afraid of

- AI sending wrong or embarrassing replies to customers
- The tool "going rogue" without him knowing
- Paying for something that requires ongoing maintenance
- Locking himself into something he cannot get out of
- Having to learn a new interface or retrain his team

### How Oliver buys

- Finds tools via Twitter/X, LinkedIn, Product Hunt, Hacker News
- Signs up for a free trial himself, decides within 2 weeks
- Cancels immediately if setup takes more than 30 minutes
- Will not involve IT or Ops manager — he IS the decision maker

---

## Signup barrier (resolved 7 Mar 2026)

The innovation manager tried to create an account and got the impression she needed her IT manager and Ops manager to approve it first. This was caused by Google blocking the sign-in because the app was requesting Gmail access scopes at the point of signup — before Oliver had even created an account.

**This has been fixed.**

Google sign-in now uses only `openid email profile` (no Gmail scopes). Oliver signs up instantly without any Google verification blocker. Gmail inbox access is requested separately, only after he is inside the product and explicitly clicks "Connect Gmail". The two steps are now decoupled:

1. **Sign up** → Google sign-in with email/profile only. No block. No IT approval language.
2. **Connect inbox** → Gmail scopes requested separately when Oliver chooses to connect, from the onboarding screen or Settings.

This matches exactly what Oliver expects: sign up in 30 seconds, decide later whether to give inbox access.

### Remaining items from the original list

The following were identified as needed alongside the signup fix. Status below:

| Item | Status |
| --- | --- |
| Sign up with just an email address — no admin approval language | Done — Google sign-in no longer blocked |
| First screen after signup shows something useful immediately (demo data) | Done — onboarding screen shows 3 live triage examples |
| Remove UI language implying multi-person approval or enterprise setup | To review — check all onboarding copy |
| Connecting a real inbox optional in trial | Done — inbox connect is a separate step after account creation |

---

## How InboxIQ works inside Oliver's existing Gmail workflow

Oliver never has to open the InboxIQ dashboard to get value day-to-day. After connecting his inbox, every email that arrives is processed automatically:

1. InboxIQ reads the email and the full prior thread (not just the latest message)
2. It classifies the email: category, priority, sentiment, whether it needs a reply
3. It applies a Gmail label directly to the message (e.g. "InboxIQ · Billing · P1")
4. If a reply is warranted, it creates a draft reply collapsed in the Gmail thread — Oliver opens the email, sees the draft, edits if needed, and sends

Oliver's workflow does not change. His inbox just has less noise and pre-written replies waiting for him.

The InboxIQ dashboard exists for configuration (knowledge base, label rules, confidence thresholds) and reporting (volume trends, response times, LLM cost per email). It is not the primary surface for daily work.

---

## Secondary ICP (do not pursue until primary ICP has one paying customer)

E-commerce operations manager at a D2C brand, 20–100 employees, using Shopify. High seasonal volume, needs AI to handle order/delivery/returns queries. Different product surface (more Shopify integration, less AI decision-making) — treat as a separate motion.

---

## Questions to answer at next meeting

1. Do we have anyone in our network who matches Oliver's profile?
2. What does "getting one customer" look like — free beta user or paying customer?
3. Can Oliver see a draft reply in his Gmail thread within 20 minutes of signing up?
4. What does the onboarding screen look like after the Google sign-in fix — does it feel like a tool he controls or a system he has been enrolled in?
