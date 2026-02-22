# Kalevent / InboxIQ — Pricing Plan (DRAFT v3)

> **Status:** Prices and quotas fully confirmed. Ready to implement on approval.
> **Stripe product names:** Keep `pro`, `business` as-is. Add `scale` as new product.
> **Pricing model:** Flat per-account (drop per-inbox billing).

---

## Decisions — All Locked

| Decision | Confirmed |
|---|---|
| Pricing model | Flat per-account |
| Trial length | 14 days (extended from 7) |
| Overage billing | Stripe Metered Billing |
| Pro price | **£49 / month** |
| Business price | **£149 / month** |
| Scale price | **£399 / month** |

---

## Current State (Live Today)

| Stripe name | Price | Notes |
|---|---|---|
| `pro` | £29 / mo / inbox | Core triage only |
| `business` | £99 / mo / inbox | Draft replies, API, tuning |

---

## Confirmed Plan Structure

### Free Trial
- Duration: **14 days** (extend from current 7)
- Access: Full Business-tier feature set
- AI decisions: 1,000 included
- No credit card required
- On expiry: all features locked, redirect to upgrade

---

### PRO — £49 / month flat
*Stripe product: `pro` — update price only, keep product name*

| Meter | Limit |
|---|---|
| AI triage decisions | 1,000 / month |
| Shared inboxes | Unlimited |
| Chat widget | disabled |
| Automation Studio | disabled |
| Content generation | disabled |
| Nurture campaigns | disabled |
| Lead discovery | disabled |
| Lead funnel | view only (manual entry, no discovery) |
| Developer API | disabled |
| Seats | 2 |

**Overage (Stripe Metered):** £4 per 100 AI decisions

---

### BUSINESS — £149 / month flat
*Stripe product: `business` — update price only, keep product name*

| Meter | Limit |
|---|---|
| AI triage decisions | 5,000 / month |
| Shared inboxes | 3 |
| Chat widget | 200 conversations / month |
| Automation Studio | 500 workflow runs / month |
| Content generation | 8 posts / month |
| Nurture campaigns | 2,000 emails / month |
| Lead discovery | disabled |
| Lead funnel | full (manual + chat captures, no AI discovery) |
| Developer API | 2 registered apps |
| Seats | 5 |

Also includes (carried from existing Business plan):
- Draft replies (AI-suggested, agent approves)
- Account-scoped DSPy tuning + evaluation metrics
- Multi-agent routing
- Team analytics, SLA alerts & QA

**Overage (Stripe Metered):**

| Meter | Rate |
|---|---|
| AI decisions | £3 per 100 |
| Chat conversations | £2 per 50 |
| Automation runs | £3 per 100 |
| Nurture emails | £1 per 100 |

---

### SCALE — £399 / month flat
*Stripe product: `scale` — new product to create*

| Meter | Limit |
|---|---|
| AI triage decisions | 25,000 / month |
| Shared inboxes | Unlimited |
| Chat widget | 1,000 conversations / month |
| Automation Studio | 5,000 workflow runs / month |
| Content generation | 30 posts / month |
| Content distribution | Social auto-publish enabled |
| Nurture campaigns | 20,000 emails / month |
| Lead discovery | 200 leads / month (AI web search + qualification) |
| Lead funnel | Full pipeline (discovery → nurture → conversion) |
| Developer API | Unlimited registered apps |
| Seats | 15 |

**Overage (Stripe Metered):**

| Meter | Rate |
|---|---|
| AI decisions | £2 per 100 |
| Chat conversations | £1 per 50 |
| Automation runs | £2 per 100 |
| Nurture emails | £0.50 per 100 |
| Leads discovered | £5 per 50 |

---

### ENTERPRISE — Custom pricing
- Unlimited everything
- SSO / SAML
- Dedicated onboarding + 99.9% SLA
- Custom data retention

---

## Plan × Feature Matrix

| Feature | Trial | Pro | Business | Scale | Enterprise |
|---|:---:|:---:|:---:|:---:|:---:|
| **Price** | Free 14d | £49/mo | £149/mo | £399/mo | Custom |
| AI decisions / mo | 1,000 | 1,000 | 5,000 | 25,000 | Unlimited |
| Shared inboxes | 3 | 1 | 3 | Unlimited | Unlimited |
| Seats | 3 | 2 | 5 | 15 | Custom |
| Draft replies | ✓ | ✗ | ✓ | ✓ | ✓ |
| Custom categories & SLAs | ✓ | ✓ | ✓ | ✓ | ✓ |
| DSPy tuning & eval | ✓ | ✗ | ✓ | ✓ | ✓ |
| Chat widget (conv/mo) | — | ✗ | 200 | 1,000 | Unlimited |
| Automation Studio (runs/mo) | — | ✗ | 500 | 5,000 | Unlimited |
| Nurture campaigns (emails/mo) | — | ✗ | 2,000 | 20,000 | Unlimited |
| Content generation (posts/mo) | — | ✗ | 8 | 30 | Unlimited |
| Content distribution (social) | — | ✗ | ✗ | ✓ | ✓ |
| Lead funnel (manual) | — | View only | ✓ | ✓ | ✓ |
| Lead discovery (AI leads/mo) | — | ✗ | ✗ | 200 | Unlimited |
| Developer API & apps | — | ✗ | 2 apps | Unlimited | Unlimited |
| Overage billing | — | ✓ | ✓ | ✓ | — |
| SSO / SAML | ✗ | ✗ | ✗ | ✗ | ✓ |

