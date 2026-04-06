# InboxIQ Developer Guide

Integrate your products and internal tools with InboxIQ using the Platform API. This guide covers everything you need to go from zero to your first authenticated API call.

## Overview

The InboxIQ Platform API lets you:

- **Push tickets into InboxIQ** from any source — forms, chat widgets, CRMs, billing platforms, or custom systems.
- **Search the SearxNG proxy** for enriched results your agents can act on.
- Automate intake and triage without touching the UI.

Access is granted per account. You register a named app, receive credentials, and authenticate every request using HTTP Basic Auth.

---

## Step 1 — Request Developer Access

Developer access is not enabled by default. To get started:

1. Sign in and go to **Settings → Developer**.
2. Select the scopes you need:
   - **intake:write** — push messages and events into InboxIQ.
   - **tickets:read** — query tickets and search.
3. Briefly describe your use case and click **Request access**.

Your request goes to the account admin. You'll see a *Under review* state until it is approved.

---

## Step 2 — Register an App

Once access is approved:

1. Go to **Settings → Developer**.
2. Fill in:
   - **App name** — a label for this integration (e.g. "Sage Connector", "Helpdesk Bridge").
   - **Scopes** — select `intake:write`, `tickets:read`, or both depending on what you need.
   - **IP allowlist** (optional) — comma-separated IPs or CIDR ranges. Leave blank to allow any IP.
   - **Webhook URL** (optional) — InboxIQ will deliver outbound events here.
3. Click **Register app**.

A modal appears with your **Client ID** and **Client Secret**. Copy the secret immediately — it is shown once and cannot be recovered. Treat it like a password.

---

## Authentication

All API requests use **HTTP Basic Auth**:

- **Username:** `client_id`
- **Password:** `client_secret`

```bash
curl -u "your_client_id:your_client_secret" \
  -H "Content-Type: application/json" \
  https://kalevent.com/api/v1/intake
```

In most HTTP libraries this is equivalent to setting the `Authorization: Basic <base64>` header. Make sure there is **no space** between the colon and your secret — `client_id:secret`, not `client_id: secret`.

### Scopes

Each registered app is granted a set of scopes at registration time. Calling an endpoint that requires a scope not granted to your app returns `403 forbidden`.

| Scope | What it unlocks |
|---|---|
| `intake:write` | `POST /api/v1/intake` — push messages and events |
| `tickets:read` | `GET /api/v1/search` — query the search proxy |

### IP Allowlist

If you configured an allowlist, requests from IPs not on the list are rejected with `403 ip_not_allowed`. The check uses the leftmost value of `X-Forwarded-For` (from a load balancer) or `REMOTE_ADDR` directly.

### Plan requirement

API access requires a Business plan or an active trial. Requests from accounts that do not meet this requirement return `403 plan_required`.

---

## API Reference

### POST /api/v1/intake

Push a message or event into InboxIQ. The AI triage agent evaluates the payload and creates a ticket if action is required.

**Required scope:** `intake:write`

**Request body** (JSON):

| Field | Type | Required | Description |
|---|---|---|---|
| `body` | string | yes | Main content of the message. Aliases: `message`. |
| `subject` | string | recommended | Title for triage. Aliases: `title`. Defaults to `"Inbound request"`. |
| `source` | string | no | Channel hint: `webhook`, `form`, `chat`, `crm`, `compliance`, `email`. |
| `from_email` | string | no | Sender address. Used for VIP and routing signals. Aliases: `sender`. |
| `summary` | string | no | Short summary to use if `body` is absent. |
| `provider_thread_url` | string | no | Link back to the originating thread (CRM, ticketing system, etc.). Aliases: `thread_url`. |
| `message_id` | string | no | External message identifier. Preserved for deduplication and threading. |
| `received_at` | string | no | ISO 8601 timestamp of the original event. |
| `context` | object | no | Arbitrary key-value metadata attached to the ticket (e.g. invoice number, customer tier). |

**Response** `202 Accepted`:

```json
{
  "success": true,
  "status": "queued",
  "task_id": "4f9c2b3a-1e8d-4a6f-b0c2-d3e5f6a7b8c9"
}
```

