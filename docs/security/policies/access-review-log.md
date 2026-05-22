# InboxIQ — Access Review Log

**Owner:** Kalevent Ltd  
**Last reviewed:** May 2026  
**Next review:** August 2026 (quarterly)  
**Version:** 1.0

---

## Purpose

This document records who has access to InboxIQ production systems and infrastructure. Access is reviewed quarterly to ensure only authorised individuals retain access. Maps to SOC2 CC6.2 (logical access reviews).

---

## Live Access Review Spreadsheet

The authoritative access review log is maintained in Google Shared Drive:

**[InboxIQ Access Review Log — Google Sheet](https://docs.google.com/spreadsheets/d/13nYSI22cRj9xOZ5ywoFwm0N9p9JRQFlIQJnLNPDx7Co/edit?usp=sharing)**

Location: `InboxIQ Security & Compliance` (Shared Drive — not personal Drive)

---

## Systems Covered

| System | Access Method |
|---|---|
| AWS (IAM) | IAM user + MFA + CLI |
| GitHub | GitHub account + 2FA |
| Stripe Dashboard | Stripe account + 2FA |
| Prod DB (RDS) | kubectl exec via EKS IRSA |
| Google Workspace | Google account + 2FA |
| OpenAI | API key stored in Kubernetes secret |
| Kubernetes (EKS) | aws eks + kubectl |

---

## Review Process

1. On the first working day of each quarter, open the Google Sheet
2. Verify each person listed still requires the access shown
3. Remove or downgrade access for anyone who has changed role or left
4. Update the "Last Reviewed" column with today's date
5. Update "Next review due" on the Review Schedule tab

**Review schedule:**

| Quarter | Due Date |
|---|---|
| Q3 2026 | 2026-08-22 |
| Q4 2026 | 2026-11-22 |
| Q1 2027 | 2027-02-22 |
| Q2 2027 | 2027-05-22 |

---

## Offboarding

When a team member leaves, their access must be revoked within **24 hours** across all systems listed above. The row is not deleted from the sheet — the access level is updated to "Revoked" and the date is recorded.
