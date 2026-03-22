# Sam — Alternative Implementation Plan (InboxIQ as Transaction System)

> Status: Draft — 2026-03-22
> **Alternative to [sam_warehouse_workflow_plan.md](sam_warehouse_workflow_plan.md)**
> Core difference: Single Transaction table replaces separate Invoice + Waybill models.
> InboxIQ owns invoice creation. QuickBooks is an optional export.
> See alternative VP: [sam_vp_alternative.md](sam_vp_alternative.md)

---

## Why This Alternative Exists

In Sam's current business, three documents are all physical paper: the invoice (given to the buyer, and separately entered into QuickBooks as a sale), the waybill (issued from a pre-printed carbonless book), and the bin card (a physical card updated by hand after every movement). QuickBooks — accessed via Microsoft OneDrive, syncing twice a day — is the only digital record, and it only captures the financial side.

The primary plan keeps this split: invoice in QB, waybill and bin card in InboxIQ, a reference number linking them, staff entering data twice.

This alternative collapses everything into one. A single Transaction record in InboxIQ is the source of truth. From it, InboxIQ generates the invoice, the waybill, and the bin card automatically. QB becomes an optional export for the accountant — not an operational dependency.

The bin card is preserved in full — generated automatically from the transaction history and printable per SKU in the format Sam's auditor already knows.

---

## 1. Core Design Principle

> One transaction — two documents — one bin card entry.

Everything that happens in Sam's warehouse is a transaction:
- A sale (goods out, money owed in)
- A purchase from a supplier (goods in, money owed out)
- A payment received or made
- A stock adjustment

From one transaction record, InboxIQ generates:
- **Invoice PDF** — financial document (price, VAT, total, payment terms)
- **Waybill PDF** — logistics document (goods, qty, driver, destination — no prices)
- **Bin card entry** — automatically, on status change (no staff action required)

---

## 2. Data Models

### 2.1 Transaction

```
id                  UUID
account_id          FK → accounts
transaction_number  string  (auto-generated: INV-0001 for sales, PO-0001 for purchases)
type                enum: sale | purchase | payment_in | payment_out | adjustment
status              enum: draft | confirmed | dispatched | received | paid | cancelled
counterparty_id     UUID
counterparty_type   enum: buyer | supplier
transaction_date    date
due_date            date (nullable)
subtotal            Numeric
vat_rate            Numeric  (default 0.075 for Nigeria)
vat_amount          Numeric  (computed: subtotal × vat_rate)
total_amount        Numeric  (computed: subtotal + vat_amount)
payment_status      enum: unpaid | part_paid | paid
amount_paid         Numeric  (default 0)
driver_name         string (nullable — outbound only)
notes               text
created_by          FK → users
created_at          datetime
updated_at          datetime
```

### 2.2 TransactionLineItem

```
id                  UUID
transaction_id      FK → Transaction
stock_item_id       FK → StockItem
description         string  (copied from StockItem.name, editable)
quantity_expected   integer
quantity_fulfilled  integer  (filled on dispatch or receipt)
unit_price          Numeric
line_total          Numeric  (computed: quantity_expected × unit_price)
discrepancy_notes   text (nullable)
```

### 2.3 BinCard (generated, not manually entered)

```
id                  UUID
account_id          FK → accounts
stock_item_id       FK → StockItem
transaction_id      FK → Transaction (nullable — null for manual adjustments)
movement_type       enum: inbound | outbound | reserved | reservation_released | adjustment | stock_count
quantity            integer  (positive = stock increases, negative = stock decreases)
balance_after       integer  (running total — always maintained)
reference           string   (transaction_number or stock count reference)
notes               text
created_by          FK → users  (system user for auto-entries, staff for manual)
created_at          datetime
```

**Rules — bin card is never manually edited:**
- Entries are created automatically by the system on transaction status changes
- Manual adjustments create a new entry (type: adjustment) — never modify existing ones
- All adjustments are visible to the auditor — there is no silent edit path

### 2.4 StockItem, Supplier, Buyer, StockCount, StockCountLine, AuditReport

Unchanged from primary plan. See [sam_warehouse_workflow_plan.md](sam_warehouse_workflow_plan.md) sections 6.1, 6.6, 6.7, 6.8, 6.9, 6.10.

---

## 3. Bin Card Trigger Rules

