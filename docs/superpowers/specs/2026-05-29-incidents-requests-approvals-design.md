# InboxIQ: Incidents, Requests, and Approvals — Design Spec

## 1. Strategic Positioning

### The Core Claim: "The inbox IS the form"

Every ITSM and approval tool on the market is built around a portal employees are supposed to use and don't. ServiceNow, Jira Service Management, Kissflow, and Freshservice all require employees to leave email, log into a separate URL, learn a new interface, and return to check status. The result is predictable: portal adoption is low, employees email it@company.com or hr@company.com anyway, and those emails exist outside the system — untracked, unassigned, unmeasured.

InboxIQ inverts this. The shared inbox is the intake channel. Employees email the address they already use. InboxIQ reads the email, classifies the intent semantically (incident vs. request vs. approval), assigns an owner, tracks SLA, and closes the loop in the same thread. No new URL. No new login. No employee change-management programme.

This is not a feature difference. It is a deployment model difference. Competitors require organisations to onboard their entire employee population into a new tool before the first ticket is tracked. InboxIQ is live the moment Gmail or Outlook is connected — 100% of volume is captured from day one because 100% of employees already know how to send an email.

### Competitive Moat: Semantic Classification vs. Field-Based Classification

Every portal-based tool uses structured forms: employees select a category from a dropdown, fill in a description field, choose a priority level. The classification is as good as the employee's understanding of the system. An employee reporting a laptop outage selects "General IT" instead of "P1 Incident" because they don't know the difference. A leave request goes in as "Other" because the employee is on mobile and doesn't see the right option.

InboxIQ classifies from free-form email text. The email subject line "my laptop won't turn on and I have a board presentation in 2 hours" is classified as a high-urgency incident with a hardware category — no form, no dropdown, no employee training required. The semantic layer reads intent, urgency, and category from natural language, the same way the employee's manager would if they read the email.

This creates a structural data quality advantage. Every ticket in InboxIQ has a machine-verified classification, not a self-selected one. Over time, that data becomes the semantic analytics layer described in section 5.

### Target Buyers by Vertical

**Incidents (/use-cases/it-incidents):** IT Manager or Head of IT at a 50–500 person company. Currently triages a shared it@company.com inbox manually or via a half-configured Freshservice or Jira SM instance. Pain: high-severity incidents buried in low-priority noise; no SLA visibility; reporting to leadership is manual. Not buying ServiceNow (cost/complexity). Evaluating Freshservice or JSM but put off by portal setup. Budget owner. Deal size: Business plan.

**Requests (/use-cases/it-requests):** Same buyer as incidents, often the same person. Secondary buyer is an Operations Manager at a company where "IT requests" includes access provisioning, equipment orders, and software licences — a mix of IT and ops. Pain: shadow emails that bypass the tracking system entirely; per-seat pricing punishes growth. Deal size: Business plan.

**Approvals (/use-cases/approvals):** Operations Manager, Finance Manager, or Chief of Staff at a 20–200 person company. Currently manages approval chains over email threads or Slack — no audit trail, no SLA, approvers lose threads. Can't justify Kissflow's £2,500/month floor. Pain: approvals disappear, decisions aren't recorded, audit requests are a scramble. Budget owner. Deal size: Business plan, occasionally Enterprise if approval volume is high and they want ApprovalPolicy auto-approval rules.

---

## 2. New Use Case Pages

### Page 1: IT Incident Management

**URL:** `/use-cases/it-incidents`

**Route function name:** `use_case_it_incidents`

**Template:** `src/templates/marketing/use_case_it_incidents.html`

**Page title tag:** `IT Incident Management Without a Portal — Email-Native ITSM | InboxIQ`

**Meta description:** "Turn every email to it@company.com into a tracked, prioritised incident — no portal login, no per-seat licence, no employee training. InboxIQ classifies and routes IT incidents from your existing Gmail or Outlook inbox."

