# Unified Intake API - Postman Collection Guide

Complete guide for integrating external systems via webhooks and API using Postman.

## Overview

The Unified Intake API provides a single endpoint for all inbound requests from:
- Website contact forms
- CRM systems (HubSpot, Salesforce, Pipedrive)
- Chat platforms (Intercom, Drift, LiveChat)
- Social media (Twitter DMs, Facebook messages)
- Slack mentions
- Custom integrations
- In-app forms

This guide covers how to test and integrate using the Postman collection.

---

## 📱 Step 1: Import the Collection in VS Code

1. Open **VS Code**
2. Open the **Postman extension** (Thunder Client or Postman for VS Code)
3. Click **"Import"** or **"Collections"** → **"Import Collection"**
4. Select `Unified_Intake_API.postman_collection.json` from the project root
5. You'll see **"Unified Intake API"** collection with 3 main requests + examples

---

## 🔑 Step 2: Get Your Intake Token (One-Time Setup)

The intake token is different from your JWT token. It's used for external webhook authentication.

### Option A: From Admin Dashboard (Recommended)

1. Go to `https://kalevent.com/admin`
2. Scroll to **"API / Webhooks"** section
3. Click **"Generate Intake Token"** if you don't have one
4. Copy the token value (e.g., `ik_live_abc123xyz...`)

### Option B: From Database (Admin Only)

```sql
SELECT token_hash, created_at, expires_at
FROM intake_tokens
WHERE account_id = 2 AND revoked_at IS NULL;
```

**⚠️ Security Note**: Never commit intake tokens to version control. Store securely.

---

## ⚙️ Step 3: Set Variables in Collection

1. In Postman, click on **"Unified Intake API"** collection name
2. Go to **"Variables"** tab
3. Set these values in **"Current Value"** field:

| Variable | Value | Example |
|----------|-------|---------|
| `baseUrl` | Your API domain | `https://api.kalevent.com` |
| `apiPrefix` | API prefix | `api` |
| `apiVersion` | API version | `v1` |
| `intake_token` | Your intake token from Step 2 | `ik_live_abc123...` |
| `jwt_token` | JWT token (for authenticated forms) | `eyJhbGc...` |

4. Click **Save**

**✅ Now all requests will automatically include authentication!**

---

## 🚀 Step 4: Test Your First Webhook

Run the requests in this order:

### Request 1: Webhook Intake (External)

This is the main endpoint for external integrations.

1. Click **"1. Webhook Intake (External)"**
2. You'll see a pre-filled example:

```json
{
  "subject": "Support Request from Contact Form",
  "body": "Customer is experiencing login issues and needs immediate assistance.",
  "from_email": "customer@example.com",
  "source": "website_contact_form",
  "provider": "custom_form",
  "channel": "web",
  "provider_thread_url": "https://example.com/submissions/12345",
  "context": {
    "user_agent": "Mozilla/5.0",
    "referrer": "https://example.com/pricing",
    "utm_source": "google",
    "utm_campaign": "support"
  }
}
```

3. Click **"Send"**

**Response:**
```json
{
  "success": true,
  "status": "queued",
  "task_id": "celery-task-abc-123"
}
```

**🎉 Your webhook was successfully received and queued for processing!**

**⚡ How Authentication Works:**

The Postman collection automatically generates:
- `X-Timestamp`: Current Unix timestamp
- `X-Signature`: HMAC-SHA256 signature to prevent tampering
- `X-Intake-Token`: Your intake token

The **Pre-request Script** handles this automatically:
```javascript
// Auto-generated HMAC signature
const timestamp = Math.floor(Date.now() / 1000).toString();
const body = pm.request.body.raw;
const message = timestamp + '.' + body;
const signature = CryptoJS.HmacSHA256(message, token).toString(CryptoJS.enc.Hex);
```

---

### Request 2: Form Submit (Authenticated)

For in-app forms where users are already logged in.

