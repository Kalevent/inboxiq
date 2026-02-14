# Feature Proposal: In-Inbox Email Classification Display

**Status:** Proposed
**Date:** 2026-02-14
**Author:** System Analysis

## Overview

Display AI-powered email classification (category, priority, sentiment) directly within Gmail/Outlook inbox interface, similar to products like Antigravity, without requiring users to leave their email client.

## Problem Statement

**Current State:**
- InboxIQ successfully classifies emails using DSPy triage agent
- Classification results (category, priority, sentiment) are stored in `Ticket` model
- Results are only visible in InboxIQ dashboard at `/dashboard`
- Users must leave Gmail/Outlook and switch to InboxIQ to see classifications

**Desired State:**
- Users see AI classification directly in their Gmail/Outlook inbox
- No context switching required
- Tickets still automatically created in InboxIQ backend
- Seamless workflow: Read email → See classification → Take action

## Current Architecture

### Email Processing Flow
```
Email arrives (Gmail/Outlook)
    ↓
Email polling task (Celery: inbox queue)
    ↓
process_incoming_email_task
    ↓
DSPy triage agent classification
    ↓
Ticket created with fields:
    - category (e.g., "billing", "support", "sales")
    - priority (e.g., "P1", "P2", "P3")
    - sentiment (e.g., "positive", "neutral", "negative")
    - decision (JSON with full triage results)
    ↓
Stored in database
    ↓
Displayed in InboxIQ dashboard only
```

### Key Components
- **Model:** `Ticket` in `src/models.py` (lines 68-97)
- **API Endpoint:** `/api/v1/inboxiq/tickets` (line 209 in `src/api/v1/inboxiq.py`)
- **Celery Task:** `process_incoming_email_task` in `src/celery_inboxiq.py`
- **Frontend:** `dashboard_welcome.html` and `dashboard_welcome.js`

## Proposed Solutions

### Option 1: Gmail Add-on / Outlook Add-in ⭐ RECOMMENDED

**Description:**
Build native add-ons that run inside Gmail/Outlook interface, displaying classification in a sidebar or inline badges.

**User Experience:**
1. User opens email in Gmail/Outlook
2. Sidebar automatically appears showing:
   - Category badge (e.g., "🎫 Billing Issue")
   - Priority indicator (e.g., "🔴 P1 - Urgent")
   - Sentiment (e.g., "😠 Negative")
   - AI reasoning/summary
   - Action buttons ("Create Ticket", "Mark Handled")
3. Click "Create Ticket" → Opens in InboxIQ with pre-filled data

**Technical Implementation:**

**Gmail Add-on (Google Apps Script):**
```javascript
// Sidebar displays when email is opened
function onGmailMessageOpen(e) {
  const messageId = e.gmail.messageId;

  // Call InboxIQ API
  const classification = callInboxIQAPI(messageId);

  // Build sidebar UI
  return CardService.newCardBuilder()
    .addSection(buildClassificationCard(classification))
    .build();
}

function callInboxIQAPI(messageId) {
  const url = 'https://api.kalevent.com/api/v1/inboxiq/classify';
  const token = getUserProperty('inboxiq_token');

  const response = UrlFetchApp.fetch(url, {
    method: 'post',
    headers: { 'Authorization': `Bearer ${token}` },
    payload: JSON.stringify({ message_id: messageId })
  });

  return JSON.parse(response.getContentText());
}
```

**Outlook Add-in (Office.js):**
```javascript
// Taskpane displays classification
Office.initialize = function() {
  const item = Office.context.mailbox.item;

  fetch('https://api.kalevent.com/api/v1/inboxiq/classify', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      message_id: item.internetMessageId
    })
  })
  .then(res => res.json())
  .then(data => displayClassification(data));
};
```

**Backend Changes Required:**
```python
# New endpoint: /api/v1/inboxiq/classify
@v1.route("/inboxiq/classify", methods=["POST"])
@jwt_required()
def classify_email():
    """
    On-demand classification for Gmail/Outlook add-ons.
    Returns classification without creating a ticket if one exists.
    """
    payload = request.get_json()
    message_id = payload.get("message_id")

    # Check if already classified
    ticket = Ticket.query.filter_by(message_id=message_id).first()
    if ticket:
        return jsonify({
            "category": ticket.category,
            "priority": ticket.priority,
            "sentiment": ticket.sentiment,
            "decision": ticket.decision,
            "ticket_id": ticket.id,
            "exists": True
        })

    # Fetch email from Gmail/Outlook and classify
    # (Implementation details omitted for brevity)

    return jsonify(classification_result)
```

**Deployment Options:**
- **Private (No Review):** Deploy to your Google Workspace domain instantly
- **Public:** Submit to Google Workspace Marketplace (2-4 week review)