The bin card is owned by the system. Staff never update it directly.

### Outbound (sale to buyer)

| Transaction status change | Bin card entry | Effect on stock |
|---|---|---|
| draft → confirmed | reserved: −quantity | Available decreases, balance unchanged |
| confirmed → dispatched | outbound: −quantity, reservation released | Balance decreases |
| confirmed → cancelled | reservation_released: +quantity | Available restored |
| dispatched → cancelled (return) | inbound: +quantity | Balance increases |

### Inbound (purchase from supplier)

| Transaction status change | Bin card entry | Effect on stock |
|---|---|---|
| draft → confirmed | No entry | — |
| confirmed → received | inbound: +quantity_fulfilled | Balance increases |
| received (partial) | inbound: +quantity_fulfilled, note: expected vs received | Balance increases by actual qty |

### Available stock formula

```
Available = BinCard.balance_after (latest entry per SKU)
           − sum of reserved quantities for that SKU (confirmed but not dispatched)
```

This is what Sam and staff see. Never the raw balance.

---

## 4. Printable Documents Generated from One Transaction

### 4.1 Invoice PDF

- Sam's letterhead + logo
- Transaction number, date, due date
- Buyer name and address
- Line items: description, quantity, unit price, line total
- Subtotal, VAT (7.5%), total amount
- Payment terms and bank details
- "INVOICE" header

### 4.2 Waybill PDF — 3 pages, text-labelled (no colour printing)

All 3 pages contain identical logistics information. Only the header label differs.

```
Page 1: ── CUSTOMER COPY ──
Page 2: ── COLLECTOR'S COPY ──   (buyer's driver or representative who physically collects)
Page 3: ── WAREHOUSE COPY ──
```

Each page contains:
- Sam's letterhead + logo
- Waybill reference (same as transaction number)
- Date, buyer name, collector name
- Line items: description, quantity, unit — **no prices**
- QR code — links to the digital waybill (signed, time-limited token — see section 4.4)
- Signature lines: Collector signature | Warehouse manager signature

No colour printing required. One black-and-white print job, 3 pages.

### 4.3 Bin Card PDF — printable per SKU

The auditor can print the bin card for any SKU for any date range. Format matches the traditional paper card the auditor already knows.

```
SKU: RICE-50KG | Product: Rice (50kg bag) | Period: 01 Mar – 31 Mar 2026
─────────────────────────────────────────────────────────────────────────
Date        Reference    In    Out   Reserved   Balance   Notes
2026-03-01  INV-0041          30              70
2026-03-05  PO-0018     100                   170
2026-03-10  INV-0042               20         170        reserved - Emeka
2026-03-12  INV-0042          20              150        dispatched
─────────────────────────────────────────────────────────────────────────
Closing balance: 150 units
```

- Printable as PDF per SKU, per period
- Exportable as CSV for the auditor's own records
- Accessible from the auditor's read-only login at any time

### 4.4 Digital Waybill — No Printer / No Power Fallback

Power cuts are common in Nigeria. The dispatch flow must not stop when the printer is down.

When a transaction moves to `confirmed`, InboxIQ generates a **waybill token** — a cryptographically signed, time-limited URL — and sends it to the buyer immediately via SMS:

```
"Hello Emeka, your goods are ready for collection at Sam's Warehouse.
Show this link when you arrive: https://app.inboxiq.com/w/INV-0042?token=<t>&exp=<ts>
This link expires in 7 days. Ref: INV-0042"
```

The collector shows the link on their phone. Warehouse staff verify it matches their system. No printer required.

**Token security:**

| Property | Implementation |
| --- | --- |
| Signed | HMAC-SHA256(transaction_id + account_id + expiry, server_secret). Any URL modification breaks the signature immediately |
| Time-limited | Expires 7 days after creation (configurable). Old links are automatically invalid |
| Minimal exposure | Page shows goods and quantities only — no prices, no other customers, no stock position |
| No unilateral release | Scanning the link shows information only. Release requires warehouse staff to tap "Mark as Dispatched" on their own authenticated session |
| Audit log | Every access logged: timestamp, IP, user agent — visible to Sam and auditor |

**Collector signature capture:**

When the collector is present, warehouse staff tap **"Collect Signature"** — the phone becomes a signature pad. The collector draws their signature on screen. This replaces the physical signature on the paper warehouse copy.

