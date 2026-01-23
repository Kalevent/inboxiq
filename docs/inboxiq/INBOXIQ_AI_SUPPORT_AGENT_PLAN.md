# InboxIQ: AI Support Agent (Auto Ticket Triage)

**Value proposition:** For small support teams, we solve overwhelming inbox chaos by automatically triaging emails into structured, prioritized tickets — so nothing is missed and response time drops by 80%.

## Core Focus (keep agents blueprint)
- Keep the existing agents blueprint and `app/api/v1/agents.py` as the compatibility entrypoint; add new triage endpoints there instead of inventing a new surface.
- Single job: turn every incoming email into a structured, prioritized ticket automatically.
- Aha moment: user connects inbox → sees the first 5 emails auto-triaged into tickets with priority + category + sentiment in under 60 seconds.
- Success checks: time-to-first-ticket < 2 minutes from signup; ≥90% of inbound emails become tickets; manual correction rate on category/priority <15% after day one.

## Market Size & Opportunity
- Extremely large TAM: every business with support emails (SaaS startups, e-commerce, SMEs, agencies, customer service teams, healthcare admin, logistics, hospitality, real estate, B2B support desks).
- Category is huge and expanding.

## Problem Urgency
- Very high: support delays drive churn, bad reviews, inefficiencies, burnout, and SLA violations.
- InboxIQ functions as a painkiller rather than a vitamin.

## Competitive Landscape
- Crowded and fast-moving: Zendesk AI, Intercom AI agent, Front, Freshdesk, HelpScout, Zoho Desk, Ada, Forethought, Lang.ai.
- Gaps: many incumbents are expensive or enterprise-focused.
- Differentiators for InboxIQ: fast onboarding, lower cost, works directly in inboxes, integrates with CRM/workflows/AI agents, and runs fully private without external CRMs—positioned for SMB and mid-market.

## Willingness to Pay
- Medium to very high: common bands of £49–£299/mo for AI support; select enterprise segments at £400–£800/mo.
- If staff workload drops, ROI is easy to justify.

## Adoption Barriers
- Low to medium: connect email, auto-train the agent, no behavior change, no migration to pricey help desks—strong for early adoption.

## Operational Cost (You)
- Medium to high depending on email volume, classification calls, sentiment analysis, vector search, and ticket creation logic.
- Cost controls: tool budgets, local HF models, DeepSeek-R1, and rate limits.

## Revenue Potential
- Very high recurring revenue with enterprise-scale headroom.

## Side-by-Side Summary
| Factor | AI Scheduling | AI Support Agent |
| --- | --- | --- |
| Market Size | Large | Very Large |
| Urgency | High | Very High |
| Competition | Medium | High |
| Differentiation | High (AI conflict detection) | Medium-High (SMB-focused AI agent) |
| Willingness to Pay | Medium–High | High |
| Adoption Barrier | Medium | Low |
| Your Operational Cost | Low-Medium | Medium-High |
| Revenue Potential | Medium-High | Very High |
| Time to Value for Customer | Medium | Fast |
| Time to Onboard | Medium | Fast |
| Virality | Low | Medium |

## Consulting Synthesis
- Both opportunities are strong, but the AI Support Agent (InboxIQ) wins on market size, urgency, willingness to pay, onboarding speed, and long-term revenue potential.

---

# Landing Page Copy for InboxIQ

## Hero
**Your AI Support Agent. Automatically triage emails and create tickets 24/7.**

- Never miss an urgent customer message again.  
- Reduce response time by 80%.  
- Scale support—without scaling headcount.

✔ 7-day free trial  
✔ No credit card required  
✔ Works with Gmail, Outlook, custom domains

## One Core Feature
### Automatic Email → Ticket Conversion (Powered by AI)
InboxIQ reads every incoming email, identifies intent, extracts relevant details, and instantly creates a structured support ticket in your system.

What InboxIQ does automatically:
- Detects topic (billing, bug, onboarding, refund, general support, etc.)
- Assigns sentiment (angry, frustrated, neutral, satisfied)
- Extracts entities (order number, phone, customer ID)
- Prioritizes urgent cases
- Creates a ticket in Kalevent’s CRM
- Routes to the right team or agent

Configure once; InboxIQ handles the rest. No manual triage, no backlog, no chaos.

## Three Benefits
1) Reduce response times by 80%: mindless sorting disappears; teams focus on high-value replies.  
2) Zero missed messages: every email becomes a clean, trackable ticket—no forgotten inboxes or dropped leads.  
3) Scale without hiring: replaces repetitive triage work, saving hundreds of hours and thousands in staffing; most users see ROI in the first week.

## Testimonials
- “InboxIQ cut our support workload in half.” — Sarah M., COO of HealthFlow Clinics  
- “We used to drown in emails. Now everything is neatly triaged.” — Jake L., Founder @ QuickServe  
- “We responded 4× faster and customer satisfaction shot up.” — Maria S., Customer Success Lead @ Finlytics  
*(Swap in real customer names when ready.)*

## Pricing
- **Free Trial — 7 days:** Full access; no credit card.  
- **Pro — £29/month per inbox:** Automatic triage, AI ticket creation, priority routing, sentiment, custom categories, up to 3,000 AI actions/month.  
- **Business — £99/month per inbox:** Everything in Pro plus up to 15,000 AI actions/month, multi-agent routing, team analytics, SLA breach alerts, API access, priority support.  
- **Enterprise — Custom:** Unlimited AI actions, dedicated infrastructure, custom workflows, compliance packages (HIPAA-ready), dedicated account manager.