---

## Usage Meters to Enforce

| Meter key | Triggered by | Code location |
|---|---|---|
| `ai_decisions` | Each email through triage | `celery_inboxiq.py` → `process_incoming_email_task` |
| `chat_conversations` | Each new chat session | `intake.py` → `chat_submit()` |
| `automation_runs` | Each workflow execution | automation / tool-calling agent |
| `content_posts` | Each blog post generated | `content/tasks.py` → `generate_blog_post` |
| `leads_discovered` | Each lead from AI web search | `funnel/tasks.py` → `discover_leads_via_search` |
| `nurture_emails` | Each nurture email sent | `nurture_campaigns.py` |

---

## Stripe Metered Billing

Overage is billed automatically by Stripe at period end. No manual invoicing.

**How it works:**
1. Each plan subscription in Stripe has a flat base price item + one metered price item per overage meter
2. When usage exceeds the included quota, `quota.py` reports overage units to Stripe via `stripe.SubscriptionItem.create_usage_record()`
3. Stripe aggregates usage and adds overage line items to the next invoice

**Metered prices to create in Stripe:**

| Plan | Metered items needed |
|---|---|
| Pro | `pro_ai_overage` |
| Business | `business_ai_overage`, `business_chat_overage`, `business_automation_overage`, `business_nurture_overage` |
| Scale | `scale_ai_overage`, `scale_chat_overage`, `scale_automation_overage`, `scale_nurture_overage`, `scale_leads_overage` |

---

## Codebase Changes Required

### 1. Stripe
- Update `pro` price: £29/inbox → £49/account flat (new price ID, keep product)
- Update `business` price: £99/inbox → £149/account flat (new price ID, keep product)
- Create `scale` product + £399/month flat price
- Create metered overage prices (table above)
- Update env vars: `STRIPE_PRICE_PRO`, `STRIPE_PRICE_BUSINESS`, add `STRIPE_PRICE_SCALE`
- Add env vars for metered price IDs

### 2. Expand `Plan` model (`src/billing/models.py`)
Add feature flag + quota columns:
```python
# Feature gates (False = disabled on this plan)
chat_enabled             = db.Column(db.Boolean, nullable=False, default=False)
automation_enabled       = db.Column(db.Boolean, nullable=False, default=False)
content_gen_enabled      = db.Column(db.Boolean, nullable=False, default=False)
lead_discovery_enabled   = db.Column(db.Boolean, nullable=False, default=False)
nurture_enabled          = db.Column(db.Boolean, nullable=False, default=False)
distribution_enabled     = db.Column(db.Boolean, nullable=False, default=False)
api_access_enabled       = db.Column(db.Boolean, nullable=False, default=False)
registered_apps_limit    = db.Column(db.Integer, nullable=False, default=0)

# Monthly included quotas (None = unlimited)
ai_decisions_limit       = db.Column(db.Integer, nullable=True)
chat_limit               = db.Column(db.Integer, nullable=True)
automation_runs_limit    = db.Column(db.Integer, nullable=True)
content_posts_limit      = db.Column(db.Integer, nullable=True)
leads_limit              = db.Column(db.Integer, nullable=True)
nurture_emails_limit     = db.Column(db.Integer, nullable=True)

# Stripe metered price IDs for overage reporting
stripe_ai_overage_price_id         = db.Column(db.String(128), nullable=True)
stripe_chat_overage_price_id       = db.Column(db.String(128), nullable=True)
stripe_automation_overage_price_id = db.Column(db.String(128), nullable=True)
stripe_leads_overage_price_id      = db.Column(db.String(128), nullable=True)
stripe_nurture_overage_price_id    = db.Column(db.String(128), nullable=True)
```

