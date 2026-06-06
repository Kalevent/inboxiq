# CaseDesk — Strategic Direction
## The Ticket as the Unit of Work

**Date:** 4 June 2026
**Status:** Direction document — not yet an implementation plan

---

## The Genuinely Novel Piece

Every existing tool — OTRS, Zammad, Mattermost, ServiceNow — assumes the same thing:

> A human describes the organisation. The system executes what the human described.

Someone builds the playbook. Someone defines the process. Someone configures the workflow. The system then runs it faithfully.

CaseDesk inverts this:

> Work arrives. The system observes. The system proposes. The human approves.

Nobody builds the playbook. Nobody configures the workflow. The organisation does not model itself. The system learns the organisation from observed work — and proposes process back to the humans who do that work.

That is not a better ticketing system. That is a different category.

This is the section of the document worth refining most. Everything else — tickets, workflows, templates, lifecycle, APIs — is implementation. This is the reason CaseDesk exists.

---

## What CaseDesk Is

Operational work arrives through multiple entry points and gets lost because there is no consistent lifecycle for managing it.

Entry points fall into two categories — **human-initiated** and **system-initiated**. The ticket lifecycle is identical for both. What differs is how the classifier handles them and how much of the workflow runs without human involvement.

**Human-initiated — a person sends or submits something:**

- Email or shared inbox
- Website contact form or customer portal
- Internal request form or referral form
- Social media message
- Voice — phone call, voicemail, IVR response, recorded meeting
- Video — uploaded footage, match recordings, meeting replays, training content
- Manual creation

**System-initiated — a machine pushes an event:**

- Webhook — payment notification (Stripe), delivery update, integration trigger
- API submission — partner system pushes a record, CRM sync, data feed
- Scheduled trigger — deadline reached, SLA breach, calendar event, recurring job

Human-initiated work often needs a reply drafted, sentiment assessed, and a person assigned. System-initiated work almost always closes automatically — a record is created, an API is called, the ticket closes. Exceptions in system-initiated workflows surface to humans only when something fails.

Regardless of where work arrives, it needs the same thing: an owner, a status, a history, and a resolution.

**Voice and video are premium entry points.** Processing them requires transcription and frame analysis, which carry real inference and infrastructure cost. They belong in the architecture — every business uses the phone, and industries like sports, legal, media, and professional services generate significant work from recorded content — but they are positioned as upsell rather than base tier. A sports analyst reviewing match footage to extract decisions, flag patterns, and assign tasks to coaches is the same ticket lifecycle as every other entry point. The volume and cost profile is just different. CaseDesk provides that — for every entry point, in one place.

CaseDesk is a lightweight operations platform for small teams. It receives work from any entry point and tracks each piece through a defined lifecycle until it is resolved. It routes to humans or calls APIs depending on what each task requires.

It is not an inbox management tool. It is not a helpdesk. It is the operational layer that sits between incoming work and completed work.

> *"CaseDesk turns incoming requests into completed work — by routing to humans or calling APIs, depending on what the task requires."*

---

## The Core Principle: Ticket as Unit of Work

The ticket represents the **problem being solved**, not the message that arrived.

A customer who emails, then calls, then tweets about the same issue creates one ticket — not three. All inputs attach to the same record. The ticket has a lifecycle:

```
received → triaged → assigned → in_progress → pending_approval → resolved → closed
```

Each transition is an event. Every input received, every action taken, every reply sent is recorded against the ticket. The full history is visible in one place.

**Not every message creates a ticket.** The intelligence layer decides:

```
Message arrives (any channel)
        ↓
Is this work?
        ↓              ↓
      Yes              No
       ↓               ↓
Create ticket      Log and file
Enter lifecycle    No further action
```

Some inputs are informational, conversational, or noise. They do not require tracking. The triage pipeline classifies every message before deciding whether a ticket is created.

**Forms are the exception.** A form submission is almost always work — someone filling in a form has intent. Every form submission enters the ticket lifecycle immediately, with no classification required. This makes forms the lowest-friction entry point for new organisations.

---

## Entry-Point-Agnostic Architecture

CaseDesk does not require any specific entry point. Each organisation connects what they already have.

| Organisation | Connected entry points | Ticket source |
|---|---|---|
| Charity | Contact form only | Every submission |
| SaaS team | Gmail only | Classified emails |
| Operations team | Gmail + form + social | All three, unified |
| MSP | Webhook + email + portal | All three, unified |
| Sports analyst team | Video upload + email | Classified footage + correspondence |
| New user | Nothing yet | Manual ticket creation |

The intelligence layer operates per entry point:

```
── Human-initiated ──────────────────────────────────────────────────────
Email connected      → triage classifies messages          → work? → ticket
Form connected       → every submission is work             → ticket always
Social connected     → triage classifies messages          → work? → ticket
Voice connected      → transcribed, then classified        → work? → ticket
Video connected      → transcribed + analysed, classified  → work? → ticket
Manual               → created directly                     → ticket always

── System-initiated ─────────────────────────────────────────────────────
Webhook/API          → event type determines action         → ticket always
Scheduled trigger    → job fires, condition met             → ticket always
```

Human-initiated tickets may need a reply, a sentiment assessment, and a person assigned. System-initiated tickets run the workflow automatically and close unless an exception occurs — then and only then does a human appear.

The ticket is entry-point-agnostic. What matters is: something arrived, it may or may not be work, and if it is — track it to resolution.

---

## The Routing Layer — Work to the Most Appropriate Resource

Every ticket, once classified as work, is routed to the most appropriate resource. That resource might be an AI model, a human, an API, or a workflow template. CaseDesk treats this as a single question — not three separate mechanisms bolted together.

> *Route work to the most appropriate resource — whether that resource is a model, a person, an API, or a workflow.*

**All resource types in one view:**

| Complexity | Resource | Example |
|---|---|---|
| simple | AI: small model | "Where is my invoice?" |
| medium | AI: mid-tier model | "I need to reschedule my appointment" |
| complex | AI: strongest model | "Customer claims breach of contract and demands refund" |
| high_risk | Human: review queue | "Patient safeguarding concern involving vulnerable child" |
| structured | Workflow: template | New employee onboarding — spawns child tickets |
| executable | API: external or internal | Stripe charge, device provisioning, internal webhook |

