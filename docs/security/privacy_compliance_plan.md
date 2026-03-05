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

### 1.1 AI processing opt-out toggle

**Why:** The single biggest trust concern for privacy-sensitive prospects.
**What:** Add `ai_processing_enabled` boolean to `AccountFeatureFlags` model.
Gate all OpenAI calls behind this flag — if disabled, tickets are received/managed but
no AI inference is run and no email content is sent to OpenAI.
**Where:** `src/models/core.py` (AccountFeatureFlags), `src/settings/routes.py` (toggle UI),
`src/dspy/triage.py`, `src/ai/client.py`
**Migration:** `flask db migrate -m "Add ai_processing_enabled to AccountFeatureFlags"`

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

| Policy | Owner |
|---|---|
| Information Security Policy | Founder |
| Access Control Policy | Founder |
| Incident Response Plan | Founder |
| Business Continuity / DR Plan | Founder |
| Vulnerability Management Policy | Founder |
| Vendor Risk Management Policy | Founder |
| Acceptable Use Policy | Founder |

Most compliance tools provide policy templates. Fill in, review, version-control in `docs/security/policies/`.

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

SOC 2 CC6 (Logical Access) requires evidence of who accessed what.
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