### 3. Add `AccountUsageCounter` model (`src/models.py`)
Monthly counter row per account, composite PK on `(account_id, billing_month)`:
```python
class AccountUsageCounter(db.Model):
    __tablename__ = "account_usage_counters"
    account_id         = db.Column(db.Integer, db.ForeignKey("accounts.id"), primary_key=True)
    billing_month      = db.Column(db.String(7), primary_key=True)   # "2026-02"
    ai_decisions       = db.Column(db.Integer, nullable=False, default=0)
    chat_conversations = db.Column(db.Integer, nullable=False, default=0)
    automation_runs    = db.Column(db.Integer, nullable=False, default=0)
    content_posts      = db.Column(db.Integer, nullable=False, default=0)
    leads_discovered   = db.Column(db.Integer, nullable=False, default=0)
    nurture_emails     = db.Column(db.Integer, nullable=False, default=0)
    updated_at         = db.Column(db.DateTime(timezone=True), onupdate=func.now())
```

### 4. Add `src/quota.py`
```python
def check_and_increment(meter: str, account_id: int, quantity: int = 1) -> None:
    """
    1. Upsert AccountUsageCounter for (account_id, current billing_month)
    2. Read plan limit for this meter via get_account_plan(account_id)
    3. If limit is None  → unlimited plan, increment and return
    4. If within limit   → increment and return
    5. If over limit     → increment (we bill overage, not block)
                         → report overage units to Stripe via create_usage_record()
    Uses SELECT FOR UPDATE to prevent race conditions.
    Raises FeatureDisabled (HTTP 403) if the feature flag is off for this plan.
    """
```

### 5. Add `src/features.py` extensions
```python
def feature_enabled(feature: str, account_id: int) -> bool:
    """
    Returns True if the account's plan has the feature flag enabled,
    OR if the account is on an active trial.
    Features: "chat", "automation", "content_gen", "lead_discovery",
              "nurture", "distribution", "api_access"
    """
```

### 6. Gate each callsite
```
chat_submit()               → feature_enabled("chat")  + check_and_increment("chat_conversations")
Automation run              → feature_enabled("automation") + check_and_increment("automation_runs")
generate_blog_post          → feature_enabled("content_gen") + check_and_increment("content_posts")
discover_leads_via_search   → feature_enabled("lead_discovery") + check_and_increment("leads_discovered")
send_discovery_nurture      → feature_enabled("nurture") + check_and_increment("nurture_emails")
process_incoming_email_task → check_and_increment("ai_decisions")
```

### 7. Seed `plans` table

```sql
-- Pro
UPDATE plans SET
  ai_decisions_limit=1000, chat_enabled=false, automation_enabled=false,
  content_gen_enabled=false, lead_discovery_enabled=false, nurture_enabled=false,
  api_access_enabled=false, registered_apps_limit=0
WHERE code='pro';

-- Business
UPDATE plans SET
  ai_decisions_limit=5000, chat_enabled=true, chat_limit=200,
  automation_enabled=true, automation_runs_limit=500,
  content_gen_enabled=true, content_posts_limit=8,
  nurture_enabled=true, nurture_emails_limit=2000,
  lead_discovery_enabled=false, api_access_enabled=true, registered_apps_limit=2
WHERE code='business';

-- Scale (INSERT new row)
INSERT INTO plans (code, price_cents, currency,
  ai_decisions_limit, chat_enabled, chat_limit,
  automation_enabled, automation_runs_limit,
  content_gen_enabled, content_posts_limit,
  nurture_enabled, nurture_emails_limit,
  lead_discovery_enabled, leads_limit,
  distribution_enabled, api_access_enabled, registered_apps_limit)
VALUES ('scale', 39900, 'GBP',
  25000, true, 1000,
  true, 5000,
  true, 30,
  true, 20000,
  true, 200,
  true, true, -1);  -- -1 = unlimited apps
```

### 8. Update pricing page
- Change prices to £49 / £149 / £399 flat
- Remove all "per inbox" language
- Add Scale tier card
- Update feature lists to match matrix above

### 9. Existing customer migration
- Email customers 30 days before go-live
- Migrate Pro subscriptions: cancel old price, create new price subscription (same product)
- Migrate Business subscriptions: same
- Consider 1-month credit for customers whose bill increases

---

## Implementation Order

1. ✅ Plan locked (this file)
2. ⬜ `flask db migrate` — add `AccountUsageCounter` model
3. ⬜ Add `quota.py` + extend `features.py` (counting only, no Stripe reporting yet)
4. ⬜ Expand `Plan` model columns → `flask db migrate`
5. ⬜ Seed `plans` table with quotas + feature flags
6. ⬜ Gate each feature callsite one at a time (deploy + verify between each)
7. ⬜ Create Scale + metered overage prices in Stripe, add env vars
8. ⬜ Wire Stripe usage reporting into `quota.py`
9. ⬜ Update pricing page (flat prices, Scale card, remove per-inbox language)
10. ⬜ Email existing customers (30-day notice)
11. ⬜ Migrate existing Stripe subscriptions to new flat price IDs
12. ⬜ Extend trial: update config from 7 → 14 days

---

*Last updated: 2026-02-22*
