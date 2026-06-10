# InboxIQ — Code Removal Plan
**Date:** 2026-06-10
**Status:** Direction document — not yet an implementation plan

---

## Objective

Strip InboxIQ down to the minimum required to serve active customers while Ranger and CaseDesk are built. Remove dead weight in phases — each phase gated on a verifiable condition. End state: InboxIQ is archived, not deleted.

---

## Ground Rules

**Never remove code before confirming zero customer dependency.**
The validation query for each phase is listed explicitly. Run it. If it returns rows, the removal is blocked.

**Never delete the GitHub repository.**
CASA Tier 2 / SOC2 audit trail requires the full git history. Archive via GitHub Settings → Archive repository when all phases are complete.

**Removal order follows dependency, not preference.**
Internal-only modules can go first. Customer-facing modules wait until the absorbing product (Ranger or CaseDesk) has proven it works.

---

## What "Active Customer" Means

```sql
-- An active customer is any account with a paying or trialling subscription
SELECT id, email FROM accounts
JOIN customer_billing_profiles ON customer_billing_profiles.account_id = accounts.id
WHERE subscription_status IN ('active', 'trialing')
   OR trial_status = 'active';
```

Run this before every phase. If it returns zero rows, all phases are unblocked from a customer-impact perspective. If it returns rows, customer-facing phases require feature parity in Ranger/CaseDesk first.

---

## Phase 1 — Remove Internal-Only Modules (Safe Now)

These modules were never customer-facing. They were built for internal use only. Removing them reduces Celery task count, API surface, and compute cost without affecting any customer.

**Validation gate:** Confirm no account has used these features in the last 30 days.

```sql
-- Check for recent LinkedIn/YouTube/HeyGen/content activity
SELECT count(*) FROM ticket_events
WHERE event_type IN ('youtube_published', 'heygen_generated', 'linkedin_sent')
AND created_at > NOW() - INTERVAL '30 days';
```

**Modules to remove:**

| Module | Files | Reason |
| --- | --- | --- |
| YouTube cadence | `src/tasks/youtube.py`, `src/api/v1/youtube.py`, `src/mcp/youtube_mcp.py` | Internal only |
| HeyGen video | `src/tasks/onboarding_video.py`, `src/tasks/outreach_video.py`, `src/api/v1/heygen.py`, `src/mcp/heygen_mcp.py` | Internal only |
| LinkedIn cadence | `src/tasks/linkedin.py`, `src/api/v1/linkedin.py` | Internal only |
| Content generation | `src/content/`, `src/api/v1/content.py`, `src/api/v1/admin_content.py` | Internal only |
| Publishing / blog | `src/publishing/`, `src/blog/`, `src/api/v1/publishing.py`, `src/api/v1/blog.py` | Internal only |
| Social distribution | `src/marketing/social_distribution.py`, `src/mcp/social_distribution_mcp.py` | Internal only |
| Marketing analytics | `src/marketing/competitors.py`, `src/marketing/customer_insights.py`, `src/marketing/monthly_reports.py` | Internal only |
| Funnel analytics MCP | `src/mcp/funnel_analytics_mcp.py`, `src/api/v1/funnel_analytics.py` | Moving to Ranger |
| Attribution MCP | `src/mcp/attribution_mcp.py`, `src/api/v1/attribution.py` | Moving to Ranger |
| Engagement tracking MCP | `src/mcp/engagement_tracking_mcp.py` | Moving to Ranger |
| Stage orchestration MCP | `src/mcp/stage_orchestration_mcp.py` | Moving to Ranger |
| GCal MCP | `src/mcp/gcal_mcp.py`, `src/booking/` | Internal only, not customer-facing |
| Landing pages | `src/landing_pages/` | Not a live feature |
| A/B testing | `src/marketing/ab_testing.py` | Not a live feature |

**Cost impact:** Removing these Celery tasks eliminates ~8-10 beat schedule entries, reducing worker idle churn. Removing the MCP servers eliminates subprocess startup cost on every relevant Celery task.

**Celery beat schedule entries to remove from `celery_inboxiq.py`:**
- `youtube_cadence_*`
- `linkedin_*`
- `content_generation_*`
- `social_distribution_*`
- `funnel_orchestration_*`

---

## Phase 2 — Remove Outreach Modules (Gated on Ranger)

These modules are being ported to Ranger. They stay in InboxIQ until Ranger's versions are live and tested.

**Validation gate:** Ranger is processing outreach campaigns for at least 30 days without incident. Zero active campaigns running through InboxIQ.

