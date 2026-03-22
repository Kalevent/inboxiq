# Sam — Warehouse Distribution Workflow Implementation Plan

**Customer:** Sam (Nigeria)
**Business:** Distribution / trading company
**Context:** Brittle internet, smartphone-first users, low tech literacy among warehouse staff
**Status:** Planning — do not implement until confirmed with Sam

---

## 1. Business Overview

Sam's company buys goods from suppliers and sells to buyers. The warehouse is the physical hub. All three core documents — the invoice, the waybill, and the bin card — are physical paper. The invoice is a handwritten or pre-printed paper document given to the buyer; the same sale is also entered separately into QuickBooks (Desktop, via Microsoft OneDrive) as a sale record. QuickBooks is the only digital element, syncing to the cloud twice a day. The waybill is issued from a pre-printed carbonless book. The bin card is a physical card on the shelf, updated by hand after each movement.

### Core Entities

| Entity | Description |
|---|---|
| **Waybill** | Document listing goods in a movement (inbound from supplier, outbound to buyer) |
| **Invoice** | Physical paper document given to the buyer. The same sale is also entered separately into QuickBooks as a sale record. |
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
  → Purchase entered into QuickBooks as a bill/purchase record
  → OneDrive syncs to cloud (up to twice a day)
```

### Flow B — Goods Outbound (Warehouse → Buyer)

```
Sam's team writes a physical paper invoice → buyer receives invoice + waybill
  → Sale entered separately into QuickBooks as a sale record
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

## 3a. Stock States & Bin Card Trigger Rules

This section is the source of truth for how stock moves between states and what triggers each bin card entry. Implement nothing that contradicts these rules.

---

### The three documents and what they own

| Document | System | Owns | Does NOT own |
|---|---|---|---|
| Invoice | QuickBooks | Financial record — price, tax, payment terms | Stock levels, goods movement |
| Waybill | InboxIQ | Logistics record — goods moving, direction, parties | Financial amounts |
| Bin Card | InboxIQ | Running stock ledger per SKU | Financial or logistics decisions |

**The invoice never touches the bin card directly. The waybill does.**

---

### Stock states per SKU

At any point in time, every unit of a SKU is in exactly one of three states:

| State | Meaning | Visible to staff as |
|---|---|---|
| **Available** | In warehouse, uncommitted | Can be sold |
| **Reserved** | Sold, waybill created, buyer not yet collected | Committed — cannot be sold again |
| **Dispatched** | Physically left the warehouse | Gone — not in stock |

```
Available stock = Bin card balance − Reserved quantity
```

This is what Sam sees on his phone. Not the raw bin card balance — the available balance.

---

### Bin card trigger rules — Outbound (sale to buyer)

| Action | Who does it | Bin card entry | Stock state change |
|---|---|---|---|
| Outbound waybill created | Staff (InboxIQ) | No entry yet | Available → Reserved |
| Waybill marked Dispatched | Warehouse staff (one tap) | −quantity | Reserved → Dispatched |
| Waybill cancelled | Staff or Sam | No entry | Reserved → Available (released) |

**Rule**: A waybill being created does not reduce the bin card balance. It reserves the quantity. The bin card balance only decreases when the waybill is marked Dispatched.

This means:
- The bin card balance always reflects physical stock in the warehouse (including reserved goods still on the shelf)
- The available balance is what staff and Sam act on
- An auditor can verify: bin card balance − reservations = available at any point in time

---

### Bin card trigger rules — Inbound (supplier delivery)

| Action | Who does it | Bin card entry | Stock state change |
|---|---|---|---|
| Inbound waybill created | Warehouse manager (InboxIQ) | No entry yet | — |
| Goods checked against waybill | Warehouse manager | No entry yet | — |
| Waybill marked Received | Warehouse manager (one tap) | +quantity received | Stock increases |
| Discrepancy recorded | Warehouse manager | +quantity actually received | Notes show expected vs received |

**Rule**: The bin card increases only when the waybill is marked Received — not when the truck arrives, not when the waybill is created.

---

### Bin card trigger rules — Adjustments

| Action | Who does it | Bin card entry | Notes |
|---|---|---|---|
| Stock count conducted | Warehouse manager / Sam | Adjustment entry (±variance) | Linked to StockCount record |
| Manual adjustment | Sam only | Adjustment entry with reason | Auditor can see all manual adjustments |

Manual adjustments are always visible to the auditor. There is no way to adjust stock silently.

---

### The full outbound sequence with document trail