**OTP fallback** (if collector cannot sign): InboxIQ sends a one-time PIN to the buyer's registered phone. The collector reads it out. Staff enter it. The OTP match is stored as the acknowledgment.

The signature PNG or OTP record is permanently attached to the transaction. The auditor can view or print it alongside the bin card entry.

**Transaction model additions:**

```
Transaction:
  waybill_token           string    (HMAC-signed token, stored hashed)
  waybill_token_expires   datetime  (default: 7 days from confirmation)
  waybill_sms_sent_at     datetime  (nullable)
  collector_signature_url string    (S3 via files.kalevent.com, Content-Disposition: attachment)
  collector_signed_at     datetime  (nullable)
  dispatch_otp            string    (hashed — cleared after use)
  dispatch_otp_expires    datetime  (nullable)
  dispatched_by_user_id   FK → users (nullable)
```

**Endpoints:**

```
GET  /w/<transaction_ref>?token=<t>&exp=<ts>    public, token-verified — mobile waybill view
POST /api/v1/warehouse/transactions/<id>/signature   upload collector signature PNG
POST /api/v1/warehouse/transactions/<id>/otp         generate and send OTP to buyer phone
POST /api/v1/warehouse/transactions/<id>/otp/verify  verify OTP, record acknowledgment
```

---

## 5. The Two Core Flows

### Flow A — Outbound Sale

```
Staff creates Transaction (type: sale) in InboxIQ
  → Select buyer from dropdown
  → Add line items (SKU + quantity + unit price)
  → VAT calculated automatically
  → Status: draft
        ↓
Staff confirms transaction
  → Invoice PDF available
  → Waybill PDF (3 pages) available to print
  → Bin card: quantities reserved
  → Status: confirmed
        ↓
Staff prints waybill — buyer takes 2 copies (one for themselves, one for their driver/collector)
Warehouse keeps the third copy
[Buyer brings their copy to the warehouse when collecting — InboxIQ not involved in this exchange]
        ↓
Buyer or buyer's driver/collector arrives to collect goods
Staff verify the waybill copy the buyer has brought
Goods handed over — buyer's collector departs
Staff tap "Mark as Dispatched"
  → Bin card: quantities deducted (reservation cleared)
  → Buyer notified (SMS or email confirming dispatch)
  → Status: dispatched
        ↓
Payment received — staff records payment
  → payment_status → paid, amount_paid updated
  → Status: paid
```

### Edge Case — Invoice Raised, Buyer Has Not Yet Collected

This is Sam's most common and most costly scenario. A sale is agreed. The transaction is confirmed. But the buyer does not collect immediately — they arrive hours, days, or longer later. During that window the goods are physically on the shelf and visible to other staff.

**How InboxIQ handles it:**

When a transaction moves to `confirmed`, the system immediately reserves the line item quantities. No separate action by staff is required — reservation is automatic on confirmation.

```
Transaction confirmed (type: sale, status: confirmed)
  → For each line item:
       BinCard entry: movement_type = reserved, quantity = −line_item.quantity_expected
       Available stock decreases immediately
       Balance unchanged (goods still physically present)

Staff stock view shows:
  Rice (50kg) — Balance: 150 | Reserved: 30 (INV-0042 – Emeka) | Available: 120
```

Reserved goods cannot be sold or allocated to any other transaction. The system enforces this — it is not a manual process or a written rule.

**When the buyer collects:**

Staff tap "Mark as Dispatched" → transaction moves to `dispatched`:
- BinCard entry: movement_type = outbound, quantity = −quantity_fulfilled
- Reservation entry is cleared
- Balance decreases

**When the buyer cancels or does not come:**

Staff cancel the transaction → status = `cancelled`:
- BinCard entry: movement_type = reservation_released, quantity = +quantity_expected
- Available stock restored immediately
- No bin card correction needed — a release entry is added, nothing is deleted

**What the auditor sees:**

Every reservation, every release, and every dispatch is a separate dated entry on the bin card. The auditor can reconstruct exactly when goods were committed, to whom, and when they were either collected or released. Nothing is hidden or overwritten.

---

### Flow B — Inbound Purchase from Supplier

