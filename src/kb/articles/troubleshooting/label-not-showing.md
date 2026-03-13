# Label not showing in Gmail

InboxIQ creates labels in Gmail automatically when your inbox is connected. If labels are missing or not appearing on emails, follow these steps.

## Labels not created at all

If no InboxIQ labels appear in your Gmail sidebar:

1. Go to **Settings → Inboxes** in InboxIQ and confirm the inbox shows **Connected**.
2. Check that you granted the correct Gmail permissions during setup. InboxIQ requires `gmail.modify` scope to create labels.
3. Reconnect your inbox: **Settings → Inboxes → Disconnect → Connect Gmail inbox**. This re-triggers label setup.

## Labels exist but not applied to emails

If the labels exist in Gmail but classified emails are not being labelled:

1. Confirm the email appeared in InboxIQ's triage view. If not, see [Email not appearing in InboxIQ](/kb/troubleshooting/email-not-appearing).
2. Check your confidence threshold (**Settings → Triage**). Emails below the threshold are not labelled.
3. Check whether an Automation rule is overriding labelling behaviour.

## Label showing wrong colour

InboxIQ sets standard colours when labels are created. Gmail may reset colours if you change them manually. To restore default InboxIQ colours:

1. In Gmail, right-click the label in the sidebar
2. Select **Label colour**
3. Choose the colour matching your InboxIQ category

Alternatively, disconnecting and reconnecting your inbox re-bootstraps labels with the correct colours.

## Nested labels not visible in Gmail sidebar

Gmail collapses nested labels by default. Look for an arrow next to the parent label (e.g. **InboxIQ**) and click it to expand. You can also hover over the label and click the three-dot menu to **Show in label list**.

## Label list is very long

InboxIQ creates one label per email category. If you want to hide unused labels:

1. In Gmail, go to **Settings → Labels**
2. Click **Hide** next to any InboxIQ label you don't need visible in the sidebar

The labels still exist and emails still get tagged — they just won't appear in the sidebar list.

## Related articles

- [Understanding Gmail labels](/kb/triage-and-ai/gmail-labels)
- [Email not appearing in InboxIQ](/kb/troubleshooting/email-not-appearing)
- [Reconnecting a disconnected inbox](/kb/troubleshooting/reconnect-inbox)
