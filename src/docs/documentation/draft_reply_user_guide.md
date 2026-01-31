# AI-Powered Draft Replies

InboxIQ's AI Draft Reply feature automatically generates professional, context-aware response drafts for customer emails, saving your team time while maintaining high-quality support.

## Overview

When a customer email requires action, InboxIQ can automatically generate a draft reply that:
- Understands the customer's issue and intent
- Provides relevant, helpful responses
- Maintains a professional, empathetic tone
- References your knowledge base articles (when configured)
- Requires human review before sending

## Availability

**Draft Replies are available to:**
- Business plan subscribers
- Enterprise plan subscribers
- Active trial accounts

## How It Works

### 1. Email Arrives
When a customer email arrives, InboxIQ's AI:
1. Analyzes the email content, subject, and context
2. Classifies the issue type (billing, technical, refund, etc.)
3. Determines if it requires human action
4. Generates an appropriate draft reply

### 2. Draft Generation
The AI considers:
- **Customer intent**: What they're asking for or reporting
- **Sentiment**: Their emotional state (frustrated, confused, etc.)
- **Urgency**: Priority level based on content
- **Knowledge base**: Relevant help articles (when KB is connected)
- **Conversation history**: Previous interactions with this customer

### 3. Review & Send
Your team receives:
- The original customer email
- An AI-generated draft reply
- Confidence score (how confident the AI is in its response)
- Relevant knowledge base articles referenced

Agents can:
- ✅ **Accept**: Send the draft as-is
- ✏️ **Edit**: Make adjustments before sending
- ❌ **Reject**: Write a completely new reply

## Using Draft Replies

### In the Dashboard

1. **View Drafts**: Navigate to your InboxIQ dashboard
2. **Enable Filter**: Toggle "DraftReply only" to see only tickets with AI drafts
3. **Review Badge**: Tickets with drafts show a blue "DraftReply" badge
4. **Open Ticket**: Click to view the draft alongside the customer email

### Draft Reply Interface

When viewing a ticket with a draft:
```
┌─────────────────────────────────────────┐
│ Customer Email                           │
│ Subject: Refund request for order #12345│
│ From: customer@example.com              │
│ Body: I received a damaged product...   │
└─────────────────────────────────────────┘

┌─────────────────────────────────────────┐
│ 🤖 AI Draft Reply (Confidence: 85%)     │
│                                          │
│ Thank you for contacting us about your  │
│ refund request. I understand that order │
│ #12345 arrived damaged. We sincerely... │
│                                          │
│ [Edit] [Accept] [Reject]                │
└─────────────────────────────────────────┘
```

### Providing Feedback

After reviewing a draft, provide feedback to improve future responses:

**Accepted Draft:**
- Click "Accept" or send without changes
- System logs: ✅ Draft accepted, 120 seconds saved
- Helpfulness: Rate 1-5 stars

**Edited Draft:**
- Make your changes in the editor
- Click "Send"
- System logs: ✏️ Draft edited, measures edit distance
- Helps AI learn what to improve

**Rejected Draft:**
- Click "Reject" and write your own reply
- System logs: ❌ Draft rejected
- AI learns what types of responses didn't work

## Quality & Training

### Confidence Scores

Each draft includes a confidence score:
- **80-100%**: High confidence, typically accurate
- **70-79%**: Medium confidence, review carefully
- **Below 70%**: Low confidence, likely needs editing

Drafts with confidence below 70% are automatically flagged for review.

### Continuous Improvement

Your feedback trains the AI:
1. **Accepted drafts** reinforce successful patterns
2. **Edits** show the AI what to adjust
3. **Rejections** indicate when a different approach is needed

The system compares draft vs final text to learn:
- Tone adjustments you prefer
- Information you add
- Sections you remove
- Formatting you use

### Accuracy Metrics

Track draft reply performance:
- **Acceptance Rate**: % of drafts sent without edits
- **Average Edit Distance**: How much editing is needed
- **Time Saved**: Minutes saved per ticket
- **Helpfulness Score**: Average agent rating (1-5)

