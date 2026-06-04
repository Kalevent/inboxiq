# CaseDesk — Strategic Direction
## The Ticket as the Unit of Work

**Date:** 4 June 2026
**Status:** Direction document — not yet an implementation plan

---

## What CaseDesk Is

Operational work arrives through multiple entry points and gets lost because there is no consistent lifecycle for managing it.

The entry point might be:

- Email or shared inbox
- Website contact form or customer portal
- Internal request form or referral form
- API submission or webhook
- Social media message
- Phone call transcript
- Manual creation

Regardless of where work arrives, it needs the same thing: an owner, a status, a history, and a resolution. CaseDesk provides that — for every entry point, in one place.

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
| New user | Nothing yet | Manual ticket creation |

The intelligence layer operates per entry point:

```
Email connected      → triage classifies messages   → work? → ticket
Form connected       → every submission is work      → ticket always
Social connected     → triage classifies messages    → work? → ticket
Voice connected      → transcript classified         → work? → ticket
Webhook/API          → every submission is work      → ticket always
Manual               → created directly              → ticket always
```

The ticket is entry-point-agnostic. What matters is: something arrived, it may or may not be work, and if it is — track it to resolution.

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

**Three layers of connectivity:**

```
Input connectors      — how work arrives into CaseDesk
(Gmail, Outlook, web forms, social, voice, webhooks, API)

Knowledge connectors  — what CaseDesk understands about context
(CRM, ERP, FHIR, HR systems, directories, internal databases)

Execution connectors  — what CaseDesk can act on
(Microsoft 365, Google Workspace, Stripe, QuickBooks, internal APIs)
```

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

CaseDesk builds its knowledge base from observation, not configuration.

The organisation does not describe itself upfront. CaseDesk watches what happens:

- HR emails about a new employee → CaseDesk observes how the team responds
- The same pattern repeats three times → CaseDesk suggests: *"This looks like a workflow. Should I automate it?"*
- The team says yes → the workflow is defined from behaviour, not a visual editor

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