```
1. Sale agreed verbally or in writing
         ↓
2. Invoice raised in QuickBooks (financial record created)
   — Bin card: no change
   — Stock state: no change
         ↓
3. Staff creates outbound waybill in InboxIQ
   — Enters buyer, SKU(s), quantities, QB invoice reference
   — Bin card: quantity moves to Reserved
   — Available stock decreases immediately
   — PDF generated: 3 copies printed (Customer / Driver / Warehouse)
         ↓
4. Driver collects goods from warehouse
   — Paper copies handed to driver as before
   — Staff taps "Mark as Dispatched"
   — Bin card entry: −quantity (Reserved → Dispatched)
   — Buyer notified via SMS / email
         ↓
5. QuickBooks sync (Phase 2+)
   — InboxIQ reads QB invoice export from OneDrive
   — Matches waybill invoice_ref to QB invoice number
   — Flags any waybill with no matching QB invoice (audit alert)
```

---

### The full inbound sequence with document trail

```
1. Supplier arrives with goods + their own paper waybill + invoice
         ↓
2. Warehouse manager creates inbound waybill in InboxIQ
   — Enters supplier, SKU(s), quantities expected, supplier waybill reference
   — Bin card: no change yet
         ↓
3. Manager physically checks goods against supplier waybill
   — Counts goods, checks SKU and condition
         ↓
4. Manager taps "Mark as Received" (with actual quantity if different)
   — Bin card entry: +quantity received
   — If discrepancy: notes recorded, Sam alerted
         ↓
5. Sam enters supplier invoice into QuickBooks as a purchase
   — InboxIQ inbound waybill linked to QB purchase reference
```

---

### Edge cases to handle explicitly

| Scenario | Correct behaviour |
|---|---|
| Buyer cancels after waybill created | Cancel waybill → reservation released → available stock restored |
| Partial delivery (supplier short-ships) | Mark received with actual qty → discrepancy note → Sam alerted |
| Goods returned by buyer | New inbound waybill (direction: return) → bin card increases |
| Stock count finds variance | Adjustment entry linked to StockCount — never edit existing entries |
| Staff creates waybill for wrong SKU | Cancel waybill → create new one — no direct editing of dispatched entries |

---

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
- Digital waybill creation with printable PDF output (replaces pre-printed carbonless books)
- Stock reservation for sold-but-uncollected goods
- Audit trail — every movement logged with timestamp and user
- QuickBooks sync awareness (flag unsynced transactions)
- Auditor dashboard and monthly report generation
- Multi-channel notifications (buyer, staff, auditor, Sam)

---

## 4a. Printable Waybill — The 3-Copy Paper System

Sam uses a 3-part carbonless waybill book. This is a **trust mechanism**, not a paper habit — each party holds physical proof of a transaction. Regulatory and operational norms in Nigeria distribution make this non-negotiable. Do not try to replace it with digital-only delivery.

**InboxIQ's role**: replace the pre-printed carbonless book with a PDF that staff print. The paper flow is identical. The difference is the digital record is created at the moment of print.

### How the 3 copies work

| Copy | Goes to | Purpose |
|---|---|---|
| 1 | Customer / buyer | Their proof of goods received |
| 2 | Driver | Proof they delivered the goods |
| 3 | Warehouse manager | Triggers bin card update; retained for auditor |

Inbound (supplier waybill) is the mirror: supplier keeps original, driver returns a signed copy to the supplier as proof of delivery, warehouse manager keeps one for the inbound record.

### Copy identification — text labels, not colour

Colour printing is expensive and unreliable in Nigeria. Do not design around colour-coded copies.

InboxIQ generates a **3-page PDF** from a single waybill record. Each page is identical in content but has a large bold header identifying it:

```
Page 1: ── CUSTOMER COPY ──
Page 2: ── COLLECTOR'S COPY ──   (buyer's driver or representative who physically collects)
Page 3: ── WAREHOUSE COPY ──
```

Staff print all 3 pages in one black-and-white print job. No handwriting, no colour required. The reference number on all 3 copies ties them together.

### What the PDF must contain

- Sam's company name and logo (letterhead)
- Waybill number (large, top of page) + QR code linking to the digital waybill record
- Date, buyer/supplier name, collector name
- Line items: SKU, description, quantity, unit
- Signature lines: Collector signs | Warehouse manager signs
- Copy label at top: `── CUSTOMER COPY ──` / `── COLLECTOR'S COPY ──` / `── WAREHOUSE COPY ──`

### What InboxIQ does NOT track after print

Once the waybill is printed and handed to the collector, the paper flow is Sam's concern. InboxIQ does not model where each copy is physically filed or who passes their copy on.

InboxIQ asks one question later: **did the goods actually leave?**
That is a two-step action: signature capture → "Mark as Dispatched".

### Printable waybill workflow

