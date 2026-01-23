# InboxIQ Trial-to-Paid Billing Implementation Plan

Goal: proactively convert trial users to paid (Pro/Business) with reliable payments (Stripe primary, secondary PSP fallback), overdue handling, and lean APIs in `src/api/v1`.

## Scope & Phases
1) **Data + config**
   - Add billing entities: `CustomerBillingProfile`, `PaymentMethod`, `Subscription`, `Invoice`, `ChargeAttempt`, `PaymentProviderAccount` (provider cfg/status).
   - Trial tracking: trial start/end, grace window, conversion state, and plan selection (Pro/Business).
2) **Provider integrations**
   - Stripe as primary (payment intent + webhooks).
   - Secondary PSP (suggest Adyen/Braintree) with parallel abstractions and webhooks.
   - Provider-agnostic service layer to minimize code paths.
3) **Trials → conversion**
   - Pre-expiry nudges, forced card capture before expiry, automatic subscription activation, and invoice/receipt emailing.
4) **Overdue + retries**
   - Smart retry schedule, provider fallback, dunning emails, and workspace access changes.
5) **APIs (lean)**
   - REST endpoints in `src/api/v1` for payment methods, subscription activation, invoices, and webhooks.
6) **Jobs + notifications**
   - Scheduled workers for trial checks, retries, and email sends.
7) **Audit/logging**
   - Idempotency keys, event logs, and admin visibility.

## Data Model (proposed tables/fields)
- `payment_provider_accounts`: provider (`stripe|secondary`), credentials, status, livemode flag.
- `customer_billing_profiles`: account_id, email, billing_name, address, tax_id, trial_start/end, plan_choice (pro|business), trial_status (active|ending_soon|ended), subscription_status (none|active|past_due|canceled), default_payment_method_id.
- `payment_methods`: profile_id, provider, provider_pm_id, brand, last4, exp_month/year, status (active|failed|detached).
- `subscriptions`: profile_id, plan_id, provider, provider_sub_id, current_period_end, status (trialing|active|past_due|canceled), cancel_at/end_of_period flags.
- `invoices`: profile_id, subscription_id, amount_cents, currency, status (draft|open|paid|void|uncollectible), due_at, provider_invoice_id, pdf_url, last_attempt_at.
- `charge_attempts`: invoice_id, provider, provider_payment_intent_id, status (requires_action|processing|succeeded|failed), failure_reason, attempt_number, used_fallback (bool).
- `plans`: code (pro|business), price_cents, currency, ai_actions, seats, metadata.

## Service Layer (keep slim)
- `payments/providers/base.py`: interface for create_payment_method_from_token, attach_to_customer, create_subscription, create_invoice, pay_invoice, handle_webhook, detach_method.
- `payments/providers/stripe.py` and `payments/providers/secondary.py`: concrete implementations; map provider events to internal statuses.
- `payments/providers/barclay.py`: Hosted Payment Page client for Barclays as secondary PSP; builds redirect URL + HMAC signature and normalizes callbacks.
- `payments/billing_service.py`: orchestrates flows (trial expiry checks, charge retries, fallback provider).
- `payments/email_service.py`: sends invoice/receipt/dunning via existing mailer.

## API Endpoints (in `src/api/v1`)
- `POST /billing/payment-methods`: tokenized card → create PM with primary provider, attach to profile. Body: token, name, address, plan_choice. Returns pm summary + next action (if SCA).
- `POST /billing/activate`: requires PM; starts subscription on chosen plan, sets provider subscription/payment intent, returns invoice/receipt info.
- `GET /billing/invoices`: list invoices for the account/profile.
- `GET /billing/invoices/<id>`: fetch invoice detail + provider PDF URL if available.
- `POST /billing/webhooks/stripe`: Stripe webhook handler (idempotent).
- `POST /billing/webhooks/secondary`: secondary PSP webhook handler.
- `POST /billing/barclay/initiate`: build hosted payment payload/redirect (no network until SOAP wired).
- `POST /billing/barclay/callback`: normalize hosted payment callback payload.
- `POST /billing/retry/<invoice_id>` (optional): manual retry (auth users only).
- `POST /billing/cancel`: schedule cancel at period end.

