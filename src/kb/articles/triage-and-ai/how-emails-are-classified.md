# How emails are classified

Every incoming email is passed through InboxIQ's AI pipeline. The pipeline assigns three values to each email: category, priority, and sentiment.

## Category

| Category | What it means |
|---|---|
| **Support** | Customer questions, bug reports, feature requests, help requests |
| **Billing** | Invoices, payment failures, subscription questions, charge disputes |
| **Transactions** | Automated receipts, order confirmations, shipping notifications |
| **Updates** | Product updates, newsletters, platform notifications |
| **Promotions** | Marketing emails, offers, announcements from external senders |
| **Social** | LinkedIn, Twitter/X, and other social network notifications |
| **Forums** | Community platforms, GitHub, Stack Overflow digests |

## Priority

- **P1 (Urgent)** — The email requires immediate attention. Support emails from frustrated customers, disputed charges, and critical bug reports typically receive P1. An `/Urgent` sublabel is applied (e.g. `InboxIQ/Support/Urgent`).
- **Normal** — Everything else.

## Sentiment

- **Frustrated** — The customer is unhappy, using strong language, or threatening to cancel.
- **Neutral** — Standard enquiry tone.
- **Positive** — The customer is happy, expressing satisfaction or praise.

## What the AI uses

The classification uses the email subject, body, sender address, and full thread history. It also uses your knowledge base — if you've uploaded product documentation or past replies, the AI uses that context to make more accurate classifications.

## Correcting a classification

If an email is miscategorised:

- **Gmail** — drag the email to the correct `InboxIQ/` label in the sidebar. InboxIQ detects the move on the next poll and records a correction.
- **Outlook** — right-click the email → Categorize → select the correct `InboxIQ/` category.

Corrections improve future classifications for similar emails.

## Related articles

- [Understanding Gmail labels](/kb/triage-and-ai/gmail-labels)
- [AI draft replies — how they work](/kb/triage-and-ai/ai-draft-replies)