**H1 headline:** "Your employees already email IT when something breaks — now every message becomes a tracked incident."

**Eyebrow label:** `Use Case · IT Incident Management`

**Hero subheading:** "High-severity incidents get buried in a shared inbox no one owns. InboxIQ classifies urgency from the email itself, assigns priority automatically, and routes to the right resolver — before the employee even knows to check a portal."

**Hero trust badges:**
- No portal login for employees
- Priority classification from plain email
- SLA tracking from day one

**The 3 workflow steps (How It Works section):**

1. **An employee emails it@company.com** — They describe the problem in plain language: "my VPN stopped working", "production database is down", "can't log into Salesforce." No form. No category selection. Just an email to the address they already use.

2. **InboxIQ classifies severity and type** — The email text is read semantically. A report of a production system down is classified P1 and tagged as a service-disruption incident. A password reset request is classified P3 and tagged as access. Priority and category are assigned without the employee making a single selection — and without a human reading the email first.

3. **The right resolver is assigned and notified** — Based on classification, InboxIQ routes the incident to the correct owner: network issues to the network team, security flags to the security team, general requests to the helpdesk queue. SLA clock starts. The employee receives a confirmation in the same email thread with a case reference — never a portal URL.

**Competitor name-checks:**
- ServiceNow: "ServiceNow routes incidents correctly — once your £500K implementation is complete."
- Freshservice: "Freshservice's portal works great for employees who remember to use it."
- Jira Service Management: "Jira Service Management adds a second inbox your IT team has to manage."
- PagerDuty: "PagerDuty is built for on-call engineers. Not for the employee whose laptop won't start."

**Pain points (The Problem section):**

1. **High-priority incidents are invisible until they escalate.** A production outage email arrives at 9:04 AM. It sits below 23 other unread emails in a shared inbox. By the time a human opens it, 40 minutes have passed and the CEO is asking questions. Without urgency classification at arrival, severity is determined by accident.

2. **Employees email IT directly and bypass the ITSM system entirely.** Every ITSM portal is a second inbox. Employees who know the IT Manager personally email them directly. Employees who can't find the portal URL email it@company.com. Both create untracked incidents that never appear in your SLA reports or incident volume data.

3. **Per-seat pricing punishes the team that resolves incidents, not the employees who raise them.** ServiceNow charges per fulfiller seat. Jira SM charges per agent. As the IT team grows, the bill grows — even though the employee population raising incidents has not changed. InboxIQ charges per inbox, not per resolver.

**Outcomes section:** "What IT teams report after 30 days"
- **100%** — Incidents captured and tracked. Every email to it@company.com becomes a logged incident from day one, including the ones employees sent directly before the system was in place.
- **70%** — Reduction in mean time to assign. Semantic classification eliminates the triage queue — incidents are routed before a human reads the email.
- **0** — New tools employees need to learn. The intake channel is the same email address they used before InboxIQ was deployed.

**SEO keyword focus:**
- Primary: "IT incident management email", "email-based ITSM", "incident tracking shared inbox"
- Secondary: "Freshservice alternative", "Jira Service Management alternative no portal", "IT helpdesk without portal"
- Long-tail: "how to track IT incidents from email", "ITSM without employee training", "shared inbox incident management"

**Pricing tier gate:** Business plan. Hero eyebrow reads `Use Case · Business Plan`. Bottom CTA includes note: "Incidents, requests, and approvals are included in every Business plan — no add-ons."

**JSON-LD HowTo steps:**
1. "Connect your IT inbox" — Connect the Gmail or Outlook inbox at it@company.com via OAuth. InboxIQ begins classifying incoming emails immediately.
2. "Set incident routing rules" — Define routing by classification: P1 incidents to the on-call engineer, access requests to the helpdesk queue, hardware issues to the ops team.
3. "Incidents resolve from the same inbox" — Resolvers work inside Gmail or Outlook. Status updates go back to the employee in the original thread. No portal. No second tool.

