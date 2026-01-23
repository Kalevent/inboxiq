# InboxIQ Webhook Intake Scenarios

Below are concrete ways teams send structured or semi-structured data into InboxIQ via webhook, and why they want a single AI agent to make intake decisions.

## 🔑 Anchor: One Intake Brain

> Any system can POST a payload to InboxIQ. The same AI agent decides:
> - Does this need action?
> - How urgent is it?
> - Who should handle it?
> - Should it become a ticket at all?
>
> Result: all intake logic lives in one place, not scattered across tools.

## 1️⃣ Website Contact Forms (very common)
- **Scenario:** Website has “Contact us”, “Support”, “Sales enquiry”, “Report a bug” forms.
- **Instead of:** Sending emails to different inboxes or writing brittle form-specific logic.
- **Flow:** Form POSTs to InboxIQ via webhook.
- **InboxIQ decides:** Detects intent (support vs sales vs feedback), detects urgency, filters spam/non-actionable, routes to support queue, sales queue, or auto-handle.
- **Value:** One triage brain for email + forms; no “support@ vs sales@” confusion; consistent prioritisation logic everywhere.

## 2️⃣ Product Feedback & Bug Reports
- **Scenario:** In-app “Send feedback”, “Report a bug”, “Something isn’t working” forms that otherwise dump into Jira (noisy), Slack (lost), or email (messy).
- **Sample payload:**
```json
{
  "source": "product_form",
  "type": "bug_report",
  "user_id": "1234",
  "message": "App crashes when I click Save"
}
```
- **InboxIQ decides:** Classifies severity, detects blocking issues, determines if human action is needed, creates a ticket only when justified.
- **Value:** Engineers avoid low-quality noise; high-impact issues surface immediately.

### How your existing In-app “Send feedback” form fits InboxIQ
- **What you have today:** In-app “Send feedback” with free-text message and logged-in user context (user ID, account, plan, etc.). Historically these often email founders, dump into a DB table, or push straight to Jira/Slack (noise).
- **Recommended:** Treat “Send feedback” as webhook/API intake. The form submits to InboxIQ via a webhook or authenticated API endpoint—same pattern as email/chat.
- **Example POST:**
```json
{
  "source": "in_app_feedback",
  "type": "feedback",
  "user_id": "user_123",
  "account_id": "acct_456",
  "message": "The dashboard is great, but filtering feels slow on large inboxes.",
  "metadata": {
    "plan": "Pro",
    "page": "Dashboard",
    "app_version": "1.3.2"
  }
}
```

### What InboxIQ does with that feedback (webhook/API intake path)
1️⃣ **Understand intent:** Feature request? Bug report? Praise/testimonial? Confusion/support?  
2️⃣ **Decide urgency:** Blocking? Mild annoyance? Informational only?  
3️⃣ **Decide if human action is required:** ❌ “Nice feedback” → auto-handle; ⚠️ “Feels slow” → optional follow-up; 🚨 “Blocks workflow” → action required.  
4️⃣ **Route appropriately:** Product/Engineering, Support, or Auto-handled feedback bucket.

### What doesn’t happen anymore
- ❌ Every feedback becomes a ticket.
- ❌ Engineers see raw, unfiltered text.
- ❌ Founders read everything manually.

### How this appears in your InboxIQ UI
- **In Work Queue:** Only actionable feedback shows; labeled as Feedback/Bug/Feature request.
- **In Auto-handled:** Praise, non-actionable comments, “just saying hi” — collapsed by default but auditable; can be grouped separately as “Auto-handled (Feedback)” vs “Auto-handled (Email)” to keep sources clear.

### Why this is powerful (and rare)
- Most products “collect and hope someone reads.” InboxIQ triages feedback like any other inbound request (email, forms, bug reports, chat handoffs) through the same decision engine.
- **Compounding value:** Structured feedback + occasional human overrides become training data; InboxIQ learns what matters, what never needs a ticket, and how to prioritise product signals.

## 3️⃣ Customer Onboarding / Implementation
- **Scenario:** “Request onboarding”, “Schedule setup”, “Implementation questions” (operational, not generic support).
- **InboxIQ via webhook:** Recognises onboarding intent, assigns to Customer Success/Implementation, sets SLA automatically, keeps these out of generic support noise.
- **Value:** Onboarding requests stay visible; teams work from a clean queue of real tasks.

## 4️⃣ E-commerce Order Issues
- **Scenario:** “Where is my order?”, “Request refund”, “Damaged item”; forms capture order ID, reason, message.
- **InboxIQ via webhook:** Extracts order ID, classifies issue (refund/delivery/damage), sets urgency from sentiment, routes to the right queue, auto-handles status-only asks.
- **Outcome:** Faster resolutions, fewer manual lookups, unified handling with email complaints.

## 5️⃣ Internal Tools (HR, Ops, IT)
- **Scenario:** “IT support request”, “Access request”, “Report an issue” via Google Forms, internal portals, or Slack bots.
- **InboxIQ via webhook:** Evaluates urgency, ownership, and whether action is required now.
- **Value:** Same decision engine for external and internal requests; reduced operational chaos.

## 6️⃣ CRM / Sales Handoffs (Qualified)
- **Scenario:** CRM events like “Needs human follow-up”, “Escalated”, “Customer replied angrily”.
- **InboxIQ via webhook:** Receives CRM event, evaluates context + sentiment, then decides to create a ticket, assign an owner, or suppress if no action is needed.
- **Value:** No more blind handoffs; only actionable work reaches humans.

## 7️⃣ Chat Widgets & Live Chat Handoff
- **Scenario:** Live chat ends or a bot fails; chat platform sends transcript via webhook.
- **InboxIQ via webhook:** Reads transcript, determines if follow-up is required, creates a ticket only when needed, assigns appropriately.
- **Benefit:** Chat stays clean; unified follow-up logic across channels.

## 8️⃣ Compliance & Incident Reporting
- **Scenario:** Security incidents, compliance reports, whistleblowing—must be logged, routed carefully, and auditable.
- **InboxIQ via webhook:** Tags as sensitive, restricts access, logs AI decision + human override for traceability.
- **Outcome:** Auditable, careful handling with the same intake brain.

## 🔄 Why Webhook Ingestion Wins
- One decision layer across email, forms, apps, and tools.
- No duplicated rules in every form/app.
- Single audit trail + training loop for improvements.
- InboxIQ becomes the front door for all inbound requests.

## How to Explain in the UI
“Send any request into InboxIQ—from forms, apps, or internal tools—and let the same AI agent decide what deserves human attention.”

**If you want next, I can:**
- Draft the webhook payload schema. ✅ (see `/docs/intake_api`)
- Write example `curl` requests. ✅ (see `/docs/intake_api`)
- Design a “Test webhook” UI.
- Suggest security/auth best practices (HMAC, tokens). ✅ (Intake API uses `X-Intake-Token` if configured)
- Rewrite Integrations page copy with this positioning.
