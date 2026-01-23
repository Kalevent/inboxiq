# InboxIQ Feedback API (In-App / Webhook-Style Intake)

Send in-app feedback directly into InboxIQ via API. The same triage agent classifies, decides action_required, and creates a ticket only when needed. Non-actionable feedback is stored and shown under “Auto-handled (Feedback)” in the dashboard.

## Endpoint
- `POST /api/v1/feedback`
- Auth: JWT (same session token used in the app). For external/webhook-style usage, use a service token or HMAC proxy; anonymous is not supported yet.

## Request body
```json
{
  "message": "The dashboard is great, but filtering feels slow on large inboxes.",
  "context": "Page: Dashboard; Browser: Chrome; Plan: Pro",
  "urgency": 3,
  "subject": "Feedback from in-app form (optional)"
}
```
- `message` (required): main feedback text.
- `context` (optional, free text): extra metadata you want stored (string).
- `urgency` (optional): 1–5 (defaults to 3).
- `subject` (optional): overrides the generated subject.

## Behavior
1. Runs triage (same as email/webhook), tagged `source="feedback"`.
2. Persists feedback with:
   - `action_required` (“true” | “false” | “optional”)
   - `ai_decision_json` (decision + trace)
   - `metadata_json` (entities/context)
3. If `action_required == true`, a ticket is created and linked to `ticket_id`.
4. If not, it appears in dashboard under **Auto-handled (Feedback)** (separate from Auto-handled Email).

## Response (example)
```json
{
  "success": true,
  "feedback": {
    "id": "fb_123",
    "action_required": "optional",
    "metadata": { "order_ids": [], "customer_ids": [] },
    "decision": { "...": "triage payload" },
    "ticket_id": null
  },
  "ticket": null,
  "decision": {
    "category": "feature",
    "priority": "P2",
    "sentiment": "neutral",
    "action_required": "optional",
    "ai_reason": "Not blocking; monitor."
  }
}
```

## Sample curl
```bash
curl -X POST https://api.kalevent.com/api/v1/feedback \
  -H "Authorization: Bearer <JWT>" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "The dashboard is great, but filtering feels slow on large inboxes.",
    "context": "Page: Dashboard; Browser: Chrome; Plan: Pro",
    "urgency": 3
  }'
```

## Notes
- Use your app session JWT or a service token. If you need HMAC/webhook auth, add a proxy or new endpoint before exposing publicly.
- Tickets are only created when action_required is true. Otherwise, feedback stays grouped separately from email auto-handled items.***
