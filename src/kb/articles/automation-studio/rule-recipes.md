# Rule recipes and examples

Ready-made phrases you can type into the Automation Studio natural language builder. Go to **Settings → Automation**, paste any of these into the text box, and click **Create rule**.

---

## Department routing

### Route transaction receipts to accounting

> "When category is Transactions, forward to accounting@yourcompany.com and archive it"

Receipts and order confirmations are classified automatically. This rule forwards them to your accountant and removes them from your inbox so they never pile up.

---

### Route bug reports to engineering

> "If the subject contains 'bug report' or category is Support, forward to engineering@yourcompany.com"

Or route by both AI category and keywords:

> "When category is Support and subject contains bug, forward to engineering@yourcompany.com and star it"

---

### Route billing queries to finance

> "When category is Billing and priority is P1, forward to billing@yourcompany.com"

---

### Escalate frustrated customers to the founder

> "When sentiment is frustrated and priority is P1, forward to founder@yourcompany.com and star it"

---

## Slack and webhook alerts

### Alert the team for urgent support tickets

> "When category is Support and priority is P1, star the email and send a Slack webhook"
>
> "When sentiment is frustrated and category is Support, send a Slack webhook alert"

---

### Alert on billing disputes

> "When category is Billing and sentiment is frustrated, send a Slack webhook and forward to billing@yourcompany.com"

---

## Inbox clean-up

### Archive automated receipts

> "When category is Transactions, archive it and mark as read"

Automated receipt emails (Stripe, PayPal, Xero) don't need human review. Archive them after InboxIQ logs them.

---

### Move newsletters out of your inbox

> "When category is Promotions, move to the Newsletters folder"

---

### Archive all social and promotional noise

> "When category is Promotions, archive and mark as read"
>
> "When category is Social, archive and mark as read"

---

### Star anything that needs a reply

> "When action required is true and priority is P1, star the email"

---

## Accounting integrations

### Extract invoice data and send to QuickBooks

> "Extract invoices from vendor emails and send to QuickBooks"

### Extract receipts and sync to Xero

> "Extract receipts from Stripe and PayPal emails and sync to Xero"

---

## Tips

- You can combine multiple actions in one sentence: *"forward to X, mark as read, and archive it"*
- Use **and** to add conditions: *"When category is Billing and priority is P1"*
- Use **or** for alternatives: *"If subject contains 'invoice' or 'receipt'"*
- InboxIQ understands natural language — write how you'd explain it to a colleague

---

## Related articles

- [Inbox actions — Gmail & Outlook](/kb/automation-studio/inbox-actions)
- [How rules work](/kb/automation-studio/how-rules-work)
- [Available conditions](/kb/automation-studio/conditions)
- [Available actions](/kb/automation-studio/actions)
