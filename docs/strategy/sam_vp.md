# Value Proposition — Sam (ICP 2: Distribution & Trading, Nigeria)

> Status: Draft — 2026-03-20
> See implementation plan: [sam_warehouse_workflow_plan.md](../inboxiq/sam_warehouse_workflow_plan.md)
> See primary ICP: [ICP.md](ICP.md)

---

## Who Sam Is

Sam is the owner-operator of a distribution and trading company in Nigeria. He buys goods from suppliers, warehouses them, and sells them to buyers. He manages a warehouse, a small staff, and an independent auditor — all running on paper-based processes with QuickBooks as the only digital system.

**Quick reference**

| | |
|---|---|
| Role | Owner / operator, distribution company |
| Location | Nigeria |
| Company size | Small — owner + warehouse staff + auditor |
| Tech stack today | QuickBooks (via OneDrive), physical bin cards, paper waybills |
| Connectivity | Unreliable internet, smartphone primary device |
| Buying behaviour | Hands-on — Sam makes all decisions, no procurement process |
| Persona | "Scrambling Sam" — running a real business on paper in 2026 |

---

## The Problem InboxIQ Solves for Sam

Sam's business is real, profitable, and operationally complex — but it runs almost entirely on paper. Every movement of stock is recorded on a physical card. Every delivery is verified by hand. Every sale exists in a cloud system that syncs twice a day. The auditor arrives monthly to check what happened weeks ago.

The result is that Sam is always operating blind. He does not know his real stock position without walking into the warehouse. He does not know if a waybill was matched to an invoice until the auditor tells him. He does not know his buyers' collection status without calling his staff. And when goods are sold but not yet collected, they sit in a grey zone — committed on paper, physically still on the shelf, invisible to any system.

---

## The Pain Points

### 1. No real-time stock visibility

Sam's bin card is a physical card on a shelf. His QuickBooks balance is up to 12 hours behind reality. If a customer calls to ask whether a product is available, Sam's warehouse manager must physically walk into the warehouse to check.

**What InboxIQ does**: Replaces the bin card with a live digital record. Every inbound receipt and outbound dispatch updates the balance in real time. Sam checks stock from his phone — no walking, no waiting for a sync.

---

### 2. Goods sold but not yet collected — invisible to the system

Sam raises an invoice in QuickBooks the moment a sale is agreed. But the buyer may not collect the goods for hours, days, or longer. During that time, those goods still appear on the bin card as available. Another staff member could commit the same goods to a different buyer.

**What InboxIQ does**: When an outbound waybill is created, the goods are immediately marked as reserved — visible to everyone as committed and unavailable — until the buyer collects them. Overselling becomes structurally impossible.

---

### 3. Paper trail errors only caught a month later

The auditor visits periodically. By the time they find a discrepancy — a waybill without an invoice, a bin card balance that does not match the movement history — it happened weeks ago. The root cause is cold. The lesson is theoretical.

**What InboxIQ does**: Every movement is logged in real time with a timestamp, a user, and a document reference. The audit trail is always current. When the auditor visits, they are reviewing a live ledger, not reconstructing history from paper. Discrepancies are flagged automatically — not discovered manually.

---

### 4. Staff operating on paper with no confirmation loop

When goods leave the warehouse, the bin card is updated manually by a staff member — if they remember, and if the entry is correct. There is no confirmation that the update happened. No one is notified. The system assumes the staff did their job.

**What InboxIQ does**: When a staff member marks a waybill as dispatched on their phone, the bin card updates automatically. Sam and the warehouse manager receive a notification. The buyer is notified that goods are ready or have been dispatched. Every action closes a loop.

---

### 5. Buyers and staff have no shared communication channel

When a buyer's goods are ready for collection, the buyer finds out by calling, showing up, or through a WhatsApp message from someone who remembered to send it. There is no structured, trackable notification. If the buyer shows up and the goods are not ready, there is no record of what was communicated.

**What InboxIQ does**: Buyers and staff communicate through the channel they prefer — **email**, **SMS**, or the **InboxIQ messaging app**. Sam chooses the default; each party can choose their own preference. Every notification is logged against the transaction. No information lives only in someone's WhatsApp.

---

### 6. The auditor is a lagging indicator, not a live control

Currently the auditor's value is retrospective — they find what went wrong last month. They cannot prevent anything in real time because they only see the paper records when they visit.