**JSON-LD FAQ pairs:**
1. Q: "Does InboxIQ replace our ITSM portal?" / A: "InboxIQ replaces the employee-facing portal entirely — employees raise incidents by emailing the address they already use. For teams using ServiceNow or Jira SM for internal asset management, InboxIQ can run in parallel as the intake and classification layer."
2. Q: "How does InboxIQ prioritise incident severity?" / A: "InboxIQ classifies urgency from the email text itself — no employee input required. A report of a production system outage is classified higher priority than a password reset request based on semantic analysis of the message content."
3. Q: "What happens to incidents submitted before InboxIQ was connected?" / A: "Retroactive classification is not applied — InboxIQ classifies emails from the connection date forward. Historical emails remain in Gmail or Outlook unchanged."
4. Q: "Is IT incident management available on all plans?" / A: "Incident classification and routing is available on Business and Enterprise plans. Starter and Pro plans include general email triage and automation but not multi-inbox shared routing with SLA tracking."

**Related solutions pills:** HR Operations, Approval Workflows, Support Automation, IT Requests

---

### Page 2: IT / Ops Service Requests

**URL:** `/use-cases/it-requests`

**Route function name:** `use_case_it_requests`

**Template:** `src/templates/marketing/use_case_it_requests.html`

**Page title tag:** `IT Service Request Management — No Portal Required | InboxIQ`

**Meta description:** "Employees email access requests, equipment orders, and software licences to it@company.com. InboxIQ classifies, routes, and tracks every request automatically — no portal login, no per-agent pricing."

**H1 headline:** "Your employees are already emailing IT for access, equipment, and software — now every request gets tracked and resolved."

**Eyebrow label:** `Use Case · IT & Ops Requests`

**Hero subheading:** "IT service requests arrive by email whether you have a portal or not. InboxIQ turns that email into a structured, routed, SLA-tracked request without asking employees to change a single behaviour."

**Hero trust badges:**
- Access, equipment, and software requests in one queue
- Per-inbox pricing — not per-agent seat
- Deployed in hours, not weeks

**The 3 workflow steps:**

1. **An employee sends a request to it@company.com** — "I need admin access to the billing system", "my monitor stopped working", "can you add me to the Figma team licence?" The email is plain text, sent the way they always have. No form, no category dropdown, no portal URL to remember.

2. **InboxIQ classifies the request type and approver** — Access requests are flagged for security review. Equipment requests are routed to IT ops. Software licence requests are forwarded to the person who owns that licence. Classification is semantic — the request "I can't get into the Salesforce instance" routes the same as "Salesforce access request" without requiring the employee to use correct terminology.

3. **The request is tracked until closed** — The assignee works from their own inbox. When they reply, the thread is updated. When the request is fulfilled, the record is closed with an audit entry. The employee receives confirmation in the original thread. No portal check-in required.

**Competitor name-checks:**
- ServiceNow HRSD / ITSM: "ServiceNow handles service requests — after a 10-week implementation and a per-fulfiller licence for everyone who might need to act on a request."
- Freshservice: "Freshservice's Growth plan caps automation at 5,000 transactions/month — and charges £29/agent/month extra for the AI that makes it useful."
- Jira Service Management: "JSM's help-centre portal works for employees who find the URL. The rest email you directly anyway."
- Zendesk (Employee Service): "Zendesk's employee service suite requires a second paid instance if you already use Zendesk for customer support."

**Pain points:**
1. **Shadow requests bypass every system you build.** The VP of Sales emails the IT Manager directly. The new hire asks on Slack. The contractor sends a WhatsApp. None of these appear in your request queue, your SLA report, or your audit log. No portal solves shadow requests — employees will always find a path that doesn't involve a login.

