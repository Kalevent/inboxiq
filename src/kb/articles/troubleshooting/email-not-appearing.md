# Email not appearing in InboxIQ

If an email arrived in your inbox but is not showing up in InboxIQ, work through the steps below.

## 1. Check that your inbox is connected

Go to **Settings → Inboxes**. Your inbox should show a green **Connected** badge. If it shows **Disconnected** or **Error**, see [Reconnecting a disconnected inbox](/kb/troubleshooting/reconnect-inbox).

## 2. Check when the email arrived

InboxIQ polls your inbox every few minutes. Emails that arrived in the last 5–10 minutes may not have been picked up yet. Wait a moment and refresh.

## 3. Check the email's folder

InboxIQ monitors your **primary inbox** folder only:

- **Gmail** — InboxIQ reads emails in your Inbox. Emails in Spam, Promotions (if tabbed inbox is enabled and not monitored), or other folders are not processed unless they land in the main Inbox.
- **Outlook** — InboxIQ reads the **Inbox** folder. Emails routed directly to subfolders by Outlook rules are not picked up.

If the email was filtered elsewhere by a Gmail/Outlook rule before InboxIQ could see it, InboxIQ will not process it.

## 4. Check your confidence threshold

If InboxIQ received the email but did not classify it with sufficient confidence, it may not appear in a triage view. Check **Settings → Triage** to see your threshold setting.

## 5. Check for scope errors (Outlook)

For Outlook connections, InboxIQ needs `Mail.Read`, `Mail.ReadWrite`, and `offline_access` scopes. If you authorised InboxIQ before these scopes were required, reconnect your inbox:

1. Go to **Settings → Inboxes**
2. Click **Disconnect** next to the affected inbox
3. Click **Connect Outlook inbox** and complete the authorisation flow

## 6. Contact support

If emails are still missing after the steps above, [contact support](mailto:support@kalevent.com) with:

- Your email address
- The subject and approximate arrival time of a missing email
- Whether the inbox is Gmail or Outlook

## Related articles

- [Reconnecting a disconnected inbox](/kb/troubleshooting/reconnect-inbox)
- [How InboxIQ works](/kb/getting-started/how-inboxiq-works)