**What InboxIQ does**: The auditor gets a read-only login. They can review any transaction, any waybill, any bin card movement at any time — without visiting the warehouse. The monthly report is generated automatically from the live audit trail. Their role shifts from forensic investigation to ongoing assurance.

---

## The Value in One Sentence

InboxIQ gives Sam complete, real-time visibility over his warehouse operations — stock levels, waybill status, buyer collection, and audit trail — from his phone, with every party notified through the channel they prefer, without replacing QuickBooks.

---

## Return on Investment

This is harder to calculate than Oliver's (time-per-email) but equally concrete.

| Current cost | Caused by |
|---|---|
| Stock discrepancies and write-offs | Bin card errors, overselling, unrecorded movements |
| Disputes with buyers | No record of what was communicated, goods not ready on arrival |
| Audit fees on wasted time | Auditor reconstructing history from paper instead of reviewing a live ledger |
| Delayed sales | Staff cannot confirm stock availability without physically checking |
| Goods committed twice | Sold-but-uncollected stock invisible to staff |

InboxIQ does not save Sam hours in an inbox. It saves him **stock losses, buyer disputes, audit inefficiency, and the operational blindness that comes from running a real business on paper**.

---

## What Sam Does Not Have to Change

InboxIQ does not replace QuickBooks. It does not replace his invoicing process. It does not require his warehouse staff to learn a complex new system. It does not require his buyers to create accounts if they do not want to.

- QuickBooks stays. Sam's team continues entering invoices there.
- Waybills are raised in InboxIQ instead of on paper — same information, digital form.
- Bin cards are digital instead of physical — same concept, real-time and accessible from anywhere.
- Buyers receive notifications through SMS or email — no login required.
- Staff operate from a simple mobile form on their phones.

The behaviour change is minimal. The operational improvement is structural.

---

## Why This Is a Second ICP, Not a Distraction

Sam represents a fundamentally different buyer from Oliver:

| | Oliver (ICP 1) | Sam (ICP 2) |
|---|---|---|
| Geography | UK / US / EU | Nigeria, emerging markets |
| Industry | B2B SaaS | Distribution / trading |
| Problem | Email inbox overload | Operational blindness, paper processes |
| Tech comfort | High | Low to medium |
| System complexity | Low (email + AI) | Medium (warehouse + audit + communication) |
| Build effort | Low — email infra exists | Medium — new warehouse models needed |
| Willingness to pay | SaaS-native | Outcome-driven — pays if it stops the bleeding |

Sam is not a distraction from Oliver. He is evidence that InboxIQ's platform — communication, AI, workflows, notifications — can be configured for any operational workflow, not just email support. Sam is the first customer in a **distribution and operations** vertical that is deeply underserved by software in emerging markets.

---

## Objections Sam Will Raise

### "My staff are not technical"
Warehouse staff see one screen: a waybill with a "Mark as Dispatched" button. That is the entire interface for them. No training needed.

### "The internet is unreliable"
SMS notifications work on GSM, not data. The mobile web app caches the current stock state on load and queues actions when offline. Critical information reaches people even when the connection drops.

### "I don't want to change how I use QuickBooks"
You don't have to. Continue using QuickBooks exactly as you do now. InboxIQ just gives you a digital bin card and waybill system alongside it, with the same reference numbers so the auditor can trace both.

### "What happens if the app is down?"
The bin card history and waybill records are the system of record. They do not disappear. If the app is inaccessible briefly, staff can still operate — they catch up entries when it comes back.

---

## Open Questions Before Pitching to Sam

1. Does Sam want buyers to have logins, or receive notifications only (no account)?
2. Preferred communication channel for buyers — SMS, email, or InboxIQ messaging?
3. Single warehouse or multiple locations?
4. Does the auditor want a login or just a monthly report by email?
5. QuickBooks setup confirmed: Desktop version, file synced via OneDrive — not QuickBooks Online. InboxIQ will read invoice exports from a designated OneDrive folder via Microsoft Graph API (same OAuth as Outlook). No QB cloud subscription needed. Other customers using QuickBooks Online will get a direct API connection instead.
6. Currency: Naira (NGN) only, or does Sam deal in foreign currency with some suppliers?

---

*Written: 2026-03-20. Review with Sam before beginning Phase 1 implementation.*