1. Make sure you have `jwt_token` set in collection variables
2. Click **"2. Form Submit (Authenticated)"**
3. You'll see:

```json
{
  "form_name": "support_request",
  "subject": "Help with integration",
  "message": "I need help setting up the Slack integration. The bot is not responding to mentions.",
  "context": "User is on Business plan, Slack workspace: acme-corp",
  "use_case": "slack_integration_support"
}
```

4. Click **"Send"**

**Response:**
```json
{
  "success": true,
  "status": "queued",
  "task_id": "celery-task-xyz-789"
}
```

**Difference from Webhook Intake:**
- Uses JWT authentication instead of intake token
- Automatically associates request with logged-in user
- Tracks form name for analytics
- No HMAC signature required (already authenticated)

---

### Request 3: Webhook Shim (Legacy)

⚠️ **Only use this for legacy systems that can't generate HMAC signatures.**

1. Click **"3. Webhook Shim (Legacy)"**
2. Send simple JSON without authentication headers
3. Server-side shim adds authentication automatically

**When to use:**
- Old monitoring systems
- Third-party tools without webhook signing
- Internal tools without HMAC support

**Security consideration**: This endpoint requires `INTAKE_TOKEN` environment variable on server. Less secure than main `/intake` endpoint.

---

## 📊 Step 5: Real-World Integration Examples

The collection includes 3 example integrations under the **"Examples"** folder.

### Example 1: HubSpot Form Webhook

```json
{
  "subject": "New lead from HubSpot",
  "body": "Company: Acme Corp\nContact: John Smith\nInterest: Enterprise plan",
  "from_email": "john.smith@acme.com",
  "source": "hubspot",
  "provider": "hubspot",
  "channel": "web_form",
  "provider_thread_url": "https://app.hubspot.com/contacts/123456/contact/987654",
  "context": {
    "company_size": "50-200",
    "industry": "SaaS",
    "lifecycle_stage": "opportunity"
  }
}
```

**Use case**: HubSpot form submission webhook → InboxIQ triages → Auto-assigns to sales rep.

---

### Example 2: Intercom Chat Message

```json
{
  "subject": "Chat: Billing question",
  "body": "Hi, I was charged twice this month for my subscription. Can you help?",
  "from_email": "sarah@startup.io",
  "source": "intercom",
  "provider": "intercom",
  "channel": "chat",
  "provider_thread_url": "https://app.intercom.com/a/apps/abc123/inbox/inbox/conversation/456789"
}
```

**Use case**: Intercom chat → InboxIQ triages → Routes to billing team → Creates ticket.

---

### Example 3: Slack Mention

```json
{
  "subject": "Slack: @support request",
  "body": "@support The API is returning 500 errors for /api/v1/tickets endpoint. Started 10 minutes ago.",
  "from_email": "mike@engineering.com",
  "source": "slack",
  "provider": "slack",
  "channel": "slack",
  "provider_thread_url": "https://acme-corp.slack.com/archives/C123456/p1234567890",
  "context": {
    "channel_name": "#support",
    "user_id": "U123456",
    "team_id": "T123456"
  }
}
```

**Use case**: Slack @mention → InboxIQ triages → Routes to engineering → Creates urgent ticket.

---

## 🔧 Payload Field Reference

### Required Fields

| Field | Description | Example |
|-------|-------------|---------|
| `subject` or `title` | Request title | `"Support Request"` |
| `body` or `message` | Request content | `"Customer needs help with..."` |

### Optional Fields

| Field | Description | Example |
|-------|-------------|---------|
| `from_email` or `sender` | Sender email | `"customer@example.com"` |
| `source` | Where it came from | `"website_form"`, `"hubspot"`, `"slack"` |
| `provider` | Integration name | `"intercom"`, `"salesforce"`, `"custom"` |
| `channel` | Communication channel | `"email"`, `"chat"`, `"voice"`, `"social"` |
| `provider_thread_url` | Link to original message | `"https://app.intercom.com/..."` |
| `message_id` | External message ID | `"intercom_msg_123456"` |
| `received_at` | ISO timestamp | `"2026-02-08T10:30:00Z"` |
| `use_case` | Business context | `"billing_support"`, `"sales_inquiry"` |
| `context` | Additional metadata | `{"plan": "enterprise", "region": "us-west"}` |

