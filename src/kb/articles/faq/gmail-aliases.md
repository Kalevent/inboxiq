# Does InboxIQ work with Gmail aliases and shared inboxes?

## Gmail aliases (Send As addresses)

If you have aliases set up in Gmail (e.g. `support@yourdomain.com` sending as `you@gmail.com`), InboxIQ classifies emails sent to the alias normally — they all land in the same Inbox that InboxIQ monitors.

Draft replies created by InboxIQ will use the **default sending address** for that Gmail account. If you want a draft to be sent from a specific alias, you will need to change the From field in Gmail before sending.

## Google Workspace shared inboxes (Google Groups)

InboxIQ connects to **individual Gmail accounts**, not Google Groups. If your team uses a shared inbox via Google Groups (e.g. `support@yourcompany.com`), InboxIQ cannot connect to it directly.

The recommended approach is to use a Google Workspace account that receives a copy of group emails via **routing** or **forwarding**, then connect that individual account to InboxIQ.

## Outlook shared mailboxes

InboxIQ can connect to Outlook shared mailboxes if you have full access permissions to the mailbox and the OAuth flow is completed using your own Microsoft credentials. After connecting, InboxIQ polls the shared mailbox's Inbox folder.

## Multiple addresses, one account

If you receive emails for multiple addresses in a single Gmail or Outlook account (e.g. via forwarding or aliases), InboxIQ processes all emails that land in that account's Inbox — regardless of which address they were sent to.

## Related articles

- [Connect your Gmail inbox](/kb/getting-started/connect-gmail)
- [Invite a teammate's inbox](/kb/getting-started/invite-teammate-inbox)
- [Can I connect more than one inbox?](/kb/faq/multiple-inboxes)
