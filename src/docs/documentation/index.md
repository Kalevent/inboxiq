# InboxIQ Documentation

Welcome to the InboxIQ docs. Useful guides:

- [Invite teammates](/docs/invite_teammates)
- [User guide](/docs/users_guide)
- [Security (Passkeys & 2FA)](/docs/security_auth)
- [Publishing brief templates](/docs/publishing_brief_templates)
- [Channel intake guide](/docs/channel_intake_guide)
- [Developer guide](/docs/developer_guide)
- [External Forms](/docs/external_forms)
- [Intake API reference](/docs/intake_api)

# InboxIQ User Guide

Welcome to InboxIQ. This guide highlights what the app does, how to get started, and how to resolve common issues so you can stay responsive to customers.

See also: [Security (Passkeys & 2FA)](/docs/security_auth)

## What InboxIQ Delivers
- Smart triage: automatic ticket creation with suggested category and priority.
- Unified inbox: one place to see new, in-progress, and recent tickets.
- Reply faster: send responses, comments, and reminders directly from each ticket.
- Onboarding nudges: trigger reminder sequences for new users or customers.
- Search and filters: quickly find threads by keyword, status, category, or date.

## Get Started
1) Sign in with the account your admin created.
2) Connect your mailbox (IMAP/SMTP or Microsoft 365/Google if enabled by your admin).
3) Set your default reply-from address, time zone, and signature in Settings.
4) (Admins) Review categories/priorities so triage suggestions match your workflow.

## Daily Workflow
- **Dashboard:** View today’s tickets, missed emails, and recent activity at a glance.
- **Triage:** Open a ticket, confirm or adjust the suggested category/priority, then reply or add a comment.
- **Reminders:** Use the reminder action to follow up on idle threads; onboarding reminders are available in the reminder tool.
- **Search & filter:** Use subject/body keywords plus filters for status and category to find the right thread fast.
- **Attachments:** Upload replies or notes with files; if a file fails, try a smaller version or a supported format.

## Review and correct triage (Need fix)
- In the dashboard ticket table, click **[Need fix](/dashboard#tickets)** to correct a mis-triaged ticket.
- Enter the right category/priority (and team/assignee if needed). The ticket updates immediately and is sent for re-triage with your feedback.
- If the triage was right, use **Triage correct** instead to reinforce the model’s choice.
- Use this when the model misclassifies or routes to the wrong team; the feedback is recorded and biases future suggestions.

## Troubleshooting
- **Cannot sign in:** Reset your password from the login page or ask an admin to reactivate your account.
- **Mailbox connection fails:** Verify host, port, username, and app password; for 365/Gmail OAuth, confirm the admin set up the integration.
- **Tickets not appearing:** Check that polling is enabled, credentials are valid, and the watched folder has new mail.
- **Outbound email blocked:** Ensure the From address is allowed for the connected mailbox and domain SPF/DKIM are configured by your admin.
- **Attachments missing:** Re-upload with a smaller file size; extremely large files may be declined by policy.

## Good Practices
- Keep categories/priorities tidy so suggestions stay accurate.
- Close or archive tickets that are done to keep the inbox focused.
- Avoid sharing credentials or secrets in tickets.

## Getting Help
If an issue persists, share the ticket URL, time of the error, and a short description with your admin or support contact. This helps the team resolve it quickly.

## Related guides
- [Invite teammates](/docs/invite_teammates)
