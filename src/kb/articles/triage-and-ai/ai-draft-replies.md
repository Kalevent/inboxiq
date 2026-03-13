# AI draft replies — how they work

For every email that needs a response, InboxIQ writes a draft reply and places it directly in the Gmail thread (or Outlook Drafts). You review it, edit if needed, and send — you never compose from scratch.

## What goes into a draft

InboxIQ uses four sources when writing a draft:

1. **The full email thread** — not just the latest message. If this is a follow-up, InboxIQ knows what was already said and doesn't repeat it.
2. **Your knowledge base** — articles, FAQs, and past replies you've uploaded in Settings → Integrations → Knowledge Base. The more you add, the more accurate and on-brand the drafts become.
3. **Sender context** — InboxIQ builds a profile for each sender domain over time. A customer at `acme.com` who always asks billing questions will get billing-appropriate drafts faster.
4. **Triage output** — the category, priority, and sentiment inform the tone and urgency of the draft.

## Draft modes

| Mode | Behaviour |
|---|---|
| **Draft only** (default) | InboxIQ writes the draft. You review and send. Nothing goes out without your action. |
| **Auto-send** | For high-confidence, low-risk categories (e.g. Transactions), you can configure an automation rule to send automatically. See [Automation Studio](/kb/automation-studio/how-rules-work). |

## Confidence threshold

Each draft has a confidence score. If the score is below your threshold, InboxIQ creates the draft but adds a note indicating low confidence. You can adjust the threshold in **Settings → AI Features**.

## Editing a draft

Drafts appear in Gmail as a collapsed reply at the bottom of the thread. Click to expand, edit, and send as you normally would. Any edits you make are not fed back to InboxIQ — only label corrections are used for retraining.

## Related articles

- [Adding articles and past replies](/kb/knowledge-base/adding-content)
- [Adjusting your confidence threshold](/kb/triage-and-ai/confidence-threshold)