```
Staff raises waybill in InboxIQ (phone or desktop)
  → Digital record created, bin card marked reserved
  → Waybill token generated + SMS sent to buyer with secure link
  → Staff taps "Print Waybill" → 3-page PDF generated (if power/printer available)
  → Staff prints all 3 pages (black and white)
  → Buyer takes 2 copies; warehouse keeps 1
  → [Buyer brings copies to warehouse when collecting — InboxIQ not involved]
  → Collector arrives — staff verify paper copy OR digital link on collector's phone
  → Staff tap "Collect Signature" → collector signs on screen
  → Staff tap "Mark as Dispatched"
  → Bin card updates: reserved → dispatched
  → Buyer notified automatically via their preferred channel
```

---

## 4b. Digital Waybill — No Printer / No Power Fallback

Power cuts are common in Nigeria. If the printer is unavailable, the dispatch flow must not stop.

### How it works

When the waybill is created (bin card marked reserved), InboxIQ immediately generates a **waybill token** — a cryptographically signed, time-limited URL — and sends it to the buyer via SMS:

```
"Hello Emeka, your goods are ready for collection at Sam's Warehouse.
Show this link when you arrive: https://app.inboxiq.com/w/WB-0042?token=<t>&exp=<ts>
This link expires in 7 days. Ref: WB-0042"
```

The collector shows the link on their phone screen. Warehouse staff tap the transaction on their own phone to verify it matches.

### Token security design

| Property | Implementation |
|---|---|
| Signed | HMAC-SHA256(transaction_id + account_id + expiry, server_secret) — any URL modification breaks the signature |
| Time-limited | Expires 7 days after creation (configurable per account) — old links become invalid |
| Minimal data exposure | Link page shows goods and quantities only — no prices, no other customers, no stock levels |
| Does not release goods | Scanning the link shows information only. Goods are released only when warehouse staff tap "Mark as Dispatched" on their authenticated session |
| Audit log | Every access to the link is logged: timestamp, IP, user agent — visible to Sam and auditor |

Token verification endpoint (unauthenticated, token-protected):
```
GET /w/<waybill_ref>?token=<t>&exp=<ts>
  → Recompute HMAC, verify signature and expiry
  → Valid: render mobile waybill page (goods + qty only)
  → Invalid or expired: "This waybill link has expired. Contact the seller."
```

### Collector signature capture

When the collector is present at the warehouse, staff tap **"Collect Signature"** — the phone screen becomes a signature pad. The collector draws their signature on the screen.

**OTP fallback** (if collector cannot sign): InboxIQ sends a one-time PIN to the buyer's registered phone. The collector reads it out. Staff enter it. The OTP match is stored as the collection acknowledgment.

The signature (PNG) or OTP record is permanently attached to the waybill. The auditor can view or print it alongside the bin card entry.

### Waybill model additions

```
Waybill:
  waybill_token           string    (HMAC-signed token, hashed for storage)
  waybill_token_expires   datetime  (default: 7 days from creation)
  waybill_sms_sent_at     datetime  (nullable)
  collector_signature_url string    (S3 URL via files.kalevent.com — nullable)
  collector_signed_at     datetime  (nullable)
  dispatch_otp            string    (hashed — cleared after use)
  dispatch_otp_expires    datetime  (nullable)
  dispatched_by_user_id   FK → users (nullable)
```

The `collector_signature_url` uses the existing upload infrastructure (`src/uploads.py`) — stored in S3, served from `files.kalevent.com` with `Content-Disposition: attachment`.

### New API endpoint

```
GET  /w/<waybill_ref>                   public, token-verified — digital waybill view
POST /api/v1/warehouse/waybills/<id>/signature   upload collector signature PNG
POST /api/v1/warehouse/waybills/<id>/otp         generate OTP (sends SMS to buyer)
POST /api/v1/warehouse/waybills/<id>/otp/verify  verify OTP, record acknowledgment
```

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
GET    /api/v1/warehouse/waybills/<id>/pdf  generate 3-page printable PDF (Customer / Driver / Warehouse copies)

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

### Phase 2 — Reservations, Digital Waybill & Audit Trail

- [ ] Model: StockReservation
- [ ] "Sold but not collected" state on outbound waybills
- [ ] Waybill token generation (HMAC-signed, time-limited) on waybill creation
- [ ] SMS delivery of digital waybill link to buyer (Termii)
- [ ] Public token-verified waybill view endpoint (`GET /w/<ref>?token=...`)
- [ ] Collector signature capture (signature pad on phone → S3 upload via `src/uploads.py`)
- [ ] OTP fallback: generate + verify dispatch OTP via SMS
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
