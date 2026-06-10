# Ranger — Product Design
**Date:** 2026-06-10
**Status:** Direction document — not yet an implementation plan

---

## What Ranger Is

Ranger is a multi-tenant email outreach SaaS. It finds the right prospects for you — based on a customer-defined ICP — enriches them, personalises the outreach with AI, and sends via the customer's own email account.

**Positioning:** "Find the right people. Fill your pipeline."

**The differentiator:** ICP-based lead discovery is built in. Competitors (Instantly, Lemlist, Apollo) make you bring your own list. Ranger finds the list for you using SearXNG + Playwright, then enriches each lead before a single email is sent.

**Target market:** B2B teams (5–50 people) who want quality outreach to exactly the right people — not high-volume spray-and-pray.

---

## What Ranger Is Not

- Not InboxIQ. The inbox management, triage, and AI reply features are not part of Ranger.
- Not a shared sending platform. Ranger does not manage sender domains. Each customer connects their own Gmail, Outlook, or SMTP account.
- Not multi-channel at launch. Email only. LinkedIn outreach is a future addition.
- Not a CRM. Ranger tracks leads through a campaign lifecycle, not a full sales pipeline.

---

## Origin

Ranger is extracted from InboxIQ's internal marketing ops pipeline — the email outreach, lead discovery, and enrichment modules that were built for internal use. The Google Trends signal (Instantly, Lemlist, Salesloft all at "Breakout" in the UK market, June 2026) confirms there is strong, growing demand for exactly this product category.

InboxIQ will be archived once Ranger is live and CaseDesk has absorbed InboxIQ's operational features. Ranger is not a fork of InboxIQ — it is a clean extraction of its most valuable pipeline into a focused, shippable product.

---

## Architecture

Ranger is a new repository. It does not carry InboxIQ's 38 directories and 43 API blueprints. It starts lean.

**Code origin — three sources:**

| Module | Source |
| --- | --- |
| Lead discovery (SearXNG + Playwright MCP) | Port from InboxIQ `src/mcp/lead_discovery_mcp.py` |
| Lead enrichment MCP | Port from InboxIQ `src/mcp/enrichment_v2_mcp.py` |
| Email campaigns + sending | Port from InboxIQ `src/outreach/`, `src/models/campaigns.py` |
| DSPy email personalisation | Port from InboxIQ `src/dspy/email_personalization.py` |
| Connection model (sending accounts + AI) | Borrow from CaseDesk `models/connections.py` |
| Account / auth / multi-tenancy | Borrow from CaseDesk `models/auth.py` patterns |
| ConnectorResult fallback pattern | Borrow from CaseDesk `services/connector_service.py` |
| Celery task structure | Borrow from CaseDesk `celery_casedesk.py` pattern |
| `make ai-context` infrastructure | Borrow from CaseDesk `Makefile` + scripts |

**Folder structure:**

```
ranger/
├── app.py
├── config.py
├── extensions.py
├── celery_ranger.py        # explicit task imports, no autodiscover
│
├── models/
│   ├── auth.py             # Account, User
│   ├── connections.py      # Sending accounts + AI provider (CaseDesk pattern)
│   ├── leads.py            # Lead, ICP definition
│   ├── campaigns.py        # EmailCampaign, CampaignStep
│   └── outreach.py         # EmailOutreach, tracking events
│
├── mcp/
│   ├── lead_discovery_mcp.py
│   └── enrichment_mcp.py
│
├── dspy/
│   └── email_personalization.py
│
├── api/v1/
│   ├── auth.py
│   ├── icp.py
│   ├── leads.py
│   ├── campaigns.py
│   └── connections.py      # sending account setup + Test Connection
│
├── jobs/
│   ├── discovery.py        # Celery: ICP search + enrichment
│   └── sending.py          # Celery: send + track
│
├── services/
│   ├── connector_service.py
│   └── campaign_service.py
│
├── frontend/               # Built from scratch — premium UI
│
├── infra/                  # Deployment configs
├── docs/
│   └── ai_context/
│       └── sqlalchemy_relationships.md
└── Makefile
```

---

## Multi-Tenancy

Every model is scoped by `account_id`. No data crosses account boundaries. Pattern is identical to CaseDesk — every query includes `.filter_by(account_id=account_id)`.

Each account configures independently:
- Their own ICP definitions (can have multiple)
- Their own sending account (Gmail / Outlook / SMTP)
- Their own AI provider and model (BYOAK — same pattern as CaseDesk)
- Their own lead lists and campaigns

---

## The Core Loop

