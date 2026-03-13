# Draft not appearing in the thread

InboxIQ saves AI-generated reply drafts directly into Gmail or Outlook. If a draft is missing, follow these steps.

## 1. Check the email was classified

Drafts are only created for emails that InboxIQ classified and deemed suitable for a draft reply. Check your InboxIQ triage view to confirm the email appeared there and shows a draft.

If no draft is shown in InboxIQ, the AI may have determined a draft was not appropriate (e.g. the email was a receipt, newsletter, or notification rather than a reply-needed message).

## 2. Check Gmail Drafts folder

In Gmail, drafts created by InboxIQ appear in your **Drafts** folder and are also accessible from the email thread.

- Open the thread in Gmail
- Look for a **Draft** label at the top of the thread
- Or open the **Drafts** folder and search for the subject

## 3. Check Outlook Drafts folder

In Outlook, open the **Drafts** folder. InboxIQ drafts appear there and are also linked from the original thread when you open it.

> **Note:** Outlook on mobile may take a few minutes to sync drafts from the server.

## 4. Check inbox permissions (Gmail)

To save drafts, InboxIQ requires the `gmail.modify` scope, which includes compose/draft write access. If this scope was not granted:

1. Go to **Settings → Inboxes**
2. Disconnect and reconnect the inbox, ensuring you approve all requested permissions

## 5. Check inbox permissions (Outlook)

InboxIQ requires `Mail.ReadWrite` scope to save Outlook drafts. Reconnect your inbox if the scope was not granted during initial setup.

## 6. Draft delay

Draft creation runs asynchronously after classification. On high-volume inboxes, there may be a short delay. Wait 1–2 minutes after an email is classified, then check again.

## Related articles

- [AI draft replies — how they work](/kb/triage-and-ai/ai-draft-replies)
- [Email not appearing in InboxIQ](/kb/troubleshooting/email-not-appearing)
- [Reconnecting a disconnected inbox](/kb/troubleshooting/reconnect-inbox)
