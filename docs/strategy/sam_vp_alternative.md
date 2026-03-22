# Value Proposition — Sam (Alternative: InboxIQ as Transaction System)

> Status: Draft — 2026-03-22
> **This is an alternative approach to [sam_vp.md](sam_vp.md)**
> Core difference: InboxIQ owns invoice creation. QuickBooks becomes optional.
> See alternative implementation plan: [sam_warehouse_workflow_plan_alternative.md](sam_warehouse_workflow_plan_alternative.md)

---

## The Simplification

In the primary VP, InboxIQ sits alongside QuickBooks — Sam writes a physical paper invoice and enters the sale into QB as he does today; the waybill moves to InboxIQ; the two systems are linked by a reference number written on both documents. Staff still enter data in two places. Sync remains a dependency.

In this alternative, InboxIQ is where Sam's team creates invoices. The waybill is generated from the same transaction — no re-entry, no sync, no dependency on a second system. QuickBooks becomes an optional export for his accountant, not a core workflow tool.

---

## The Problem This Solves (Same as Primary VP)

Sam operates blind. He does not know his real stock position. Goods sold but not collected are invisible. The audit trail is paper and always behind. Staff have no confirmation loop.

See [sam_vp.md](sam_vp.md) for the full problem statement. The pain points are identical. The difference is how InboxIQ solves them.

**Foundation — everything is currently physical paper:**
The invoice is a physical paper document given to the buyer; the same sale is also entered separately into QuickBooks (via Microsoft OneDrive) as a digital record. The waybill is a physical paper document from a pre-printed carbonless book. The bin card is a physical paper card updated by hand after every movement. QuickBooks is the only digital element in Sam's current operation, and it only captures the financial side — it has no connection to the waybill or the bin card.

### Pain point reinforced: Goods invoiced but not yet collected

This scenario is Sam's most costly operational failure and must be explicitly handled in this alternative model — not just implied by the data model.

When a transaction is confirmed in InboxIQ (invoice raised, sale agreed), those goods are **immediately reserved**. The stock balance on the shelf does not change — the goods are still physically there — but they are marked as committed to that buyer and invisible to any new sale.

```
Transaction confirmed (type: sale)
  → Bin card: quantities reserved (available stock decreases, balance unchanged)
  → Staff see: "30 bags Rice — RESERVED — Emeka, INV-0042"
  → Cannot be sold or committed to any other buyer

Buyer arrives and collects
  → Staff tap "Mark as Dispatched"
  → Bin card: quantities deducted (balance decreases)
  → Reservation cleared automatically

Buyer cancels or does not come
  → Staff cancel the transaction
  → Reservation released — stock returns to available immediately
```

**Available stock formula** (what Sam and staff see — never the raw balance):

```
Available = Bin card balance − Reserved quantities
```

This is enforced at the system level, not by a rule on a piece of paper. Overselling becomes structurally impossible.

---

## What Changes

### One system instead of two

| Today | Primary VP | Alternative VP |
|---|---|---|
| Invoice on paper + entered in QB as sale | Invoice in QB + waybill in InboxIQ (linked by reference) | Invoice in InboxIQ — one form generates both |
| Waybill on paper (carbonless book) | Waybill in InboxIQ | Waybill auto-generated from same transaction |
| Bin card on paper (updated by hand) | Bin card in InboxIQ | Bin card generated automatically from transactions |
| QB only digital record (finance only) | Two systems, sync required | One system — QB is optional export only |

### The flow

```
Staff creates transaction in InboxIQ
  → select buyer, add line items, quantities, unit price
  → VAT calculated automatically (7.5% Nigeria)
        ↓
One transaction generates two documents instantly:
  → Invoice PDF   (financial: price, VAT, total, payment terms)
  → Waybill PDF   (logistics: goods, qty, driver — no prices shown)
        ↓
Waybill printed — 3 copies (Customer / Driver / Warehouse)
Bin card: goods reserved immediately
        ↓
Goods dispatched — staff tap "Mark as Dispatched"
Bin card: goods deducted
Buyer notified via SMS or email
        ↓
Payment received — staff record payment amount
Transaction closes
```

### Bin card — digital and printable

The bin card is not a separate data entry. It is **generated automatically** from the transaction history for each SKU. Every inbound and outbound transaction that moves a SKU creates a bin card entry automatically.

The auditor can:
- View the digital bin card in real time from their login
- Print the bin card per SKU as a PDF — format matches the traditional paper card (date, reference, in, out, running balance)
- Export the full period bin card history to CSV

The auditor's workflow does not change. The bin card is simply always current and always printable, instead of being a manual card on a shelf.

---

## What Sam Does Not Have to Change

- Waybills still exist — printed, 3 copies, handed to the buyer and their collector exactly as before
- The bin card still exists — the auditor still uses it, it just lives in InboxIQ
- Buyers still receive their copy of the waybill and payment invoice
- Signature and paper ceremony unchanged — InboxIQ generates the paper, Sam's team handles it

## What Sam No Longer Needs

- QuickBooks as a day-to-day operational tool
- Manual double-entry (invoice in QB, waybill in InboxIQ)
- OneDrive sync dependency
- Waiting 12 hours for QB to sync before stock position is current

QuickBooks remains available if Sam's accountant requires it. InboxIQ exports transactions in a format the accountant can import. Sam never needs to open QuickBooks himself.

---

## Why This Is The Simpler Build

| Complexity point | Primary VP | Alternative VP |
|---|---|---|
| Invoice creation | QB (out of our control) | InboxIQ — one form |
| Waybill data entry | Manual re-entry of QB invoice data | Auto-populated from transaction |
| QB sync | Required — OneDrive polling, CSV parsing | Optional export only |
| Bin card | Generated from waybill events | Generated from transaction events |
| Audit trail | Waybill + QB invoice cross-referenced | Single transaction — all in one place |

---

## Open Questions Before Pitching This Alternative to Sam

1. Is Sam willing to stop entering sales into QuickBooks and let InboxIQ export to QB instead? (His accountant may resist.)
2. Does his accountant accept a CSV export, or do they require QB access directly?
3. Does Sam need to issue VAT invoices in a specific FIRS-approved format?
4. Will the auditor accept a digitally generated bin card printout, or do they require the physical card?
5. Currency: Naira only, or does Sam deal with foreign currency suppliers?

---

*Written: 2026-03-22. Present both VP approaches to Sam before committing to either.*