## Workspace seat invites (how teams join an existing workspace)
- Owners invite teammates via the app/API instead of asking them to self-signup (which would create a new workspace).  
- Flow: authenticated owner calls `POST /users/invite` with teammate email (account inferred from the JWT) → system creates the user stub, reserves a seat, sends activation email with workspace ID baked in.  
- Teammate clicks activation link, sets password, and lands in the same workspace—no extra signup required.  
- Seat limit enforced: invites fail with 403 if `seats_used >= seats_limit`.  
- Admin UI follow-up: add a simple “Invite teammate” form under Settings → Team to wrap this endpoint.

## ROI Calculator (Content)
Prompts to collect:
- Support emails per month  
- Time spent triaging each email (default: 2 minutes)  
- Team cost per hour (default: £20/hr)  

Outputs:
- Hours saved per month  
- £ saved in labor cost  
- % faster response time  
- “Pays for itself in under N days.”

## Demo Video Script (60 seconds)
1) Problem (5s): cluttered inbox, hundreds of unread emails, overwhelmed team.  
2) Enter InboxIQ (5s): “Meet your AI Support Agent.”  
3) Email Triage (10s): real-time reads—“Billing issue detected,” “High urgency,” “Extracted: Invoice #8831.”  
4) Ticket Creation (10s): automatic ticket card with structured fields.  
5) Routing (10s): “Assigned to Billing Team — SLA: 2h,” “Escalated due to negative sentiment.”  
6) Analytics (10s): dashboard showing 80% faster triage, 40% fewer SLA breaches, 2× CSAT improvement.  
7) CTA (5s): “Start your 7-day free trial. No credit card required.”

## Call to Action
Start your free trial → Instant setup, no credit card. Get your AI Support Agent running in under 60 seconds.

## Slim V1 build (app/api/v1/agents.py)
- Endpoints (reuse agents blueprint): `POST /api/v1/agents/inboxiq/triage` (ingest single email payload or batch from Gmail/Outlook webhook), `GET /api/v1/agents/inboxiq/tickets` (paginated list), `POST /api/v1/agents/inboxiq/tickets/<id>/override` (manual reassign category/priority), and OAuth callback helpers for Gmail/Outlook under the same blueprint.
- Flow: webhook → triage worker → `Ticket` row (subject, sender, category, priority P0–P2, sentiment, extracted IDs, status=new, source message-id, link to provider).
- AI pipeline (deterministic defaults first): cheap classifier (rules or small model) for category/priority/sentiment; fallback to heavier LLM only on low-confidence; extract entities (order/customer IDs) with regex first then LLM; log decision + confidence per field.
- UI: single setup screen to connect inbox; ticket queue with subject, category, priority, sentiment, and link to original email; override form writes back through `POST /tickets/<id>/override`.
- Ops guardrails: idempotency on message-id to avoid double-create; retries with backoff; rate-limit LLM calls; redact secrets on logs; flag low-confidence tickets for human review.
- Defer: multi-inbox, SLA rules, analytics dashboards, auto-replies, custom categories, bulk imports. Keep the blueprint stable so existing consumers don’t break.

## Slim Product Spec (preserve kalevent_mcp)
- Surface: keep `app/api/v1/agents.py` and Kalevent MCP (`kalevent_mcp`) intact; expose the triage endpoints through the existing agents blueprint so MCP consumers can continue to call through a stable surface.
- User: small support teams (1–10 agents) drowning in email; they likely use Gmail/Outlook and spreadsheets, not full Zendesk.
- Objective: first 5 emails auto-triaged into tickets within 60s of connecting inbox; no setup beyond OAuth and selecting a default team.
- Data model (minimum): `Ticket(id, subject, from_email, category, priority, sentiment, entities JSON, status, message_id, provider, provider_thread_url, created_at, updated_at)`.
- Providers: Gmail + Outlook OAuth only in v1; IMAP/SMTP deferred. Use existing MCP email tools if available in `kalevent_mcp` to fetch/poll.
- AI: start with rules/cheap model for category/priority/sentiment; escalate to LLM on low confidence; store confidence per field. Entity extraction: regex for IDs first, then LLM fill. Log all decisions for inspection.
- Safety: dedupe on `message_id`, retry queue with backoff, dead-letter for failures, rate-limit LLM calls, redact secrets on logs, mark low-confidence tickets as `needs_review`.
- Telemetry: time from OAuth completion → first ticket; % emails triaged; % manual overrides; classification accuracy sampled via overrides.

## Onboarding Flow (happy path)
1) Landing → CTA: “Connect your inbox.”
2) OAuth: choose Gmail or Outlook; after success, show “Connected” check and start background sync.
3) Progress screen: “Triaging your last 20 emails…” with a spinner; once 5 are done, show a green banner “5 tickets created — go to your queue.”
4) Ticket queue: list view with subject, category, priority, sentiment, status. Link to original email/thread. Inline override for category/priority.
5) Optional: send a daily digest email/Slack after v1; not required for GA.
6) Empty/dry-run mode: if no inbox connected (demo), seed 5 sample emails and show triage results to prove the value.


## Next Step Options
1) HTML + Tailwind code for this page  
2) Modern UI design mockup  
3) Full onboarding funnel (email → dashboard)  
4) Product explainer video animation script  
5) Product Hunt launch kit  
6) SEO strategy for “AI support agent” keywords  
7) Implementation plan inside Flask + AngularJS app
