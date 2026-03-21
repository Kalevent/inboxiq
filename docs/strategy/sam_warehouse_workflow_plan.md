# Sam — Warehouse Distribution Workflow Implementation Plan

**Customer:** Sam (Nigeria)
**Business:** Distribution / trading company
**Context:** Brittle internet, smartphone-first users, low tech literacy among warehouse staff
**Status:** Planning — do not implement until confirmed with Sam

---

## 1. Business Overview

Sam's company buys goods from suppliers and sells to buyers. The warehouse is the physical hub. All current processes are paper-based (bin cards, waybills) with QuickBooks as the only digital system, syncing via OneDrive twice a day.

### Core Entities

| Entity | Description |
|---|---|
| **Waybill** | Document listing goods in a movement (inbound from supplier, outbound to buyer) |
| **Invoice** | Financial document. Currently raised in QuickBooks. |
| **Bin Card** | Physical card per SKU tracking running stock balance in the warehouse |
| **Stock Item (SKU)** | A product tracked in inventory |
| **Supplier** | Entity delivering goods to the warehouse |
| **Buyer** | Entity collecting goods from the warehouse |
| **Warehouse Staff** | Low tech literacy, smartphone only, verifies and dispatches goods |
| **Warehouse Manager** | Receives inbound deliveries, checks against supplier waybills |
| **Auditor** | Independent, periodic, checks paper trail and stock count vs QuickBooks |
| **Sam** | Owner — needs full visibility across all flows |

---

## 2. The Two Core Flows

### Flow A — Goods Inbound (Supplier → Warehouse)

```
Supplier arrives with truck
  → Brings: supplier waybill + supplier invoice
  → Warehouse manager takes waybill
  → Goods discharged from truck into warehouse
  → Manager physically checks goods against waybill (qty, SKU)
  → Bin card updated: stock balance increases
  → Invoice entered into QuickBooks as a purchase
  → OneDrive syncs to cloud (up to twice a day)
```

### Flow B — Goods Outbound (Warehouse → Buyer)

```
Sam's team raises invoice in QuickBooks (sale recorded)
  → Waybill generated for buyer
  → Buyer receives invoice + waybill
  → Buyer brings waybill to warehouse to collect
  → Staff verifies waybill
  → Goods handed to buyer
  → Bin card updated: stock balance decreases
```

### Edge Case — Sold But Not Yet Collected

```
Invoice raised in QuickBooks → goods marked as sold
  BUT buyer has not yet arrived to collect
  → Goods are still physically in the warehouse
  → Bin card still shows them as available
  → Risk: goods appear available but are already committed
  → Must be tracked as "pending collection" — a reserved state
```

---

## 3. The Audit Process

- Auditor visits periodically (not daily)
- Traces each waybill to its corresponding invoice in QuickBooks
- Verifies all dispatched goods have a QuickBooks sale entry
- Does physical stock count — compares to QuickBooks inventory balance
- Checks bin card running balance is correct given all inbound/outbound movements
- Produces a monthly report with discrepancies and lessons

---

## 4. What We Are Building

A **warehouse management module** inside InboxIQ that digitises Sam's workflow end to end:

- Digital bin card (replaces physical card)
- Digital waybill creation and tracking
- Stock reservation for sold-but-uncollected goods
- Audit trail — every movement logged with timestamp and user
- QuickBooks sync awareness (flag unsynced transactions)
- Auditor dashboard and monthly report generation
- Multi-channel notifications (buyer, staff, auditor, Sam)

---

## 5. User Roles & Access Levels

| Role | Access |
|---|---|
| **Owner (Sam)** | Full visibility — all stock, all transactions, all reports, all communication |
| **Warehouse Manager** | Inbound receipts, stock levels, bin card, supplier waybills |
| **Warehouse Staff** | Outbound dispatch only — verify buyer waybill, mark as collected |
| **Buyer** | View their own orders, collection status, receive notifications |
| **Auditor** | Read-only access to all transactions, waybills, bin card history, reports |

---

## 6. Data Models (New)