```
Supplier arrives with goods + their own paper waybill + invoice
        ↓
Warehouse manager creates Transaction (type: purchase) in InboxIQ
  → Select supplier from dropdown
  → Add line items: SKU + quantity expected (from supplier's waybill)
  → Record supplier's waybill/invoice reference number
  → Status: draft → confirmed
        ↓
Manager physically checks goods against supplier waybill
  → Counts units, checks SKU and condition
        ↓
Manager taps "Mark as Received" — enters actual quantities received
  → Full delivery: bin card +expected qty, status: received
  → Discrepancy (short / damaged / wrong goods):
       - Bin card +actual qty received only
       - Discrepancy notes recorded (timestamp + manager name)
       - Sam alerted immediately via notification
       - Flagged on transaction for auditor review
        ↓
Optional: Supplier receives confirmation notification (SMS or email)
  → "Delivery Ref PO-0018 received. Qty: 100 bags Rice 50kg."
  → Receipt confirmation only — no pricing, no other business info
        ↓
Payment to supplier recorded when made
  → amount_paid updated, payment_status → paid
  → Appears in aged creditors report
        ↓
QuickBooks export (on schedule) includes this purchase transaction
  → Accountant imports to QB — no manual entry needed from Sam
```

### Supplier Waybill — Paper Handling

The supplier brings their own paper waybill. Sam's team does not print one for inbound deliveries. The supplier's waybill reference number is recorded in InboxIQ as `supplier_reference` on the purchase transaction. The auditor can trace any inbound stock movement back to the supplier's original document using this reference.

Sam's team retains the supplier's paper copy in their records as they do today. InboxIQ records alongside it — it does not replace it.

### Discrepancy Handling

| Scenario | InboxIQ behaviour |
|---|---|
| Full delivery, all correct | Bin card +expected qty, status: received |
| Short delivery | Bin card +actual qty, discrepancy noted, Sam alerted |
| Wrong goods delivered | 0 received for wrong SKU, notes added, Sam alerted |
| Goods damaged on arrival | Qty received = undamaged units only, damage notes recorded |

All discrepancies are visible to the auditor and included in the monthly report. The original expected quantity and actual received quantity are always stored — neither is overwritten.

---

## 6. API Endpoints (Blueprint: /api/v1/warehouse)

```
# Transactions
GET    /api/v1/warehouse/transactions              list (filter: type, status, date range)
POST   /api/v1/warehouse/transactions              create transaction
GET    /api/v1/warehouse/transactions/<id>         get transaction + line items
PATCH  /api/v1/warehouse/transactions/<id>         update status or payment
DELETE /api/v1/warehouse/transactions/<id>         cancel (draft only)

# Documents — generated from transaction
GET    /api/v1/warehouse/transactions/<id>/invoice-pdf    generate invoice PDF
GET    /api/v1/warehouse/transactions/<id>/waybill-pdf    generate 3-page waybill PDF

# Bin Card
GET    /api/v1/warehouse/bin-card/<sku_id>         full movement history (filterable by date)
GET    /api/v1/warehouse/bin-card/<sku_id>/pdf     printable bin card PDF
GET    /api/v1/warehouse/bin-card/<sku_id>/export  CSV export

# Stock
GET    /api/v1/warehouse/stock                     all SKUs with available balance
POST   /api/v1/warehouse/stock                     create SKU
GET    /api/v1/warehouse/stock/<id>                SKU detail

# Export for accountant
GET    /api/v1/warehouse/transactions/export       CSV export (QB-importable format)

# Audit
GET    /api/v1/warehouse/audit/trail               full transaction audit trail
POST   /api/v1/warehouse/audit/reports             generate monthly report
GET    /api/v1/warehouse/audit/reports             list reports

# Stock Counts
POST   /api/v1/warehouse/stock-counts              start count
PATCH  /api/v1/warehouse/stock-counts/<id>         submit count results

# Suppliers & Buyers
GET/POST /api/v1/warehouse/suppliers
GET/POST /api/v1/warehouse/buyers
```

---

## 7. QuickBooks Integration — Three Paths, Same Core Model

InboxIQ is the operational system of record in all three paths. The Transaction table does not change. Only how QuickBooks is connected differs.

---

### Path A — No QuickBooks (Sam's default)

InboxIQ is the only system. If Sam's accountant needs a record:

- Export transactions as a structured CSV on demand or on schedule
- Accountant reviews and imports into whatever accounting tool they use
- No QB models needed in Phase 1–4