---

## 🔐 Authentication & Security

### HMAC Signature Generation

The intake endpoint uses HMAC-SHA256 to verify requests haven't been tampered with.

**Algorithm:**
```
message = timestamp + "." + request_body
signature = HMAC-SHA256(intake_token, message)
```

**Headers required:**
- `X-Intake-Token`: Your intake token
- `X-Timestamp`: Unix timestamp (must be within 5 minutes)
- `X-Signature`: HMAC signature (hex-encoded)

**Example in Python:**
```python
import hmac
import hashlib
import time
import json

intake_token = "ik_live_abc123..."
timestamp = str(int(time.time()))
body = json.dumps({"subject": "Test", "body": "Hello"})

message = f"{timestamp}.{body}"
signature = hmac.new(
    intake_token.encode(),
    message.encode(),
    hashlib.sha256
).hexdigest()

headers = {
    "X-Intake-Token": intake_token,
    "X-Timestamp": timestamp,
    "X-Signature": signature,
    "Content-Type": "application/json"
}
```

**Example in JavaScript (Node.js):**
```javascript
const crypto = require('crypto');

const intakeToken = 'ik_live_abc123...';
const timestamp = Math.floor(Date.now() / 1000).toString();
const body = JSON.stringify({subject: 'Test', body: 'Hello'});

const message = `${timestamp}.${body}`;
const signature = crypto
  .createHmac('sha256', intakeToken)
  .update(message)
  .digest('hex');

const headers = {
  'X-Intake-Token': intakeToken,
  'X-Timestamp': timestamp,
  'X-Signature': signature,
  'Content-Type': 'application/json'
};
```

---

## 🛡️ Rate Limiting & IP Whitelisting

### Rate Limits

- **120 requests per 60 seconds** per intake token
- Per-token rate limiting (not per IP)
- `429 Too Many Requests` response when exceeded

**Example response:**
```json
{
  "error": "rate_limited"
}
```

**Best practice**: Implement exponential backoff when rate limited.

### IP Whitelisting (Optional)

Restrict intake tokens to specific IPs for extra security.

1. Go to Admin Dashboard → API/Webhooks
2. Edit intake token
3. Add allowed IPs (comma-separated):
   ```
   203.0.113.1, 203.0.113.2, 192.0.2.0/24
   ```

If configured, requests from other IPs get:
```json
{
  "error": "forbidden",
  "message": "ip_not_allowed"
}
```

---

## 📈 What Happens After Intake?

### Processing Pipeline

1. **Webhook received** → Returns `202 Accepted` with `task_id`
2. **Queued to Celery** → Task: `inboxiq.process_incoming_email`
3. **DSPy Triage** → AI determines category, urgency, intent
4. **Smart Routing** → Routes to correct team/queue
5. **Ticket Creation** → Creates ticket in InboxIQ
6. **Notifications** → Emails/Slack to assigned team
7. **Auto-Response** → Optional auto-reply to customer

**Timeline:**
- Intake: < 100ms
- Triage + Routing: 2-5 seconds
- Ticket Created: 5-10 seconds
- Team Notified: 10-15 seconds

### Checking Task Status

Use the `task_id` from response to check status:

```bash
# Query Celery task status
celery -A src.celery_inboxiq inspect query_task <task_id>
```

Or check in Admin Dashboard → Tasks → Task ID.

---

## 🚨 Troubleshooting

### Error: 401 Unauthorized - Missing token/signature/timestamp

**Cause**: Missing required authentication headers.