### 6.1 StockItem
```
id               UUID
account_id       FK → accounts
sku              string (unique per account)
name             string
unit             string (e.g. "carton", "kg", "piece")
reorder_level    integer (alert threshold)
created_at       datetime
updated_at       datetime
```

### 6.2 BinCard (replaces physical card)
```
id               UUID
account_id       FK → accounts
stock_item_id    FK → StockItem
movement_type    enum: inbound | outbound | adjustment | stock_count
reference_type   enum: supplier_waybill | buyer_waybill | manual | stock_count
reference_id     UUID (FK to Waybill or StockCount)
quantity         integer (positive = in, negative = out)
balance_after    integer (running total)
notes            text
created_by       FK → users
created_at       datetime
```

### 6.3 Waybill
```
id               UUID
account_id       FK → accounts
waybill_number   string (unique per account)
direction        enum: inbound | outbound
status           enum: draft | in_transit | received | dispatched | cancelled
counterparty_id  FK → Supplier or Buyer (polymorphic)
counterparty_type enum: supplier | buyer
invoice_ref      string (QuickBooks invoice reference)
notes            text
created_by       FK → users
created_at       datetime
updated_at       datetime
```

### 6.4 WaybillLineItem
```
id               UUID
waybill_id       FK → Waybill
stock_item_id    FK → StockItem
quantity_expected  integer
quantity_received  integer (filled on receipt/dispatch)
discrepancy_notes  text
```

### 6.5 StockReservation (sold but not collected)
```
id               UUID
account_id       FK → accounts
waybill_id       FK → Waybill (outbound)
stock_item_id    FK → StockItem
quantity_reserved  integer
status           enum: reserved | collected | cancelled
reserved_at      datetime
collected_at     datetime (nullable)
cancelled_at     datetime (nullable)
```

### 6.6 Supplier
```
id               UUID
account_id       FK → accounts
name             string
contact_name     string
phone            string
email            string
address          text
created_at       datetime
```

### 6.7 Buyer
```
id               UUID
account_id       FK → accounts
name             string
contact_name     string
phone            string
email            string
notification_preference  enum: email | sms | inboxiq_message | all
created_at       datetime
```

### 6.8 StockCount
```
id               UUID
account_id       FK → accounts
conducted_by     FK → users
count_date       date
status           enum: in_progress | completed | reviewed
notes            text
created_at       datetime
```

### 6.9 StockCountLine
```
id               UUID
stock_count_id   FK → StockCount
stock_item_id    FK → StockItem
system_balance   integer (snapshot of BinCard balance at time of count)
physical_count   integer (what was actually counted)
variance         integer (computed: physical - system)
notes            text
```

### 6.10 AuditReport
```
id               UUID
account_id       FK → accounts
auditor_id       FK → users (role = auditor)
period_start     date
period_end       date
status           enum: draft | submitted | reviewed
summary          text
findings_json    JSON (structured discrepancies)
created_at       datetime
```

---

## 7. API Endpoints (New Blueprint: /api/v1/warehouse)

```
# Stock Items
GET    /api/v1/warehouse/stock              list all SKUs with current balance
POST   /api/v1/warehouse/stock              create SKU
GET    /api/v1/warehouse/stock/<id>         get SKU detail + bin card history

# Bin Card
GET    /api/v1/warehouse/bin-card/<sku_id>  full movement history for a SKU

# Waybills
GET    /api/v1/warehouse/waybills           list (filter by direction, status)
POST   /api/v1/warehouse/waybills           create waybill
GET    /api/v1/warehouse/waybills/<id>      get waybill + line items
PATCH  /api/v1/warehouse/waybills/<id>      update status (received / dispatched)

# Reservations (sold but not collected)
GET    /api/v1/warehouse/reservations       list active reservations
POST   /api/v1/warehouse/reservations       create reservation when sale raised
PATCH  /api/v1/warehouse/reservations/<id>  mark collected / cancelled

# Stock Counts
POST   /api/v1/warehouse/stock-counts       start a new count
PATCH  /api/v1/warehouse/stock-counts/<id>  submit count results

# Audit
GET    /api/v1/warehouse/audit/trail        full waybill → invoice audit trail
POST   /api/v1/warehouse/audit/reports      create monthly report
GET    /api/v1/warehouse/audit/reports      list reports

# Suppliers & Buyers
GET/POST /api/v1/warehouse/suppliers
GET/POST /api/v1/warehouse/buyers
```