---

### Path B — QuickBooks Desktop via OneDrive (Sam's current setup)

Sam uses QB Desktop synced via OneDrive. InboxIQ already has Microsoft Graph OAuth wired for Outlook — the same token and connection can write files to OneDrive.

InboxIQ places a structured CSV into a designated OneDrive folder on a schedule. Sam's accountant finds a fresh export waiting, reviews it, and imports it into QB. Sam does not intervene.

```
InboxIQ generates structured CSV (daily or weekly)
        ↓
InboxIQ writes file to OneDrive via MS Graph API
→ e.g. OneDrive/InboxIQ Exports/transactions_2026-03.csv
        ↓
Accountant opens CSV, reviews, imports into QB Desktop
        ↓
Done — no download, no email, no action from Sam
```

**Note on IIF format**: QB Desktop's IIF import format is unreliable for recurring imports and not recommended. The export is a structured CSV — the accountant imports using QB's CSV import or reviews it alongside QB manually. This keeps the accountant in control and prevents silent errors.

**Accuracy safeguards built into the export:**

| Risk | How InboxIQ mitigates it |
|---|---|
| Duplicate transactions | Each export contains only NEW transactions since `last_exported_at`. Every row has a unique InboxIQ reference number the accountant can cross-check in QB |
| Wrong account mapping | One-time setup: accountant defines QB account names in InboxIQ settings. CSV uses exact QB account names. Preview shown before first export |
| VAT miscalculation | VAT rate stored as config (default 7.5% for Nigeria). CSV shows taxable amount, VAT amount, and total as separate columns — accountant verifies maths before importing |
| Partial import failure | Every batch has a batch ID and row count header. InboxIQ can regenerate any batch by ID if the accountant reports a problem |
| Sam entering manually in QB | Process rule enforced on setup: once InboxIQ is live, direct QB entries stop. Export covers a date range — accountant clears any manual QB entries for that period before importing |

**What needs to be configured (once, by accountant):**
- Sam connects Microsoft account in InboxIQ (same OAuth as Outlook — one click)
- Accountant defines QB account name mapping in InboxIQ settings
- Choose OneDrive folder path for exports
- Set export schedule (daily / weekly / monthly)

**What InboxIQ needs to store:**

```
QuickbooksDesktopExport:
  account_id              FK → accounts
  onedrive_folder_path    string   (e.g. /InboxIQ Exports/)
  export_schedule         enum: daily | weekly | monthly
  chart_of_accounts_json  JSON     (maps InboxIQ categories → QB account names)
  last_exported_at        datetime
  last_export_status      enum: ok | error
  last_batch_id           string
```

**Celery task:** `warehouse.export_transactions_to_onedrive` — runs on schedule, generates CSV for new transactions since `last_exported_at`, writes to OneDrive via Graph API, updates `last_exported_at` and `last_batch_id`.

No QB operational dependency. InboxIQ does not read from QB. It only writes exports to the folder the accountant uses.

---

### Path C — QuickBooks Online (other customers)

Customers already using QB Online get a live bidirectional integration. InboxIQ already has the QB Online API and webhook infrastructure in place.

**Direction 1 — InboxIQ pushes to QB Online (default)**

When a transaction is confirmed in InboxIQ, it is automatically created as an invoice or bill in QB Online via the API. The accountant's QB stays current without any manual export.

```
Transaction confirmed in InboxIQ
        ↓
InboxIQ calls QB Online API → creates Invoice (sale) or Bill (purchase)
        ↓
QB Online invoice number written back to Transaction.qbo_invoice_id
        ↓
Payment recorded in InboxIQ → InboxIQ marks invoice paid in QB Online
```

**Direction 2 — QB Online pushes to InboxIQ (for customers who invoice in QB first)**

Some customers prefer to keep raising invoices in QB Online. A QB webhook fires when a new invoice is created.

```
Invoice created in QB Online
        ↓
QB webhook → InboxIQ receives event
        ↓
InboxIQ creates Transaction (type: sale, status: confirmed)
  → Line items populated from QB invoice
  → Buyer matched by name/email or created if new
        ↓
Waybill PDF ready to print immediately
Bin card reserved
Staff notified that goods need to be prepared
```

**QB Online connection model (already exists — confirm field names before implementing):**

