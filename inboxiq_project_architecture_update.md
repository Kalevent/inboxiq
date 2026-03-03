# InboxIQ — Project Architecture Cleanup Plan

**Author:** Architecture review
**Status:** Phase A in progress
**Goal:** Make the codebase clean and maintainable without breaking the running app.

---

## Why This Is Needed

The app started as a small Flask monolith and grew organically. The result:
- ~25 loose Python files dumped at `src/` root that belong inside domain packages
- Project root littered with one-off scripts, CSV exports, credentials, and planning docs
- Files with duplicate names in different folders (two `admin_marketing.py`, two email files)
- `models.py` likely 1000+ lines with every domain in one file

No single change will fix it — this is a phased, low-risk cleanup done one commit at a time.

---

## Phase A — Root directory cleanup (zero risk)

**Risk:** None. No code imports change. Files are not referenced by the app.
**Status:** ✅ Done

### Scripts → `scripts/`

The following one-off and utility scripts were at the project root. Moved to `scripts/`:

| File | Purpose |
| --- | --- |
| `check_csrf.py` | One-off CSRF header test |
| `configure_account_labels.py` | One-off account label setup |
| `find_automation_studio_leads.py` | Lead export utility |
| `find_leads_simple.py` | Simplified lead lookup |
| `test_csp_headers.py` | CSP header verification |
| `test_lead_discovery.py` | Lead discovery smoke test |
| `test_seo_cleanup.py` | SEO cleanup verification |
| `test_security_headers.sh` | Security header HTTP tests |
| `deploy-gsc-credentials.sh` | GSC credentials deployment |
| `verify-gsc-secret.sh` | GSC secret verification |
| `rebuild-and-deploy.sh` | Build + deploy helper |

### Docs → `docs/`

| File | Purpose |
| --- | --- |
| `IMPLEMENTATION_PLAN.md` | Original feature implementation plan |
| `LEAD_DISCOVERY_STATUS.md` | Lead discovery progress notes |
| `LEAD_DISCOVERY_SUMMARY.md` | Lead discovery summary |
| `add_user_name_field.md` | Migration note |
| `marketing_video_prompt.txt` | Marketing copy |

### Data → `data/`

These are exported data files — not source code. Created `data/` folder:

| File | Purpose |
| --- | --- |
| `automation_studio_leads.csv` | Lead export |
| `automation_studio_leads_20260207_112308.csv` | Lead export (timestamped) |
| `automation_studio_leads_20260207_112721.csv` | Lead export (timestamped) |
| `leads_export.csv` | Leads export |
| `blog_post_maximizing-revenue-automation-in-revenue-operations.json` | Blog post data |

### Credentials — stayed in place

`gsc-service-account.json` — kept at root (referenced by `deploy-gsc-credentials.sh`).
Ensure it is in `.gitignore` and never committed.

### Runtime artifacts — add to `.gitignore`

`celerybeat-schedule.db` — generated at runtime by Celery Beat. Should never be in the repo.
Added to `.gitignore`.

---

## Phase B — Move loose `src/` root files into packages

**Risk:** Low. Each file move requires updating import paths.
**Rule:** One file per commit. Grep all imports. Verify deploy before next move.
**Status:** ✅ Done

### Files to move (ordered safest → riskiest)

