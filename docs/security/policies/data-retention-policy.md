# InboxIQ — Data Retention Policy

**Owner:** Kalevent Ltd  
**Last reviewed:** May 2026  
**Next review:** May 2027  
**Version:** 1.0

---

## Purpose

This policy defines how long InboxIQ retains different categories of data, and how data is deleted when retention periods expire or deletion is requested. Maps to SOC2 CC6.5 (data disposal).

---

## Data Retention Schedule

| Data Category | Retention Period | Deletion Method | Trigger |
|---|---|---|---|
| Email / ticket content (body, subject, attachments) | Duration of active account | Hard delete from PostgreSQL | Account cancellation or customer deletion request |
| Ticket metadata (timestamps, labels, status) | Duration of active account | Hard delete from PostgreSQL | Account cancellation or customer deletion request |
| User account records | Duration of active account | Hard delete from PostgreSQL | Account cancellation |
| Billing records (invoices, subscription history) | 7 years | Retained for legal/tax compliance | Not deleted until legal retention period expires |
| Audit logs (in-app user activity) | 14 days | Automated purge via Celery task (daily at 02:30 UTC) | Automatic — Celery Beat schedule |
| Application logs (server logs) | 30 days | Automatic rotation via AWS CloudWatch | Automatic |
| OAuth tokens (Gmail / Outlook) | Until revoked or account deleted | Hard delete from PostgreSQL | Account cancellation, disconnection, or user request |
| S3 uploaded files (attachments, compliance reports) | Duration of account + 30 days grace | Hard delete via S3 lifecycle policy | Account cancellation |
| Compliance evidence reports (SOC2 JSON) | 3 years | Manual deletion from S3 | Annual review |
| Lead / prospect data | 12 months from last activity | Hard delete from PostgreSQL | Automated or on request |
| DSPy training artefacts | Until superseded by new model version | Overwritten on retrain | Automated |

---

## Deletion on Account Cancellation

When a customer cancels their InboxIQ account:

1. All email content, tickets, and user data are hard-deleted from PostgreSQL within **30 days**
2. OAuth connections are revoked and tokens deleted immediately
3. S3 files are deleted within **30 days** via lifecycle policy
4. Billing records are retained for 7 years (UK tax law requirement)
5. Customer receives written confirmation of deletion on request

---

## Customer Deletion Requests (Right to Erasure)

Under UK GDPR Article 17, customers may request deletion of their personal data. InboxIQ will:

1. Acknowledge the request within **72 hours**
2. Complete the deletion within **30 days**
3. Confirm completion in writing

Requests are sent to: **privacy@kalevent.com**

---

## Automated Enforcement

The following retention periods are enforced automatically in code:

| Rule | Implementation |
|---|---|
| Audit log purge (14 days) | Celery Beat task `inboxiq.purge_old_audit_logs` — runs daily at 02:30 UTC |
| Application log rotation (30 days) | AWS CloudWatch Logs retention policy |

---

## Backups

PostgreSQL backups (via AWS RDS automated snapshots) are retained for **7 days**. Snapshots older than 7 days are deleted automatically by RDS.

---

## Annual Review

This policy is reviewed annually. The data retention schedule is checked against current legal requirements (UK GDPR, Companies Act) and updated if necessary.
