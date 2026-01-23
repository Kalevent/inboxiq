
# InboxIQ Slim V1 Launch Plan

**Value prop:** For small support teams, we solve overwhelming inbox chaos by automatically triaging emails into structured, prioritized tickets — so nothing is missed and response time drops by 80%.

## Naming/packaging note
- Align project naming with the Docker container path (`/usr/src`); use this as the canonical app root in docs and deployment notes. Keep code changes minimal until the auth/users-first slice is stable.

## Multi-tenancy from day one
- Model: `accounts` own `users`; `users` belong to exactly one `account`. Track `seats_limit` and `seats_used` on the account; enforce on user creation.
- Auth: login is scoped to an account; tokens carry `account_id`. All queries must filter by `account_id`.
- Provisioning: one account owner creates the account; invites/adds additional users until seats are exhausted. Seat expansion via plan change is deferred but keep the field.
- Isolation: no cross-account data sharing; every table introduced in v1 must carry `account_id` (tickets, attachments, etc.).
- Default roles (v1): `owner`, `member` (optional `admin` later). Keep permissions simple until later phases.


## Database parity (local ↔ production)
- Same Postgres engine/version locally as AWS RDS (no SQLite fallback); use a local Postgres container matching the RDS version/params.
- One `.env` template for DB URLs; local uses `localhost`/Docker bridge, staging/prod use RDS endpoints. Never point local to prod; use sanitized staging snapshots if needed.

### Migration discipline
- Golden rule: migrations live in-repo; run per-environment against that environment’s DB.
- Local: `flask db migrate` (generate) then `flask db upgrade` (apply) against local Postgres.
- Staging/production: never hand-edit DB; do not tie migrations to image build. CI/CD or a Helm/K8s job runs `flask db upgrade` against that environment’s `DATABASE_URL` on deploy.

### Seeded data discipline (plans/pricing)
- Define an idempotent seed module (Click command) that upserts required plans/prices by stable slug/ID; no manual DB edits.
- Local: run seeds after `flask db upgrade` to mirror prod catalog.
- CI/CD: after migrations, run the seed command in each environment (staging/prod) so plans are always present; do not exec into pods.
- Health check: add a startup check that fails fast if required plan slugs are missing to avoid runtime crashes.

## Core Focus
- One job: turn every incoming email into a structured, prioritized ticket automatically.
- Aha moment: user connects inbox → sees first 5 emails auto-triaged into tickets with priority + category + sentiment in under 60 seconds.
- Keep the existing agents blueprint (`app/api/v1/agents.py`) and `kalevent_mcp` surface; add new triage endpoints there.

## Ship Only This
- Integrations: Gmail + Outlook OAuth only (custom IMAP later).
- AI pipeline: classify intent (billing/bug/refund/general), sentiment, priority (P0–P2), extract IDs (order/customer), write ticket to a simple `Tickets` table with status `New`.
- UI: minimal setup screen to connect inbox; queue showing tickets (subject, category, priority, sentiment, link to original email). Manual override to reassign category/priority.
- Ops: daily summary email/Slack digest **after** the core works; skip dashboards, analytics, notifications, customization, multi-tenant roles for now.

## Cut/Defer
- Multi-inbox, advanced routing, SLA rules, analytics dashboards, themes/custom categories, bots/auto-replies, API access, on-prem, compliance packages. Keep name/brand/domain; don’t restart unless code blocks you.

## Success Metrics
- Time to first triaged ticket < 2 minutes from signup.
- ≥90% of inbound emails become tickets; <1% missed.
- Manual correction rate on category/priority <15% after day one.
- Response-time proxy: high-priority emails surfaced within 5 minutes.

## 2-Week Implementation Path
- Day 1–2: Wire setup flow; Gmail/Outlook connect; seed dummy inbox for demos.
- Day 3–5: Build triage worker: pull email → classify/extract → create ticket → mark priority/sentiment; log decisions.
- Day 6–7: Ticket list UI + manual override; link back to source email.
- Day 8–10: Reliability passes: retries, rate limits, idempotency on message-id, basic alert on failures.
- Day 11–12: Onboarding polish: empty-state, first-run demo, “triaged 5 emails” banner.
- Day 13–14: Smoke tests with 5 pilot users; measure metrics; fix biggest misses.

## Startup Execution (DRIs & checkpoints)
- Single success metric: time from “Connect inbox” click to 5 triaged tickets; target <2 minutes. Always keep a demo path live.
- DRIs (assign names/dates):
  - OAuth + provider hooks (Gmail/Outlook)
  - Triage worker (classification/extraction, idempotency, logging)
  - Ticket UI (setup screen + queue + overrides)
  - Reliability/alerts (retries, rate limits, dead-letter, monitoring)
  - Pilot success (user recruitment, sessions, feedback loop)
- Operating rules: build → ship → measure daily; defer anything not on “Ship Only This”; keep infra lean using `kalevent_mcp` and `app/api/v1/agents.py` surfaces.