**The two-stage handoff — no conflict:**

The routing decision involves two distinct judgements, handled by two files that operate in sequence:

```
Stage 1 — model_router.py
  Question: can this be handled automatically, and at what cost?
  Output:   small / medium / large / human_review

Stage 2 — router.py
  Question: given that decision, which specific resource handles it?
  Output:   model ID, person, team, API endpoint, or workflow template
```

When `model_router.py` returns `human_review`, AI processing is skipped entirely. `router.py` receives the signal and assigns directly to the appropriate human review queue — no AI draft is generated, no model is called. This is the clean handoff that removes the conflict.

When `model_router.py` returns a model tier (`small`, `medium`, `large`), AI processes the ticket. `router.py` still runs — it assigns a human owner to review, approve, or follow up on the AI output. Human ownership is present in all paths. The difference is whether AI acts first or the human acts first.

**Why DSPy, not keyword rules:**

A keyword router works as a first pass — `if "password reset" in text: return SMALL_MODEL` — but it becomes brittle immediately. It cannot generalise, it misses edge cases, and it requires constant manual updates. DSPy replaces this with a structured reasoning signature that outputs the complexity tier and a reason for the decision.

A rule-based pre-filter still runs before DSPy for obvious cases — short messages under 50 tokens, out-of-office replies, automated receipts. These route directly to `small` with no inference cost. DSPy handles the ambiguous cases where complexity genuinely needs to be assessed.

The tier names map to actual model IDs and queue names in `config.py`, not in the router. Models can be swapped without touching routing logic.

**The full triage pipeline:**

```
classifier.py     → is this work?
model_router.py   → which AI tier, or route straight to human_review?
router.py         → which specific resource (model ID, person, team, API, workflow)?
observer.py       → record outcome (resource used, cost, resolution)
```

Each file has one responsibility. The output of each stage is the input to the next. `router.py` always runs — it assigns ownership regardless of whether AI processed the ticket first.

**The optimisation flywheel:**

Every routing decision recorded by `observer.py` becomes a training example:

```
ticket → complexity → resource_used → outcome → cost
```

DSPy is optimised against this dataset. The router learns — from actual CaseDesk usage — which requests genuinely require expensive resources and which can safely use cheaper ones. No synthetic labels. No manual tuning. The improvement comes from the work itself.

This is the "system learns from observed work" principle applied directly to cost and quality. The longer CaseDesk runs, the more accurate and efficient the routing becomes.

---

## Workflow Orchestration — One Trigger, Multiple Tasks

A single incoming message can represent a structured workflow requiring multiple people and systems.

**Example — New employee joins:**

HR sends an email: *"John Smith starts Monday as Operations Manager"*

CaseDesk recognises this as a workflow trigger, not just a message to reply to.

```
Parent ticket: New Employee — John Smith
│
├── Task 1 → IT team:   Set up laptop       (automated — calls device provisioning API)
├── Task 2 → IT team:   Create accounts     (automated — calls Microsoft 365 API)
├── Task 3 → Manager:   Approve access      (human — required before Task 2 runs)
└── Task 4 → HR:        Send welcome pack   (human — assigned, tracked to completion)
```

Each task is its own ticket. The parent ticket tracks overall completion. Progress is visible to everyone involved — including the person who triggered it.

**What this requires:**

1. **Workflow templates** — defined once, triggered from any input channel
2. **Parent-child tickets** — one trigger spawns multiple coordinated tasks
3. **Task dependencies** — Task 2 cannot start until Task 3 is approved
4. **Mixed execution** — some tasks call APIs, some wait for humans
5. **A progress portal** — the trigger owner tracks where every task stands

---

## Execution Model — APIs, Not Code

CaseDesk does not write or execute code. It calls APIs.

When a task requires automated execution:

```
External API available?   → Call it
(Stripe, Microsoft 365, Google Workspace, QuickBooks, FHIR, etc.)
        ↓
Internal API available?   → Call it
(Client's own systems exposed via webhook or REST endpoint)
        ↓
Neither available?        → Assign to a human, track to completion
```

**The developer portal is the registration layer.** Organisations register their internal API endpoints in CaseDesk's developer portal. CaseDesk calls those endpoints as workflow steps — the same way it calls any external API. No code is written. The organisation exposes a webhook, CaseDesk calls it when the task requires execution.

CaseDesk is an orchestration layer. It knows what needs to happen and routes accordingly. It is not a development platform.

---

## The Unified Connection Layer

CaseDesk is only as intelligent as the systems it is connected to. The Unified Connection Layer is not a feature — it is the foundation that makes everything else possible.

Without connections, CaseDesk can observe that HR emailed about a new employee but knows nothing about:
- Who that person actually is — no CRM lookup
- What their role requires — no HR system access
- Which systems need provisioning — no directory service connection
- Whether budget is approved — no finance system access

The observation is useless without context. The context comes from connections.

**Four layers of connectivity — the LLM provider comes first:**

```
0. AI provider connector   — the foundational connector; nothing intelligent happens without it
   (OpenAI, Anthropic, local Ollama endpoint, or any OpenAI-compatible API)

1. Input connectors        — how work arrives into CaseDesk
   (Gmail, Outlook, web forms, social, voice, webhooks, API)

2. Knowledge connectors    — what CaseDesk understands about context
   (CRM, ERP, FHIR, HR systems, directories, internal databases)

3. Execution connectors    — what CaseDesk can act on
   (Microsoft 365, Google Workspace, Stripe, QuickBooks, internal APIs)
```

**The AI provider is the first connection every new account must make.** It is also the most important differentiator in CaseDesk's pricing model.

**BYOAK — Bring Your Own API Key (or local endpoint):**

CaseDesk does not bundle AI cost into its subscription. It calls whatever LLM endpoint the account configures. The tier names (`small`, `medium`, `large`) are abstract — each tier is configured independently and can point to a completely different provider. A mixture of cloud and local is not only supported, it is often the optimal setup.

