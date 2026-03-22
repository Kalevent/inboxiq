# InboxIQ for Your Business — What We Are Building for You

> Prepared for: Sam
> Date: March 2026
> Purpose: Review and confirm before we begin building

---

## The Problem We Are Solving

Here is how your business works today — as you described it:

**Everything in your warehouse runs on physical paper.** The invoice is a paper document. The waybill is a paper document from a pre-printed book. The bin card — the running record of your stock balance for each product — is a physical card. These three paper documents are the backbone of your operation.

The only digital record you have is QuickBooks, which sits inside your Microsoft OneDrive. When a sale is made, the invoice is entered into QuickBooks as a sale. QuickBooks syncs to the cloud twice a day — so for up to twelve hours, what QuickBooks shows and what actually happened in your warehouse may not match.

**When a buyer purchases goods**, your team writes a paper invoice and a paper waybill. The buyer takes both documents and later brings them to your warehouse to collect their goods. Your staff check the waybill, release the goods, and then manually write the movement onto the bin card. That bin card entry happens after the goods have already left — a staff member copies the details from the waybill onto the card by hand. If they forget, write the wrong quantity, or do it late, your stock records are already wrong.

**When a supplier delivers**, they arrive with their own paper waybill — in three copies — and their paper invoice. Your warehouse manager takes the waybill, oversees the unloading, and checks that what came off the truck matches what is on the paper. The purchase is then entered separately into QuickBooks as a purchase record.

**Your auditor visits periodically** and works entirely from paper. They pick up the physical waybills, find the matching invoice in QuickBooks, and verify that every dispatch is properly recorded. They also do a physical stock count and compare what they count on the shelves against the inventory balance in QuickBooks at that point in time. They produce a monthly report with any discrepancies and lessons learned.

**The grey zone** is goods that have been invoiced and the paper documents issued, but where the buyer has not yet come to collect. Those goods are still physically on your shelf. Your bin card still shows them as available — because the bin card is only updated after goods physically leave. Another staff member could unknowingly commit the same goods to a different buyer.

Every one of these problems has the same root cause: three separate paper documents, updated after the fact, by hand, with no connection between them except the reference number a person writes. InboxIQ replaces all three with a single digital record — one entry that updates the invoice, the waybill, and the bin card at the same moment — while still producing the printed paper documents your team and your auditor are used to.

---

## How It Works — One Form, Everything Else Is Automatic

Today, when you make a sale, your team does several things separately:
- Write a paper invoice and enter the sale into QuickBooks
- Fill in a waybill on paper
- Update the bin card by hand
- Call or message the buyer

With InboxIQ, your team fills in **one form**. Everything else happens automatically.

Here is what that looks like step by step:

---

### Step 1 — Your team creates a transaction

When a sale is agreed, your staff open InboxIQ on their phone or computer and fill in one simple form:

- Who is the buyer?
- What goods are they taking?
- How many units?
- What is the price?

InboxIQ calculates VAT automatically. The form takes about one minute to complete.

---

### Step 2 — Two documents are ready instantly

As soon as the form is saved, InboxIQ produces two documents automatically:

**The Invoice**
A formal payment document showing the buyer's name, the goods, the price, VAT, and the total amount owed. This replaces the QuickBooks invoice your team currently raises separately.

**The Waybill**
A goods movement document for the buyer. It shows the goods and quantities only — no prices. The buyer takes their copy and a copy for their driver or collector when the sale is agreed. They bring those copies to your warehouse when collecting.

Your staff print the waybill from any printer. It comes out as **three pages automatically labelled** in large bold text:

```
CUSTOMER COPY       (buyer keeps this)
COLLECTOR'S COPY    (buyer's driver or person who collects keeps this)
WAREHOUSE COPY      (your warehouse manager keeps this)
```

No colour printing is needed. Black and white is perfectly fine. Nothing changes about how the copies are handled today.

---

### Step 3 — Your stock is reserved immediately