2. **Per-agent pricing makes growing IT teams pay for every resolver.** Freshservice, Jira SM, and Zendesk all price per agent. A five-person IT team resolving 400 requests/month pays five licences. When you add a sixth resolver to handle growth, the bill jumps immediately. InboxIQ charges per inbox — adding resolvers is free.

3. **Configuration takes longer than deployment.** JSM's project schemas, permission schemes, and SLA clocks take one to two weeks to configure for a non-Atlassian team. Freshservice requires categories, templates, and automation rules before it triages correctly. InboxIQ classifies from day one using semantic analysis of email content — no category taxonomy to build first.

**Outcomes:**
- **3×** — Faster fulfilment on access requests. Requests reach the approver before an IT team member has manually read the email.
- **£0** — Additional cost per resolver. Per-inbox pricing means the IT team can grow without a licence renewal conversation.
- **100%** — Requests with an owner. Every email to the IT inbox becomes a tracked, assigned request — including the ones sent directly to the IT Manager's personal address, once that inbox is connected.

**SEO keyword focus:**
- Primary: "IT service request management email", "IT request tracking shared inbox", "service request without portal"
- Secondary: "Freshservice alternative SMB", "Jira Service Management no portal", "ITSM email-native"
- Long-tail: "employee IT requests from email", "track IT requests without Jira", "service desk without onboarding employees"

**Pricing tier gate:** Business plan. Same note as incidents page.

**JSON-LD HowTo steps:**
1. "Connect your IT service inbox" — Connect the Gmail or Outlook inbox that receives IT requests via OAuth. InboxIQ classifies request types automatically from day one.
2. "Define routing by request category" — Route access requests to the security owner, equipment requests to IT ops, and software licences to the licence manager — using plain-English rules.
3. "Requests resolve from the inbox, not a portal" — Assignees work from Gmail or Outlook. Employees receive updates in the original thread. Every request has a close date and an owner record.

**JSON-LD FAQ pairs:**
1. Q: "Can InboxIQ handle both IT incidents and IT service requests from the same inbox?" / A: "Yes. InboxIQ classifies incoming emails by intent — an outage report and a software access request arriving at the same inbox are classified differently and routed to the correct queue. Both are tracked under the same audit log."
2. Q: "Does InboxIQ support approval steps within a service request workflow?" / A: "Yes. On Business and Enterprise plans, service requests that require approval — such as software licence procurement or elevated system access — can trigger an approval step before the request is fulfilled. The approver receives an email and acts from their own inbox."
3. Q: "How does per-inbox pricing work for IT service desks?" / A: "InboxIQ charges per connected inbox (e.g., it@company.com). The number of people resolving requests from that inbox does not affect the price. This differs from per-agent tools like Freshservice and Jira SM, where every resolver is a paid seat."
4. Q: "Which plan includes IT service request management?" / A: "Multi-inbox routing, SLA tracking, and shared request queues are Business plan features. Starter and Pro are designed for individual or small team inbox automation."

**Related solutions pills:** IT Incidents, Approval Workflows, HR Operations, Support Automation

---

### Page 3: Approval Workflows

**URL:** `/use-cases/approvals`

**Route function name:** `use_case_approvals`

**Template:** `src/templates/marketing/use_case_approvals.html`

**Page title tag:** `Email Approval Workflows — No Portal, No New Login | InboxIQ`

**Meta description:** "Your team already approves by email. InboxIQ classifies approval requests, routes them to the right approver, tracks decisions, and creates an audit trail — all from inboxes your team already uses."

**H1 headline:** "Your team already approves by email — InboxIQ just makes every approval tracked, routed, and auditable."

**Eyebrow label:** `Use Case · Approval Workflows`

**Hero subheading:** "PO approvals, leave requests, access grants, and expense sign-offs all arrive as plain emails. InboxIQ classifies the request, routes it to the right approver, and records the decision — without any approver creating an account in a new tool."

**Hero trust badges:**
- Approvers act from their existing inbox
- Complete decision audit trail
- From £59/inbox/month — vs £2,500/month Kissflow minimum