**Per-tier provider configuration — the recommended pattern:**

| Tier | Provider | Model | Cost |
|---|---|---|---|
| small | Docker Model Runner (local) | `ai/phi4-mini` | free |
| medium | OpenAI API | `gpt-4o-mini` | fractions of a penny per ticket |
| large | Anthropic API | `claude-sonnet-4-5` | reserved for complex/high-risk only |

Each tier resolves independently at routing time. DSPy configures a per-tier LM:

```python
SMALL  = dspy.LM("openai/ai/phi4-mini",      api_base=account.local_endpoint)
MEDIUM = dspy.LM("openai/gpt-4o-mini",       api_key=account.openai_key)
LARGE  = dspy.LM("anthropic/claude-sonnet-4-5", api_key=account.anthropic_key)
```

`model_router.py` returns a tier name. `router.py` resolves it to the configured LM. CaseDesk does not know or care what fills each slot — it calls the tier, the tier resolves to the model.

**Supported provider types:**

```
Cloud API              → OpenAI, Anthropic, Google Gemini, Azure OpenAI
                         Any provider with an OpenAI-compatible endpoint

Local runtime          → Docker Model Runner (Docker Desktop 4.40+)
                         Ollama
                         LM Studio
                         Any process exposing an OpenAI-compatible API at a URL

Dedicated cloud GPU    → User's own GPU instance running any of the above runtimes
                         Their cost, their control, fully supported
```

**Docker Model Runner is a first-class local option.** It ships with Docker Desktop 4.40+ — no separate installation. Models are pulled like Docker images (`docker model pull ai/phi4-mini`). It exposes an OpenAI-compatible endpoint, so the connection is identical to any other provider:

```python
dspy.LM("openai/ai/phi4-mini", api_base="http://localhost:12434/engines/v1", api_key="unused")
```

Available models include `ai/llama3.2`, `ai/phi4-mini`, `ai/mistral-7b` and others from Docker Hub. For teams that already run Docker, this is zero additional infrastructure.

**One constraint on local endpoints:** the endpoint must be reachable from the CaseDesk server. For cloud-hosted CaseDesk (kalevent.com), a model on a developer's laptop is not reachable — but a model on an internal server exposed via URL (Cloudflare Tunnel, Tailscale, an internal IP) is. The settings field is always just a URL. CaseDesk does not manage the runtime.

**The optimal cost structure for most small teams:**

```
80% of tickets     → small tier → local model → free
15% of tickets     → medium tier → gpt-4o-mini → ~$0.001 per ticket
5% of tickets      → large tier → claude-sonnet → ~$0.01 per ticket
```

The `observer.py` flywheel learns this distribution from real usage and pushes more work toward the cheaper tier over time. The cloud bill shrinks as the system learns.

> *"AI is not a cost we mark up. You connect your own provider — OpenAI, Anthropic, or a model on your own hardware. CaseDesk pricing is pure software."*

This is a real differentiator against tools that hide AI costs inside a subscription. An organisation that runs Docker Model Runner or Ollama locally handles the majority of its work at zero AI cost. CaseDesk simply calls the endpoints they register.

**The settings screen this requires:** one page per tier — provider type, endpoint URL or API key, and model ID. Three rows, no developer required. Adding a new provider or swapping a model is a settings change, not a code change.

**Input connectors** determine what triggers a ticket. **Knowledge connectors** determine how intelligently that ticket is classified, routed, and enriched. **Execution connectors** determine how much of the resulting work can be completed without human intervention.

A CaseDesk instance with one Gmail connection and no knowledge or execution connectors is a basic ticket tracker. A CaseDesk instance with a full connection set is an operational intelligence platform. The intelligence scales linearly with the richness of connections.

**The developer portal registers all three layers.** Organisations connect their own systems — internal APIs, proprietary databases, bespoke tools — through the same registration interface. CaseDesk treats them identically to external integrations. No custom code required. Register the endpoint, define the schema, CaseDesk calls it.

---

## Organisational Memory

CaseDesk builds organisational memory from tickets, workflows, and connected systems.

Every ticket processed, every routing decision made, every workflow completed adds to a growing understanding of how that organisation works — who handles what, which requests follow which patterns, which workflows repeat, which systems are involved at each step.

Over time this means:

- The third ticket from the same sender is handled faster than the first
- A request that matches a previous pattern surfaces the workflow that resolved it
- Routing decisions improve without anyone reconfiguring anything

This is what makes CaseDesk more valuable the longer it is used — and progressively harder to replace.

> *"ServiceNow requires you to describe your organisation before it can help. CaseDesk learns your organisation by helping."*

---

## The Self-Building Knowledge Base

ServiceNow is built on a **Configuration Management Database (CMDB)** — a complete map of every asset, role, approval chain, and workflow in the organisation. Before ServiceNow can help, a human must build this map. That is why implementations take months and cost six figures.

CaseDesk does not ask the organisation to describe itself. It observes the organisation through the work it processes.

The inversion in practice:

- HR emails about a new employee → CaseDesk observes how the team responds
- IT creates an account → CaseDesk records that as a step
- Manager approves access → CaseDesk records that as a dependency
- The pattern repeats → CaseDesk proposes: *"This looks like a workflow. Should I save it as a template?"*
- The human approves → the workflow is defined from observed behaviour, not a visual editor

Nobody configured that workflow. Nobody even knew it was a workflow until CaseDesk surfaced it. The organisation did not model itself — the system learned the organisation from the work.

Over time, CaseDesk builds a living map of the organisation:

- Which messages constitute work for this team
- Which tasks get routed to which people
- Which workflows repeat and should be templated
- Which external systems are involved at each step

This map is never manually configured. It emerges from usage.

> *"ServiceNow requires you to describe your organisation before it can help. CaseDesk learns your organisation by helping."*

> *"ServiceNow knows what work is because you told it. CaseDesk knows what work is because it watched you."*

**What this looks like in practice — near term vs long term:**

Near term — *suggested workflow templates based on observed activity.* CaseDesk notices patterns and surfaces them: *"You have handled 7 requests like this the same way. Here is a suggested template — review and activate it."* The human reviews, approves, and the template is saved. This is achievable and valuable.

