# External Forms

Route HTML form submissions from your website into InboxIQ triage. Each submission is processed by the AI triage agent and becomes a ticket, just like an inbound email.

## How it works

1. A visitor fills in your contact or support form and clicks Submit.
2. Your server receives the POST and forwards it to the InboxIQ Intake API.
3. InboxIQ creates a ticket and routes it to the right team.

> **Why server-side?** Your `client_secret` must never appear in browser-visible HTML. Your server acts as a thin proxy — it accepts the raw form POST and calls InboxIQ with your credentials attached.

## Prerequisites

- External Forms access approved in **Settings → Developer** for your registered app.
- A `client_id` and `client_secret` from that app (scope: `intake:write`).

## Step 1 — HTML form

Add a standard HTML form to your page. The `action` points to your own server endpoint.

```html
<form method="POST" action="/contact/submit">
  <input   type="text"  name="name"    placeholder="Your name"     required />
  <input   type="email" name="email"   placeholder="Email address" required />
  <textarea             name="message" placeholder="How can we help?" required></textarea>
  <button  type="submit">Send message</button>
</form>
```

## Step 2 — Server handler

Your handler receives the form data and forwards it to InboxIQ.

**Python / Flask:**

```python
import os, requests
from flask import request, redirect

CLIENT_ID     = os.environ["INBOXIQ_CLIENT_ID"]
CLIENT_SECRET = os.environ["INBOXIQ_CLIENT_SECRET"]

@app.route("/contact/submit", methods=["POST"])
def contact_submit():
    name    = request.form.get("name", "")
    email   = request.form.get("email", "")
    message = request.form.get("message", "")

    requests.post(
        "https://kalevent.com/api/v1/intake",
        auth=(CLIENT_ID, CLIENT_SECRET),
        json={
            "subject":    f"Contact form: {name}",
            "body":       message,
            "source":     "form",
            "from_email": email,
        },
        timeout=5,
    )
    return redirect("/contact/thank-you")
```

**Node.js / Express:**

```js
const fetch = require('node-fetch');
const { CLIENT_ID, CLIENT_SECRET } = process.env;

app.post('/contact/submit', async (req, res) => {
  const { name, email, message } = req.body;
  const auth = Buffer.from(`${CLIENT_ID}:${CLIENT_SECRET}`).toString('base64');

  await fetch('https://kalevent.com/api/v1/intake', {
    method: 'POST',
    headers: { 'Authorization': `Basic ${auth}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({
      subject:    `Contact form: ${name}`,
      body:       message,
      source:     'form',
      from_email: email,
    }),
  });
  res.redirect('/contact/thank-you');
});
```

Always load credentials from environment variables — never hardcode them in source files.

## Passing extra context

Add a `context` object to send metadata that helps with triage routing:

```json
{
  "subject":    "Billing question",
  "body":       "I was charged twice in April.",
  "source":     "form",
  "from_email": "customer@example.com",
  "context": {
    "form_name": "billing_support",
    "plan":      "pro",
    "page":      "https://yoursite.com/billing"
  }
}
```

## Webhook (optional)

If you configured a webhook URL on your app, InboxIQ posts a `form.submitted` event to it whenever a form submission creates a ticket. Use **Send test event** in Settings → Developer to verify delivery.

## External Forms vs Intake API

| | External Forms | Intake API |
|---|---|---|
| Who submits | A visitor, via a browser form | Your backend code, programmatically |
| Triggered by | A human clicking Submit | An automated event (payment, alert, CRM) |
| Use case | Contact page, support form | Billing failures, CRM escalations, system alerts |

Both products use the same `/api/v1/intake` endpoint — External Forms is the pattern for human-initiated form submissions; Intake API is for backend-to-backend events.

## Related

- [Developer Guide](/docs/developer_guide) — app registration and credentials
- [Intake API reference](/docs/intake_api) — full field reference and response format
