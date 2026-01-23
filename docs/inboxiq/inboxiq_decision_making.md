# InboxIQ Decision Making

## 1. What is implemented today (from the screenshot)
InboxIQ already performs most of the decision-making work, though it is not yet operationalised end to end.

- Implemented decisions per ticket: intent, category, priority, sentiment, owner/team, due date/SLA, risk flags.
- The AI is already reading emails, understanding intent, assessing urgency, enriching context, and assigning ownership—about 90% of first-line support work.
- Technically, the decision engine exists.

## 2. Key gap: missing "Needs Action?" decision
- Every email becomes a ticket, including purely informational messages (delivery notifications, access granted, confirmations).
- Humans still decide, "Do I need to do anything here?" so the final "Requires human action?" decision is left to the agent, not the system.

## 3. Why this matters for perceived value
- The difference is "AI creates tickets" vs "AI removes work."
- If everything becomes a ticket, workload appears unchanged; even well-labeled tickets still require scanning.
- Scanning adds cognitive load and cost, so the system is not yet shielding humans from non-work.

## 4. The missing piece (simple, high impact)
Expose and act on one explicit decision: **Action Required: Yes/No**.

- No action required: informational emails, confirmations, FYI messages, automated notifications.
- Action required: customer questions, complaints, bugs, billing issues, anything blocking the customer.
- This decision likely exists implicitly in the model—it just is not exposed or enforced.

## 5. How to implement without rewriting the system
- **Step 1 — Add an explicit field:** `action_required = true | false | follow_up_optional`.
- **Step 2 — Change ticket behaviour:** if `action_required = false`, do not surface it in the main queue; send to "Auto-handled," "FYI," or "No action needed." If `action_required = true`, keep the normal ticket flow.
- **Step 3 — Update dashboard metrics:** highlight "Emails auto-handled (no human action): N," "Actionable tickets surfaced: N," "Manual triage eliminated: X%." This is where value is felt.

## 6. Precise answer to "Has deciding whether it needs action been implemented?"
- The AI is capable of making that decision.
- The product does not yet act on that decision.
- Humans are still exposed to non-actionable work.
- The feature exists logically, but not experientially.

## 7. Why this is good news
- You already have the hardest parts: decision-making, context, enrichment, routing logic.
- What is missing is a single line between "AI knows" and "human doesn't need to see it."
- Adding that turns InboxIQ into a workload shield, not just a ticketing or inbox tool.

## 8. How to talk about InboxIQ today
- Current positioning: "InboxIQ removes manual triage and decision-making by pre-prioritising, enriching, and assigning customer emails—dramatically reducing the effort required to process support work."
- After suppression: "InboxIQ removes the first layer of support work by deciding what even needs human attention."

## 9. Recommendation for the next product step
If you do one thing next, make it this: implement and surface the "Action Required" decision and hide non-actionable tickets by default. This single change will increase perceived value, reduce visible workload, strengthen the core claim, and make pricing easier to justify.

Below is a complete, end-to-end plan covering all four items, grounded in what your app already does, and designed so that companies immediately feel “less work,” not “more tickets.”

I’ll structure this as:
- What should never become a ticket (decision policy)
- Safe decision rules (AI + guardrails)
- Exact UX changes (queue + dashboard)
- Updated hero + dashboard copy (ready to paste)


### 1. What should NEVER become a ticket (critical)
This is the biggest unlock. Right now, your system treats all emails as potential work, which fuels the “is this creating more work?” doubt.

**Non-actionable emails (auto-handled / suppressed):** these should never surface to humans by default.
- Informational / FYI
- Delivery confirmations
- Access granted / account created
- Subscription confirmations
- Password reset emails
- “Your plan has been updated”
- System notifications
- Marketing / noise
- Newsletters
- Product announcements
- Promotional emails
- Sales follow-ups sent to support inbox
- Duplicate / follow-ups
- “Just following up”
- Repeated replies with no new intent
- CC-only emails
- Status-only messages
- “This will be delivered today”
- “Issue has been resolved” (from third parties)
- Out-of-office / vacation auto-replies
- Calendar invites, updates, and cancellations
- Delivery failures / bounce notices / read receipts
- Noreply/system bot emails with no request
- Replies containing no new content (only quoted threads or “checking in”)