**Pros:**
✅ Native integration with email clients
✅ Rich UI capabilities (sidebar, buttons, badges)
✅ Works on desktop and mobile
✅ Professional appearance
✅ Similar to Superhuman, Boomerang, Grammarly
✅ Can deploy privately without marketplace review

**Cons:**
❌ Requires separate development for Gmail vs Outlook
❌ Users must install add-on
❌ Ongoing maintenance for two platforms

**Effort:** 2-3 weeks (1.5 weeks per platform)

---

### Option 2: Gmail Labels (Quick Win)

**Description:**
After classification, automatically apply Gmail labels to emails using Gmail API.

**User Experience:**
1. Email arrives → InboxIQ classifies
2. Gmail labels automatically applied:
   - `IQ/Billing`
   - `IQ/P1-Urgent`
   - `IQ/Negative`
3. User sees labels in Gmail inbox immediately
4. Can filter/search by labels

**Technical Implementation:**

```python
# Add to process_incoming_email_task after classification
def apply_gmail_labels(ticket: Ticket, connection: InboxConnection):
    """Apply classification labels to Gmail message"""
    if connection.provider != 'gmail':
        return

    labels_to_add = [
        f"IQ/Category/{ticket.category}",
        f"IQ/Priority/{ticket.priority}",
        f"IQ/Sentiment/{ticket.sentiment}"
    ]

    # Get or create labels
    gmail_service = build_gmail_service(connection)
    for label_name in labels_to_add:
        label_id = get_or_create_label(gmail_service, label_name)

    # Apply to message
    gmail_service.users().messages().modify(
        userId='me',
        id=ticket.message_id,
        body={'addLabelIds': label_ids}
    ).execute()
```

**Required Changes:**
1. Add `apply_gmail_labels()` function to `src/email_poll.py`
2. Call after ticket creation in `process_incoming_email_task`
3. Add Gmail label management permissions to OAuth scope
4. Create label hierarchy: `IQ/Category/`, `IQ/Priority/`, `IQ/Sentiment/`

**Pros:**
✅ Very simple to implement (1-2 days)
✅ No user installation required
✅ Native Gmail feature
✅ Works on mobile Gmail app
✅ Can filter/search by labels
✅ Immediate visual feedback in inbox

**Cons:**
❌ Gmail only (not Outlook)
❌ Limited UI (text labels only, no custom styling)
❌ Can clutter label list
❌ Less rich than custom add-on

**Effort:** 1-2 days

---

### Option 3: Browser Extension

**Description:**
Chrome/Firefox extension that injects classification UI into Gmail/Outlook web interface.

**User Experience:**
1. Extension detects email in inbox
2. Injects badges/chips next to subject line
3. Hover for details
4. Click for actions

**Technical Implementation:**

```javascript
// Content script for Gmail
function injectClassificationBadges() {
  const emailRows = document.querySelectorAll('tr.zA'); // Gmail inbox rows

  emailRows.forEach(row => {
    const messageId = extractMessageId(row);

    fetch('https://api.kalevent.com/api/v1/inboxiq/classify', {
      headers: { 'Authorization': `Bearer ${token}` },
      body: JSON.stringify({ message_id: messageId })
    })
    .then(res => res.json())
    .then(data => {
      const badge = createBadge(data.category, data.priority);
      row.querySelector('.xW').appendChild(badge);
    });
  });
}

// Observe DOM changes for dynamic loading
const observer = new MutationObserver(injectClassificationBadges);
observer.observe(document.body, { childList: true, subtree: true });
```

**Pros:**
✅ Works for both Gmail and Outlook (web)
✅ Highly customizable UI
✅ Can inject badges, tooltips, action buttons
✅ Similar to how Grammarly works

**Cons:**
❌ Only works in web browsers (not mobile apps)
❌ Users must install extension
❌ UI injection can break if Gmail/Outlook changes HTML
❌ Requires ongoing maintenance
❌ Extension store approval needed for public distribution

**Effort:** 2-3 weeks

---

## Comparison Matrix

| Feature | Gmail Add-on | Gmail Labels | Browser Ext |
|---------|-------------|--------------|-------------|
| **Gmail Support** | ✅ | ✅ | ✅ |
| **Outlook Support** | ✅ (separate) | ❌ | ✅ |
| **Mobile Support** | ✅ | ✅ | ❌ |
| **Rich UI** | ✅✅✅ | ⚠️ Basic | ✅✅ |
| **No Installation** | ❌ | ✅ | ❌ |
| **Effort** | 2-3 weeks | 1-2 days | 2-3 weeks |
| **Maintenance** | Medium | Low | High |
| **Professional** | ✅✅✅ | ✅ | ✅✅ |

