# InboxIQ Intake API (Webhook / API)

Send any structured/semi-structured message into InboxIQ (forms, chat widgets, CRMs, internal tools). The same AI agent triages, creates tickets only when needed, and auto-handles the rest.

For channel-specific examples (hotline, Facebook, Outlook), see the [Channel Intake Guide](/docs/channel_intake_guide).

## Endpoint
- `POST /api/v1/intake`
- Auth: `X-Intake-Token` (from env `INBOXIQ_INTAKE_TOKEN`) **or** logged-in JWT. If the token env var is set, the header is required.

## Request body (examples)

- Website form:
```json
{
  "subject": "Contact us: integration question",
  "body": "How do we connect our internal CRM to InboxIQ?",
  "source": "form"
}
```

- Chat handoff:
```json
{
  "subject": "Chat handoff: billing issue",
  "body": "User: I was double-charged this month.\nBot: Let me check...\nUser: please escalate.",
  "source": "chat"
}
```

- CRM event:
```json
{
  "subject": "CRM: escalated lead responded angrily",
  "body": "Lead ABC replied: \"Why was I charged again?\"",
  "source": "crm",
  "provider_thread_url": "https://crm.example.com/leads/abc"
}
```

- Compliance/incident:
```json
{
  "subject": "Security incident report",
  "body": "Whistleblower report about access policy violation.",
  "source": "compliance"
}
```

Common fields:
- `subject` (required-ish): title/subject for triage.
- `body` or `message` (required): main content.
- `source` (optional): e.g., webhook, crm, chat, form, compliance.
- `from_email` (optional): used for VIP/routing signals.
- `message_id`, `provider_thread_url`, `received_at` (optional): preserved for threading/audit.
- `account_id` (optional): specify which account; otherwise falls back to the caller’s account (JWT).

## Behavior
1) Runs InboxIQ triage on the payload.
2) If `action_required == true`, creates a ticket and returns it.
3) Otherwise, stores as feedback-like record (auto-handled/optional) with decision + entities.

## Response (example)
```json
{
  "success": true,
  "decision": { "...": "triage payload" },
  "ticket": {
    "id": "t_123",
    "status": "new",
    "priority": "P2",
    "action_required": true
  },
  "feedback": null
}
```

## Sample curl
```bash
curl -X POST https://api.kalevent.com/api/v1/intake \
  -H "X-Intake-Token: $INBOXIQ_INTAKE_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "subject": "Customer asked about enterprise pricing",
    "body": "Hi, can you share enterprise pricing and SSO options?",
    "source": "webhook",
    "from_email": "form@yourdomain.com",
    "account_id": 42
  }'
```