These emails create cognitive load but zero value. If the correct human action is nothing, it is not work.



### 2. Safe decision rules (how InboxIQ decides “Action Required”)
You already have intent, category, sentiment, priority, and ownership. Add one explicit decision: `action_required = TRUE | FALSE | OPTIONAL`.

**Action Required = TRUE (surface to humans)**
- Questions
- Complaints
- Bugs
- Billing disputes
- Access issues
- Anything blocking the user

**Action Required = FALSE (auto-handle and suppress)**
- Confirmations
- FYI
- Notifications
- No request language
- No negative sentiment
- No question or command

**OPTIONAL (safe middle ground → low-priority queue)**
- Ambiguous emails
- Low urgency questions
- Non-blocking requests

**Safety guardrails (avoid false negatives)**
- If sentiment is negative → always TRUE
- If contains a question → always TRUE
- If mentions billing / access / outage → always TRUE
- If customer has replied before → always TRUE

This makes the system trustworthy, not risky.



### 3. Exact UX changes (where value becomes visible)
**A) Ticket Queue UX (most important)**
- Current mental model: “Here are all the tickets InboxIQ created.”
- New mental model: “Here is the work InboxIQ decided humans need to do.”

**New queue structure**
- Primary Queue: “Action Required” — only tickets where `action_required = TRUE`; this is what agents live in.
- Secondary Queue: “FYI / Auto-handled” — collapsed by default; shows suppressed emails, informational messages, duplicates, confirmations. Agents open only when auditing.
- Ticket badge (trust): on every actionable ticket, display:
  - Action Required: Yes
  - Decided by InboxIQ

This reinforces trust.



**B) Dashboard UX (executive value)**
- Your current dashboard shows activity; it needs to show work eliminated.

**Old metrics (de-emphasize)**
- Tickets created
- Emails polled

**New metrics (replace/add)**
- Today
  - Emails received: 24
  - Actionable tickets surfaced: 7
  - Emails auto-handled: 17
  - Manual triage eliminated: 71%
- This week
  - Human decisions avoided: 132
  - Estimated time saved: 4.4 hours

These instantly answer: “Is this creating more work?”



### 4. Updated copy (hero + dashboard)
**New Hero (final version)**
- H1: Your AI Support Agent — Removing Manual Triage Before Humans Touch the Inbox
- Subheadline: InboxIQ reads every customer email, decides whether action is required, prioritises urgency, assigns ownership, and surfaces only actionable work — so your team focuses on solving problems, not sorting messages.
- Micro-line: No inbox scanning. No manual triage. No decision fatigue.

**Core Feature (updated)**
- First-Line AI Support Agent (Workload Shield)
- InboxIQ replaces the first layer of customer support work. It reads incoming emails, decides what matters, filters out noise, and turns only actionable issues into pre-prioritised, pre-assigned tickets.
- Humans start with clarity — not an inbox.

**Dashboard copy (replace current language)**
- Instead of: “Tickets created automatically” → Use: “Manual triage eliminated”
- Instead of: “Emails polled” → Use: “Emails auto-handled (no human action required)”



### 5. Why this changes everything
With these changes:
- InboxIQ is no longer a ticket generator; it becomes a workload firewall.
- Companies see less work, not more structure.
- Pricing becomes easier to justify.
- Sales conversations get simpler.

You move from:
- “We help manage support”
to:
- “We remove the part of support humans shouldn’t be doing.”



### 6. What I recommend you build first (order matters)
- Add `action_required` decision
- Hide non-actionable tickets by default
- Update dashboard metrics
- Update hero + feature copy

You can do this incrementally, but the moment (1) and (2) ship, InboxIQ’s value becomes undeniable.
