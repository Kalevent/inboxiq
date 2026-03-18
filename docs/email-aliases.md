# Kalevent Email Aliases

All aliases are Google Workspace Groups on `kalevent.com`. No extra seat cost — each routes to the account owner's inbox unless otherwise noted.

| Alias | Purpose | Used in |
|---|---|---|
| `accounting@kalevent.com` | Invoices, receipts, transaction forwards | Automation Studio — Transactions rule |
| `hello@kalevent.com` | General inbound enquiries, trial onboarding emails, outbound sender for self-hosted interest | Trial onboarding sequence, security.html |
| `legal@kalevent.com` | Contracts, compliance notices, cease & desist | terms_of_service.html |
| `noreply@kalevent.com` | Automated outbound sender (password resets, system notifications) | `MAIL_FROM` in config.py |
| `privacy@kalevent.com` | GDPR requests, data deletion, DPA requests | privacy_policy.html, security.html |
| `security@kalevent.com` | Vulnerability reports, breach notices, crash alerts | security.html, `CRASH_EMAIL_TO` in ConfigMap |

## Access policy

| Alias | Google Group type | Who is a member |
|---|---|---|
| `accounting@` | Mailing | Account owner |
| `hello@` | Mailing (external can post) | Account owner |
| `legal@` | Mailing + Security (restricted) | Account owner only |
| `noreply@` | Mailing (external can post) | Account owner |
| `privacy@` | Mailing + Security (restricted) | Account owner only |
| `security@` | Mailing + Security (restricted) | Account owner only |

## App config

- `MAIL_FROM` → `noreply@kalevent.com` (set in `src/config.py`)
- `CRASH_EMAIL_TO` → `security@kalevent.com` (set in `src/k8s/inboxiq-config.yaml`)
- `ACCOUNTING_EMAIL` → `accounting@kalevent.com` (set in `src/k8s/inboxiq-config.yaml`)
- `SECURITY_ALERT_EMAIL` → `security@kalevent.com` (set in `src/k8s/inboxiq-config.yaml`)
- `TRIAL_ONBOARDING_FROM_EMAIL` → `hello@kalevent.com` (set in `src/trial/onboarding.py`)