Long term — *autonomous workflow creation.* CaseDesk detects the pattern, scores its confidence, extracts the workflow structure including dependencies, proposes it for approval, and versions it over time. This requires pattern detection at scale, confidence scoring, workflow extraction, human approval UI, and versioning. It is significantly harder than the near-term version and should not be on the MVP roadmap.

The ambition is correct. The timeline must be honest.

The defensible advantage is not the feature — every feature can be copied. The moat is what accumulates over time:

- **Customer data** — tickets, workflows, routing decisions specific to that organisation
- **Learned workflows** — automation built from observed behaviour, not manual configuration
- **Organisational memory** — who handles what, which patterns repeat, which systems connect
- **Switching costs** — the longer CaseDesk runs, the more it knows, and the more painful it is to start again elsewhere

---

## The Difference from ServiceNow

| | ServiceNow | CaseDesk |
|---|---|---|
| Knowledge base | CMDB — manually configured | Self-building — learned from behaviour |
| Workflow definition | Admin builds in Flow Designer | Emerges from observed patterns |
| Onboarding | Months, requires consultant | Connect a channel, start immediately |
| Trigger | Button click in portal | Any incoming message on any channel |
| Execution | Rules engine + scripts | API calls + human tasks |
| Target market | Enterprise (500+ employees) | Small teams (5–50 people) |
| Cost | £50k+/year | Accessible pricing |

---

## What This Is Not

**Not a Zendesk clone.** Zendesk pulls the team into a separate dashboard. CaseDesk works behind the channels the team already uses. No migration. No new platform to learn.

**Not an inbox management tool.** The inbox is one input channel among several. CaseDesk is not about managing email — it is about resolving work regardless of where it arrived.

**Not a code execution platform.** CaseDesk calls APIs. It does not write or run code on behalf of users.

---

## The Foundation — What Already Exists

The current codebase is closer to this vision than it appears. The existing ticket model already has:

- `assigned_to`, `owner`, `team` — routing and assignment
- `due_at` — SLA and deadline tracking
- `provider` + channel derivation — multi-channel awareness
- `status` — lifecycle state (needs expansion to full state machine)
- `decision` JSON — workflow decision storage
- `category`, `priority`, `sentiment` — triage classification
- DSPy triage pipeline — already classifies every message

What is missing:

1. **Parent-child ticket relationships** — workflow orchestration
2. **TicketEvent model** — append-only audit log of every transition
3. **Workflow templates** — repeatable processes defined once
4. **Task dependencies** — step sequencing and approval gates
5. **API registration** — developer portal extended to register execution endpoints
6. **Progress portal** — visibility for all parties on a workflow instance

---

## CaseDesk Codebase Architecture

**CaseDesk is a standalone repo — not a subfolder of InboxIQ.**

A separate repository (`casedesk`) is created with a read-only reference copy of InboxIQ inside it. The reference copy is for porting pipelines and understanding patterns during development — it is never deployed, never executed. When CaseDesk is complete and every important pipeline has been migrated, the reference copy is deleted. What remains is a clean, lean application with no legacy surface area.

```
casedesk/                         # Standalone repo — root
├── app.py
├── config.py
├── extensions.py
├── celery_casedesk.py
│
├── models/
│   ├── __init__.py
│   ├── tickets.py                # Ticket, TicketEvent
│   ├── workflows.py              # WorkflowTemplate, WorkflowInstance
│   ├── workflow_tasks.py         # WorkflowTask, TaskDependency
│   └── connections.py            # Entry point + connector registry
│
├── api/
│   ├── __init__.py
│   └── v1/
│       ├── __init__.py
│       ├── tickets.py
│       ├── workflows.py
│       ├── connections.py
│       └── intake.py
│
├── intake/
│   ├── __init__.py
│   ├── email.py
│   ├── form.py
│   ├── webhook.py
│   └── voice.py
│
├── triage/
│   ├── __init__.py
│   ├── classifier.py             # is this work?
│   ├── model_router.py           # which AI tier, or human_review?
│   ├── router.py                 # which person, team, workflow, or API?
│   └── observer.py               # record outcome for optimisation
│
├── services/
│   ├── __init__.py
│   ├── ticket_service.py         # create, transition, append_event
│   ├── workflow_service.py       # start workflow, child tickets, dependencies
│   └── connector_service.py      # call external/internal APIs
│
├── jobs/
│   ├── __init__.py
│   ├── intake.py
│   ├── escalation.py
│   └── observer.py
│
├── dspy/
│   ├── __init__.py
│   ├── signatures.py
│   └── triage.py
│
├── templates/
│   ├── base.html
│   ├── inbox.html
│   ├── ticket.html
│   ├── workflows.html
│   └── portal.html
│
├── static/
│   ├── css/
│   └── js/
│
├── migrations/
│   └── versions/
│
├── tests/
│   ├── __init__.py
│   ├── test_tickets.py
│   ├── test_workflows.py
│   └── test_intake.py
│
└── reference/                    # InboxIQ source — read-only, deleted when done
    └── src/                      # Port from here, never run from here
```

`schemas/` is deferred — added when external customers consume the API, versioning is needed, or request validation becomes repetitive. Not before.

**Pipelines to port from reference — in order:**

| Pipeline | Reference location | Priority |
|---|---|---|
| DSPy triage + signatures | `reference/src/dspy/` | 1 — core intelligence |
| Email intake + Gmail/Outlook | `reference/src/api/v1/inboxiq.py` | 2 — primary entry point |
| Lead enrichment (MCP) | `reference/src/tasks/` | 3 — enrichment layer |
| Billing + Stripe webhooks | `reference/src/billing/` | 4 — monetisation |
| Auth (JWT, Account, User) | `reference/src/models/core.py` | 5 — identity layer |
| Upload infrastructure | `reference/src/uploads.py` | 6 — file handling |

Once a pipeline is ported and tested in CaseDesk, mark it done. When all six are marked done, `reference/` is deleted and InboxIQ is retired.

---

## CaseDesk Deployment Architecture

