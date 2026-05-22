# InboxIQ — Vendor Risk Assessments

**Owner:** Kalevent Ltd  
**Last reviewed:** May 2026  
**Next review:** May 2027  
**Version:** 1.0

---

## Purpose

This document records the risk assessment of third-party vendors who process or have access to InboxIQ customer data. Each vendor is assessed against SOC2 Trust Service Criteria (CC6.1 — logical access, CC9.2 — vendor management).

---

## Vendor Register

### 1. Amazon Web Services (AWS)

| Field | Detail |
|---|---|
| **Service used** | EC2/EKS (compute), RDS PostgreSQL (database), S3 (file storage), CloudFront (CDN), ALB (load balancer) |
| **Data processed** | All customer data — emails, tickets, user accounts |
| **Data location** | us-west-2 (Oregon, USA) |
| **Certifications** | SOC2 Type II, ISO 27001, ISO 27017, ISO 27018, PCI DSS Level 1 |
| **Cert link** | https://aws.amazon.com/compliance/soc-faqs/ |
| **Risk level** | Low — industry-leading certifications, shared responsibility model documented |
| **Controls in place** | Encryption at rest (RDS, S3), encryption in transit (TLS 1.2+), IAM MFA enforced, CloudTrail enabled, no public S3 access |

---

### 2. Stripe

| Field | Detail |
|---|---|
| **Service used** | Payment processing, subscription billing, webhook events |
| **Data processed** | Payment card data (never touches InboxIQ servers — Stripe-hosted), billing emails |
| **Data location** | USA / EU |
| **Certifications** | SOC2 Type II, PCI DSS Level 1 Service Provider, ISO 27001 |
| **Cert link** | https://stripe.com/docs/security |
| **Risk level** | Low — PCI DSS Level 1 means InboxIQ is out of PCI scope for card data |
| **Controls in place** | Webhook signature verification enabled (STRIPE_WEBHOOK_SECRET configured), no raw card data stored |

---

### 3. OpenAI

| Field | Detail |
|---|---|
| **Service used** | GPT-4 API for email triage, draft reply generation, DSPy-optimised prompts |
| **Data processed** | Email subject lines and bodies submitted for triage/drafting |
| **Data location** | USA |
| **Certifications** | SOC2 Type II |
| **Cert link** | https://trust.openai.com |
| **Risk level** | Medium — customer email content is sent to OpenAI API; mitigated by OpenAI's zero data retention API policy (data not used for training when using the API) |
| **Controls in place** | API key stored in Kubernetes secret (not in code), zero-retention API tier used |
| **Residual risk** | Customers are informed in privacy policy that AI processing is used |

---

### 4. Google (OAuth + Workspace)

| Field | Detail |
|---|---|
| **Service used** | Gmail OAuth (inbox connection), Google Calendar OAuth, Google Workspace (internal email/docs) |
| **Data processed** | OAuth tokens for Gmail access; internal team communications |
| **Data location** | USA / EU |
| **Certifications** | SOC2 Type II, ISO 27001, ISO 27017, ISO 27018 |
| **Cert link** | https://workspace.google.com/security/ |
| **Risk level** | Low |
| **Controls in place** | OAuth tokens stored encrypted in DB, minimum required scopes only, token refresh handled server-side |

---

### 5. Microsoft (OAuth)

| Field | Detail |
|---|---|
| **Service used** | Outlook OAuth (inbox connection), Microsoft Calendar OAuth |
| **Data processed** | OAuth tokens for Outlook access |
| **Data location** | USA / EU |
| **Certifications** | SOC2 Type II, ISO 27001, CSA STAR |
| **Cert link** | https://servicetrust.microsoft.com |
| **Risk level** | Low |
| **Controls in place** | OAuth tokens stored encrypted in DB, minimum required scopes only |

---

### 6. Redis (self-hosted via AWS EKS)

| Field | Detail |
|---|---|
| **Service used** | Celery task broker and result backend |
| **Data processed** | Task payloads (transient — no persistent customer data) |
| **Data location** | us-west-2 (same EKS cluster) |
| **Risk level** | Low — self-hosted, not a third party |
| **Controls in place** | ClusterIP only (not exposed externally), in-cluster network only |

---

## Review Process

Vendor certifications are reviewed annually. If a vendor experiences a publicly disclosed breach or loses a certification, an ad-hoc review is triggered immediately.

**Next scheduled review:** May 2027