## Recommended Implementation Roadmap

### Phase 1: Gmail Labels (Week 1)
**Quick win to validate user demand**

- [ ] Add Gmail label application to `process_incoming_email_task`
- [ ] Request Gmail label management permissions in OAuth flow
- [ ] Create label hierarchy: `IQ/Category/`, `IQ/Priority/`, `IQ/Sentiment/`
- [ ] Test with 10-20 emails
- [ ] Gather user feedback

**Outcome:** Users immediately see classification in Gmail without leaving inbox.

### Phase 2: Gmail Add-on (Weeks 2-4)
**Rich UI for power users**

- [ ] Design sidebar UI mockups
- [ ] Build Google Apps Script add-on
- [ ] Implement `/api/v1/inboxiq/classify` endpoint
- [ ] Add authentication flow (OAuth + JWT token storage)
- [ ] Deploy privately to test users
- [ ] Iterate based on feedback
- [ ] Document installation for customers

**Outcome:** Professional sidebar with full classification details and action buttons.

### Phase 3: Outlook Add-in (Weeks 5-7)
**Extend to Outlook users**

- [ ] Port Gmail add-on UI to Office.js
- [ ] Test with Outlook web, desktop, mobile
- [ ] Deploy privately for testing
- [ ] Document installation
- [ ] Support both Gmail and Outlook users

**Outcome:** Feature parity across both major email platforms.

### Phase 4 (Optional): Public Marketplace
**If product-market fit is strong**

- [ ] Polish UI/UX based on feedback
- [ ] Create privacy policy and terms
- [ ] Submit to Google Workspace Marketplace
- [ ] Submit to Microsoft AppSource
- [ ] Marketing: Blog post, docs, demo video

**Outcome:** Public discovery, broader reach.

## Technical Requirements

### New Backend Endpoint

```python
# src/api/v1/inboxiq.py

@v1.route("/inboxiq/classify", methods=["POST"])
@jwt_required()
def classify_email():
    """
    On-demand email classification for add-ons/extensions.

    Request:
        {
            "message_id": "gmail-message-id",
            "subject": "Optional - if message not in DB",
            "body": "Optional - if message not in DB",
            "from_email": "Optional"
        }

    Response:
        {
            "category": "billing",
            "priority": "P1",
            "sentiment": "negative",
            "decision": { ... },
            "ticket_id": "abc123",
            "exists": true,
            "ai_reason": "Customer reporting payment failure"
        }
    """
    pass
```

### OAuth Scope Updates

**Gmail:**
- Add `https://www.googleapis.com/auth/gmail.labels` (for Option 2)
- Add `https://www.googleapis.com/auth/gmail.readonly` (for add-on)

**Outlook:**
- Add `Mail.ReadWrite` scope (for labels/categories)

### Database Schema Changes
No changes required - all classification data already stored in `Ticket` model.

## Security Considerations

1. **Authentication:** Add-ons must securely store JWT tokens (use browser secure storage)
2. **Rate Limiting:** Add rate limits to `/api/v1/inboxiq/classify` endpoint
3. **Permissions:** Request minimal OAuth scopes (read-only for add-ons)
4. **Privacy:** Don't log full email content, only metadata
5. **Token Refresh:** Implement token refresh flow for long-lived sessions

## Success Metrics

- **Adoption Rate:** % of users who install add-on
- **Engagement:** Daily active users of add-on
- **Time Saved:** Reduction in time spent in InboxIQ dashboard
- **Classification Views:** Number of times users view classification in inbox
- **Ticket Creation:** % increase in tickets created via add-on vs dashboard
- **User Satisfaction:** NPS score for in-inbox experience

## Open Questions

1. Should add-on allow inline ticket creation or just display classification?
2. Do we want to support automation rule triggers from within the add-on?
3. Should we display draft replies in the add-on sidebar?
4. Do we need offline support for classification results?
5. Should we cache classifications client-side to reduce API calls?

## References

- Gmail Add-on Development: https://developers.google.com/gmail/add-ons
- Outlook Add-in Development: https://learn.microsoft.com/en-us/office/dev/add-ins/outlook/
- Gmail API Labels: https://developers.google.com/gmail/api/guides/labels
- Similar Products: Superhuman, Boomerang, SaneBox, Antigravity

## Next Steps

1. Review this proposal with stakeholders
2. Validate user demand (survey or interviews)
3. Choose implementation path (recommend Phase 1 → Phase 2)
4. Allocate engineering resources
5. Create detailed technical spec for chosen approach

---

**Questions or feedback?** Discuss in #product-features channel or email product@kalevent.com
