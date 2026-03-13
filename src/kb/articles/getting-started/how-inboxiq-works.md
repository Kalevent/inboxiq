# How InboxIQ works

InboxIQ sits between your inbox and your team. Every email that arrives is read, classified, and actioned — all before you open it.

## The pipeline

1. **Receive** — InboxIQ polls your Gmail or Outlook inbox every few minutes using the official Google and Microsoft APIs. It never stores your emails permanently; it reads them, processes them, and discards the raw content.

2. **Classify** — Each email is passed through the AI pipeline. InboxIQ assigns:
   - **Category** — Support, Billing, Updates, Promotions, Transactions, Social, or Forums
   - **Priority** — P1 (urgent) or normal
   - **Sentiment** — Frustrated, Neutral, or Positive

3. **Label** — A label (Gmail) or category tag (Outlook) is applied directly in your inbox so you can see at a glance what every email is about, without opening it.

4. **Draft** — For emails that need a reply, InboxIQ writes a draft using your knowledge base, past replies, and the full thread context. The draft appears collapsed in the Gmail thread, ready for you to review and send.

5. **Automate** — Any automation rules you've configured in Automation Studio fire after triage. Emails can be forwarded, tagged, archived, or sent to a webhook automatically.

## What InboxIQ never does

- It never sends an email without your approval (unless you explicitly configure auto-send for a rule).
- It never reads emails in folders or labels you haven't connected.
- It never stores the body of your emails in a way that persists after processing.

## Where the intelligence comes from

InboxIQ gets smarter in two ways:

**Your knowledge base** — Articles, past replies, and help centre links you upload in Settings → Integrations → Knowledge Base. The AI uses these when drafting replies.

**Your corrections** — When you move an email to a different InboxIQ label in Gmail (or change its category in Outlook), InboxIQ detects this and records a correction. Over time, it learns your specific patterns.

## Related articles

- [Connect your Gmail inbox](/kb/getting-started/connect-gmail)
- [How emails are classified](/kb/triage-and-ai/how-emails-are-classified)
- [AI draft replies — how they work](/kb/triage-and-ai/ai-draft-replies)
