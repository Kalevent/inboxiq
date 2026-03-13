# Available actions

Actions are what InboxIQ does when a rule's conditions are met. Each rule can have one action.

## Action types

### Forward

Sends a copy of the email to another address.

**Configuration:** Enter the forwarding email address. The forwarded email includes the original sender, subject, and body.

**Example use:** Forward all bug reports to `engineering@yourcompany.com`.

---

### Tag

Applies an additional label or tag to the email inside InboxIQ.

**Example use:** Tag all emails from VIP customers for priority handling.

---

### Send webhook

Posts a JSON payload to a URL of your choice. Useful for sending notifications to Slack, triggering Zapier workflows, or integrating with your own systems.

**Payload includes:** email subject, sender, category, priority, sentiment, ticket ID, and timestamp.

**Example use:** Post a Slack message when `sentiment = Frustrated AND priority = P1`.

---

### Extract structured data

Extracts specific fields from the email body (invoice numbers, order IDs, renewal dates) and returns them in the webhook payload.

**Example use:** Extract invoice number and amount from billing emails for your accounting system.

---

### Archive

Moves the email to your Gmail archive (or Outlook archive folder) after triage.

**Example use:** Automatically archive all automated transaction receipts after logging them.

## Actions coming soon

- **Move to folder** — move emails to a specific Gmail label folder or Outlook folder.
- **Auto-send draft** — automatically send InboxIQ's draft reply for high-confidence, low-risk categories.

## Related articles

- [Available conditions](/kb/automation-studio/conditions)
- [Rule recipes and examples](/kb/automation-studio/rule-recipes)