```
QuickbooksOnlineConnection:
  account_id         FK → accounts
  qbo_realm_id       string  (Intuit company ID)
  access_token       encrypted
  refresh_token      encrypted
  token_expires_at   datetime
  last_synced_at     datetime
  sync_direction     enum: push | pull | bidirectional
```

**Transaction additions for QB Online sync:**

```
Transaction:
  qbo_invoice_id     string (nullable) — QB Online invoice ID after push
  qbo_synced_at      datetime (nullable)
  qbo_sync_status    enum: pending | synced | error | not_applicable
```

---

### Summary across all paths

| | Path A (no QB) | Path B (QB Desktop) | Path C (QB Online) |
|---|---|---|---|
| Transaction created in | InboxIQ | InboxIQ | InboxIQ (or QB push) |
| Invoice PDF | InboxIQ | InboxIQ | InboxIQ |
| Waybill PDF | InboxIQ | InboxIQ | InboxIQ |
| Bin card | InboxIQ (auto) | InboxIQ (auto) | InboxIQ (auto) |
| QB sync | CSV export on demand | CSV export on demand | Live API — push or pull |
| QB dependency | None | None (optional export) | None (mirror only) |

The core Transaction model is identical across all three paths. QB Online sync is additive — it does not change how InboxIQ works internally.

---

## 8. Implementation Phases

### Phase 1 — Core Transaction Engine

- [ ] Models: Transaction, TransactionLineItem, StockItem, BinCard
- [ ] Bin card auto-generated on transaction status change (signals/hooks)
- [ ] API: transactions CRUD, status transitions
- [ ] Available stock calculation (balance − reserved)
- [ ] Role-based access: owner, warehouse manager, warehouse staff

### Phase 2 — Printable Documents & Digital Waybill

- [ ] Invoice PDF generation (WeasyPrint or ReportLab)
- [ ] Waybill PDF generation — 3-page, text-labelled copies with QR code
- [ ] Bin card PDF generation — per SKU, per period, auditor format
- [ ] Sam's company logo/letterhead on all PDFs
- [ ] Waybill token generation (HMAC-signed, time-limited) on transaction confirmation
- [ ] SMS delivery of digital waybill link to buyer (Termii)
- [ ] Public token-verified waybill view endpoint (`GET /w/<ref>?token=...`)
- [ ] Collector signature capture (signature pad → S3 upload via `src/uploads.py`)
- [ ] OTP fallback: generate + verify dispatch OTP via SMS

### Phase 3 — Communication

- [ ] Buyer notification on dispatch (SMS via Termii, email)
- [ ] Low stock alert to Sam (below reorder level)
- [ ] Discrepancy alert on inbound receipt

### Phase 4 — Audit & Reporting

- [ ] Auditor read-only login
- [ ] AuditReport model and monthly report generation (DSPy)
- [ ] Stock count flow with variance recording
- [ ] CSV export for accountant (QB-compatible format)

### Phase 5 — Payments & Receivables (Future)

- [ ] Payment recording against transactions
- [ ] Aged debtors report (buyers with unpaid invoices)
- [ ] Aged creditors report (suppliers owed payment)

---

## 9. Files to Create (when implementation begins)

```
src/models/warehouse.py          Transaction, TransactionLineItem, BinCard,
                                 StockItem, Supplier, Buyer,
                                 StockCount, StockCountLine, AuditReport

src/api/v1/warehouse.py          All warehouse API endpoints
src/tasks/warehouse.py           Celery: notifications, audit reports, stock alerts
src/notifications/warehouse.py   Email + SMS helpers
src/templates/warehouse/         UI templates
src/warehouse/pdf.py             Invoice PDF, Waybill PDF, Bin Card PDF generation
```

---

## 10. Open Questions for Sam

1. Will his accountant accept a CSV export, or do they require direct QB access?
2. Does the FIRS (Nigerian tax authority) require invoices in a specific format?
3. Will the auditor accept a digitally generated, printable bin card — or do they insist on the physical card?
4. Does Sam want to issue receipts when payment is received?
5. Single warehouse or multiple locations?
6. Currency: Naira only, or foreign currency with some suppliers?

---

*Plan created: 2026-03-22. Present both approaches to Sam. Do not begin implementation until Sam confirms which path and answers open questions above.*