Access metrics: **Settings → Analytics → Draft Reply Performance**

## Best Practices

### For Agents

✅ **Do:**
- Review every draft before sending
- Personalize with customer name when available
- Add specific details the AI might have missed
- Rate draft helpfulness to improve quality

❌ **Don't:**
- Send drafts without reading them
- Assume the AI has all context
- Skip feedback - it helps everyone

### For Admins

**Optimize Performance:**
1. Connect your knowledge base for better answers
2. Review low-acceptance drafts to identify patterns
3. Add common FAQs to your KB
4. Monitor confidence scores over time

**Training the AI:**
- Use the feedback system consistently
- Mark high-quality replies for training
- Document internal knowledge
- Update KB articles regularly

## Knowledge Base Integration

### Supported Platforms

Connect your knowledge base to enhance draft quality:
- ✅ Zendesk Guide
- ✅ Notion
- ✅ Confluence
- ✅ Intercom Articles
- ✅ HelpScout Docs
- ✅ GitBook
- ✅ Custom REST API

### How KB Articles Help

When you connect your knowledge base:
1. AI searches for relevant articles
2. Incorporates article information into drafts
3. Includes article links for customers
4. Cites sources for agent verification

**Example:**
```
Thank you for asking about our refund policy.
According to our [Refund Policy](link), you can
request a full refund within 30 days...
```

### Setting Up KB Integration

1. Go to **Settings → Integrations**
2. Click "Connect Knowledge Base"
3. Choose your platform
4. Authorize access
5. Configure sync settings
6. Wait for initial sync (10-30 minutes)

## API Integration

### Generate Draft via API

```bash
POST /api/v1/inboxiq/triage
Content-Type: application/json

{
  "messages": [{
    "subject": "Billing question",
    "body": "Why was I charged twice?",
    "from_email": "customer@example.com"
  }],
  "account_id": 123
}
```

**Response:**
```json
{
  "reply_text": "Thank you for contacting us...",
  "reply_confidence": 0.85,
  "reply_metadata": {
    "kb_articles_used": ["article_123", "article_456"],
    "generated_at": "2026-01-31T10:00:00Z",
    "requires_review": false
  }
}
```

### Submit Feedback via API

```bash
POST /api/v1/inboxiq/tickets/{ticket_id}/reply-feedback
Content-Type: application/json

{
  "feedback_type": "accepted",
  "helpfulness_score": 5,
  "time_saved_seconds": 120
}
```

## MCP Server Integration

For workflow automation, use the MCP tool:

```python
# Via MCP server
draft_customer_reply(
    subject="Refund request",
    body="I need a refund for order #12345",
    from_email="customer@example.com",
    account_id=123
)
```

Returns draft reply with full context for automated workflows.

## Troubleshooting

### No Drafts Appearing

**Check:**
- ✅ Feature enabled: `Settings → Features → Draft Replies`
- ✅ Correct plan: Business, Enterprise, or active trial
- ✅ Toggle enabled: "DraftReply only" in dashboard
- ✅ Tickets are action_required (not auto-handled)

### Low Quality Drafts

**Improve by:**
- Connecting your knowledge base
- Providing consistent feedback
- Adding more help articles
- Training with high-quality examples

### Confidence Scores Too Low

**Common causes:**
- Insufficient context in customer email
- No relevant KB articles
- Unusual or rare request type
- Missing conversation history

**Solutions:**
- Add more KB articles
- Train with similar examples
- Review and edit to teach the AI

## Privacy & Security

### Data Handling
- Customer emails are processed securely
- Drafts are stored encrypted
- No data shared with third parties
- GDPR compliant

### Human Oversight
- All drafts require human review
- Auto-send disabled by default
- Agents always have final control
- Audit trail of all replies

## Support

Need help with Draft Replies?
- **Email**: support@kalevent.com
- **Docs**: [kalevent.com/docs](https://kalevent.com/docs)
- **Status**: [status.kalevent.com](https://status.kalevent.com)