The moment the waybill is created, InboxIQ marks those goods as **reserved**. They are still physically on your shelf, but the system shows them as committed to that buyer. No other staff member can sell the same goods to a different buyer by mistake.

Your current bin card stays up to date automatically — you do not need to write on it.

---

### What Happens When a Buyer Has Not Yet Collected

Sometimes a sale is agreed and an invoice is raised, but the buyer does not collect the goods immediately. They may come the next day, two days later, or longer. During that time, the goods are still physically sitting on your shelf.

Today, this is where things go wrong. The bin card still shows those goods as available. A different staff member could commit the same goods to another buyer. By the time the first buyer arrives to collect, the goods are gone — and you have a dispute on your hands.

InboxIQ handles this automatically. The moment the transaction is created and confirmed, those goods are marked as **reserved** in the system. Every member of your staff can see that those specific goods are committed to a specific buyer and are not available for anyone else.

The reserved goods remain on your shelf. They are still in your warehouse. But they are invisible to any new sale until the buyer collects them or the reservation is cancelled.

What your staff see when they check stock:

> Rice (50kg) — 150 bags in warehouse. **Available: 120 bags. Reserved: 30 bags (Emeka — INV-0042).**

Nobody can accidentally sell Emeka's 30 bags. Not because a rule was written on a piece of paper — because the system simply will not show them as available.

If the buyer cancels or does not show up, your staff cancel the transaction. The 30 bags return to available stock immediately. No bin card correction needed. No crossed-out entry on a paper card.

---

### Step 4 — Goods leave the warehouse

When the buyer's driver or collector arrives, your staff verify their copy of the waybill and release the goods.

---

### What if there is no power to print the waybill?

Power cuts are a fact of business in Nigeria. If the printer is down, the buyer's collector should not be turned away and your warehouse should not stop operating.

When the waybill is created in InboxIQ, the system immediately sends a short SMS to the buyer's phone containing a secure link. The collector shows that link on their phone screen when they arrive. Your warehouse staff confirm it matches their system — no paper needed.

The link is protected:
- It is tied to one specific transaction and expires after seven days
- It cannot be forged or modified — any tampering makes it invalid immediately
- It only shows the goods and quantities for that transaction. No prices, no other customers, no stock levels — nothing sensitive
- Scanning or opening the link does not release the goods. Goods are only released when your warehouse staff tap "Mark as Dispatched" on their own phone

This means your warehouse can keep running even when the printer is down.

---

### Collector signature — proof of receipt

When the collector is ready to take the goods, your warehouse staff tap **"Collect Signature"** on their phone. The screen becomes a signing pad. The collector draws their signature directly on the screen.

This replaces the physical signature your staff currently take on the paper warehouse copy. The signed record is permanently attached to the transaction. If there is ever a dispute about whether goods were collected, the signed record — with the date, time, and the name of the warehouse staff member who confirmed it — is there.

**If the collector cannot sign** (for example, they have an injury), your staff can use the OTP fallback: InboxIQ sends a one-time code to the buyer's registered phone number. The collector reads it out. Your staff enter it. The system records it as the acknowledgment of collection.

---

After the collector's signature is captured, one of your warehouse staff taps **"Mark as Dispatched"**.

That one tap does three things at the same time:
1. Updates your stock balance (goods are now gone from the warehouse)
2. Sends the buyer a notification that their goods are on the way
3. Records the movement in your audit trail with the time, the staff member's name, and the collector's signature

---

### Step 5 — Payment is recorded

When payment arrives — cash, bank transfer, or cheque — your staff record it against the transaction. InboxIQ tracks which invoices have been paid and which are still outstanding. You can see at any time which buyers owe you money and for how long.

---

## Your Bin Card — Still There, Always Current

Your auditor uses the bin card to verify your stock movements. That does not change.

