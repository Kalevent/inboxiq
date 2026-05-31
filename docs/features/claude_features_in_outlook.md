# Claude Features in Outlook

Source: Anthropic's Claude for Microsoft 365 / Outlook — official capability cards.

---

## CAN DO · WRITING

### Email Drafting & Replying

- **Draft in your voice** — Replies, forwards, and new emails written to match your personal style.
- **Apply your style rules** — First-name openers, short sentences, "Regards, Jenish" sign-off.
- **Reply or reply-all** — Send to a subset of recipients or compose entirely new emails.
- **Ghost-write from a brief** — E.g. "Write a follow-up to the workshop attendees."
- **Humanise AI text** — Polish robotic-sounding drafts or rough dictation into proper emails.

---

## CAN DO · ORGANISATION

### Mailbox Management

- **Move to folders** — Archive, client folders, or any custom folder you've set up.
- **Apply categories** — Use your colour-coded triage system automatically.
- **Mark read / unread** — Flip the read state across single or bulk emails.
- **Flag for follow-up** — Mark emails so you don't forget to come back to them.
- **Bulk archive** — Clear out by sender, subject, or date range in one command.
- **Soft delete** — Move to Deleted Items (recoverable) — never permanent delete.

---

## CAN DO · INTELLIGENCE

### Search & Memory

- **Mailbox-wide search** — Search the entire mailbox via Graph — not just the email that's open.
- **Find by conversation** — Locate threads by conversationId, sender, keyword, or date.
- **Find attachments** — Locate files even when they're on an earlier message in a thread.
- **Prep meeting briefs** — Who's attending, prior thread context, last email with each attendee.
- **Cross-session memory** — Remembers your folder structure, triage rules, clients, and preferences.
- **Auto-apply your rules** — E.g. Replit and Luma notifications automatically routed to Archive.

---

## CAN DO · ANALYSIS

### Email Reading & Analysis

- **Summarise threads** — Distil long email chains into the key points so you don't have to scroll.
- **Extract action items** — Pull out decisions, owners, and next steps from messy threads.
- **Triage your inbox** — Categorise emails using your priority system.
- **Detect hidden text** — Flag CSS-hidden text or prompt injection attempts in suspicious emails.
- **Search across mailbox** — Find emails by sender, keyword, date range, or subject.
- **Read attachments** — Open Word, Excel, CSV, JSON, and plain text files — answer questions about them.

---

## CAN DO · SCHEDULING

### Calendar

- **Check free/busy time** — See your availability and attendees' availability at a glance.
- **Find a meeting slot** — Identify times that work for everyone in the invite.
- **Draft calendar invites** — Build the agenda, attendees, location, and body — you click open in Outlook.

---

## CANNOT DO · SCOPE

### Platform Limits

- **Post outside Outlook** — Scoped to your mailbox — no Slack, social, or other tool posting.
- **Open OneDrive attachments** — Cloud-link attachments only return the URL, not file contents.
- **Access other emails inline** — Only the currently open email is visible without a Graph search.

---

## CANNOT DO · POLICY

### Hard Limits

- **Send email directly** — Drafts are presented for you to review — you click Send.
- **Permanently delete** — Soft-delete only. Irreversible deletes are blocked by design.
- **Accept or decline invites** — Use the native Outlook RSVP buttons yourself.
- **Create inbox rules** — Can suggest the rule logic, but can't set up Outlook routing rules.
- **Read PDF attachments** — No in-browser PDF parser — paste the text or upload separately.
- **Pre-fill BCC** — Add BCC recipients yourself in the Outlook compose window.
- **Schedule send** — No "send at 8am tomorrow" — use Outlook's native Send Later.
- **Set out-of-office** — Auto-replies require a permission scope Claude doesn't have.
- **Modify received emails** — Read mode is read-only on body and subject of inbound mail.