**Domain and compliance:**

```
getcasedesk.com     → 301 redirect to kalevent.com (GoDaddy, marketing only)
kalevent.com        → CaseDesk app, OAuth, all authenticated flows
```

`kalevent.com` remains the app domain. The CASA Tier 2 / SOC 2 assessment scope does not change — it covers `kalevent.com` and the AWS account behind it. No new assessment is required.

**Infrastructure — ECS Fargate (eu-west-2), same AWS account as InboxIQ:**

```
                        kalevent.com
                             │
                      Application Load Balancer
                             │
               ┌─────────────┴────────────┐
               │                          │
        ECS Service: web            ECS Service: worker
        (casedesk-web)              (casedesk-worker)
        0.25 vCPU / 2GB             0.25 vCPU / 1GB
        Flask app                   Celery worker
        Port 8080                   Long-running, no port
               │                          │
               └─────────────┬────────────┘
                             │
                    ┌────────┴────────┐
                    │                 │
              RDS Postgres      ElastiCache Redis
              (eu-west-2)       cache.t3.micro
                                Celery broker
```

**Same pattern as PolicyNumbers** — ECS task definitions, `REPLACED_BY_GITHUB_ACTION` image tag, Secrets Manager for credentials, CloudWatch for logs.

**Monthly cost estimate (eu-west-2):**

```
Web task      (0.25 vCPU, 2GB, always-on)    ~£14/month
Worker task   (0.25 vCPU, 1GB, always-on)    ~£10/month
RDS Postgres  (db.t3.micro)                  ~£15/month
ElastiCache   (cache.t3.micro)               ~£15/month
ALB                                          ~£18/month
────────────────────────────────────────────────────────
Total                                        ~£72/month
```

**Key difference from PolicyNumbers:** the worker task runs continuously (Celery consumes a Redis queue). PolicyNumbers jobs run and exit. The task definition pattern is the same — the `command` for the worker task is `celery -A celery_casedesk worker` rather than a one-off CLI command.

**Documentation — Docusaurus + Swagger, hosted free on Cloudflare Pages:**

Same toolchain as PolicyNumbers (`docs.policynumbers.com`). No additional hosting cost.

```
docs.kalevent.com          Docusaurus static site → Cloudflare Pages (free)
                           ├── Getting Started
                           ├── Authentication
                           ├── Quickstart
                           ├── API Reference (Swagger UI embed)
                           ├── Workflow Templates
                           ├── Connector Registry
                           └── MCP Integration
```

The Swagger/OpenAPI spec is served from the Flask app at `/api/docs`. Docusaurus embeds it. MCP integration gets its own section — CaseDesk will expose MCP servers for connector registration and ticket operations, the same way PolicyNumbers has `/mcp/overview`.

`docs.getcasedesk.com` is a Cloudflare redirect to `docs.kalevent.com` — same domain strategy as the main app.

---

## Target Market — Who Pays First

The customers most likely to pay quickly share three characteristics:

1. **Requests arrive from multiple channels** — email, phone, web form, walk-in, referral
2. **Work falls through the cracks** — things get missed, duplicated, or lost without a structured system
3. **They can spend money without a 12-month procurement process** — no IT committee, no enterprise tender, decision made by an owner or operations manager

These are not charities or the NHS. Those are validation targets. The paying market is:

- **Property management firms** — maintenance requests, tenant enquiries, contractor jobs, inspections
- **Recruitment agencies** — candidate queries, client briefs, compliance checks, interview coordination
- **Accounting firms** — client document requests, deadline tracking, HMRC correspondence, approvals
- **Consultancies** — project requests, client deliverables, internal approvals, scope changes
- **Managed service providers** — IT support tickets, SLA tracking, escalations, client reporting
- **Facilities management companies** — maintenance jobs, contractor dispatch, compliance certificates, inspections
- **Legal support teams** — matter intake, document requests, deadlines, client updates
- **Local service businesses** — bookings, complaints, follow-ups, supplier coordination

Every one of these businesses receives requests from multiple channels today and manages them with email, spreadsheets, or nothing. Every one of them has lost work because of it. None of them have a procurement process that takes longer than a conversation.

**This is the ICP for the first 12 months.**

Greenway Centre and NHS are discovery targets — they validate the problem space and inform the product. The organisations above are revenue targets — they have the problem, the budget, and the authority to buy without committee approval.

---

## Workflow Templates — Scope and Sourcing

**How many templates are needed:**

10–15 well-built templates cover the majority of scenarios for the target market. Most operational work falls into a small number of recurring patterns:

Universal — every organisation:
- Inbound enquiry → qualify → respond → resolve
- Complaint → acknowledge → investigate → resolve → close
- Approval request → review → approve/reject → notify

Role-specific — high frequency:
- New client onboarding
- New employee onboarding
- Maintenance or support request
- Document or information request
- Invoice or payment query
- Referral handling
- Contract renewal or review
- Compliance check or audit request

With two or three sector-specific additions — grant application for charities, referral pathway for healthcare, tenancy query for property — the library reaches 14 or 15.

**The quality constraint:**

A shallow template that covers 60% of a scenario creates more friction than no template at all. A deep template that covers 90% of the real scenario — with the right dependencies, approval gates, and API hooks — becomes genuinely relied upon. Build fewer templates and make them excellent.

**MVP scope: 5 templates.** Focus on the three fastest-paying sectors from the ICP list — property management, recruitment, and accountancy. Validate those 5 before building the next 10.

**Where to source the underlying patterns:**

The hard thinking has already been done in open source. Extract step structures and dependency logic — not code or UI — from:

- **Mattermost Playbooks** — open source incident and process playbooks. Each playbook is a structured workflow with steps, checklists, assignments, and triggers. Structurally the closest to CaseDesk's model.
- **OTRS Community Edition** — full open source ITSM platform with mature workflow templates for incident management, change requests, service requests, and problem management aligned to ITIL.
- **osTicket** — open source helpdesk with ticket categories and canned workflows. Useful for complaint and support handling patterns.
- **n8n community templates** — hundreds of real user-contributed workflows covering trigger → steps → outcome patterns relevant to the API orchestration layer.
- **BPMN.io** — the BPMN standard has a large library of process templates covering onboarding, procurement, complaints, and approvals. Useful for dependency logic reference.

