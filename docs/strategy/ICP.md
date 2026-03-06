# Ideal Customer Profile (ICP)

> Status: Draft — for discussion at next innovation meeting
> Last updated: 6 Mar 2026

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
- They have evaluated Intercom or Zendesk and found them too expensive or too complex for where they are now
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

Oliver starts the day with 47 unread support emails. He knows at least 30 of them are variations of questions he has answered before. He spends 2–3 hours per day in his inbox. His team is growing, customer queries are growing faster, and hiring another support person costs £35,000–£50,000 a year. He has looked at Zendesk — it is built for a 20-person support team, not a 2-person startup. He has tried help centre articles. Customers still email.

### What Oliver wants

- Fewer hours in the inbox
- Fast, consistent replies — even at 11pm on a Friday
- Not to have to hire his way out of the problem
- Something he can set up himself in an afternoon, not a 3-month implementation project

### What Oliver is afraid of

- AI sending wrong or embarrassing replies to customers
- The tool "going rogue" without him knowing
- Paying for something that requires ongoing maintenance
- Locking himself into something he cannot get out of

### How Oliver buys

- Finds tools via Twitter/X, LinkedIn, Product Hunt, Hacker News
- Signs up for a free trial himself, decides within 2 weeks
- Cancels immediately if setup takes more than 30 minutes
- Will not involve IT or Ops manager — he IS the decision maker

---

## Signup barrier (critical product issue)

The innovation manager tried to create an account and got the impression she needed her IT manager and Ops manager to approve it first.

**This is a blocker for the primary ICP.**

Oliver will not create a ticket with his IT team to try a new tool. He signs up, plays with it, and either gets value in 20 minutes or he leaves.

### What needs to change

The free trial must work completely independently, with no integrations required to see value:

1. Sign up with just an email address — no company details, no admin approval language
2. The first screen after signup should show something useful immediately (demo data, a test inbox, or a sample triage run)
3. Remove any UI language that implies multi-person approval or enterprise setup
4. Connecting a real inbox should be optional in the trial — let Oliver see the AI working on sample emails before he commits to giving access

This is not a marketing problem. It is a product problem. Fixing it increases trial conversion directly.

---

## Secondary ICP (do not pursue until primary ICP has one paying customer)

E-commerce operations manager at a D2C brand, 20–100 employees, using Shopify. High seasonal volume, needs AI to handle order/delivery/returns queries. Different product surface (more Shopify integration, less AI decision-making) — treat as a separate motion.

---

## Questions to answer at next meeting

1. Do we have anyone in our network who matches Oliver's profile?
2. What does "getting one customer" look like — free beta user or paying customer?
3. Is the free trial signup flow fixable before the next meeting?
