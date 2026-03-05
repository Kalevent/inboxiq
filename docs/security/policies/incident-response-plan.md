# InboxIQ — Security Incident Response Plan

**Owner:** Kalevent Ltd
**Last reviewed:** March 2026
**Next review:** March 2027
**Version:** 1.0

---

## Scope

Any event that compromises or threatens the confidentiality, integrity, or availability of customer data or InboxIQ systems.

---

## Severity Classification

| Level | Definition | Response time |
| --- | --- | --- |
| **P1 Critical** | Customer data exposed or systems unavailable | Immediate (within 1 hour) |
| **P2 High** | Vulnerability confirmed, not yet exploited | Within 24 hours |
| **P3 Low** | Anomaly detected, no confirmed impact | Within 5 business days |

---

## Step 1 — Identify

**Detection sources:**

- GitHub secret scanning alerts
- AWS GuardDuty findings
- Arize Phoenix anomaly traces
- Dependabot vulnerability alerts
- Customer or third-party reports to support@kalevent.com or in app report

**On detection:** Classify severity using the table above and immediately notify the incident lead.

---

## Step 2 — Contain

**P1 Critical:**

- Revoke affected credentials immediately (AWS IAM, API keys, database passwords)
- Isolate affected Kubernetes pods: `kubectl cordon <node>` or scale deployment to 0
- Block offending IPs at the AWS load balancer / security group
- Do not wipe affected systems before evidence is preserved

**P2 High:**

- Patch and redeploy within 24 hours
- Rotate any credentials that could have been exposed

**All levels:**

- Preserve logs — CloudTrail, VPC Flow Logs, application logs in Arize Phoenix
- Do not discuss incident details in public channels (Slack, GitHub issues, email)

---

## Step 3 — Investigate

- Review CloudTrail, VPC Flow Logs, application logs
- Determine:
  - What data was accessed or exfiltrated?
  - Which accounts or users are affected?
  - How long was the exposure window?
  - What was the entry vector?
- Document findings in a private incident ticket

---

## Step 4 — Notify

**Customer notification (GDPR Article 33/34):**

- If EU personal data is involved: notify affected customers within **72 hours** of discovery
- Notification from: security@kalevent.com
- Notification must include: nature of breach, data affected, likely consequences, measures taken

**Regulatory notification:**

- If the breach affects >250 individuals or is likely to result in high risk: file with the UK ICO at [ico.org.uk/make-a-complaint](https://ico.org.uk/make-a-complaint) within 72 hours

**Internal:**

- Notify all employees within 1 hour of P1 classification

---

## Step 5 — Remediate

- Deploy the fix; confirm no lateral movement or residual attacker access
- Rotate all credentials that could have been in scope
- Update Dependabot / dependency pins if a vulnerable library was the entry vector
- Re-enable any isolated systems only after confirming they are clean

---

## Step 6 — Post-Incident Review

Within 5 business days of resolution:

1. Write a blameless post-mortem
2. Document: timeline, root cause, customer impact, fix applied, controls added
3. Store in `docs/security/post-mortems/YYYY-MM-DD-<slug>.md`
4. Update this plan and any relevant policies based on findings
5. If P1: share a summary with affected customers (no internal detail, just what happened and what was fixed)

---

## Contacts

| Role | Contact |
| --- | --- |
| Incident lead | Founder — Kofi Afor |
| Customer notification | security@kalevent.com |
| GDPR authority (UK ICO) | [ico.org.uk/make-a-complaint](https://ico.org.uk/make-a-complaint) |
| AWS support | AWS console → Support → Create case |

---

*This document is internal. Version-controlled in git. Review annually or after any P1 incident.*