| File | Move to | Notes |
|---|---|---|
| `seo_cleanup.py` | `src/marketing/seo_cleanup.py` | Low dependency count |
| `funnel_stages.py` | `src/funnel/stages.py` | Used by funnel module |
| `trial_onboarding.py` | `src/trial/onboarding.py` | Used by trial tasks |
| `kb_integrations.py` | `src/integrations/kb.py` | Used by settings |
| `mcp_client.py` | `src/mcp/client.py` | Used by MCP modules |
| `quota.py` | `src/billing/quota.py` | Used by billing + features |
| `crash_report.py` | `src/monitoring/crash_report.py` | Create `src/monitoring/` |
| `observability.py` | `src/monitoring/observability.py` | Wide usage — do last |
| `observability_sanitizer.py` | `src/monitoring/sanitizer.py` | Paired with observability |
| `dspy_triage.py` | `src/dspy/triage_runner.py` | Rename to avoid clash |
| `dspy_eval.py` | `src/dspy/training/eval.py` | Already a training util |
| `dspy_train.py` | `src/dspy/training/train.py` | Already a training util |
| `triage_config.py` | `src/dspy/triage_config.py` | DSPy config |
| `triage_labels.py` | `src/dspy/triage_labels.py` | DSPy labels |
| `agent_worker.py` | `src/agents/worker.py` | Create `src/agents/` |
| `agents_registry.py` | `src/agents/registry.py` | Paired with worker |
| `automation_studio.py` | `src/automation/studio.py` | Large file |
| `blog_content.py` | `src/blog/content.py` | Blog utilities |
| `decision_merger.py` | `src/inbox/merger.py` | Create `src/inbox/` |
| `inboxiq_logic.py` | `src/inbox/logic.py` | Core inbox logic |
| `llm_client.py` | `src/ai/client.py` | Create `src/ai/` |
| `email_poll.py` | `src/email/poll.py` | Create `src/email/` |
| `email_outreach.py` | `src/email/outreach.py` | High deps — do last |
| `email_utils.py` | `src/email/utils.py` | Highest deps — do last |

### New packages created

| Package | Contents |
| --- | --- |
| `src/monitoring/` | `crash_report.py`, `observability.py`, `sanitizer.py` (was observability_sanitizer) |
| `src/inbox/` | `logic.py` (was inboxiq_logic), `poll.py` (was email_poll), `merger.py` (was decision_merger) |
| `src/ai/` | `client.py` (was llm_client) |
| `src/notifications/` | `emails.py` (was email_utils) |

### Files moved into existing packages

| File | Destination |
| --- | --- |
| `triage_config.py` | `src/dspy/triage_config.py` |
| `triage_labels.py` | `src/dspy/triage_labels.py` |
| `dspy_eval.py` | `src/dspy/training/eval.py` |
| `dspy_train.py` | `src/dspy/training/train.py` |
| `funnel_stages.py` | `src/funnel/stages.py` |
| `quota.py` | `src/billing/quota.py` |
| `seo_cleanup.py` | `src/marketing/seo_cleanup.py` |
| `blog_content.py` | `src/blog/content.py` |
| `trial_onboarding.py` | `src/trial/onboarding.py` |
| `kb_integrations.py` | `src/integrations/kb.py` |
| `mcp_client.py` | `src/mcp/client.py` |
| `agent_worker.py` | `src/agents/worker.py` |
| `agents_registry.py` | `src/agents/registry.py` |
| `automation_studio.py` | `src/automation/studio.py` |
| `email_outreach.py` | `src/outreach/email.py` |

### Files to keep at `src/` root (legitimate shared utilities)

- `app.py` — Flask factory
- `config.py` — Configuration
- `extensions.py` — Flask extensions
- `models.py` — All ORM models (until Phase C)
- `manage.py` — Flask CLI commands
- `celery_inboxiq.py` — Celery config
- `sanitize.py` — Shared HTML utility
- `uploads.py` — Shared upload utility
- `embeddings.py` — Shared embedding utility
- `crypto.py` — Shared crypto utility
- `security.py` — Shared security utility
- `features.py` — Feature flags
- `dspy_triage.py` — **Deprecated shim** (re-exports from `src.dspy.triage`); 0 callers; delete when confirmed safe

---

## Phase C — Split `models.py` by domain

**Risk:** Medium. SQLAlchemy relationships cross domains. Circular import risk.
**Status:** ✅ Done — zero circular import issues (all relationships use string names)

### Final layout

