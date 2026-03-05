# InboxIQ Privacy & Compliance Plan

**Owner:** Kalevent Ltd
**Last updated:** March 2026
**Status:** In progress

---

## Context

InboxIQ processes customers' support email on their behalf. Prospect concerns about data safety
are legitimate and predictable — this plan maps the remediation steps needed to go from
"we take this seriously" to "here is the evidence."

The priority order mirrors the customer base:

1. **B2B SaaS** — SOC 2 is the gating requirement
2. **E-commerce** — GDPR + CCPA parity (EU / US)
3. **Healthcare** — HIPAA deferred until FHIR integration is complete

---

## Current State (March 2026)

| Control | Status | Notes |
|---|---|---|
| Encryption in transit (TLS) | ✅ Active | HTTPS everywhere, Kubernetes Ingress |
| Encryption at rest | ✅ Active | AWS RDS AES-256, S3 SSE |
| Customer data isolation | ✅ Active | `account_id` scoping on every query |
| File upload isolation | ✅ Active | `files.kalevent.com`, `Content-Disposition: attachment` |
| RBAC (role-based access) | ✅ Active | Owner / Admin / Agent / Viewer / Billing |
| Passkey + TOTP 2FA | ✅ Active | Settings → Security |
| Self-hosted observability | ✅ Active | Arize Phoenix in cluster — traces never leave infra |
| Security page (`/security`) | ✅ Live | `kalevent.com/security` |
| Privacy Policy | ✅ Live | `kalevent.com/privacy` |
| Terms of Service | ✅ Live | `kalevent.com/terms` |
| SOC 2 Type II | 🟡 In Progress | Pursuing 2026 |
| GDPR DPA template | 🟡 Draft needed | Email `privacy@kalevent.com` in the interim |
| BYOL (Bring Your Own LLM) | ✅ Active | Settings → AI Provider; routes all AI to customer's endpoint |
| Self-hosted / on-premise licensing | 🟡 Planned | Phase 6 — customer deploys InboxIQ, data never leaves their infra |
| Right to erasure (GDPR) | 🟡 To build | Hard-delete endpoint needed |
| Data retention policy | 🟡 To define | |
| Penetration test | 🔴 Not done | Required for SOC 2 |
| HIPAA | 🔴 Deferred | Requires FHIR integration first |

---

## Phase 1 — Immediate (this month)

### 1.1 ✅ BYOL — Bring Your Own LLM (complete)

**Why:** The single biggest trust concern for privacy-sensitive prospects is that their email
content is sent to a third-party AI service (OpenAI) they did not choose.
**What was built:** Per-account LLM routing. Each account can supply their own API key and
endpoint in Settings → AI Provider. When configured, all AI inference for that account is
routed to their endpoint — InboxIQ's OpenAI key is never used for that account.

Deployment model:
- **Cloud (default):** InboxIQ's OpenAI key — no configuration required
- **BYOL:** Customer's own API key → OpenAI, Anthropic, Ollama, or any OpenAI-compatible endpoint

**Where it lives:**
- `src/models/core.py` — `AccountLLMConfig` model + `ALLOWED_LLM_PROVIDERS` registry
- `src/ai/client.py` — `resolve_llm_config()`, `call_byol()`, updated `invoke_llm()`
- `src/dspy/config.py` — `configure_dspy(byol_config=…)` for DSPy pipeline
- `src/api/v1/inboxiq.py` — `GET/POST/DELETE /api/v1/llm-config`, `POST /api/v1/llm-config/test`
- `src/templates/settings/index.html` — AI Provider tab with provider/model/key form

**Privacy story on `/security`:** Updated — links directly to Settings → AI Provider.

### 1.2 GDPR Data Processing Agreement (DPA)

