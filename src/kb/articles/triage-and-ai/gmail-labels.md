# Understanding Gmail labels

When InboxIQ processes an email in your connected Gmail inbox, it applies a label directly inside Gmail. These labels are visible in your Gmail sidebar and on each email row — you never have to open InboxIQ to see what's been triaged.

## Label structure

Labels follow a nested `InboxIQ/Category` format:

- `InboxIQ/Support`
- `InboxIQ/Support/Urgent` — P1 support emails
- `InboxIQ/Billing`
- `InboxIQ/Billing/Urgent` — P1 billing emails
- `InboxIQ/Transactions`
- `InboxIQ/Updates`
- `InboxIQ/Promotions`
- `InboxIQ/Social`
- `InboxIQ/Forums`

In the Gmail sidebar, these collapse under a single **InboxIQ** group. Click the group to expand and see each category. Click a category label to see all emails in that category.

## Label colours

Each label has a distinct colour to make scanning your inbox faster:

| Label | Colour |
|---|---|
| InboxIQ/Support | Blue |
| InboxIQ/Support/Urgent | Deep red |
| InboxIQ/Billing | Red |
| InboxIQ/Transactions | Green |
| InboxIQ/Updates | Amber |
| InboxIQ/Promotions | Purple |
| InboxIQ/Social | Light blue |
| InboxIQ/Forums | Pink |

## Correcting a label

If InboxIQ applied the wrong label, drag the email to the correct `InboxIQ/` label in the sidebar. InboxIQ detects the move on the next poll and records the correction.

## Labels not appearing?

See [Label not showing in Gmail](/kb/troubleshooting/label-not-showing).