These are production-tested patterns from real operational environments. CaseDesk adapts them to its entry-point-agnostic architecture — it does not invent them from scratch.

**Adaptation constraint — non-negotiable:**

Every template sourced from open source must be adapted to CaseDesk's model before use. The ticket is the unit of work in every template without exception.

Extract from open source:
- Step sequences — what happens in what order
- Dependency logic — what must complete before the next step starts
- Approval gates — where human sign-off is required
- Escalation triggers — what causes a task to escalate

Discard from open source:
- Data models — most are message-centric or task-centric, not ticket-centric
- Channel assumptions — most assume email or a portal as the only entry point
- Configuration-first approaches — most require upfront setup before anything works
- UI patterns — built for dashboards, not inbox-native operations

If a pattern requires the user to leave their inbox, configure a workflow manually, or think in terms of messages rather than work items — rewrite it before it becomes a CaseDesk template. The ticket remains the unit of work in every template without exception.

---

## Template 1 — Lead Management

**Why this is first:**

The founder uses CaseDesk before customers do. The existing InboxIQ outreach pipeline — email sequences, lead scoring, follow-ups — is functional but disjointed because each piece was built to solve one problem at a time with no consistent lifecycle connecting them. The Lead Management template imposes that lifecycle. If it fixes the problem for the founder, it works for a property management firm, a recruitment agency, or an accountancy practice with the same problem.

This is the fastest validation loop available: build it, use it, know within 30 days whether the concept holds.

**What it replaces:**

- Manual follow-up tracking across email threads
- Spreadsheet or mental pipeline visibility
- Disconnected outreach sequences with no unified ticket record
- No clear answer to "where does this lead stand right now?"

**The lifecycle:**

```
new → contacted → qualified → proposal_sent → negotiating → closed_won
                                                           → closed_lost
                                                           → nurture
```

Every stage transition is a `TicketEvent`. Nothing is overwritten. The full history — every email sent, every reply received, every stage change with reason — is visible on the ticket.

**Entry points — how leads arrive:**

| Entry point | Handling |
|---|---|
| Web contact form | Every submission is a lead ticket — no classification needed |
| Email to shared inbox | Classifier identifies as a lead → ticket created |
| Manual creation | Salesperson creates ticket directly |
| API / webhook | Partner referral or CRM integration pushes lead record |

**Sales activities and their events — the full taxonomy:**

There is no card to move. Every activity creates a `TicketEvent`. The stage transitions emerge from the events — they are not set manually.

*1. Communication activities — system records automatically:*

| Activity | TicketEvent |
|---|---|
| First outreach sent | `outreach_sent` — channel, subject, timestamp |
| Lead replies | `reply_received` — content, sentiment, channel |
| Follow-up sent (no reply) | `followup_sent` — attempt number, delay |
| No response after N days | `lead_cold` — triggers escalation job |
| Meeting or call scheduled | `meeting_scheduled` — date, medium |
| Meeting or call completed | `meeting_held` — notes, outcome |

*2. Qualification activities — system surfaces the moment, human decides:*

| Activity | TicketEvent |
|---|---|
| Discovery questions sent | `discovery_sent` |
| Budget confirmed | `budget_confirmed` — value, currency |
| Decision maker identified | `decision_maker_confirmed` — name, role |
| Need validated | `need_validated` — notes |
| Timeline established | `timeline_confirmed` |
| **Qualification decision** | `qualified` or `disqualified` — reason required |

The qualification decision is the only gate that requires explicit human input. It is significant and must be deliberate — not implied by moving a card. Everything before it can be automated or AI-assisted. Everything after it depends on it.

*3. Proposal activities:*

| Activity | TicketEvent |
|---|---|
| Proposal drafted | `proposal_drafted` — by whom, version |
| Proposal sent | `proposal_sent` — document reference, timestamp |
| Proposal viewed | `proposal_viewed` — if document tracking is available |
| Objection raised | `objection_received` — content, type |
| Objection addressed | `objection_addressed` — response sent |
| Negotiation started | `negotiation_open` |
| Terms agreed | `terms_agreed` — summary |

*4. Close activities:*

| Activity | TicketEvent |
|---|---|
| Contract sent | `contract_sent` |
| Contract signed | `contract_signed` — timestamp, value |
| Closed won | `closed_won` — value, source attribution |
| Closed lost | `closed_lost` — reason required |
| Moved to nurture | `nurture` — reason, reactivation date |

**What CaseDesk automates vs what stays human:**

```
Automated (system does it)          Human (explicit decision required)
──────────────────────────          ──────────────────────────────────
Classify incoming message           Qualification decision
Draft first response                Proposal review before sending
Follow-up if no reply               Objection response
Escalate cold leads                 Close decision — won / lost / nurture
Record every event                  Reason for lost (required field)
Surface the qualification gate
```

The system handles the volume. The human handles the judgment.

**Fields on the lead ticket:**

- Company name, contact name, email address
- Source (which entry point, which campaign)
- Estimated value
- Assigned owner (salesperson or team)
- Current stage
- Next action + due date

**Routing decisions:**

- New lead arrives → `classifier.py` confirms it is a lead → `model_router.py` assesses complexity → `router.py` assigns to owner
- Simple enquiry (short, clear intent) → small model drafts initial response → human reviews before sending
- Complex or high-value lead → large model → routed to senior owner
- Lead goes cold (no contact in 5 days) → `jobs/escalation.py` fires → reminder ticket assigned to owner
- Lead goes cold for 30 days → status moved to `nurture` → removed from active pipeline

**Minimum core needed to run this template:**

This is the smallest set of components the codebase must have before this template can operate:

1. `models/tickets.py` — `Ticket` and `TicketEvent`
2. `models/workflows.py` — `WorkflowTemplate` and `WorkflowInstance`
3. `intake/form.py` — form submission → ticket created
4. `services/ticket_service.py` — `create`, `transition`, `append_event`
5. `jobs/escalation.py` — cold lead reminder

