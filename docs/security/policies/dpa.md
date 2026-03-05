# Data Processing Agreement

**Between:**

**Controller:** The customer entity that has accepted InboxIQ's Terms of Service ("Customer")

**Processor:** Kalevent Ltd, Company Number 15288801, Future Space UWE North Gate, Filton Road, Bristol BS34 8RB, United Kingdom ("Kalevent")

**Effective:** The date the Customer accepted the InboxIQ Terms of Service, or the date both parties sign this agreement, whichever is earlier.

---

## 1. Definitions

- **Personal Data** — any information relating to an identified or identifiable natural person, as defined in GDPR Article 4(1)
- **Processing** — any operation performed on Personal Data, as defined in GDPR Article 4(2)
- **GDPR** — the UK GDPR (as retained in UK law by the European Union (Withdrawal) Act 2018) and/or EU Regulation 2016/679, as applicable to the Customer
- **Sub-processor** — any third party engaged by Kalevent to process Personal Data on behalf of the Customer
- **Services** — the InboxIQ email support management platform provided by Kalevent

---

## 2. Subject Matter and Nature of Processing

Kalevent processes Personal Data solely to provide the Services to the Customer. Processing activities include:

- Receiving and storing inbound support emails on behalf of the Customer
- Applying AI-based triage and classification to email content
- Generating draft replies and suggested actions
- Lead identification and scoring from email senders
- Storing Customer team member account data (name, email, role)

---

## 3. Categories of Personal Data

| Category | Examples |
| --- | --- |
| Email sender data | Name, email address, IP address, organisation |
| Email content | Message body, subject line, attachments (text extracted) |
| Customer account data | Team member names, email addresses, roles |
| Usage metadata | Login timestamps, feature usage events |

---

## 4. Categories of Data Subjects

- The Customer's end customers and email correspondents
- The Customer's team members who use InboxIQ

---

## 5. Purpose and Legal Basis

Kalevent processes Personal Data for the sole purpose of providing the Services. The Customer is responsible for ensuring it has a lawful basis under GDPR Article 6 (and Article 9 where sensitive data is involved) for the processing it instructs Kalevent to perform.

---

## 6. Duration of Processing

Kalevent processes Personal Data for the duration of the Customer's active subscription. On account deletion or subscription termination:

| Data type | Action | Timeline |
| --- | --- | --- |
| Email content (ticket body) | Hard delete | Immediately on deletion request |
| Ticket metadata | Hard delete | Immediately on deletion request |
| Lead records | Hard delete | Immediately on deletion request |
| Audit / event logs | Hard delete | Within 30 days |
| Billing records | Anonymised | Retained 7 years (legal requirement) |

---

## 7. Kalevent's Obligations

Kalevent shall:

1. Process Personal Data only on documented instructions from the Customer (including these Terms), unless required by law
2. Ensure that persons authorised to process Personal Data are bound by confidentiality obligations
3. Implement appropriate technical and organisational security measures (see Section 9)
4. Not engage Sub-processors without prior written authorisation from the Customer (general authorisation is granted by accepting this DPA — see Section 10)
5. Assist the Customer with data subject rights requests (access, erasure, portability, restriction) within 30 days, using InboxIQ's built-in tools where available
6. Notify the Customer without undue delay — and in any event within 72 hours — of becoming aware of a Personal Data breach
7. Delete or return all Personal Data at the end of the Services, at the Customer's choice
8. Provide all information necessary to demonstrate compliance with GDPR Article 28 and allow for audits

---

## 8. Customer's Obligations

The Customer shall:

1. Ensure it has a lawful basis for the processing it instructs Kalevent to perform
2. Provide accurate and complete instructions for processing
3. Notify Kalevent promptly of any changes that affect the lawfulness of processing
4. Ensure data subjects have been provided with appropriate privacy notices

---

## 9. Security Measures

Kalevent maintains the following technical and organisational measures:

| Measure | Implementation |
| --- | --- |
| Encryption in transit | TLS 1.2+ on all connections |
| Encryption at rest | AES-256 (AWS RDS, S3) |
| Access control | RBAC — Owner / Admin / Agent / Viewer / Billing roles |
| Multi-factor authentication | Passkey + TOTP 2FA available to all users |
| Data isolation | Logical isolation — every query scoped by account_id |
| File upload security | User files served from isolated domain (files.kalevent.com) |
| Observability | Self-hosted (Arize Phoenix in-cluster — traces never leave infrastructure) |
| Vulnerability management | Dependabot automated dependency scanning |
| Incident response | Documented Incident Response Plan (see docs/security/policies/incident-response-plan.md) |

---

## 10. Sub-processors

The Customer grants general written authorisation to Kalevent to engage the following Sub-processors:

| Sub-processor | Location | Purpose | DPA |
| --- | --- | --- | --- |
| Amazon Web Services (AWS) | United States (us-west-2) | Infrastructure hosting, database, file storage | [aws.amazon.com/compliance/gdpr-center](https://aws.amazon.com/compliance/gdpr-center) |
| OpenAI, L.L.C. | United States | AI inference (email triage, draft replies) — only when Customer has not configured BYOL | [openai.com/policies/data-processing-addendum](https://openai.com/policies/data-processing-addendum) |

**BYOL note:** If the Customer configures their own LLM endpoint (Settings → AI Provider), email content is sent to their chosen provider instead of OpenAI. The Customer is responsible for their chosen provider's GDPR compliance in that case.

Kalevent will notify the Customer of any intended additions or replacements of Sub-processors at least 30 days in advance. The Customer may object in writing within that period.

---

## 11. International Transfers

AWS and OpenAI are based in the United States. Transfers are made on the basis of the EU Standard Contractual Clauses (Module 2: Controller to Processor) incorporated into each Sub-processor's DPA, or the UK International Data Transfer Agreement (IDTA) where applicable.

---

## 12. Data Subject Rights

The Customer may submit data subject requests to privacy@kalevent.com. Kalevent will:

- Acknowledge within 5 business days
- Complete erasure requests within 30 days using the account deletion endpoint or manual deletion
- Provide data exports on request in JSON format

---

## 13. Audit Rights

No more than once per year, the Customer may request a written summary of Kalevent's security controls and compliance posture. Kalevent will respond within 30 business days. On-site audits require 60 days' notice and are subject to confidentiality obligations.

---

## 14. Liability

Each party's liability under this DPA is subject to the limitations set out in the InboxIQ Terms of Service.

---

## 15. Governing Law

This DPA is governed by the laws of England and Wales. Disputes are subject to the exclusive jurisdiction of the courts of England and Wales.

---

## 16. Contact

All privacy, GDPR, and DPA enquiries:

**Email:** privacy@kalevent.com
**Post:** Kalevent Ltd, Future Space UWE North Gate, Filton Road, Bristol BS34 8RB, United Kingdom

---

*Draft — review with a solicitor before sending to customers. Version-controlled in git.*
*Based on Bonterms DPA v1.0 structure (bonterms.com).*
