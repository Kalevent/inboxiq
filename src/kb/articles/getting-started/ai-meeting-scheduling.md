# AI meeting scheduling

InboxIQ detects meeting requests in incoming emails and adds a personal booking link to the draft reply — so your contact can book a time without any back-and-forth.

## How it works

When an incoming email contains a meeting request, InboxIQ's AI pipeline detects the intent and automatically inserts a booking link into the draft reply it generates. The link is unique to that email thread and expires after 7 days.

## What your contact sees

Clicking the booking link opens a public page — no account or login required. The page shows your available time slots pulled live from your connected calendar. Your contact selects a slot and confirms with their name and email address.

## What happens after booking

- A calendar event is created on your Google or Outlook calendar, with a Google Meet or Microsoft Teams link included
- A confirmation email is sent to your contact with the meeting time and a join link
- The ticket in InboxIQ is updated to **Meeting scheduled** status
- A note is added to the ticket recording the booking details

## Setup

Before booking links appear in draft replies, connect your calendar:

1. Go to **Settings → Integrations → Calendar**
2. Click **Connect Google Calendar** or **Connect Outlook Calendar**
3. Complete the authorisation flow
4. Booking links will now appear automatically in draft replies whenever InboxIQ detects a meeting request

## Related articles

- [Connect your Gmail inbox](/kb/getting-started/connect-gmail)
- [Connect your Outlook inbox](/kb/getting-started/connect-outlook)
- [How InboxIQ works](/kb/getting-started/how-inboxiq-works)