No AI routing is required for the first version. Manual assignment is sufficient to validate the lifecycle concept. DSPy routing is layered in once the lifecycle proves its value.

**Open source patterns to draw from:**

- **SuiteCRM** — complete lead lifecycle with stage definitions, qualification criteria, and escalation rules. Extract the stage sequence and required-fields-per-stage logic.
- **EspoCRM** — simpler lead management model, closer to what a small team needs. Cleaner reference for the data model.
- **n8n community templates** — lead notification and follow-up workflows covering trigger → steps → outcome patterns.

Extract stage sequences, transition logic, and escalation rules. Discard the data models (record-centric, not ticket-centric) and the UI patterns (dashboard-first, not inbox-native).

**Validation:**

Use the template yourself for 30 days before offering it to any customer. Track:

- Did every lead get a `first_contact_sent` event within 24 hours?
- Did every qualified lead get a `proposal_sent` event?
- How many leads reached `closed_won` vs `closed_lost` vs `nurture`?
- Did the escalation job surface leads that would otherwise have gone cold silently?

If the answer to those questions is visible on the ticket record without opening an email thread or checking a spreadsheet — the template works. If it is not visible — the event model or the escalation logic needs fixing before this ships to customers.

---

## Template 2 — Payment Reconciliation

**What this is:**

A fully automated workflow triggered by a Stripe payment webhook. No human initiates it. No human needs to act on it unless something goes wrong. Every payment that arrives becomes a ticket, is processed, and closes automatically — leaving a clean record in whatever spreadsheet or accounting system the business uses.

This is the first template where the incoming work is **system-initiated, not human-initiated**. The ticket lifecycle is identical to Lead Management. The difference is that the classifier must recognise it as a system event and not waste a model drafting a response to it.

**The two types of incoming work CaseDesk handles:**

```
Human-initiated                  System-initiated
───────────────                  ────────────────
Enquiry, request, complaint      Stripe payment webhook
Form submission                  Scheduled job trigger
Email reply                      API push from partner system
Manual creation                  Calendar or deadline event
```

System-initiated events never need a reply drafted. They need data extracted, an action taken, and a record created. The classifier handles the distinction.

**The lifecycle:**

```
received → extracting → posting → closed
                                → exception (if posting fails)
```

Most payments close in seconds without human involvement. Exceptions stay open and are assigned to a human.

**Entry point:**

Stripe sends a POST request to CaseDesk's webhook intake endpoint on every payment event:

- `payment_intent.succeeded` — a payment completed
- `invoice.paid` — a subscription or invoice was paid
- `refund.created` — a refund was issued
- `charge.dispute.created` — a chargeback was opened

`intake/webhook.py` receives the request, validates the Stripe webhook signature, and creates a ticket for each event that requires action.

**The workflow — what happens on every payment:**

```
Step 1 — Extract payment data
         amount, currency, customer name and email,
         description, Stripe payment ID, timestamp

Step 2 — Check for duplicate
         Has this Stripe payment ID been processed before?
         If yes → skip, close ticket as duplicate
         If no → continue

Step 3 — Post to execution connector
         Google Sheets  → append row to transaction log
         Microsoft Excel → append row via OneDrive API
         QuickBooks     → create payment entry via API
         Sage           → create payment entry via API
         Custom webhook → POST to registered endpoint

Step 4 — Record outcome
         Success → TicketEvent: entry_created → ticket closes automatically
         Failure → ticket stays open → escalated to human
```

**The execution connector is the user's choice — not CaseDesk's:**

Most small businesses do not have accounting software. They have a spreadsheet. The execution connector is registered in CaseDesk's connector registry — CaseDesk calls whatever is there:

For a Google Sheets connector, the output row is:

```
Date | Amount | Currency | Customer | Description | Stripe ID | Status
```

The bookkeeper or accountant gets read access to the sheet. At month end they have a clean, automatically populated transaction log instead of hunting through Stripe's dashboard or email receipts.

**Events recorded on every payment ticket:**

| Activity | TicketEvent |
|---|---|
| Webhook received | `webhook_received` — event type, Stripe ID, timestamp |
| Duplicate detected | `duplicate_skipped` — original ticket reference |
| Data extracted | `data_extracted` — amount, currency, customer, description |
| Entry posted | `entry_created` — connector used, row reference or record ID |
| Posting failed | `posting_failed` — reason, connector response |
| Retry attempted | `retry_attempted` — attempt number |
| Escalated to human | `escalated` — reason, assigned to |
| Human resolved | `resolved_manually` — action taken, by whom |

**Exceptions and how they are handled:**

| Exception | What CaseDesk does |
|---|---|
| Duplicate Stripe ID | Skip — close ticket as duplicate, log reference to original |
| API authentication expired | Refresh OAuth token automatically — retry once |
| Sheet or record not found | Escalate — connector is misconfigured, human must fix |
| Refund issued | Route to finance team — requires human review before credit note |
| Chargeback opened | `high_risk` route — human review required immediately |
| Connector API down | Retry with exponential backoff — escalate after 3 failures |

Exceptions represent under 10% of payment events for a healthy Stripe account. The rest close automatically.

**What the automation vs human boundary looks like here:**

```
Automated (system does it)          Human (only on exception)
──────────────────────────          ─────────────────────────
Receive and validate webhook        Fix misconfigured connector
Extract payment data                Review and approve refunds
Check for duplicates                Handle chargebacks and disputes
Post to spreadsheet or API          Resolve failed postings
Close ticket on success             Correct wrongly posted entries
Retry on transient failures
Escalate on persistent failures
```

**Connectors required:**

```
Input connector      → Stripe webhook (registered in connector registry)
Knowledge connector  → Customer data (optional — to enrich payment records
                        with additional context from CRM or contact list)
Execution connector  → Google Sheets, Microsoft Excel, QuickBooks, Sage,
                        or any custom API endpoint the account registers
```

**Minimum core needed to run this template:**