**Why:** Required to sign enterprise contracts with EU customers.
**What:** Use the [Bonterms DPA template](https://bonterms.com) as a base. Fill in:
- Controller: the customer
- Processor: Kalevent Ltd
- Sub-processors: OpenAI (API), Amazon Web Services
- Subject matter: email support management
- Retention: see Section 1.4

Review with a lawyer before sending to customers.
**Delivery:** Sign and email on request to `privacy@kalevent.com`. Upload to `/security` once finalised.

### 1.3 Update Privacy Policy

Current policy at `/privacy` is a generic placeholder. Rewrite to include:
- What data is collected (email content, metadata, account info)
- How it is processed (AI triage, lead scoring)
- Sub-processors (OpenAI, AWS)
- Retention periods (see 1.4)
- GDPR rights (access, erasure, portability, objection)
- CCPA rights (California users)
- Contact: `privacy@kalevent.com`

### 1.4 Define and publish data retention policy

Draft decisions:

| Data type | Retention | Action on account deletion |
|---|---|---|
| Email content (ticket body) | 2 years from receipt | Hard delete |
| Ticket metadata | 3 years | Hard delete |
| Lead records | 2 years from last activity | Hard delete |
| Audit / event logs | 1 year | Hard delete |
| Billing records | 7 years (legal requirement) | Anonymise only |

### 1.6 Enable Dependabot and GitHub secret scanning

**Why:** Free, immediate, and satisfies the SOC 2 Vulnerability Management control out of the box.
Vanta and Drata will detect it automatically as evidence.

**What to enable (all free, all in GitHub Settings → Security):**

| Feature | Where | Cost | What it does |
|---|---|---|---|
| Dependabot alerts | Settings → Security → Dependabot | Free | Alerts on vulnerable dependencies |
| Dependabot security updates | Settings → Security → Dependabot | Free | Auto-creates PRs to fix vulnerabilities |
| Dependabot version updates | `.github/dependabot.yml` | Free | Keeps packages current |
| Secret scanning alerts | Settings → Security → Secret scanning | Free | Alerts if API keys are committed to the repo |
| Secret scanning push protection | Settings → Security → Secret scanning | Free | Blocks commits containing secrets before they land |
| CodeQL code scanning | Settings → Security → Code scanning | ~~$49/user/month~~ — **skip** | Static analysis — requires GitHub Advanced Security; not worth it at this stage |

**Setup:** Create `.github/dependabot.yml` in the repo root:

```yaml
version: 2
updates:
  - package-ecosystem: "pip"
    directory: "/"
    schedule:
      interval: "weekly"
    open-pull-requests-limit: 5
    labels:
      - "dependencies"
      - "security"
```

**Process:** Review Dependabot PRs weekly. Merge security updates immediately;
batch version updates into a monthly maintenance window.

**Status:** 🔴 Not yet enabled

---

### 1.5 Add Security footer link to homepage

Manually add to `src/templates/index.html` footer (lines ~1385–1389).
**Do not use the Edit tool on Tailwind class lines** — edit raw in your editor.

```html
<span class="hidden md:inline text-slate-600">•</span>
<a href="{{ url_for('security') }}" class="hover:text-white">Security</a>
```
Insert after the Contact link and before Cookies.

---

## Phase 2 — SOC 2 Readiness (months 1–6)

### 2.1 Choose a compliance automation platform

Recommended: [Vanta](https://vanta.com) or [Drata](https://drata.com).
Both integrate with AWS, GitHub, and Slack to collect evidence automatically.
Budget: ~$15k–$25k/year for tooling + ~$15k–$30k for the audit firm.

Connect:
- AWS account (monitors EC2, RDS, S3 encryption, IAM)
- GitHub (monitors code review, branch protection, PR approvals)
- Slack (monitors user offboarding)
- Google Workspace / email (employee background checks, policies)

### 2.2 Write required policies

SOC 2 requires written policies. Minimum set:

| Policy | Owner | Status |
|---|---|---|
| Information Security Policy | Founder | 🔴 Draft needed |
| Access Control Policy | Founder | 🔴 Draft needed |
| Incident Response Plan | Founder | 🟡 Starter template below |
| Business Continuity / DR Plan | Founder | 🔴 Draft needed |
| Vulnerability Management Policy | Founder | 🟡 Dependabot satisfies this technically |
| Vendor Risk Management Policy | Founder | 🔴 Draft needed |
| Acceptable Use Policy | Founder | 🔴 Draft needed |

Most compliance tools provide policy templates. Fill in, review, version-control in `docs/security/policies/`.

#### Security Incident Response Plan (starter template)

> Copy this into `docs/security/policies/incident-response-plan.md`, fill in the blanks, and version it in git. Even this one-page version satisfies SOC 2 auditors and impresses enterprise security reviewers.

---

**InboxIQ — Security Incident Response Plan**
Owner: Kalevent Ltd | Reviewed: March 2026 | Next review: March 2027

**Scope:** Any event that compromises or threatens the confidentiality, integrity, or
availability of customer data or InboxIQ systems.

#### Step 1 — Identify

- Monitor: GitHub secret scanning alerts, AWS GuardDuty, Arize Phoenix anomaly traces, customer reports
- Classify severity:
  - **P1 Critical** — customer data exposed or systems unavailable
  - **P2 High** — vulnerability confirmed, not yet exploited
  - **P3 Low** — anomaly detected, no confirmed impact

#### Step 2 — Contain

- P1: Immediately revoke affected credentials, isolate affected pods (`kubectl cordon`), block offending IPs at the load balancer
- P2: Patch and redeploy within 24 hours
- Preserve logs — do not wipe affected systems before investigation

#### Step 3 — Investigate

- Review CloudTrail, VPC Flow Logs, application logs in Arize Phoenix
- Determine: what was accessed, by whom, for how long, what data was affected
- Document findings in a private incident ticket (not a public GitHub issue)

#### Step 4 — Notify

- **GDPR requirement:** If EU personal data is involved, notify affected customers within 72 hours of discovery
- Notification channel: email from `security@kalevent.com`
- If the breach affects >250 individuals, file with the relevant Data Protection Authority (UK ICO / EU lead SA)
- Internal: notify all employees within 1 hour of P1 classification

#### Step 5 — Remediate

- Deploy the fix; confirm no lateral movement or residual access
- Rotate all credentials that could have been exposed
- Update Dependabot / dependency pins if a vulnerable library was the vector

#### Step 6 — Post-incident review

- Within 5 business days: write a blameless post-mortem
- Document: timeline, root cause, customer impact, fix applied, controls added
- Store in `docs/security/post-mortems/YYYY-MM-DD-<slug>.md`
- Use findings to update this plan and relevant policies

#### Contacts

| Role | Contact |
| --- | --- |
| Incident lead | Founder |
| Customer notification | security@kalevent.com |
| GDPR authority (UK) | [ico.org.uk/make-a-complaint](https://ico.org.uk/make-a-complaint) |
| AWS support | AWS console → Support |

### 2.3 Implement right to erasure (GDPR Article 17)

Add `DELETE /api/v1/account` endpoint that hard-deletes:
- All `Ticket` + `TicketEmbedding` rows for the account
- All `Lead`, `LeadFunnelStage`, `LeadEngagementEvent`, `LeadAttribution` rows
- All `EmailCampaign`, `EmailOutreach`, `NurtureEmailSend` rows
- All `BlogPost`, `KBArticle`, `GeneratedContent` rows
- All `User` rows (after confirming no shared resources)
- The `Account` row last

Soft-delete (`deleted = True`) is not sufficient for GDPR erasure — must be hard delete
or irreversible anonymisation.
Add an admin UI confirmation modal to trigger this.

### 2.4 Implement audit logging

**⏸ Deferred — do not build until triggered.**

Build this when the first enterprise prospect asks: *"Can you show me who accessed my data?"*
That question is the signal it earns its engineering cost. Without it, there are no paying customers
generating meaningful logs and no compliance driver (SOC 2 is deferred).

**Trigger checklist — build when ANY of these are true:**

- [ ] A prospect explicitly asks for access logs during a sales call
- [ ] SOC 2 audit window begins (CC6 Logical Access requires it)
- [ ] First enterprise contract >£10k ACV is being negotiated

**When the time comes, implement:**

Add an `AuditLog` model:

```python
class AuditLog(db.Model):
    id           = UUID primary key
    account_id   = FK accounts
    user_id      = FK users (nullable for system actions)
    action       = String(100)   # "ticket.viewed", "user.role_changed"
    resource_id  = String(64)
    resource_type= String(50)
    ip_address   = String(45)
    user_agent   = String(255)
    created_at   = DateTime UTC
```

Log: login, logout, role changes, data export, account deletion, API key creation/deletion.
Surface in: Settings → Security → View audit log (link already exists in the UI).

### 2.5 Penetration test

Engage a qualified penetration testing firm (e.g. Cobalt, Synack, Bishop Fox).
SOC 2 auditors expect an annual pentest.
Scope: web application + API (`kalevent.com`, `api.kalevent.com`).
Budget: ~$5k–$15k.
Remediate all critical/high findings before the SOC 2 audit window begins.

### 2.6 AWS infrastructure hardening

Review with [AWS Security Hub](https://aws.amazon.com/security-hub/):
- Enable CloudTrail (all regions)
- Enable GuardDuty
- Enable AWS Config
- Ensure RDS is not publicly accessible
- Ensure S3 buckets block public access
- Enable VPC Flow Logs
- Rotate IAM keys — no long-lived access keys for production

---

## Phase 3 — SOC 2 Audit (months 6–12)

1. Select audit firm (A-LIGN, Schellman, Johanson Group are common for early-stage SaaS)
2. Define observation window (minimum 3 months for Type II)
3. Provide evidence collection via compliance platform
4. Remediate auditor findings
5. Receive SOC 2 Type II report
6. Publish "SOC 2 Type II certified" on `/security` page
7. Make report available to customers under NDA on request

---

## Phase 4 — GDPR Full Compliance (parallel to Phase 2–3)

- [ ] Appoint a Data Protection contact (can be the founder initially)
- [ ] Complete Record of Processing Activities (ROPA) — list every data flow
- [ ] Cookie consent banner (if using analytics on `kalevent.com`)
- [ ] Data subject request workflow (access, erasure, portability within 30 days)
- [ ] Implement right to data portability — `GET /api/v1/account/export` returns JSON dump
- [ ] Review all third-party integrations for GDPR sub-processor agreements:
  - OpenAI — DPA available at openai.com/policies
  - AWS — DPA available via AWS console
  - Any future CRM / email provider

---

## Phase 6 — Self-hosted / On-premise Licensing (post-SOC 2)

### Overview

A self-hosted deployment means the customer runs InboxIQ on their own infrastructure
(cloud account, data centre, or air-gapped environment) and pays Kalevent a license fee.
No email content, ticket data, or AI inference results ever leaves their infrastructure.
Kalevent receives only license validation pings.

This is the strongest possible privacy posture for enterprise customers with strict data
residency requirements (finance, government, regulated industries).

**Deployment tiers:**

| Tier | Who runs infra | AI inference | Data leaves customer infra? |
|---|---|---|---|
| Cloud SaaS (current) | Kalevent | InboxIQ's OpenAI key | Yes — to AWS us-west-2 + OpenAI |
| BYOL (complete) | Kalevent | Customer's API key | Email content to customer's chosen LLM endpoint |
| Self-hosted | Customer | Customer's LLM (BYOL or local Ollama) | No |
| Air-gapped | Customer (no outbound) | Local Ollama only | No |

**When to build:** After SOC 2 audit is complete and there is at least one enterprise prospect
blocked on data residency. Do not build speculatively — the app is ~80% ready already.

---

### 6.1 Resources required

#### 6.1.1 Docker image distribution

**Effort:** 1–2 days

- Publish `ghcr.io/kalevent/inboxiq:<version>` via GitHub Actions on release tags
- Images are public (no secrets baked in — all config via env vars)
- License key required to start the server (see 6.1.3)
- The existing `src/Dockerfile.inboxiq` is the base; build context = project root

#### 6.1.2 Helm chart and Docker Compose

**Effort:** 3–5 days

Provide two deployment options:

**Docker Compose** (single-server / small teams):
- Services: `app`, `postgres`, `redis`, `worker` (Celery)
- Optional: `ollama` service for local AI inference
- `.env.example` with all required variables documented

**Helm chart** (Kubernetes / enterprise):
- Chart structure mirrors existing `src/k8s/` manifests
- Values: `image.tag`, `replicaCount`, `resources`, `ingress.host`, `env.*`
- Sub-charts or dependencies: PostgreSQL (Bitnami), Redis (Bitnami)
- Publish to a public Helm repo or as a tarball on GitHub Releases

#### 6.1.3 License key validation

**Effort:** 2–3 days

- Add `INBOXIQ_LICENSE_KEY` env var, validated on app startup in `src/config.py`
- License key encodes: `account_slug | expiry_date | max_seats | plan_tier`
- Signed with an Ed25519 private key held by Kalevent; public key baked into the image
- Validation: decode → verify signature → check expiry → check seats
- On failure: app refuses to start with a clear error message and an email to contact
- Online validation optional: ping `license.kalevent.com/verify` if outbound allowed;
  skip gracefully for air-gapped installs (offline-first signed token is sufficient)

```python
# src/license.py (new file, ~60 lines)
# validate_license(key: str) -> LicenseClaims
# called from src/app.py create_app() before registering blueprints
```

#### 6.1.4 Remove hard-coded kalevent.com references

**Effort:** 1–2 days

Self-hosted operators use their own domain. Audit and parameterise:

| Hard-coded reference | Current location | Fix |
|---|---|---|
| `files.kalevent.com` (upload CDN) | `src/uploads.py`, `UPLOADS_HOST` env var | Already env-var driven — document it |
| `kalevent.com` in email sender | `src/notifications/emails.py` | Add `MAIL_FROM_DOMAIN` env var |
| `kalevent.com` links in email templates | `src/templates/emails/` | Replace with `{{ config.APP_BASE_URL }}` |
| `support@kalevent.com` in error pages | Various templates | Add `SUPPORT_EMAIL` env var |
| Arize Phoenix collector URL | `src/monitoring/observability.py` | Already env-var driven |

No code changes required today — this is a pre-release checklist item.

#### 6.1.5 Operator documentation

**Effort:** 2 days

Create `docs/self-hosted/` with:
- `README.md` — overview, prerequisites, quickstart
- `configuration.md` — full env var reference table
- `upgrade.md` — how to pull new image versions, run migrations (`flask db upgrade`)
- `air-gapped.md` — disable all outbound calls, use Ollama for AI inference
- `license.md` — how to obtain, renew, and apply a license key

---

### 6.2 Total effort estimate

| Item | Effort |
|---|---|
| Docker image distribution | 1–2 days |
| Docker Compose + Helm chart | 3–5 days |
| License key validation | 2–3 days |
| Remove hard-coded domain references | 1–2 days |
| Operator documentation | 2 days |
| **Total** | **~2 weeks (one engineer)** |

---

### 6.3 What is already done

The app is ~80% ready for self-hosting today:
- Fully containerised (`src/Dockerfile.inboxiq`)
- All secrets via env vars (`src/config.py`)
- Kubernetes manifests exist (`src/k8s/`)
- BYOL routes all AI inference through customer's own key — no forced dependency on Kalevent's OpenAI
- Self-hosted observability (Arize Phoenix) already deployed and documented
- RBAC, encryption, account isolation all production-grade

---

## Phase 5 — HIPAA (deferred)

**Do not accept healthcare customers until this phase is complete.**

Prerequisites:
1. FHIR API integration is live
2. Signed BAA with OpenAI (requires OpenAI Enterprise plan)
3. Signed BAA with AWS (available via AWS console)
4. HIPAA-compliant audit logging (7-year retention)
5. PHI encryption at the field level (not just disk encryption)
6. Employee HIPAA training records
7. Annual risk assessment

---

## Messaging for Prospects (use verbatim)

### Short version (email / chat)
> Your email data is stored in AWS (us-west-2), encrypted at rest and in transit,
> and logically isolated — no other customer can access your data. For AI features,
> email content is sent to OpenAI's API under their DPA, which prohibits training
> on API inputs. We are pursuing SOC 2 Type II. AI processing can be disabled
> per account. Full details: kalevent.com/security

### For enterprise security questionnaires
> - **Data location:** AWS us-west-2
> - **Encryption at rest:** AES-256 (AWS RDS + S3)
> - **Encryption in transit:** TLS 1.2+
> - **Multi-tenancy isolation:** Logical (account_id scoping on all queries)
> - **AI sub-processor:** OpenAI API (DPA in place, no training on inputs)
> - **Observability:** Self-hosted (no traces leave our infrastructure)
> - **Certifications:** SOC 2 Type II in progress (expected 2026)
> - **GDPR:** DPA available on request — privacy@kalevent.com
> - **HIPAA:** Not currently supported
> - **Penetration testing:** Planned as part of SOC 2 programme
> - **Security contact:** security@kalevent.com

---

## Key contacts

All issues — security vulnerabilities, privacy/GDPR requests, data deletion, DPA requests, billing — go to:

| Channel | Use |
|---|---|
| **support@kalevent.com** | Security reports (subject: "Security vulnerability"), DPA requests, data deletion, general privacy questions |
| **In-app feedback form** | Dashboard → Feedback tab — bugs, billing, feature requests |

---

*This document is internal. Do not publish publicly.*