---

## 8. Communication Channels — All Three Offered, User Chooses

Sam's users have different tech levels. All three channels are presented on setup and each user picks their preference (stored in `notification_preference` on Buyer / User model).

### Channel A — Email
- Uses InboxIQ's existing email infrastructure (zero additional build for delivery)
- Triggers: waybill received, goods ready for collection, stock discrepancy, audit report ready
- Best for: Auditor, Sam, buyers with stable internet
- Compose structured HTML emails with transaction summary

### Channel B — SMS
- Provider: Termii (Nigerian provider, reliable coverage, competitive rates)
- Triggers: "Your goods are ready for collection — Waybill #WB-0042", low stock alerts, stock count reminder
- Best for: Buyers, warehouse staff, anyone without reliable internet
- Keep messages under 160 characters
- Integrate via Termii REST API (or Infobip as fallback)
- Config: `SMS_PROVIDER`, `SMS_API_KEY`, `SMS_SENDER_ID` env vars

### Channel C — InboxIQ Messaging App
- Uses existing InboxIQ inbox/messaging feature
- Each waybill or transaction creates a thread
- Sam, the auditor, and managers communicate in context — attached to the specific transaction
- Best for: Sam, auditor, warehouse manager
- Buyers can be invited as external users if they want this level of detail

### Notification Logic
```
When a waybill is marked dispatched:
  → Check buyer.notification_preference
  → If email: send dispatch confirmation email
  → If sms: send "Your goods are ready for collection" SMS
  → If inboxiq_message: create message thread on the waybill
  → If all: do all three
```

---

## 9. QuickBooks Integration — Two Distinct Paths

InboxIQ does not replace QuickBooks. It sits alongside it. But how it connects depends on which version the customer uses.

---

### Path A — QuickBooks Desktop via OneDrive (Sam's setup)

Sam uses QuickBooks Desktop (locally installed, not a cloud subscription). The `.qbw` company file lives on his PC and is synced to Microsoft OneDrive twice a day. He will not pay for QuickBooks Online.

**How InboxIQ reads it:**

QuickBooks Desktop cannot be called via an API. The only practical read path is via exports. The approach:

1. Sam (or his accountant) exports a standard QB Desktop report as CSV or Excel on a schedule — e.g. "Sales by Invoice" or "Open Invoices" report — and saves it to a designated OneDrive folder (e.g. `OneDrive/InboxIQ Sync/invoices_export.csv`)
2. InboxIQ connects to Sam's OneDrive via the Microsoft Graph API (already wired for Outlook OAuth — same credentials, same token)
3. InboxIQ reads the export file from that folder on a schedule (e.g. every 2 hours, aligned with Sam's sync cadence)
4. It parses the invoice list and matches invoice numbers to Waybill `invoice_ref` fields automatically
5. Unmatched waybills are flagged for Sam to review

**What Sam has to do:**

- Connect his Microsoft account in InboxIQ (one click — same OAuth as Outlook)
- Run a QB Desktop report export once (or set it to auto-export via QB's scheduled reports feature)
- Point InboxIQ at the OneDrive folder

**What InboxIQ needs to store:**

```
QuickbooksDesktopSync:
  account_id         FK → accounts
  onedrive_file_path string  (path to the CSV/Excel export in OneDrive)
  last_synced_at     datetime
  sync_status        enum: ok | error | pending
  column_map_json    JSON  (maps QB column names → InboxIQ fields, in case export format varies)
```

---

### Path B — QuickBooks Online API (other customers)

Customers using QuickBooks Online (cloud subscription) get a direct API integration.

- OAuth 2.0 connection via Intuit's developer platform
- Pull invoices, payment status, and line items in real time
- No manual export required — fully automatic
- Config: `QUICKBOOKS_CLIENT_ID`, `QUICKBOOKS_CLIENT_SECRET` env vars

**What InboxIQ stores:**

```
QuickbooksOnlineConnection:
  account_id         FK → accounts
  qbo_realm_id       string  (Intuit company ID)
  access_token       encrypted
  refresh_token      encrypted
  token_expires_at   datetime
  last_synced_at     datetime
```

---

### Shared behaviour (both paths)

- Each Waybill has an `invoice_ref` field — the QB invoice number
- InboxIQ matches waybill → invoice automatically after each sync
- Waybills with no matched invoice after 24 hours are flagged for Sam
- The auditor sees the matched invoice reference on every waybill in the audit trail — no need to open QuickBooks
- Phase 1: `invoice_ref` is entered manually by staff; sync auto-confirms the match
- Phase 2 onwards: sync populates `invoice_ref` automatically from QB data

---

## 10. Nigeria / Low Bandwidth Considerations

- All API responses paginated — no large payloads
- Waybill and bin card views load incrementally
- SMS fallback for all critical notifications (no internet required on buyer side)
- Offline mode consideration for warehouse staff mobile view:
  - Cache current stock levels on load
  - Queue dispatch actions locally if offline
  - Sync when connection returns (service worker / PWA pattern)
- Avoid image-heavy pages — text and table-driven UI
- All forms must work on Chrome Android (primary browser in Nigeria)

---

## 11. Implementation Phases

### Phase 1 — Core Warehouse (Foundation)
- [ ] Models: StockItem, BinCard, Waybill, WaybillLineItem
- [ ] API: stock, waybills, bin card movements
- [ ] UI: stock list, waybill create/view, bin card history
- [ ] Role-based access: owner, warehouse manager, warehouse staff

### Phase 2 — Reservations & Audit Trail
- [ ] Model: StockReservation
- [ ] "Sold but not collected" state on outbound waybills
- [ ] Audit trail view: waybill → invoice_ref linkage
- [ ] Stock count flow: conduct count, record variance

### Phase 3 — Communication Channels
- [ ] Notification preference on Buyer and User models
- [ ] Email notifications (reuse existing InboxIQ email infra)
- [ ] SMS via Termii (new integration)
- [ ] InboxIQ messaging thread per waybill transaction

### Phase 4 — Auditor & Reporting
- [ ] Auditor role with read-only access
- [ ] AuditReport model and generation
- [ ] Monthly report: variance summary, unlinked waybills, stock count results
- [ ] Export to PDF for auditor's physical records

### Phase 5 — QuickBooks Integration (Future)
- [ ] QuickBooks OAuth connection
- [ ] Pull invoice status automatically
- [ ] Auto-link waybill to QB invoice by reference number
- [ ] Flag unmatched invoices

---

## 12. Files to Create (when implementation begins)

```
src/models/warehouse.py          StockItem, BinCard, Waybill, WaybillLineItem,
                                 StockReservation, Supplier, Buyer,
                                 StockCount, StockCountLine, AuditReport

src/api/v1/warehouse.py          All warehouse API endpoints
src/api/v1/__init__.py           Register warehouse blueprint

src/tasks/warehouse.py           Celery tasks: send notifications,
                                 flag unlinked waybills, generate audit reports

src/notifications/warehouse.py   Email + SMS notification helpers

src/templates/warehouse/         UI templates (stock list, waybill form,
                                 bin card, audit dashboard)

src/settings/routes.py           Add SMS provider config under integrations
```

---

## 13. Open Questions for Sam

1. **Communication preference** — email, SMS, or InboxIQ messaging? (or combination)
2. **Buyer accounts** — do buyers get a login, or are they external recipients only?
3. **QuickBooks access** — does Sam want to connect the QuickBooks API eventually, or keep it as manual reference entry?
4. **Multiple warehouses** — does Sam operate from one location or multiple?
5. **Currency** — invoices in Naira (NGN)? Any foreign currency purchases from suppliers?
6. **Who conducts stock counts** — Sam, the manager, or a separate team?
7. **Auditor access** — does the auditor get a login or receive reports by email only?

---

*Plan created: 2026-03-20. Do not begin implementation until Sam confirms preferences above.*
