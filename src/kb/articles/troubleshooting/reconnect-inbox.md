# Reconnecting a disconnected inbox

An inbox can become disconnected if you revoked InboxIQ's access, changed your password, or if the OAuth token expired. Here's how to reconnect.

## Why does an inbox disconnect?

- You revoked InboxIQ's access in Google or Microsoft account settings
- You changed your Google/Microsoft account password
- The refresh token expired (typically after 6 months of inactivity)
- InboxIQ encountered repeated API errors and paused the connection

## How to reconnect

1. Go to **Settings → Inboxes**
2. Find the disconnected inbox (it will show a red **Disconnected** badge or an error message)
3. Click **Reconnect**
4. Complete the Google or Microsoft authorisation flow
5. Approve all requested permissions

Once reconnected, InboxIQ resumes polling immediately. You will not lose your automation rules, triage config, or AI settings.

## Reconnecting does not re-process old emails

InboxIQ only processes new emails received after reconnection. Emails that arrived while the inbox was disconnected are not retroactively classified or labelled.

## Permissions checklist

Make sure you approve all permissions during the OAuth flow:

**Gmail**
- Read and manage your email (`gmail.modify`)
- Manage labels (`gmail.labels`)

**Outlook**
- Read and write mail (`Mail.ReadWrite`)
- Offline access (`offline_access`)

If you skip any permission, InboxIQ will reconnect but certain features (labelling, draft creation) may not work. In that case, disconnect and reconnect again, approving all permissions.

## Revoked access in Google/Microsoft settings

If you revoked access directly from your Google or Microsoft account:

**Google:** Go to [myaccount.google.com/permissions](https://myaccount.google.com/permissions), find InboxIQ, and check if it is listed. If not, simply reconnect from InboxIQ settings — the OAuth flow will re-grant access.

**Microsoft:** Go to [myapplications.microsoft.com](https://myapplications.microsoft.com), find InboxIQ, and remove it. Then reconnect from InboxIQ settings to re-grant access cleanly.

## Still having trouble?

[Contact support](mailto:support@kalevent.com) with your email address and a description of the error shown in Settings → Inboxes.

## Related articles

- [Connect your Gmail inbox](/kb/getting-started/connect-gmail)
- [Connect your Outlook inbox](/kb/getting-started/connect-outlook)
- [Email not appearing in InboxIQ](/kb/troubleshooting/email-not-appearing)