InboxIQ maintains a digital bin card for every product in your warehouse. Every inbound delivery and every outbound dispatch is recorded automatically — with the date, the reference number, the quantity, and the running balance.

Your auditor can:
- View the bin card for any product at any time from their own login
- Print it as a document that looks exactly like the paper card they are used to
- See every movement for any period they choose — a week, a month, a quarter

The bin card is never edited or altered. Every entry is permanent. If a mistake is made, a correction entry is added — the original entry stays visible. This is the standard your auditor expects and it is what InboxIQ provides.

---

## When Goods Arrive from Your Supplier

The inbound side of your business is just as important as the outbound side. InboxIQ handles both in the same way — one form, everything automatic.

When a supplier arrives with a delivery, here is what happens:

---

### Step 1 — The supplier arrives with their paperwork

Your supplier brings their own waybill and their own invoice. Your warehouse manager takes those documents as they do today. Nothing changes about that handover.

---

### Step 2 — Your warehouse manager records the delivery in InboxIQ

The manager opens InboxIQ on their phone and creates a **goods received form**:

- Which supplier is delivering?
- What goods are expected? (taken from the supplier's waybill)
- How many units are expected?

This takes about one minute.

---

### Step 3 — Manager checks goods and confirms what actually arrived

After the goods are unloaded, the manager counts them against the supplier's waybill. If everything matches, they tap **"Mark as Received"**.

The bin card updates immediately — the stock balance for those goods increases. You can see the new stock level on your phone the moment it is confirmed.

**If there is a discrepancy — supplier sent fewer goods than stated:**
The manager enters the actual quantity received. InboxIQ records both the expected quantity and the actual quantity, flags the difference, and sends you an alert. You have a written record of the discrepancy with a timestamp and the manager's name — useful if you need to go back to the supplier.

---

### Step 4 — Supplier payment is tracked

When payment to the supplier is due, your staff record it in InboxIQ against that delivery. You can see at any time:
- Which suppliers you owe money to
- How much and for how long
- Which deliveries have been paid and which are outstanding

---

### Step 5 — Your stock is now available for sale

Once the goods are marked as received, they appear immediately in your available stock. Your staff can sell them, reserve them for a buyer, and raise a waybill — all from the same system.

---

### What the supplier gets

If you want to notify your supplier that their goods have been received and checked, InboxIQ can send them a short confirmation by email or SMS — for example:

> "Hello [Supplier Name], we confirm receipt of your delivery (Ref: PO-0018) on [date]. Quantity received: 100 bags of Rice (50kg). Thank you."

This is a courtesy notification only. It does not contain your pricing, your other suppliers, or any other business information. You choose whether to send it or not.

---

You currently use QuickBooks Desktop to keep your accounts. You do not need to give that up.

On a schedule you choose — daily, weekly, or monthly — InboxIQ generates a summary file of all your transactions and places it automatically into a folder in your OneDrive. Your accountant opens that file, reviews it, and imports the records into QuickBooks. They continue working in QuickBooks exactly as they do today.

**What this means for you:**

- You stop entering sales and purchases into QuickBooks yourself — that double-entry work is gone
- Your accountant receives a clean, organized file with every transaction, VAT, and payment detail already filled in
- They review it once and import — no re-typing, no emails back and forth, no USB drives
- If anything needs a correction before import, your accountant handles it in the file before it goes into QuickBooks — one review step, not a month of reconciliation

**One important step when you start:** Your accountant will need to spend about thirty minutes mapping your product categories and income types to the matching account names in QuickBooks. This is a one-time setup. After that, every export uses the same mapping and imports cleanly.

The first export is always reviewed by your accountant before import. Once they are satisfied the mapping is correct, subsequent exports can be imported with minimal review.

---

## Text Messages and Emails — What They Contain

InboxIQ will send short notifications to your buyers and your staff when something happens in the workflow. These are **notifications only** — they do not contain your business records, your prices, your stock levels, or any sensitive information.

Here are examples of exactly what these messages look like:

**To a buyer when their goods are ready:**
> "Hello Emeka, your order (Ref: INV-0042) is ready for collection at Sam's Warehouse. Please bring your copy of the waybill."

**To a buyer when goods have been dispatched:**
> "Hello Emeka, your goods (Ref: INV-0042) have left our warehouse. Thank you for your business."

**To Sam when stock falls below a reorder level:**
> "Stock alert: Rice (50kg) is running low — 12 bags remaining. Consider restocking."

**Nothing more than that is sent.**

No prices. No financial details. No information about other customers. No information about your overall stock position. Just a short, factual message about one specific movement.

Each buyer chooses how they want to receive these messages — by SMS to their phone, or by email. Buyers who do not want messages do not receive any. You are in control of who gets notified and how.

---

## What Your Auditor Gets

Your auditor currently visits to check your paper records. With InboxIQ, their job becomes easier and faster.

They receive their own login with read-only access. They can see everything but change nothing.

From their login they can:
- View every transaction — sales, purchases, payments — for any period
- See every waybill, with the matching invoice reference beside it
- Print the bin card for any product for any period
- Download a full audit report that InboxIQ generates automatically at the end of each month

The monthly audit report summarises every stock movement, flags any transaction where a waybill has no matching invoice, and shows the opening and closing stock position for every product. Your auditor receives this automatically. They do not need to visit to get it.

When they do visit for a physical stock count, they compare what is on the shelf against what InboxIQ shows. If there is a difference, it is recorded and flagged. Nothing is hidden.

---

## What Your Staff Need to Learn

**Warehouse staff** — see one screen on their phone. It shows the goods on the current waybill and a button to mark them as dispatched. That is the entire interface for them. No training is required beyond showing them that one screen.

**The warehouse manager** — uses InboxIQ to receive inbound deliveries from suppliers. When a supplier arrives, the manager opens the delivery form, confirms the goods received, and taps "Mark as Received." The bin card updates automatically.

**Your office staff** — create the transaction (the one form described above) when a sale is agreed. This replaces the process of writing a paper invoice, entering the sale into QuickBooks, and filling in a paper waybill.

**You** — see everything. From your phone, at any time, you can check:
- Current stock levels for every product
- Which orders are confirmed and waiting for collection
- Which goods have been dispatched today
- Which buyers have outstanding payments

---

## What Does Not Change

- The buyer still gets a paper waybill with three copies — one for them, one for their collector, one for your warehouse
- The buyer's collector still brings their copy to your warehouse to collect goods
- The warehouse manager still keeps their copy
- Your auditor still reviews the bin card
- Your accountant still works in QuickBooks

The only thing that changes is where the paperwork starts — on a phone or computer screen instead of a paper book — and the fact that everything after that happens automatically.

---

## Questions We Need You to Answer Before We Begin

Before we start building, we need your guidance on a few things. There are no wrong answers — these are choices about how the system works for your specific business.

1. **QuickBooks export** — Would you like us to automatically drop the export file into your OneDrive for your accountant, or would you prefer to send it to them manually when needed?

2. **Buyer notifications** — Do your buyers generally prefer SMS or email? Or does it vary by buyer? We can set a default and allow exceptions.

3. **Buyer privacy** — Are you comfortable with buyers receiving a short SMS or email notification when their goods are ready? Or would you prefer all communication to go through you or your staff directly?

4. **Auditor access** — Would your auditor like their own login so they can check records at any time, or do they prefer to receive a monthly report by email?

5. **Multiple warehouses** — Do you operate from one location, or do you have more than one warehouse we need to account for?

6. **Currency** — Are all your transactions in Naira, or do you deal with some suppliers in foreign currency (dollars or euros)?

7. **Stock count** — Who normally conducts your physical stock count — you, your warehouse manager, or a separate team?

---

*This document is a working draft. Once you have reviewed it and answered the questions above, we will confirm the plan and begin building.*
