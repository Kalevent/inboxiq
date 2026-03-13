# How do I stop InboxIQ drafting for a specific sender?

You can prevent InboxIQ from creating draft replies for emails from a specific sender using an Automation rule.

## Create a "no draft" rule

1. Go to **Automation Studio → New rule**
2. Set the condition:
   - **Field:** Sender email
   - **Operator:** is
   - **Value:** the sender's email address (e.g. `newsletter@example.com`)
3. Set the action:
   - **Action:** Skip draft
4. Save and enable the rule

From then on, any email from that sender is still classified and labelled, but no draft reply is created.

## Block an entire domain

To stop drafts for all emails from a domain (e.g. `example.com`):

1. Create a new rule
2. Condition: **Sender email** → **ends with** → `@example.com`
3. Action: **Skip draft**

## Stop all drafts for a category

If you never want drafts for a specific category (e.g. InboxIQ/Transactions), you can set this at the triage level:

1. Go to **Settings → Triage**
2. Find the category
3. Toggle **Draft replies** off for that category

## Related articles

- [How rules work](/kb/automation-studio/how-rules-work)
- [Available conditions](/kb/automation-studio/conditions)
- [AI draft replies — how they work](/kb/triage-and-ai/ai-draft-replies)