1. `intake/webhook.py` — validate Stripe signature, parse payload, create ticket
2. `models/tickets.py` — `Ticket` and `TicketEvent`
3. `services/ticket_service.py` — `create`, `transition`, `append_event`
4. `services/connector_service.py` — call registered execution connector
5. `models/connections.py` — connector registry (which connector is active for this account)
6. `jobs/escalation.py` — retry logic and escalation on persistent failures

No AI routing is required for standard payments — the webhook type determines the workflow. DSPy is only needed for ambiguous or high-risk events (disputes, unusual amounts).

**Validation:**

Connect a Stripe test webhook. Fire ten test payment events. Verify:

- Did every payment create a ticket?
- Did every ticket close automatically after the sheet row was appended?
- Did the duplicate check prevent double-posting?
- Did a simulated failure escalate correctly?

If all four pass in test mode — the template is ready for a live connection.

---

## Future Intelligence Layer — Non-MVP

> *Not in the first release. But the foundation must be laid now so this can grow from it.*

CaseDesk processes every piece of operational work that passes through an organisation. As a byproduct of doing that work, it accumulates structured data: routing decisions, lifecycle transitions, step timing, escalation counts, resolution outcomes, model costs. That data exhaust is the raw material for business intelligence — not because a BI product was built, but because the operational work produced it naturally.

**The expansion path:**

```
Today      →  CaseDesk observes work         →  proposes workflows

Near-term  →  CaseDesk observes patterns     →  surfaces operational health
               "Complaint volume up 40%.
                62% relate to billing."

Future     →  CaseDesk observes trends       →  flags decision points
               "Your contract renewal workflow
                stalls at approval 80% of the
                time — average delay: 4.2 days."

Long-term  →  CaseDesk observes outcomes     →  advises on cost and quality
               "23% of tickets route to the large
                model. Based on outcomes, 18% could
                safely use the medium tier."
```

This is the same "system observes → system proposes → human approves" principle extended from workflow proposals to operational decisions.

**What the MVP must not do:**

Bake analytics into the transactional tables. The ticket, event, and workflow tables must stay clean for operational use. The intelligence layer reads from them — it does not write back into them. That separation is what allows a BI layer to be added later without a schema rewrite.

**What the MVP must do — the three non-negotiable foundations:**

1. `observer.py` records rich structured data per routing decision — complexity, model tier used, resolution time, escalation count, outcome
2. `TicketEvent` is indexed and query-friendly — the append-only audit log doubles as the analytics source
3. Workflow instances record step-level timing — when each step started, how long it waited, where it stalled

None of this requires building a BI product in the first release. It requires designing the data model so a BI layer can be added without a rewrite. The work to collect the data is small. The work to analyse it comes later.

**Industries where the intelligence layer is a product in its own right:**

Once CaseDesk has accumulated sufficient ticket volume per account, the intelligence layer becomes a separate selling point — particularly in:

- **Sports** — analysts reviewing match footage, extracting decisions, tracking patterns across opponents and seasons
- **Legal** — matter lifecycle analytics, deadline compliance rates, partner utilisation
- **Professional services** — project delivery patterns, approval bottlenecks, client request trends
- **Healthcare operations** — referral pathway timing, administrative request volumes, SLA compliance

In these verticals, the operational data CaseDesk collects is itself valuable — not just as a byproduct of ticketing, but as a source of insight that informs decisions. That is a different product category from ticketing. It is also a natural upsell once the operational layer is trusted.

---

## MVP Delivery — Showing Value Before the System Has Learned Anything

CaseDesk's long-term value comes from learning. But learning takes time. The MVP must show value on day one — before any observation has happened.

The answer is: **immediate value comes from visibility and organisation, not automation. Automation is what learning adds over time.**

**The value ladder:**

```
Day 1      → Visibility
             Everything in one place. Every request tracked.
             Nothing falls through the cracks.

Week 1     → Classification
             CaseDesk knows what is urgent, what is noise,
             what category each request belongs to.

Month 1    → Pattern recognition
             "You have handled 7 requests like this the same way.
              Should I turn that into a workflow?"

Month 3+   → Automation
             Workflows run without human intervention.
             APIs are called. Tasks complete themselves.
```

Each stage delivers value independently. A user on day one does not need to wait for month three to justify the product.

**Day one value requires no learning:**

Connect a form → every submission immediately becomes a tracked ticket with a lifecycle status. The user sees in real time what arrived, who it is assigned to, whether it is resolved. Nothing has been learned yet. The value is pure organisation — requests no longer get lost.

That is enough to justify the product on day one.

**Pre-built templates bridge the cold start gap:**

CaseDesk ships with workflow templates for known common patterns. These work immediately — no observation required. Observed behaviour refines them over time.

Initial template library:
- New employee onboarding
- Customer complaint
- IT support request
- Grant application (charity-specific)
- Referral handling (healthcare-specific)
- Supplier invoice (finance)

The user selects the template closest to their need, connects their channel, and has a working workflow in minutes. CaseDesk then watches how the team actually uses it and suggests refinements.

**The MVP demo — 5 minutes, shows both immediate value and learning trajectory:**

1. Connect a form — 2 minutes
2. Submit a test enquiry — appears as a ticket immediately
3. Assign it, mark it resolved — the lifecycle is visible
4. Submit two more identical enquiries — CaseDesk surfaces: *"This looks like a recurring pattern. Should I create a workflow?"*
5. User clicks yes — first workflow defined without any manual configuration

The user sees day one value and the learning trajectory in a single session. The product sells itself.

---

## Validation Gate

Do not build ahead of the evidence.

The Greenway Centre discovery meeting and the non-converter feedback form responses must answer one question before any implementation begins:

*What is the most expensive thing that falls through the cracks today?*

People do not buy lifecycle management. They buy:
- Fewer missed sales opportunities
- Fewer missed client requests
- Fewer SLA breaches
- Fewer compliance failures
- Fewer unhappy customers

The lifecycle is the mechanism. The pain is what they pay to solve.

If discovery surfaces a specific, costly, recurring thing that falls through the cracks — build the mechanism that stops it. If discovery surfaces only vague frustration with email volume — the current product is closer to right than this document suggests.

The discovery form is ready. The meeting is imminent. Build nothing until the evidence arrives.
