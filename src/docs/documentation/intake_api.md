# InboxIQ Intake API

Push any structured message into InboxIQ from forms, chat widgets, CRMs, billing platforms, or internal tools. The AI triage agent evaluates each payload and creates a ticket when action is required.

For full setup instructions, credential management, and security guidance, see the [Developer Guide](/docs/developer_guide).

For channel-specific examples (hotline, Facebook, Outlook), see the [Channel Intake Guide](/docs/channel_intake_guide).

## Endpoint

```http
POST /api/v1/intake
```

**Authentication:** HTTP Basic Auth with your `client_id` and `client_secret` (scope: `intake:write`).
Register your app at **Settings → Developer** to obtain credentials.

## Request body

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `body` | string | yes | Main content. Aliases: `message`. |
| `subject` | string | recommended | Title for triage. Aliases: `title`. |
| `source` | string | no | Channel hint: `form`, `chat`, `crm`, `webhook`, `compliance`. |
| `from_email` | string | no | Sender address. Aliases: `sender`. |
| `provider_thread_url` | string | no | Link back to the originating thread. Aliases: `thread_url`. |
| `message_id` | string | no | External message ID (deduplication, threading). |
| `received_at` | string | no | ISO 8601 timestamp of the original event. |
| `context` | object | no | Arbitrary metadata (invoice IDs, customer tier, etc.). |

## Response

`202 Accepted` — payload queued for async processing:

```json
{
  "success": true,
  "status": "queued",
  "task_id": "4f9c2b3a-1e8d-4a6f-b0c2-d3e5f6a7b8c9"
}
```

## Examples

**Contact form:**

```bash
curl -u "$CLIENT_ID:$CLIENT_SECRET" \
  -X POST https://kalevent.com/api/v1/intake \
  -H "Content-Type: application/json" \
  -d '{
    "subject": "Pricing question",
    "body": "Can you share enterprise pricing for a team of 50?",
    "source": "form",
    "from_email": "buyer@acme.com"
  }'
```

**CRM webhook:**

```bash
curl -u "$CLIENT_ID:$CLIENT_SECRET" \
  -X POST https://kalevent.com/api/v1/intake \
  -H "Content-Type: application/json" \
  -d '{
    "subject": "CRM: escalated lead responded",
    "body": "Lead ABC replied: Why was I charged again?",
    "source": "crm",
    "provider_thread_url": "https://crm.example.com/leads/abc",
    "context": { "deal_id": "abc", "account": "Acme Corp" }
  }'
```

**Accounting event (Sage / QuickBooks):**

```bash
curl -u "$CLIENT_ID:$CLIENT_SECRET" \
  -X POST https://kalevent.com/api/v1/intake \
  -H "Content-Type: application/json" \
  -d '{
    "subject": "Invoice INV-2047 overdue",
    "body": "Invoice INV-2047 for £4,200 is 30 days overdue.",
    "source": "webhook",
    "context": { "invoice_id": "INV-2047", "amount": "4200", "currency": "GBP" }
  }'
```

## Related

- [Developer Guide](/docs/developer_guide) — app registration, scopes, error reference
- [Channel Intake Guide](/docs/channel_intake_guide) — email, chat, social channel examples