### Request/Response essentials
- Accept `Idempotency-Key` header on mutation endpoints; return `idempotency_key` echoed.
- On 3DS/SCA, surface `client_secret` + `requires_action=true` and expected next step.

## Trial Conversion Flow
1) **T-3 days** (configurable): email reminder to add card + pick plan; include CTA deep-link to `/billing`.
2) **T-1 day**: stronger reminder; if no PM on file, require card before further usage.
3) **T day (expiry)**: auto-create subscription & invoice with plan selection; attempt charge on primary provider.
4) **If success**: mark subscription active, send receipt, unlock usage caps.
5) **If requires_action**: send SCA email with action link; hold workspace in limited mode.
6) **If failure**: queue retry (see schedule) and attempt fallback provider with stored tokenizable data or prompt user to re-enter.

## Retry & Dunning Strategy
- Retry schedule: 0h, 12h, 48h, 96h. Mark `past_due` after first failure.
- Each retry: attempt primary → if failed and secondary available, attempt secondary.
- After final failure: set invoice `uncollectible`, lock workspace features, send pay-link + invoice PDF.
- Dunning emails at each failure with actionable pay link.

## Invoicing & Emails
- Generate invoice records on subscription start and each renewal.
- Email templates: trial ending (T-3, T-1), payment succeeded (receipt), payment failed, action required (SCA), overdue, converted to paid.
- Include invoice PDF link (from provider) when available; otherwise render HTML/PDF via wkhtmltopdf/weasyprint if needed.

## Webhooks (idempotent)
- Stripe events: `payment_intent.succeeded/processing/failed`, `invoice.payment_succeeded/failed`, `customer.subscription.updated/deleted`, `payment_method.detached`.
- Secondary PSP: map equivalent success/failure/require_action events.
- Store `event_id`, dedupe via table; process in transaction; update `charge_attempts`, `invoices`, `subscriptions`.

## Jobs / Schedules
- `trial_checker`: daily; finds trials near expiry and sends reminders; on expiry, auto-start subscription/invoice and attempt charge.
- `retry_processor`: hourly; picks past_due invoices with next_attempt_at <= now; runs retry + fallback.
- `dunning_sender`: daily; sends overdue communications.
- `cleanup`: detach stale payment methods flagged failed.

## Access & Feature Gates
- Require authenticated account for billing endpoints.
- On `past_due` / `uncollectible`: reduce AI actions/seats; show banner prompting payment.
- On `requires_action`: gated until user completes SCA.

## Security & Compliance
- Use provider tokens only; no raw PAN storage. Ensure TLS, HSTS already in place.
- Limit logging of PII; redact tokens in logs.
- Use provider test keys in non-prod; env-based selection via `PAYMENT_PROVIDER=primary|secondary`.
- Add `Idempotency-Key` support to handlers and DB-backed idempotency table if needed.

## Implementation Steps (lean)
1) Migrations for billing tables + indexes (account_id/profile_id foreign keys).
2) Provider client wiring (Stripe secret/public keys, secondary PSP keys) via env/config.
3) Build provider interface + Stripe/secondary adapters.
4) Implement billing service orchestration (trial expiry, subscription start, retry logic).
5) Implement API endpoints + schemas (pydantic/dataclasses) under `src/api/v1/billing.py` (or folder).
6) Add webhooks with signature verification and idempotency storage.
7) Background jobs (Celery/cron) for trial checker, retries, dunning emails.
8) Email templates for receipts/invoices/reminders; hook to mailer.
9) UI: payment capture form (custom) and status banners (outside scope here but required for flow).
10) Monitoring: structured logs, metrics for success/failure rates.

## Risks / Mitigations
- Provider downtime: retry + fallback PSP; exponential backoff; circuit-breaker.
- SCA failures: clear messaging, links with client_secret; store status `requires_action`.
- Race conditions on retries/webhooks: enforce idempotency keys + DB locks on invoice row updates.
- Compliance: keep PCI scope minimal (tokenization only); avoid storing card data.