**Fix**: Ensure all 3 headers are present:
```
X-Intake-Token: ik_live_abc123...
X-Timestamp: 1707394800
X-Signature: a1b2c3d4e5f6...
```

---

### Error: 401 Unauthorized - Invalid signature

**Cause**: HMAC signature doesn't match server calculation.

**Common causes:**
- Wrong intake token
- Body content changed after signing
- Timestamp format incorrect
- Character encoding issues

**Fix:**
1. Verify intake token is correct
2. Don't modify request body after signing
3. Use Unix timestamp (integer seconds, not milliseconds)
4. Use UTF-8 encoding

**Debug signature generation:**
```javascript
// Log each step
console.log('Token:', intakeToken);
console.log('Timestamp:', timestamp);
console.log('Body:', body);
console.log('Message:', message);
console.log('Signature:', signature);
```

---

### Error: 401 Unauthorized - Stale timestamp

**Cause**: Timestamp is more than 5 minutes old.

**Fix**: Use current timestamp. Common issue when replaying old requests.

```javascript
// Always generate fresh timestamp
const timestamp = Math.floor(Date.now() / 1000).toString();
```

---

### Error: 401 Unauthorized - Token expired

**Cause**: Intake token has passed its `expires_at` date.

**Fix**: Generate new token from Admin Dashboard.

---

### Error: 403 Forbidden - IP not allowed

**Cause**: Request came from IP not in whitelist.

**Fix**:
1. Check your current IP: `curl ifconfig.me`
2. Add IP to token whitelist in Admin Dashboard
3. Or remove IP restrictions if not needed

---

### Error: 403 Forbidden - Plan required

**Cause**: API/webhooks require Business plan or active trial.

**Response:**
```json
{
  "error": "plan_required",
  "message": "API/webhooks require Business plan or active trial. Contact sales to upgrade."
}
```

**Fix**: Upgrade to Business plan or start trial.

---

### Error: 429 Rate Limited

**Cause**: Exceeded 120 requests per 60 seconds.

**Fix**: Implement exponential backoff:
```javascript
async function sendWithRetry(url, data, maxRetries = 3) {
  for (let i = 0; i < maxRetries; i++) {
    const response = await fetch(url, {method: 'POST', body: data});

    if (response.status !== 429) {
      return response;
    }

    // Exponential backoff: 1s, 2s, 4s
    const delay = Math.pow(2, i) * 1000;
    await new Promise(resolve => setTimeout(resolve, delay));
  }
  throw new Error('Rate limited after retries');
}
```

---

### Error: 400 Validation Error - Body/message required

**Cause**: Missing required `body` or `message` field.

**Fix**: Include at least one of these fields:
```json
{
  "subject": "Test",
  "body": "This field is required"
}
```

---

### Error: 502 Forward Failed (Shim only)

**Cause**: Shim endpoint can't reach main `/intake` endpoint.

**Fix**: Check server logs for network issues. Verify `INTAKE_URL` environment variable if using custom URL.

---

## 🔄 Common Integration Patterns

### Pattern 1: HubSpot Workflow Webhook

**HubSpot Setup:**
1. Go to Workflows → Create workflow
2. Add action: "Send webhook"
3. URL: `https://hook.kalevent.com/api/v1/intake`
4. Method: `POST`
5. Add headers (use custom code action):
   ```javascript
   const token = 'ik_live_abc123...';
   const timestamp = Math.floor(Date.now() / 1000).toString();
   const body = JSON.stringify({
     subject: `New lead: ${contact.firstname} ${contact.lastname}`,
     body: `Company: ${contact.company}\nEmail: ${contact.email}\nPhone: ${contact.phone}`,
     from_email: contact.email,
     source: 'hubspot',
     provider: 'hubspot',
     channel: 'crm'
   });

   const crypto = require('crypto');
   const signature = crypto.createHmac('sha256', token).update(`${timestamp}.${body}`).digest('hex');

   // Return headers
   return {
     'X-Intake-Token': token,
     'X-Timestamp': timestamp,
     'X-Signature': signature
   };
   ```