**The 3 workflow steps:**

1. **A request arrives as a plain email** — A department head emails approvals@company.com: "I need sign-off on a £4,200 vendor invoice before end of week." A team member emails hr@company.com: "Requesting two weeks' leave from 15 July." An engineer emails it@company.com: "Need admin access to the production database." No form. No portal. The email is the request.

2. **InboxIQ classifies the request type and identifies the approver** — The semantic layer identifies this as a financial approval, a leave request, or an access grant. Routing rules determine the correct approver: the CFO for invoices above £1,000, the line manager for leave, the security lead for elevated access. The approver receives a notification in their own inbox — not a portal login prompt.

3. **The approver replies and the decision is recorded** — The approver replies approve or decline from Gmail or Outlook. InboxIQ captures the decision, timestamps it, links it to the original request, and creates an immutable audit entry. The requestor receives confirmation in the original thread. The complete chain — request received, routed to approver, decision made, timestamp — is available for audit at any time.

**Competitor name-checks:**
- Kissflow: "Kissflow's approval workflows are powerful — once you've cleared the £2,500/month minimum and the sales call required to start a trial."
- Nintex: "Nintex connects deeply to SharePoint — and requires dedicated IT or ops resources to configure multi-stage approval flows before the first request can be submitted."
- ProcessMaker: "ProcessMaker's BPM engine handles complex approval chains — for organisations with a process modelling team to build and maintain them."
- DocuSign: "DocuSign is built for signatures, not operational approvals. Using it for PO sign-offs requires custom template work and sends approvers to a separate signing portal."
- ApprovalMax: "ApprovalMax requires Xero, QuickBooks, or NetSuite as a prerequisite and a portal account for every approver."

**Pain points:**
1. **Approval requests disappear into email threads no one owns.** A purchase order request sent on Tuesday gets a "looks fine" reply on Friday — but no one captured the approver's name, the approved amount, or the timestamp. When the auditor asks for evidence of the approval, the thread is buried in someone's personal inbox and the CFO can't remember the details.

2. **Every approver needs a portal account.** Kissflow, ApprovalMax, and Nintex all require approvers to create accounts and log into a separate tool to act on requests. A finance director who approves three POs a month is expected to maintain a Kissflow login for those three clicks. Portal friction causes approvals to stall — approvers defer action until they have time to log in.

3. **Approval tool pricing assumes every approver is a power user.** Kissflow's £2,500/month floor is for the whole platform — including features an approval-only team will never use. ApprovalMax's per-organisation pricing bundles features you don't need. InboxIQ charges per inbox, not per approver — adding five more approvers to the routing rules costs nothing.

**Outcomes:**
- **80%** — Faster approval turnaround. Requests reach the correct approver before anyone manually reads and forwards the email.
- **100%** — Approvals with a timestamped decision record. Every approval or rejection is logged with the approver's identity, decision, and timestamp — automatically.
- **0** — New accounts for approvers to create. Approvers act from the Gmail or Outlook inbox they already use. No platform onboarding required.

**Feature deep-dive section — 2-column card grid:**

Card 1: "Built for the approval chain, not the approval tool administrator"
- No form builder required — approval categories are learned from email intent
- Approvers receive routed requests via standard email forwarding
- Multi-stage approvals: route to secondary approver if primary is unresponsive after N hours (Business plan)
- On Business plan: ApprovalPolicy auto-sends approval confirmation when confidence threshold and conditions are met — no human step needed for routine low-risk approvals

Card 2: "Audit-ready by design"
- Every request, routing decision, and approval logged with timestamp
- Approval chain stored per request: who requested, who approved, when, on what basis
- Evidence export available for audit, compliance review, or internal record
- GDPR and SOX-aware: sensitive approval data (HR, finance) is classified and routed with access scoping