Intake is asynchronous — the payload is queued for processing. The `task_id` can be used for tracing in Celery logs.

**Example — website contact form:**

```bash
curl -u "$CLIENT_ID:$CLIENT_SECRET" \
  -X POST https://kalevent.com/api/v1/intake \
  -H "Content-Type: application/json" \
  -d '{
    "subject": "Contact form: pricing question",
    "body": "Hi, we are evaluating InboxIQ for a team of 50. Can you share enterprise pricing?",
    "source": "form",
    "from_email": "procurement@acme.com"
  }'
```

**Example — CRM event:**

```bash
curl -u "$CLIENT_ID:$CLIENT_SECRET" \
  -X POST https://kalevent.com/api/v1/intake \
  -H "Content-Type: application/json" \
  -d '{
    "subject": "CRM: Deal stage changed — escalated",
    "body": "Deal ABC moved to Escalated. Last note: customer unhappy with SLA.",
    "source": "crm",
    "from_email": "crm-events@yourcrm.com",
    "provider_thread_url": "https://yourcrm.com/deals/abc",
    "context": {
      "deal_id": "abc",
      "account_name": "Acme Corp",
      "arr": "120000"
    }
  }'
```

**Example — chat handoff:**

```bash
curl -u "$CLIENT_ID:$CLIENT_SECRET" \
  -X POST https://kalevent.com/api/v1/intake \
  -H "Content-Type: application/json" \
  -d '{
    "subject": "Chat handoff: billing dispute",
    "body": "User: I was charged twice this month.\nBot: I am escalating this to the team.\nUser: Please fix it urgently.",
    "source": "chat",
    "from_email": "user@customer.com"
  }'
```

**Example — accounting event (Sage / QuickBooks):**

```bash
curl -u "$CLIENT_ID:$CLIENT_SECRET" \
  -X POST https://kalevent.com/api/v1/intake \
  -H "Content-Type: application/json" \
  -d '{
    "subject": "Sage: Invoice INV-2047 overdue",
    "body": "Invoice INV-2047 for £4,200 is 30 days overdue. Customer: Acme Ltd.",
    "source": "webhook",
    "context": {
      "invoice_id": "INV-2047",
      "amount": "4200",
      "currency": "GBP",
      "customer": "Acme Ltd"
    }
  }'
```

---

### GET /api/v1/search

Proxy to the SearxNG search engine. Use this from AI agents or automation rules to retrieve enriched search results.

**Required scope:** `tickets:read`

**Query parameters:**

| Parameter | Required | Description |
|---|---|---|
| `q` | yes | Search query string. |

**Example:**

```bash
curl -u "$CLIENT_ID:$CLIENT_SECRET" \
  "https://kalevent.com/api/v1/search?q=enterprise+pricing+InboxIQ"
```

Returns SearxNG results as JSON. The exact response schema follows the SearxNG API format.

---

## Error Reference

| HTTP status | `error` value | Meaning |
|---|---|---|
| `400` | `validation_error` | Missing or invalid request body. Check that `body` or `message` is present. |
| `401` | `unauthorized` | Missing or invalid credentials. Verify your `client_id` and `client_secret` and that the app status is *active*. |
| `403` | `forbidden` / `ip_not_allowed` | Your IP is not on the allowlist. |
| `403` | `forbidden` | Scope not granted for this app. |
| `403` | `plan_required` | Your account needs a Business plan or active trial. |
| `502` | `enqueue_failed` | Internal queue error. Retry with exponential back-off. |

All error responses follow this shape:

```json
{
  "error": "unauthorized",
  "message": "invalid credentials"
}
```

---

## Rotating Credentials

If your `client_secret` is exposed:

1. Go to **Settings → Developer**.
2. Click **Revoke** next to the compromised app.
3. Register a new app and update your integration.

There is no partial rotation — revoking an app invalidates the `client_id` and `client_secret` immediately.

---

## Security Best Practices

- **Never commit credentials** to source control. Use environment variables or a secrets manager.
- **Use the IP allowlist** for server-to-server integrations where the source IP is predictable.
- **Store the secret securely.** It is shown once at registration and cannot be retrieved again.
- **Scope minimally.** Only request the scopes your integration actually needs.
- **Rotate on exposure.** Revoke and re-register immediately if credentials are compromised.

