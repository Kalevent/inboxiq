# Rule recipes and examples

Ready-made rule configurations for the most common use cases. Copy these into your Automation Studio.

---

## Route bug reports to engineering

**Conditions:** `category = Support` AND `action_required = True`
**Action:** Forward to `engineering@yourcompany.com`

> Refine this by adding a `sender_domain` condition if you only want bugs from paying customers.

---

## Slack alert for frustrated urgent customers

**Conditions:** `sentiment = Frustrated` AND `priority = P1`
**Action:** Send webhook → your Slack incoming webhook URL

This is one of the highest-value rules. Frustrated, urgent customers need a human response fast — a Slack ping ensures nothing slips through.

---

## Archive automated receipts

**Conditions:** `category = Transactions` AND `is_automated = True`
**Action:** Archive

Automated receipt emails (Stripe, PayPal, Xero) don't need human review. Archive them automatically after InboxIQ logs them.

---

## Flag billing disputes for founder review

**Conditions:** `category = Billing` AND `sentiment = Frustrated`
**Action:** Forward to `founder@yourcompany.com`

Billing disputes need senior attention. Forward them directly rather than leaving them in the general inbox queue.

---

## Extract invoice data for accounting

**Conditions:** `category = Billing` AND `is_automated = True`
**Action:** Extract structured data + Send webhook → your accounting webhook

InboxIQ extracts the invoice number, amount, and date and posts them to your accounting integration.

---

## Archive social and promotional noise

Two rules:

**Rule 1** — `category = Social` → Archive
**Rule 2** — `category = Promotions` → Archive

Keeps your inbox focused on emails that actually need your attention.

---

## Related articles

- [How rules work](/kb/automation-studio/how-rules-work)
- [Available conditions](/kb/automation-studio/conditions)
- [Available actions](/kb/automation-studio/actions)
