# Finance Add-on: Stripe → QuickBooks Automation

## What It Is

A paid add-on to InboxIQ's Automation Studio. When a Stripe payment notification lands in your inbox and InboxIQ labels it `transaction`, that label becomes the trigger for an accounting automation — no separate webhook configuration, no Zapier.

This is not included in the base plan. If you want it, you pay for it. Pricing is volume-based: the more transactions you process through the automation, the more you pay.

---

## Pre-Built Template

Rather than asking users to build this rule from scratch, InboxIQ ships a ready-made Finance template. The user activates the add-on, opens the template, and customises it:

- Which sender domains to watch (default: `stripe.com`)
- Output mode: Direct QuickBooks sync or Weekly CSV export
- Approval step: on or off
- QuickBooks account mapping (which income account, which product/service)

The template is the entry point. Natural language rule-building is available for users who want to go further.

---

## Two Phases: Discovery and Execution

### Phase 1 — Discovery (email-driven)

InboxIQ labels incoming Stripe notification emails as `transaction` during triage. DSPy entity extraction runs at that point — amount, currency, customer name, transaction ID are extracted and stored on the ticket. This is pattern detection only. The email identifies the opportunity:

```text
Recurring Topic Detected:
"43 Stripe payment notifications this month"

[ Automate this? ]
```

The email is never the trigger for the running automation. It is the signal that an automation is worth setting up.

### Phase 2 — Execution (webhook-driven)

Once the user activates the automation, InboxIQ registers a Stripe webhook listener using its existing webhook infrastructure. From that point, every qualifying Stripe event triggers the automation directly — no email involved.

```text
Stripe event: checkout.session.completed
           or payment_intent.succeeded
    ↓
InboxIQ webhook handler fires
    ↓
Fetch full payment, customer, fee, tax, refund data from Stripe API
    ↓
Match or create customer in QuickBooks
    ↓
Create SalesReceipt / Payment / Invoice / RefundReceipt in QuickBooks
    ↓
Log result in InboxIQ
Alert user if mapping fails
```

This is more efficient and more accurate than email-based triggering: webhook events are real-time, carry complete data, and are not subject to email delays or filtering.

---

## Two Output Modes

### Mode 1: Direct QuickBooks API Sync (real-time)

Triggered by Stripe webhook. No email in the loop once the automation is active.

```text
Stripe webhook → checkout.session.completed or payment_intent.succeeded
    ↓
InboxIQ webhook handler
    ↓
Fetch full payment, customer, fee, tax, refund data from Stripe API
    ↓
Match or create customer in QuickBooks
    ↓
QuickBooks API → SalesReceipt / Payment / Invoice / RefundReceipt
    ↓
Audit log + dashboard status
Alert user if mapping fails
```

**Best for:** Shopify, WooCommerce, Stripe Checkout, subscription businesses that want real-time reconciliation.

### Mode 2: AI-Generated CSV/Excel Export (review-first)

Stripe webhooks fire as normal and InboxIQ records each transaction. On a schedule (e.g. every Friday), InboxIQ bundles them into a QuickBooks-ready CSV and emails it to the user or their accountant. The user imports it into QuickBooks via "Import Data" — no QuickBooks API connection required.

```text
Stripe webhooks → InboxIQ records transactions throughout the week
    ↓
Scheduled task (e.g. every Friday) generates Intuit-compatible CSV/Excel
    ↓
Emailed to accounting@ or available for download
    ↓
User imports into QuickBooks
```

InboxIQ handles: transaction type classification (sale, refund, payout, fee), tax/VAT mapping, Stripe fee categorisation, Intuit-compatible column headers.

**Best for:** Businesses that use external accountants, want a review step, or aren't comfortable with a direct accounting API connection.

---

## How the User Discovers This

Stripe notification emails land in the inbox and are labelled `transaction` during triage. This feeds the **Top Topics** section of the InboxIQ dashboard — the list of recurring patterns InboxIQ has noticed in the inbox. Each row has an "Automate →" button.

```text
TOP TOPICS
──────────────────────────────────────────────
Stripe payment notifications    43 emails  [ Automate → ]
```

The email's job ends here. It got the user's attention and surfaced the opportunity. Clicking "Automate →" checks whether the Finance add-on is active. If not, the user sees the add-on upsell. If yes, they are taken to the pre-built template.

Once the add-on is active, InboxIQ asks:

> "What should happen when you receive a Stripe payment confirmation?"

User responds in natural language. InboxIQ proposes:

> "Would you like:
>
> - Direct QuickBooks sync (real-time, via API)
> - Weekly Excel export (emailed to you or your accountant)
> - Approval before posting (review each entry before it goes to QuickBooks)"

From this point the automation runs on Stripe webhooks. The inbox is no longer involved.

---

## Pricing Model

Volume-based. Charged per transaction processed through the automation (i.e. per automation execution, not per email received). Base plan users see the discovery prompt but cannot activate the rule without purchasing the add-on.

Proposed tiers (to be confirmed):

| Transactions/month | Price               |
| ------------------ | ------------------- |
| Up to 100          | £9/mo               |
| 101–500            | £19/mo              |
| 501–2,000          | £39/mo              |
| 2,001+             | Custom / enterprise |

---

## Why This Is Stronger Than Zapier

| | Zapier | InboxIQ Finance Add-on |
| --- | --- | --- |
| Workflow discovery | Manual — user must know to build it | Automatic — detected from inbox behaviour |
| Configuration | Node-based visual editor | Pre-built template + natural language |
| Trigger | Stripe webhook — user configures manually | Stripe webhook — InboxIQ registers it automatically |
| Data extraction | User maps fields manually | DSPy extracts entities at triage |
| Review mode | Not built in | Native (approval step available) |
| Accountant-friendly | No CSV export mode | Weekly CSV emailed to accountant |

---

## Existing Architecture Already Supports This

InboxIQ already has:

- Webhook infrastructure (used here to receive Stripe events)
- DSPy entity extraction at triage time (surfaces the discovery opportunity from emails)
- Email label classification (`CATEGORY_PURCHASES` / `transaction`) — for pattern detection only
- Automation Studio (natural language rules + templates)
- Recurring topic detection

The missing pieces are: Stripe webhook listener registration, QuickBooks API integration, Intuit-compatible CSV formatter, the add-on paywall, and volume-based usage metering.

---

## Outstanding: Finance Use Case Landing Page

The current `/use-case/finance` marketing page does not reflect this vision. It needs a full rewrite to cover:

- The Stripe → QuickBooks automation workflow
- The pre-built template angle
- The CSV export mode for accountant-led businesses
- The "no Zapier configuration" positioning
- The add-on pricing model

**Deferred** — rewrite when the add-on is closer to shipping. The GEO spec (`2026-05-20-geo-design.md`) includes the finance use case page in its structured data plan; the page content must be upgraded before that schema is worth adding.