```
1. Connect sending account
   Gmail / Outlook / custom SMTP
   Test Connection required before account activates (CaseDesk pattern)

2. Define ICP
   Industry, company size, role, geography, keywords
   Multiple ICPs per account — each can seed its own campaigns

3. Lead discovery  (Celery job)
   SearXNG + Playwright MCP searches for matching prospects
   Returns: name, company, email, LinkedIn URL

4. Enrichment  (Celery job)
   enrichment_mcp fills: title, company size, tech stack, intent signals
   Lead scored against ICP — match % stored on lead record

5. Campaign composition
   User selects leads and builds a sequence
   (step 1 email + up to 3 follow-ups, configurable delay between each)
   DSPy personalises each email using enriched lead data
   User reviews and approves before anything sends

6. Sending  (Celery job)
   Sends via connected account
   Tracks: sent, opened, clicked, replied — per lead
   Auto-pauses sequence on reply — no follow-up after a response
   Unsubscribe link included in every email

7. Reporting
   Per-campaign: sent / opened / clicked / replied rates
   Per-lead: full event history
```

---

## Connections — Sending + AI

Ranger uses the CaseDesk `Connection` model pattern. Two connection types per account:

**`connector_type = "sending"`**
- Gmail (OAuth)
- Outlook (OAuth)
- Custom SMTP (host, port, username, password)

**`connector_type = "ai_provider"`**
- BYOAK — same as CaseDesk
- Used for DSPy email personalisation
- Small / medium / large tiers, each independently configurable

Every connection row has `last_test_status` and `is_active`. A sending account or AI provider cannot be used until it passes Test Connection.

---

## UI Direction

The current InboxIQ marketing ops screen is functional internal tooling. Ranger's UI is a product — built to the standard of Instantly and Lemlist, not adapted from what exists.

**Key screens:**

1. **ICP Builder** — the most important screen. Must be beautiful, interactive, and intuitive. Users define who they're targeting with immediate visual feedback. Not a form — a guided experience.

2. **Lead Discovery** — shows prospects being found in real time as the MCP searches. Status per lead: discovered → enriched → ICP match score.

3. **Campaign Composer** — sequence builder with step visualisation. DSPy preview shows personalised email per lead before sending. Approve/edit per lead or in bulk.

4. **Campaign Dashboard** — per-campaign metrics: sent, opened, clicked, replied. Clean stats, not a data dump.

5. **Connections** — sending account + AI provider setup. Test Connection button inline. Clear status: connected / unhealthy / missing.

**Frontend approach (confirmed 2026-06-10):** React SPA — Vite + React, no Next.js.

Flask is a pure API (JWT auth, JSON endpoints, no Jinja2 for app screens). The ICP Builder and Lead Discovery feed require complex interactive state and real-time streaming that pushes Jinja2 + Alpine.js beyond its natural fit.

Stack:
- `shadcn/ui` + Tailwind — component quality of Linear/Instantly without building from scratch
- TanStack Query — data fetching and caching
- Vite — build tool (no SSR needed — Ranger is fully behind auth)

Premium UI is non-negotiable.

---

## Infrastructure

**Decision (confirmed 2026-06-10):** ECS Fargate — eu-west-2, mirroring CaseDesk's infra setup.

Ranger does not share the InboxIQ EKS cluster. It runs independently on Fargate in eu-west-2 from day one. CaseDesk already runs on Fargate in eu-west-2 — the task definitions, IAM roles, and deployment patterns transfer directly.

**Why Fargate over EKS:**
- £0 control plane (a new EKS cluster would cost ~£73/month)
- eu-west-2 is the right region for a UK/EU B2B SaaS — lower latency, cleaner data residency story
- CaseDesk expertise already in place — no new ops patterns to learn

**Cost:**

| Item | Cost | Note |
| --- | --- | --- |
| ECS Fargate control plane | £0 | No cluster to manage |
| Web + worker tasks | ~£25-35/month | Scales to zero when idle |
| RDS `db.t4g.micro` | ~£15-20/month | Ranger-only, never shared |
| Redis (Fargate sidecar or ElastiCache `t4g.micro`) | ~£0-15/month | Start with sidecar, upgrade if needed |
| ALB | ~£15/month | Ranger-dedicated |

**Infra folder structure (`ranger/infra/`):**

```
infra/
├── ecs-web.json           # web task definition
├── ecs-worker.json        # Celery worker task definition
├── ecs-beat.json          # Celery beat task definition
├── alb.tf / alb.json      # ALB + target groups
├── rds.tf                 # RDS instance
└── iam.tf                 # task execution roles
```

Mirror CaseDesk's `infra/` structure exactly. Same GitHub Actions deployment pattern.

Region: eu-west-2. Same AWS account as CaseDesk and InboxIQ.

---

## What InboxIQ Modules Are Retained

**Ported to Ranger:**
- `src/mcp/lead_discovery_mcp.py`
- `src/mcp/enrichment_v2_mcp.py`
- `src/mcp/search_mcp.py`
- `src/outreach/email.py` (AWS SES sending, link tracking, unsubscribe)
- `src/outreach/tasks.py`
- `src/models/campaigns.py` (EmailCampaign, EmailOutreach, CampaignSender)
- `src/models/leads.py`
- `src/dspy/email_personalization.py`
- `src/kb/` — Knowledge base infrastructure (models, retrieval, embeddings)
- `src/retrieval/` — pgvector semantic search

