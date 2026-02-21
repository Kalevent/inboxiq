# Channel Intake Guide (Hotline, Outlook, Facebook)

Unified support intake means InboxIQ accepts support requests from any channel—email, IVR/phone, chat, forms, social messages, and CRM events—and normalizes them into one triage pipeline with consistent dedupe, routing, and SLA handling.
This guide shows how to connect those channels using the Intake API or the shim—no app changes required.

## Principles (must-follow)
- Use a stable `message_id` + `provider` per platform event to dedupe (e.g., call SID, FB message ID).
- If your gateway does not emit an ID, generate one yourself (UUID or hash of timestamp + source + sender) and reuse it on retries for the same event; do not increment per retry.
- Put the contact handle in `from_email` for cross-channel linking: email, `tel:+1...`, or `social:fb:<page-id>/<user-id>`.
- Prefer `POST /api/v1/intake` with HMAC headers; fall back to `/api/v1/intake/shim` if the source cannot sign requests.
- Automation: set your provider’s webhook to `https://hook.kalevent.com/api/v1/intake/shim` (no headers) or `…/intake` with HMAC headers. Every inbound event will then create/update tickets automatically—no manual posts.

## Outlook (email)
1) In Settings → Integrations, click Outlook/365 and complete OAuth.
2) New emails flow into triage automatically; no webhook needed.
3) Routing, dedupe, and `action_required` are applied out of the box.

## Hotline / Call Events
- Endpoint: `/api/v1/intake` (or `/api/v1/intake/shim` if you cannot sign).
- Required fields:
  - `source`: `"hotline"`
  - `provider`: your telephony vendor (e.g., `"twilio"`, `"aws_connect"`)
  - `message_id`: call SID or unique call record ID
  - `from_email`: `tel:+15551234567`
  - `provider_thread_url`: link to the call/recording in your provider console (helps agents jump to the raw call)
  - `body`: include IVR path + caller input + transcript/notes (this is what InboxIQ reads to classify/reroute)
- Example via shim (no HMAC on caller side):
```bash
curl -X POST https://hook.kalevent.com/api/v1/intake/shim \
  -H "Content-Type: application/json" \
  -d '{
    "source": "hotline",
    "provider": "tesco_mobile",
    "message_id": "CA123456789",
    "from_email": "tel:+15551234567",
    "provider_thread_url": "https://console.tescomobile.example/threads/123",
    "body": "IVR path: 1 > 3. Caller said: billing issue, double charged."
  }'
```
- Expected result: ticket with `action_required` + due time; duplicates suppressed by `message_id` + `provider`.

### Twilio IVR (recording + transcription)
Use Twilio to record the call, generate a transcript, and forward it into InboxIQ via the Twilio webhooks.

- Voice webhook (TwiML): `https://hook.kalevent.com/api/v1/twilio/voice`
- Recording callback: `https://hook.kalevent.com/api/v1/twilio/recording`
- Transcription callback: `https://hook.kalevent.com/api/v1/twilio/transcription`

TwiML served by `/api/v1/twilio/voice`:
```xml
<Response>
  <Say>Thanks. Please describe your issue after the beep.</Say>
  <Record
    maxLength="120"
    transcribe="true"
    recordingStatusCallback="https://hook.kalevent.com/api/v1/twilio/recording"
    transcriptionCallback="https://hook.kalevent.com/api/v1/twilio/transcription"
  />
</Response>
```

Security (recommended):
- Set `TWILIO_AUTH_TOKEN` so we verify `X-Twilio-Signature` on Twilio webhooks.

## Facebook / Social Messages
- Endpoint: `/api/v1/intake` (or shim).
- Required fields:
  - `source`: `"facebook"` (or `"social"`)
  - `provider`: `"facebook"`
  - `message_id`: platform message/comment ID
  - `from_email`: `social:fb:<page-id>/<user-id>`
  - `provider_thread_url`: permalink to the message/comment
  - `body`: message text and optional metadata (post title, thread snippet)
- Example via shim:
```bash
curl -X POST https://hook.kalevent.com/api/v1/intake/shim \
  -H "Content-Type: application/json" \
  -d '{
    "source": "facebook",
    "provider": "facebook",
    "message_id": "m_mid.$abcd",
    "from_email": "social:fb:1234567890/99887766",
    "provider_thread_url": "https://facebook.com/.../posts/1122334455?comment_id=99887766",
    "body": "Customer: I was charged twice for the pro plan. Please help."
  }'
```

## WhatsApp (e.g., Tesco Mobile or other gateways)
- Endpoint: `/api/v1/intake` (or shim).
- Required fields:
  - `source`: `"whatsapp"` (or `"social"`)
  - `provider`: your current gateway (e.g., `"tesco_mobile"`, `"twilio"`, `"meta_cloud_api"`). If you change gateways later, update this value; dedupe keys remain `provider` + `message_id`.
  - `message_id`: WhatsApp message ID/SID (unique per message)
  - `from_email`: `tel:+<phone>` for identity linking (e.g., `tel:+15551234567`)
  - `provider_thread_url`: optional deep link to the convo in your gateway console
  - `body`: message text (include media captions/URLs if relevant)
- Example via shim:
```bash
curl -X POST https://hook.kalevent.com/api/v1/intake/shim \
  -H "Content-Type: application/json" \
  -d '{
    "source": "whatsapp",
    "provider": "tesco_mobile",
    "message_id": "wamid.HBgMNTU1MTIzNDU2Nw==",
    "from_email": "tel:+15551234567",
    "provider_thread_url": "https://console.tescomobile.example/threads/123",
    "body": "I was billed twice for Pro. Please check."
  }'
```

## HMAC option (preferred)
If the source can sign requests, call `/api/v1/intake` directly with:
- `X-Intake-Token`: your token
- `X-Timestamp`: Unix epoch seconds
- `X-Signature`: `HMAC_SHA256(token, "<timestamp>.<body>")`
- `Content-Type: application/json`

## Troubleshooting
- 401/403: missing or invalid token/signature, stale timestamp, or disallowed IP.
- 429: per-token rate limit exceeded (120 reqs/min).
- Duplicates: check that `message_id` + `provider` are stable per event.