---

## Prior Authorisation — Approval Policies API

Approval policies control which emails are **auto-sent directly** — bypassing the Gmail/Outlook draft queue — when the AI reply confidence meets a threshold. Simple single-condition policies can be created in **Settings → AI Features**. Policies with multiple conditions (e.g. email type AND sentiment guard) must be created via this API.

### Authentication

This API uses **JWT Bearer auth**, not HTTP Basic Auth. Obtain a token by logging in first:

```bash
curl -X POST https://kalevent.com/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "you@example.com", "password": "yourpassword"}'
```

Use the returned `access_token` on every request:

```bash
-H "Authorization: Bearer <access_token>"
```

---

### Condition fields

Conditions are matched against the AI triage output for each incoming email.

| Field | Allowed values |
|---|---|
| `email_type` | `support_request`, `sales_inquiry`, `billing`, `bug_report`, `feature_request`, `marketing`, `newsletter`, `spam`, `transactional`, `auto_reply`, `notification`, `internal`, `other` |
| `category` | Any category produced by your triage config (e.g. `billing`, `support`) |
| `sentiment` | `positive`, `neutral`, `negative` |

Allowed operators: `equals`, `not_equals`, `contains`, `not_contains`, `in_list`

For `in_list`, pass a comma-separated string as the value — `"support_request,sales_inquiry"`.

---

### GET /api/v1/approval-policies

List all policies for your account.

```bash
curl -H "Authorization: Bearer <token>" \
  https://kalevent.com/api/v1/approval-policies
```

---

### POST /api/v1/approval-policies

Create a new policy.

| Field | Type | Required | Description |
|---|---|---|---|
| `name` | string | yes | Label shown in the Settings UI |
| `description` | string | no | Optional explanation |
| `conditions` | array | yes | At least one condition object |
| `condition_logic` | string | no | `AND` (default) or `OR` |
| `min_confidence` | float | no | Threshold 0–1. Default: `0.85` |
| `enabled` | boolean | no | Default: `true` |

Each condition:

```json
{"field": "email_type", "operator": "equals", "value": "support_request"}
```

**Example — auto-send support requests, never when negative sentiment:**

```bash
curl -X POST https://kalevent.com/api/v1/approval-policies \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Auto-send support requests",
    "conditions": [
      {"field": "email_type", "operator": "equals", "value": "support_request"},
      {"field": "sentiment", "operator": "not_equals", "value": "negative"}
    ],
    "condition_logic": "AND",
    "min_confidence": 0.88,
    "enabled": true
  }'
```

**Example — auto-send multiple email types:**

```bash
curl -X POST https://kalevent.com/api/v1/approval-policies \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Auto-send routine support",
    "conditions": [
      {"field": "email_type", "operator": "in_list", "value": "support_request,sales_inquiry"}
    ],
    "min_confidence": 0.85,
    "enabled": true
  }'
```

Returns `201 Created` with the full policy object including its `id`.

---

### GET /api/v1/approval-policies/\<id\>

Fetch a single policy by ID.

---

### PATCH /api/v1/approval-policies/\<id\>

Update any fields. Only fields you send are changed.

**Disable a policy:**

```bash
curl -X PATCH https://kalevent.com/api/v1/approval-policies/<id> \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"enabled": false}'
```

**Raise the confidence threshold:**

```bash
curl -X PATCH https://kalevent.com/api/v1/approval-policies/<id> \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"min_confidence": 0.92}'
```

---

### DELETE /api/v1/approval-policies/\<id\>

Permanently delete a policy.

---

### Approval policy errors

| Status | Error |
|---|---|
| `400` | `name is required` |
| `400` | `condition field must be one of: category, email_type, sentiment` |
| `400` | `condition operator must be one of: contains, equals, in_list, not_contains, not_equals` |
| `400` | `min_confidence must be a float between 0 and 1` |
| `400` | `at least one condition is required` |
| `404` | Policy not found or belongs to a different account |

---

## Related guides

- [Channel Intake Guide](/docs/channel_intake_guide)
- [Service Integrations](/docs/service_integrations)
- [Automation Studio](/docs/automation_studio_accounting)
