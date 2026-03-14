# Inbox actions — execute directly in Gmail or Outlook

InboxIQ can take actions inside your Gmail or Outlook inbox automatically after triage — no separate tool to open, no manual sorting.

Because these actions run **after** AI triage, they can use context that native Gmail filters and Outlook rules cannot access: category, priority, sentiment, whether a reply is required.

---

## What inbox actions can do

| Action | What happens in your inbox |
|---|---|
| **Archive** | Removes the email from your inbox. It stays in All Mail / Archive. |
| **Mark as read** | Removes the unread badge. |
| **Star / Flag** | Adds a star (Gmail) or flag (Outlook) to the message. |
| **Apply label** | Adds a label (Gmail) or category (Outlook) to the message. |
| **Move to folder** | Moves the email out of inbox into a folder or label. |
| **Forward** | Forwards the email to another address — e.g. a team member or shared inbox. |
| **Trash** | Moves the email to Trash / Deleted Items. |

---

## Setting up an inbox action rule

Inbox action rules are created using the **natural language builder** in Settings → Automation. Describe what you want to happen in plain English — InboxIQ builds the rule for you.

### How to use the builder

1. Go to **Settings → Automation**
2. Type your rule in the text box (examples below)
3. Click **Create rule**
4. Review the generated rule and enable it

You do not need to know field names, operators, or action types. Just describe the outcome you want.

---

## What to type — example phrases

### Route transaction receipts to your accountant

> "When category is Transactions, forward to accounting@yourcompany.com and archive it"

InboxIQ will create a rule that forwards every classified transaction email to your accountant, then removes it from your inbox automatically.

---

### Route bug reports to your engineering team

> "If the subject contains 'bug report' or 'bug:', forward to engineering@yourcompany.com"

You can also route by AI category:

> "When category is Support and subject contains bug, forward to engineering@yourcompany.com"

---

### Alert your team for urgent support emails

> "When category is Support and priority is P1, star the email and send a Slack webhook alert"

---

### Clean up promotional email automatically

> "When category is Promotions, archive it and mark it as read"

---

### Move newsletters out of your inbox

> "When category is Promotions, move to the Newsletters folder"

---

### Flag billing disputes for founder review

> "When category is Billing and sentiment is frustrated, forward to founder@yourcompany.com"

---

## Multiple actions in one rule

You can combine actions in a single sentence:

> "When category is Transactions, forward to accounting@yourcompany.com, mark as read, and archive it"

InboxIQ creates all three actions and runs them in order after each email is triaged.

---

## Forwarding limits

To protect your account, InboxIQ limits automatic forwards to **50 per day**. This prevents a misconfigured rule from forwarding your entire inbox externally. If the limit is reached, the rule pauses for that day and resumes the next.

Every forward is logged in **Settings → Activity Log** with the destination address and the message that triggered it. You can review this log at any time.

---

## Which inboxes are supported?

Inbox actions work with any connected Gmail or Outlook inbox on your account. The action executes using the OAuth connection you granted when you connected the inbox — no additional permissions are required.

---

## Troubleshooting

**The rule fired but nothing happened in my inbox**
Check Settings → Activity Log → filter by your rule name. If the action shows as failed, the most common cause is an expired OAuth token. Go to Settings → Integrations and reconnect the inbox.

**I set up a forward rule but emails are not arriving**
Check your spam folder at the destination address. Also confirm the forwarding address is spelled correctly — the rule will fail silently if the address is invalid.

**I want to undo a trash action**
Go to your Gmail Trash or Outlook Deleted Items folder and move the email back. InboxIQ does not permanently delete emails — they follow your provider's normal retention period.