**SEO keyword focus:**
- Primary: "email approval workflow", "approval tracking inbox", "no portal approval software"
- Secondary: "Kissflow alternative small business", "ApprovalMax alternative email", "purchase order approval email tracking"
- Long-tail: "how to track email approvals with audit trail", "approval workflow without portal login", "email-native PO approval process"

**Pricing tier gate:** Business plan for approval routing and audit trail. Enterprise tier for ApprovalPolicy auto-approval rules, SLA escalation on approval stall, and semantic analytics on approval categories. The approvals page hero eyebrow reads `Use Case · Business & Enterprise`. The feature card for ApprovalPolicy auto-approval is marked with a subtle "Enterprise" badge.

**JSON-LD HowTo steps:**
1. "Connect your approvals inbox" — Connect the Gmail or Outlook inbox that receives approval requests (e.g., approvals@company.com or finance@company.com) via OAuth. InboxIQ begins classifying requests immediately.
2. "Define approvers by request type" — Route PO approvals to the CFO, leave requests to line managers, and access grants to the security lead — using plain-English routing rules, no form builder required.
3. "Decisions are recorded automatically" — Approvers reply from their inbox. InboxIQ captures the decision, creates an audit entry, and notifies the requestor in the original thread.

**JSON-LD FAQ pairs:**
1. Q: "Do approvers need an InboxIQ account?" / A: "No. Approvers receive routed requests in their existing Gmail or Outlook inbox and reply from there. InboxIQ captures the reply as the decision. Only the inbox administrator (the person managing the shared approval inbox) needs an InboxIQ account."
2. Q: "How does InboxIQ create an audit trail for approvals?" / A: "Every inbound request, routing action, and reply is logged with a timestamp and the identity of the actor. The approval record stores who requested, who approved or rejected, when, and the original email content. This log is exportable and available for audit or compliance review."
3. Q: "Can InboxIQ auto-approve routine requests without human review?" / A: "Yes, on Enterprise plans. The ApprovalPolicy feature allows you to define conditions — request type, value threshold, requestor role — and a confidence threshold. When both are met, InboxIQ sends the approval confirmation automatically and logs it as a policy-triggered auto-approval."
4. Q: "Is there a minimum contract or seat count?" / A: "No minimum seat count. InboxIQ charges per connected inbox. A single approvals@company.com inbox on the Business plan covers unlimited approvers acting from their own inboxes."

**Related solutions pills:** IT Incidents, IT Requests, HR Operations, Finance

---

## 3. Existing Page Updates

### HR Page (`/use-cases/hr`)

**Hero copy change:** The current H1 reads "Route every HR request to the right person before it becomes a complaint." This stays unchanged — it already frames the problem correctly for the expanded scope.

**New section to add:** Insert a "Requests and Approvals" section between the Compliance Callout and the Related Solutions strip. This section is a 2-column feature card identical in structure to the Finance page's Output Modes card.

Card 1 — **Leave requests and expense approvals, tracked automatically**
- Employees email hr@company.com as they always have — no portal, no new submission form
- InboxIQ classifies "requesting two weeks leave from 15 July" as a leave request and routes to the line manager for approval
- Approval reply captured and logged with timestamp — GDPR-compliant decision record
- Late approvals escalated automatically after configurable SLA window

Card 2 — **Policy queries answered, requests resolved**
- Routine policy questions (maternity entitlement, notice period, dress code) receive AI draft replies grounded in your HR knowledge base
- Non-routine requests route to the right HR Business Partner with full classification context
- Every request has a named owner and close date — complete for SAR evidence and tribunal documentation
- Business plan: ApprovalPolicy handles routine leave approvals below threshold automatically

**One sentence to update in hero sub-paragraph:** Add to the end of the current subheading: "Leave requests, expense approvals, and policy queries are classified automatically — employees email hr@company.com exactly as before."

---

### Finance Page (`/use-cases/finance`)

