# Connect Sources Plan (No RPA)

## Goal
Make Voice, Social, Email, Forms, Chat, and CRM connect as easily as email by providing a single, low‑friction “Connect Sources” flow that supports OAuth, webhook/API, and file import.

## Principles
- **One unified flow:** a single “Connect Sources” surface in the dashboard.
- **Native auth first:** OAuth where available; webhooks/API tokens where not.
- **No RPA:** avoid brittle UI automation in production.
- **Don’t hide existing integrations:** keep the existing webhook configuration in Settings; surface it as “advanced” or “view details.”

## User Journey (Ideal)
1. User starts in **Guided Setup (Onboarding)** → Step 1 becomes **Connect Sources** (not just email).
2. Sees **Connect Sources** cards by channel (Email, Voice, Social, Forms, Chat, CRM, API).
3. Each card offers:
   - Primary: OAuth or “Connect” (when supported).
   - Secondary: “Use Webhook” or “Manual Upload”.
4. After connecting, the card shows status + test button (like email).
5. Advanced configuration remains in **Settings → Integrations → Webhooks**, linked from each card as “Advanced.”

## Channel‑by‑Channel Connection Paths
### Email (already easy)
- OAuth: Gmail, Outlook
- Fallback: IMAP

### Voice / IVR
- Preferred: provider webhook (Twilio, Aircall, Dialpad, Five9)
- Fallback: CSV upload or email‑forwarded transcripts

### Social
- Preferred: platform APIs (Meta, X/Twitter, LinkedIn via approved apps)
- Fallback: social inbox platforms (Sprout, Hootsuite, Front) → webhook/API into InboxIQ

### Forms
- Preferred: webhook token endpoint (Typeform, Tally, Webflow, HubSpot Forms)
- Fallback: email‑to‑webhook transform or CSV import

### Chat
- Preferred: webhook integrations (Intercom, Zendesk, Drift, HubSpot, Freshchat)
- Fallback: export or transcript webhook via agent handoff

### CRM
- Preferred: native OAuth apps (Salesforce, HubSpot, Pipedrive)
- Fallback: webhook/event subscriptions or scheduled export

### API / Webhooks
- Preferred: Intake API token + webhook URL
- Fallback: CSV import

## UX Spec (Dashboard)
### New Panel: “Connect Sources”
- **Layout:** 2–3 columns of cards.
- **Card content:** channel name, brief description, primary CTA, secondary CTA, status, test button.
- **Primary CTAs:**
  - Email: “Connect Gmail”, “Connect Outlook”
  - Voice: “Connect IVR”
  - Social: “Connect Social”
  - Forms: “Connect Forms”
  - Chat: “Connect Chat”
  - CRM: “Connect CRM”
  - API: “Get Webhook URL”

### Advanced Links
- “Configure Webhooks” → Settings → Integrations → Webhooks (existing screen).
- “View Intake API Docs” → documentation.

## Guided Setup (Onboarding)
Replace **Step 1: Connect your support inbox** with **Step 1: Connect Sources**.
- Show Email + non‑email cards in onboarding.
- Keep it simple: 1–2 primary CTAs per card.
- Provide “Skip for now” and “Advanced” links to Settings → Webhooks.

## Settings Integration (Existing)
We already have **Settings → Integrations → Webhooks**. Keep it as the advanced configuration page and link to it from:
- Onboarding Step 1 (Connect Sources)
- Dashboard Connections (Connect Sources)

## Backend Changes
1. **Unified Intake Endpoint**
   - Single endpoint for non‑OAuth sources (already exists): `/api/v1/intake`
   - Support metadata fields: `channel`, `source`, `use_case`.

2. **Connection Registry**
   - Track connection types per account: email, voice, social, forms, chat, crm, api.
   - Store status and last test event.

3. **Test Event**
   - POST `/api/v1/inboxiq/connection-test` with channel + payload to validate setup.

4. **File Upload Path (Existing)**
   - Use the existing upload pipeline in `/Users/kofi/kalevent/src/uploads.py`.
   - All user files are stored/served via `UPLOADS_HOST=https://files.kalevent.com`.
   - Any CSV/transcript upload flows should route through this upload service.

## Settings Integration (Existing)
- Keep the **Settings → Integrations** page intact.
- Add a short note: “If you prefer advanced configuration, use Webhooks in Settings.”
- Link from dashboard cards to settings.

## Rollout Plan
1. **Phase 1:** UI-only “Connect Sources” panel + links to existing webhooks.
2. **Phase 2:** Add basic status + test events for non‑email channels.
3. **Phase 3:** Add OAuth connectors for top providers per channel.

## Success Metrics
- Time-to-first-connection (per channel).
- % of accounts with ≥2 channels connected.
- % of connections with successful test event.
- Reduction in manual triage time after multi‑channel intake.

## Open Questions
- Which providers to prioritize for Voice/Social/Chat/CRM?
- Do we need separate pricing tiers for multi‑channel connections?
- How should we display channel health on the dashboard?