---

### Pattern 2: Zapier Integration

**Zapier Setup:**
1. Create Zap: Trigger (any app) → Action (Webhooks by Zapier)
2. Action: **POST**
3. URL: `https://hook.kalevent.com/api/v1/intake/shim`
4. Data:
   ```
   subject: New Contact from [App Name]
   body: {{trigger.description}}
   source: zapier
   provider: {{trigger.app_name}}
   ```

**Why use `/shim`**: Zapier can't easily generate HMAC signatures, so use the shim endpoint.

---

### Pattern 3: Intercom Webhook

**Intercom Setup:**
1. Settings → Developers → Webhooks
2. Create webhook for "conversation.user.created"
3. URL: `https://hook.kalevent.com/api/v1/intake`
4. Add custom middleware to generate HMAC (or use `/shim`)

**Payload transformation** (use middleware):
```javascript
// Intercom webhook payload
{
  "type": "notification_event",
  "data": {
    "item": {
      "id": "123456",
      "conversation_message": {
        "body": "Customer message here"
      },
      "user": {
        "email": "customer@example.com"
      }
    }
  }
}

// Transform to InboxIQ format
{
  "subject": "Chat: New conversation",
  "body": data.item.conversation_message.body,
  "from_email": data.item.user.email,
  "source": "intercom",
  "provider": "intercom",
  "channel": "chat",
  "provider_thread_url": `https://app.intercom.com/a/apps/${app_id}/inbox/inbox/conversation/${data.item.id}`
}
```

---

### Pattern 4: Slack Bot Integration

**Slack Bot Code** (Python example):
```python
from slack_bolt import App
import requests
import hmac
import hashlib
import time
import json

app = App(token=os.environ["SLACK_BOT_TOKEN"])

@app.event("app_mention")
def handle_mention(event, say):
    # Extract message details
    user = event.get("user")
    text = event.get("text")
    channel = event.get("channel")
    ts = event.get("ts")

    # Get user info
    user_info = app.client.users_info(user=user)
    user_email = user_info["user"]["profile"].get("email", "unknown@slack.local")

    # Prepare payload
    payload = {
        "subject": "Slack: @support request",
        "body": text,
        "from_email": user_email,
        "source": "slack",
        "provider": "slack",
        "channel": "slack",
        "provider_thread_url": f"https://your-workspace.slack.com/archives/{channel}/p{ts.replace('.', '')}",
        "context": {
            "channel": channel,
            "user_id": user,
            "thread_ts": ts
        }
    }

    # Generate HMAC signature
    intake_token = os.environ["INTAKE_TOKEN"]
    timestamp = str(int(time.time()))
    body = json.dumps(payload)
    message = f"{timestamp}.{body}"
    signature = hmac.new(
        intake_token.encode(),
        message.encode(),
        hashlib.sha256
    ).hexdigest()

    # Send to InboxIQ
    response = requests.post(
        "https://hook.kalevent.com/api/v1/intake",
        json=payload,
        headers={
            "X-Intake-Token": intake_token,
            "X-Timestamp": timestamp,
            "X-Signature": signature,
            "Content-Type": "application/json"
        }
    )

    if response.status_code == 202:
        say(f"✅ Request submitted! Task ID: {response.json()['task_id']}")
    else:
        say(f"❌ Failed to submit request: {response.text}")
```

---

## 📚 Related Documentation

- [Users Guide](users_guide.md)
- [Security & Auth](security_auth.md)
- [Service Integrations](service_integrations.md)
- [Channel Intake Guide](channel_intake_guide.md)

---

## 🤝 Need Help?

If you encounter issues:

1. Check the **Troubleshooting** section above
2. Verify intake token is valid and not expired
3. Test signature generation matches server-side
4. Check server logs for detailed error messages
5. Contact the development team

---

**Ready to integrate?** Import the Postman collection and test your first webhook! 🚀