**Hero copy change:** The current H1 is specific to Stripe/QuickBooks. This page needs a new introductory section placed above the existing Stripe/QuickBooks content that broadens the frame to PO approvals and invoice routing before narrowing to the payment automation feature. The H1 itself stays unchanged (it is the Finance Add-on page, not a general finance page). Instead, add a new eyebrow section at the top of the page body (below the hero, above the Pain Points) that reads:

**New section to add:** Insert a "PO Approvals and Invoice Routing" callout section between the hero and the existing pain-points section. This is a single full-width lavender-background card (matching the How It Works section style) with the following content:

Headline: "Before invoices sync to QuickBooks — they need to be approved."

Body: "InboxIQ classifies incoming purchase order requests and invoice approval emails, routes them to the correct approver, and records the decision — all from the inbox your finance team already uses. The approval is logged before the transaction is synced. On Business plan: approval routing for POs up to your configured threshold. On Enterprise: ApprovalPolicy auto-approves routine vendor invoices below threshold with a full audit entry."

CTA within the card: "See how approvals work" linking to `/use-cases/approvals`.

This framing positions the Finance page as covering the full PO-to-payment workflow: approval routing (new content) and then payment sync (existing Stripe/QuickBooks content) as the downstream step.

---

### Healthcare Page (`/use-cases/healthcare-triage`)

**Hero copy change:** Add one sentence to the existing hero subheading after the current text: "Prior authorisation requests, referral approvals, and staff access requests follow the same inbox-native workflow — classified, routed, and resolved without a separate portal login."

**New section to add:** Insert a "Requests and Approvals in Clinical Operations" section after the How It Works section and before the Outcomes section. This is a 2-column card grid.

Card 1 — **Prior authorisation as an approval workflow**
- PA requests arrive by email from referring physicians and payers — InboxIQ classifies and routes to the correct clinical reviewer
- Reviewer responds from their existing inbox — decision is logged with timestamp and clinical classification
- Business plan: SLA escalation triggers if no response within the configured window (default: 24 hours for urgent PA requests)
- Audit trail supports CMS and HIPAA compliance documentation requirements

Card 2 — **Staff access requests and referral intake**
- System access requests for clinical staff are classified as IT/admin requests and routed to the appropriate approver
- Referral intake emails are classified by specialty and urgency, routed to the relevant department
- ApprovalPolicy (Enterprise) enables auto-routing of low-complexity referrals to the triage queue without manual classification
- All decision records are stored with the classification basis for compliance audit

---

## 4. Pricing Design

### Tier Structure for Incidents, Requests, and Approvals

These are team features — they require a shared inbox, shared routing rules, and shared audit state. They are not available on Starter or Pro because those tiers are designed for individual or small-team inbox automation, not shared multi-party workflows.

**Business plan (£59/inbox/month) — includes:**
- Incident classification and priority assignment from email content
- IT service request routing to assigned owners
- Approval request routing to designated approvers
- Approval decision capture and basic audit log (1 year retention, same as existing activity log)
- SLA tracking and escalation via Automation Studio (100 rules)
- Multi-stage approval routing (route to secondary approver on no-response)
- Finance Add-on (existing): PO approval routing as described in section 3

No new pricing items are needed. "Incidents, requests, and approvals" are existing Business plan capabilities (AI triage + routing automation + Automation Studio + audit trail) applied to a new use case framing. The pricing page copy update (section 6) makes this explicit.

**Enterprise plan (custom) — adds:**
- ApprovalPolicy auto-approval rules: define conditions + confidence threshold → InboxIQ sends confirmation automatically and logs as policy-triggered
- SLA escalation automation beyond Automation Studio (custom escalation chains, on-call paging via email notification)
- Semantic analytics dashboard: approval volumes by category, incident trends by type, request SLA performance — queryable from the inbox data
- Unlimited AI decisions (approval and incident volume can be high)
- Custom DPA and compliance configuration for HIPAA (healthcare), SOX (finance), and ISO 27001