**Knowledge base — ported with new content:**

The KB is retained but repurposed. In InboxIQ it supported inbox triage. In Ranger it feeds the email personalisation pipeline — DSPy draws on KB articles when composing and personalising outreach emails.

Each account's KB holds:
- Company messaging and value propositions
- Product or service descriptions
- ICP-specific pain points and objections
- Campaign playbooks and proven subject line patterns

The KB content from InboxIQ (inbox triage articles, Gmail/Outlook guides) is not migrated. Ranger starts with a blank KB per account. Users populate it — or Ranger pre-fills it based on their website URL during onboarding.

The embeddings infrastructure (`src/retrieval/`, pgvector) is ported unchanged. The content is new.

**Left in InboxIQ / not ported:**
- Inbox management (Gmail/Outlook triage, AI reply drafting)
- Content / blog / publishing
- LinkedIn / YouTube / HeyGen
- Booking
- Tickets
- Compliance
- Landing pages
- Social auth (except OAuth for sending account connection)
- Funnel analytics (complex — Ranger has its own simple campaign reporting)

---

## InboxIQ Retirement

Once Ranger is live and the outreach pipeline has been migrated:

1. Verify all outreach campaigns are running in Ranger
2. Verify no active customers depend on InboxIQ's inbox management features (CaseDesk absorbs these)
3. Archive InboxIQ GitHub repository — never delete (SOC2 / CASA audit trail)
4. Scale EKS node group to 0 → delete cluster
5. Delete InboxIQ RDS, ElastiCache, ALB

Same teardown sequence as documented in `docs/strategy/ticket_as_unit_of_work.md`.

---

## Phase 2 — Booking MCP (Post-Launch Upsell)

Not in v1. Designed now so the architecture accommodates it cleanly.

### What it does

When a lead replies to an outreach sequence, Ranger can insert a personalised, expiring booking link into the follow-up email. When the lead books a slot, the MCP server creates a calendar invite in the sender's Gmail or Outlook and sends a confirmation email to the attendee.

### Connection reuse — no separate credential

The user's Gmail or Outlook OAuth token is already registered in Ranger's `Connection` model for sending. The booking MCP reuses that same connection — the `access_token` on the active sending connection is the calendar credential. No new connection screen. No separate OAuth flow.

### Load pattern — context-driven, not always-on

The MCP subprocess only starts when the context demands it:

```
Sequence step configured as "book_meeting"?
        ↓
Account has booking feature access?     ← plan gate
        ↓
Active sending connection present?      ← OAuth token already there
        ↓
booking_mcp subprocess starts
        ↓
Tool call executes
        ↓
Subprocess exits
```

No idle process. No memory cost for accounts on the base plan. The `PersistentMCPClient` pattern from InboxIQ handles instantiation — the plan gate is checked before the client is created.

### MCP tools exposed

```
generate_booking_link(lead_id, context, ttl_hours)
    → short-lived URL with lead context embedded

book_slot(booking_id, slot_datetime, attendee_email)
    → confirms the selected slot

create_calendar_invite(booking_id)
    → adds event to sender's Gmail / Outlook calendar via existing OAuth token
```

No video. No confirmation email beyond what the calendar invite provides. The MCP's job is exactly: generate link → slot confirmed → invite in calendar.

### Positioning

- Base Ranger: find leads → send outreach → track replies
- Booking add-on (upsell): reply → insert booking link → lead books a slot → invite lands in the sender's calendar automatically

Calendly charges £8-12/month for this alone. Ranger bundles it into the outreach flow as an upgrade — no separate tool, no context switching.

### Marketplace distribution (deferred — post-Ranger validation)

The booking MCP server is self-contained — it takes a connection token, generates a link, creates a calendar invite. Nothing about it is specific to Ranger.

It can be published to MCP marketplaces (Anthropic, Smithery, others) for any agent or AI product to call. A developer building a sales agent in Claude, GPT, or any other framework could plug in `booking_mcp` without building calendar integration themselves.

**Sequencing decision (confirmed 2026-06-10):** Build for Ranger first. Run in production for 30–60 days. Once the integration is stable and the security posture around OAuth token handling is proven, publish to marketplace as a separate initiative. The server requires no changes — the only difference is who calls it and how external billing is handled.

Do not publish before Ranger's booking feature is production-validated. Paid marketplace distribution also requires per-call metering infrastructure (Stripe) that is not yet built.

---

## Open Decisions (resolve before implementation plan)

1. **Infrastructure:** Kubernetes (EKS) vs ECS Fargate
2. **Frontend approach:** React SPA vs Jinja2 + Alpine.js + HTMX
3. **Domain:** `getprowl.ai` — registered 2026-06-10 on GoDaddy
4. **Billing:** Stripe — pricing tiers to be defined (competing at £37-39/month entry point)
5. **LinkedIn outreach:** future roadmap — not in scope for v1
