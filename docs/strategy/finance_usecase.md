# Finance Use Case: Stripe → QuickBooks Automation via InboxIQ

## The Core Idea

When a Stripe payment notification lands in the inbox and InboxIQ labels it as `transaction`, that label becomes the trigger for an automation rule — no separate webhook configuration needed. The email IS the trigger.

InboxIQ detects the pattern, extracts the transaction data, formats it as a QuickBooks-ready CSV (Intuit-compatible columns), and asks the user how they want to proceed:

> "Would you like:
>
> - Direct QuickBooks sync
> - Weekly Excel export
> - Approval before posting?"

This is more intelligent than Zapier because the workflow is discovered from inbox behaviour, not manually configured. The user describes what they want in natural language; InboxIQ builds the mapping.

---

## How the Trigger Works

InboxIQ already labels incoming emails by category. A Stripe payment confirmation email gets labelled `transaction` automatically. An automation rule then fires on that label + sender domain (`stripe.com`):

```yaml
WHEN   label = "transaction"
AND    sender domain = "stripe.com"
THEN   extract transaction data
       → format as Intuit-compatible CSV
       → [user-chosen action]
```

This means the user doesn't need to configure a Stripe webhook. They write a natural-language rule:

> "Whenever a Stripe payment succeeds, create or update the customer in QuickBooks, create a sales receipt, record Stripe fees, and reconcile refunds automatically."

InboxIQ translates that into the automation.

---

## Two Automation Modes

### Mode 1: Direct QuickBooks API Sync (real-time)

```text
Stripe email → InboxIQ labels "transaction"
    ↓
Automation rule fires
    ↓
AI Intent + Workflow Mapper
    ↓
Transaction Normalizer (customer, amount, fees, tax, refunds)
    ↓
QuickBooks API → SalesReceipt / Payment / Invoice / RefundReceipt
    ↓
Audit log + dashboard status
```

**Best for:** Shopify, WooCommerce, Stripe Checkout, subscription businesses.

**Advantages:** Real-time, auto-reconciliation, no manual imports, cleaner bookkeeping.

### Mode 2: AI-Generated CSV/Excel Export (review-first)

```text
Stripe emails (weekly batch)
    ↓
InboxIQ AI extracts and normalizes transactions
    ↓
Generates QuickBooks-ready CSV (Intuit-compatible columns)
    ↓
Emails file to accounting@ / user downloads
    ↓
User imports into QuickBooks via "Import Data"
```

**Best for:** Businesses that fear direct accounting integrations, use external accountants, or want approval before posting.

Natural-language command:

> "Every Friday generate a QuickBooks-ready spreadsheet from all Stripe sales and email it to accounting."

InboxIQ handles:

- Classifying transaction types (sale, refund, payout, fee)
- Mapping taxes/VAT
- Separating refunds
- Categorizing Stripe fees
- Generating Intuit-compatible column headers
- Emailing the file automatically

QuickBooks Online accepts CSV/Excel imports for: transactions, customers, vendors, products/services, chart of accounts, bank transactions, invoices, journal entries.

---

## Recurring Topic Detection Flow

InboxIQ surfaces this as an automation opportunity in the dashboard:

```text
Recurring Topic Detected:
"43 Stripe payment notifications this month"

[ Automate this? ]
```

User clicks Automate. InboxIQ asks:

> "What should happen when you receive a Stripe payment confirmation?"

User responds in natural language. InboxIQ builds the workflow and asks:

> "Would you like:
>
> - Direct QuickBooks sync (real-time, via API)
> - Weekly Excel export (emailed to you or your accountant)
> - Approval before posting (review each entry before it goes to QuickBooks)"

---

## Why This is Stronger Than Zapier

| | Zapier | InboxIQ |
| --- | --- | --- |
| Workflow discovery | Manual — user must know to build it | Automatic — detected from inbox behaviour |
| Configuration | Node-based, visual editor | Natural language |
| Trigger | Webhook setup required | Email label (already in place) |
| Accounting mapping | User maps fields manually | AI generates Intuit-compatible format |
| Review mode | Not built in | Native (human-in-control model) |

---

## Existing Architecture Already Supports This

InboxIQ already has:

- Email label classification (`CATEGORY_PURCHASES` / `transaction`)
- Webhook infrastructure
- Automation Studio (natural language rules)
- AI agents for data extraction
- Recurring topic detection
- Email-native UX

The missing pieces are: QuickBooks API integration, CSV formatter with Intuit field mapping, and the "how would you like to handle this?" prompt flow.

---

## Outstanding: Finance Use Case Landing Page

The current `/use-case/finance` marketing page is inadequate for this vision. It does not yet reflect:

- The Stripe → QuickBooks automation workflow
- The natural-language rule builder angle
- The CSV export mode for accountant-led businesses
- The "no Zapier configuration" positioning

**This page needs a full rewrite** once the automation feature is closer to shipping. The GEO spec (`2026-05-20-geo-design.md`) includes the finance use case page in its structured data plan — the page content must be upgraded before that schema is worth adding.

**Future work:** Deferred — revisit when Automation Studio Phase 4 (purchases automation) is scoped. See `docs/strategy/native_inbox_intelligence_pipeline.md`.