**Pricing page copy addition (Business tier feature list):**

Add two lines to the Business plan feature list in `src/templates/marketing/pricing.html`, after the existing "Prior authorization workflows" line:

```
Incident & request routing (IT, HR, Ops)
Approval workflows with audit trail
```

**Pricing page copy addition (Enterprise tier feature list):**

Add two lines to the Enterprise plan feature list, after "Self-hosted & air-gapped options":

```
ApprovalPolicy auto-approval rules
Semantic analytics: incident and approval trends
```

Do NOT create a separate "Service Desk" add-on or separate SKU. The capability is already present (triage + routing + audit); the new pages surface the use case. Keeping it within existing tiers avoids pricing complexity and preserves the "no à-la-carte AI add-ons" brand promise stated on the pricing page.

---

## 5. The Semantic Layer Pitch

Every portal-based ITSM and approval tool generates structured data — because it forces employees to enter structured data via forms and dropdowns. InboxIQ's semantic classification layer generates the same structured data from unstructured free-form email, and the quality is higher because the classification is verified by machine, not self-selected by an employee in a hurry. The result is an analytics layer that lives in the inbox. "What were our top five incident types last quarter?" is answered by querying InboxIQ's classification history — not by exporting from Jira SM into a BI tool and hoping the employees chose the right category dropdown. "How long does a PO approval take on average, and which approver is the bottleneck?" is answered from the approval routing log. "Which leave request categories have the highest escalation rate?" is answered from HR classification data. This is the Enterprise semantic analytics dashboard: it does not require a BI integration, a data warehouse, or a dedicated analyst. The data is already classified, structured, and timestamped — because every email was classified the moment it arrived.

---

## 6. Implementation Scope (MVP)

### New files

**3 new Jinja2 templates:**
- `src/templates/marketing/use_case_it_incidents.html`
- `src/templates/marketing/use_case_it_requests.html`
- `src/templates/marketing/use_case_approvals.html`

Each follows the exact section order of existing use case pages: head/SEO block with HowTo + FAQPage JSON-LD, hero, pain points (3 cards), how it works (3 steps, lavender bg), outcomes (3 stat cards), feature deep-dive (2-column card grid), related solutions pills, bottom CTA banner.

**3 new route registrations in `src/app.py`** (following the existing pattern at lines 432–457):
```python
@app.get("/use-cases/it-incidents")
def use_case_it_incidents():
    return render_template("marketing/use_case_it_incidents.html")

@app.get("/use-cases/it-requests")
def use_case_it_requests():
    return render_template("marketing/use_case_it_requests.html")

@app.get("/use-cases/approvals")
def use_case_approvals():
    return render_template("marketing/use_case_approvals.html")
```

### Existing file edits

**`src/templates/marketing/use_case_hr.html`:** Add the "Leave requests and expense approvals" 2-column card section (described in section 3) before the Related Solutions strip. Add one sentence to the hero subparagraph.

**`src/templates/marketing/use_case_finance.html`:** Add the PO Approvals callout card section between the hero and the existing pain points section. Card links to `/use-cases/approvals`.

**`src/templates/marketing/use_case_healthcare_triage.html`:** Add one sentence to hero subheading. Add the "Requests and Approvals in Clinical Operations" 2-column card section after How It Works and before Outcomes.

**`src/templates/marketing/pricing.html`:** Add two lines to the Business plan feature list (after "Prior authorization workflows" at line 246). Add two lines to the Enterprise plan feature list. No structural changes — these are `<li>` additions inside existing `<ul>` blocks.

### What is NOT built

- No new SQLAlchemy models
- No new API endpoints
- No new Celery tasks
- No new settings UI
- No new database migrations
- No new JavaScript
- No form builder, portal, or separate tracking UI
- No changes to `src/blog/routes.py` — use case routes live in `src/app.py` following the established pattern