```sql
-- Confirm no active InboxIQ campaigns before removal
SELECT count(*) FROM email_campaigns
WHERE status = 'active';
```

**Modules to remove:**

| Module | Files | Absorbed by |
| --- | --- | --- |
| Email outreach | `src/outreach/` | Ranger |
| Campaigns model | `src/models/campaigns.py` | Ranger |
| Lead discovery MCP | `src/mcp/lead_discovery_mcp.py` | Ranger |
| Enrichment MCP | `src/mcp/enrichment_v2_mcp.py` | Ranger |
| Search MCP | `src/mcp/search_mcp.py` | Ranger |
| Leads model + routes | `src/models/leads.py`, `src/leads/`, `src/api/v1/leads.py` | Ranger |
| DSPy email personalisation | `src/dspy/email_personalization.py` | Ranger |
| KB + retrieval | `src/kb/`, `src/retrieval/` | Ranger (repurposed) |
| Marketing ops UI | `src/marketing_ops/` | Ranger (new UI) |
| Funnel | `src/funnel/` | Ranger |
| Outreach API | `src/api/v1/outreach.py` | Ranger |

---

## Phase 3 — Remove Operational Modules (Gated on CaseDesk)

These modules are being absorbed by CaseDesk.

**Validation gate:** CaseDesk is live at kalevent.com and handling operational work for all active accounts.

**Modules to remove:**

| Module | Files | Absorbed by |
| --- | --- | --- |
| Tickets | `src/models/tickets.py`, `src/api/v1/inboxiq.py` (ticket logic) | CaseDesk |
| Automation rules | `src/automation/`, `src/api/v1/automation_rules.py` | CaseDesk |
| Developer portal | `src/developer/`, `src/api/v1/developer*.py` | CaseDesk |
| Developer webhooks | `src/tasks/developer_webhooks.py` | CaseDesk |
| Finance add-on | `src/tasks/finance_addon.py`, `src/api/v1/finance_webhook.py` | CaseDesk |
| Intake | `src/api/v1/intake.py` | CaseDesk |

---

## Phase 4 — Final Teardown (Gated on Zero Active Accounts)

**Validation gate:**

```sql
-- Must return zero rows before Phase 4 begins
SELECT id FROM accounts
JOIN customer_billing_profiles ON customer_billing_profiles.account_id = accounts.id
WHERE subscription_status IN ('active', 'trialing')
   OR trial_status = 'active';
```

**Sequence:**

```
1. Cancel all active Stripe subscriptions (notify customers first)
2. Export final data snapshot — accounts, tickets, leads, billing records
3. Verify all data has been migrated to Ranger / CaseDesk
4. Scale EKS node group to 0    ← stops compute cost immediately
5. Delete EKS cluster
6. Delete RDS instance           ← after confirming data snapshot is safe
7. Delete ElastiCache
8. Delete ALB
9. Archive GitHub repository     ← Settings → Danger Zone → Archive
10. Remove SearXNG k8s deployment
```

---

## What Survives Until Phase 4

After Phases 1–3, InboxIQ's running codebase is:

```
src/
├── app.py
├── extensions.py
├── celery_inboxiq.py       (stripped beat schedule)
├── models/
│   ├── core.py             (Account, User, InboxConnection)
│   ├── auth.py
│   └── billing.py
├── inbox/                  (Gmail/Outlook sync — the customer-facing core)
├── api/v1/
│   ├── auth.py
│   ├── billing.py
│   └── inboxiq.py          (inbox sync endpoints only)
├── billing/
├── auth/
├── settings/               (connection management UI)
└── templates/              (inbox UI only)
```

That is the minimum viable InboxIQ — the inbox management product that live customers are using. Nothing else. Infrastructure cost at that point is one pod serving the inbox sync and one Celery worker polling Gmail/Outlook. Significantly cheaper than today.

---

## Removal Checklist (track per phase)

- [ ] Phase 1 validation query run — zero rows confirmed
- [ ] Phase 1 modules removed and deployed
- [ ] Phase 1 beat schedule entries removed
- [ ] Ranger live and processing campaigns (30-day window)
- [ ] Phase 2 validation query run — zero active campaigns
- [ ] Phase 2 modules removed and deployed
- [ ] CaseDesk live at kalevent.com
- [ ] Phase 3 modules removed and deployed
- [ ] All accounts migrated — validation query returns zero rows
- [ ] Phase 4 teardown sequence executed
- [ ] GitHub repository archived