```
src/models/
    __init__.py     ← re-exports all 47 classes (no external import changes needed)
    core.py         ← Account, User, InboxConnection, AccountFeatureFlags
    auth.py         ← AuthEvent, Passkey, TOTPDevice
    tickets.py      ← Ticket, TicketEmbedding, TriageLabelConfig, DraftReplyFeedback, TriageConfig
    ai.py           ← DspyTrainingMetric, AgentEvent, AgentModel, MCPServerCatalog
    leads.py        ← Lead, LeadFunnelStage, LeadEngagementEvent, LeadAttribution, FunnelMetricsDaily
    content.py      ← BlogPost, KBIntegration, KBArticle, KBArticleEmbedding, GeneratedContent, PitchedBlogTopic
    campaigns.py    ← CampaignSender, HunterDomainCache, EmailCampaign, EmailOutreach, NurtureEmailSend
    automation.py   ← AutomationStudioWaitlist, AutomationRule, AutomationRuleExecution, WebhookProvider, AutomationSuggestion
    marketing.py    ← Referral, InAppMessage, InAppMessageDismissal, LandingPage, MarketingSpend, EnterpriseInquiry
    misc.py         ← Testimonial, Feedback
    developer.py    ← DeveloperAccessRequest, RegisteredApp
    billing.py      ← PaymentProviderAccount, CustomerBillingProfile, PaymentMethod, Plan,
                       Subscription, Invoice, ChargeAttempt, AccountUsageCounter, table_exists
    publishing.py   ← NewsletterDraft, WhitepaperDraft
```

`src/billing/models.py` and `src/publishing/models.py` have been deleted; all callers updated to
`from src.models.billing import ...` / `from src.models.publishing import ...`.

---

## Phase D — Naming and structural fixes

**Risk:** Low (renames only). One at a time.
**Status:** ✅ Done

### Naming collisions — resolved

| Problem | Outcome |
| --- | --- |
| `src/admin/admin_marketing.py` vs `src/api/v1/admin_marketing.py` | `src/admin/` only ever had `routes.py` — no real collision existed |
| `email_utils.py` vs `email_outreach.py` | Resolved in Phase B: `notifications/emails.py` and `outreach/email.py` |
| `src/admin/admin.py` and `src/admin/routes.py` | `admin.py` never existed in `src/admin/` — no real collision |

### `_require_admin()` duplication — resolved

Was defined identically in 8 files. Now defined once in `src/api/v1/admin.py`
and imported in `admin_marketing.py`, `admin_content.py`, `admin_funnel.py`,
`admin_insights.py`, `admin_trial.py`, `outreach.py`.
`src/admin/routes.py` keeps its own placeholder stub (different blueprint, returns True).

### Template split — resolved

`src/templates/admin.html`: 2,489 lines → 1,475 lines
9 section partials extracted to `src/templates/admin/`:

| Partial | Lines | Content |
| --- | --- | --- |
| `section_overview.html` | 57 | Dashboard overview + testimonial invite |
| `section_funnel.html` | 140 | Funnel v2 metrics + lead discovery |
| `section_content.html` | 77 | Content & publishing |
| `section_trial.html` | 102 | Trial onboarding stats |
| `section_saas.html` | 132 | SaaS metrics + revenue |
| `section_marketing.html` | 399 | A/B tests, nurture, attribution, landing pages |
| `section_ai.html` | 63 | AI & DSPy training |
| `section_developer.html` | 34 | Developer section |
| `section_system.html` | 19 | System section |

---

## Rules for all phases

1. **One file per commit.** Never batch moves — a regression needs to be trivially revertable.
2. **Grep before moving.** Run `grep -r "from src.X import" src/` before moving any file.
3. **Never move `models.py`** until Phase C is explicitly started.
4. **Never rename Celery task names** (`name="marketing.foo"`) — Beat schedules reference these strings.
5. **Never touch `index.html` with the Edit tool** — Tailwind whitespace issue (see MEMORY).
6. **No `flask db migrate`** — Phase A and B don't touch models.
