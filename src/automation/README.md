# Automation Studio - AI-Powered Support Triage Automation

## The InboxIQ Difference

**Traditional approach:** Spend weeks building complex rule engines, hiring engineers to code logic trees.

**InboxIQ approach:** 3-minute setup. AI analyzes your tickets, suggests automation rules in plain English, you click "Yes."

> "We're making manual support triage socially unacceptable—the same way manual data entry became obsolete."

## Core Value Proposition

Unlike Zendesk/Freshdesk's static rule builders or AI chatbots that replace agents, InboxIQ is the **intelligence layer that makes existing teams 10x more efficient**.

### 1. AI Writes the Rules for You

Our system analyzes your last 90 days of tickets and says:

> "I noticed your team always routes billing questions to Sarah. Want me to automate that?"

You just click **"Yes."** No coding, no complex logic trees.

### 2. Plain English Rule Builder

Need something custom? Type it like you'd explain it to a coworker:

- *"Send refund requests to the billing team if over $500"*
- *"Flag tickets mentioning 'lawsuit' or 'attorney' as urgent"*
- *"Route integration questions to developers during business hours"*

Our LLM converts your natural language → executable workflow → starts working immediately.

### 3. See Your ROI in Real-Time

Every rule shows:
- ⏱️ **Time saved per week** (e.g., "32 hours saved this month")
- 💰 **Cost reduction** (e.g., "$4,800 saved by avoiding mis-routes")
- 📊 **Accuracy rate** (e.g., "94% of auto-routed tickets stayed in assigned team")

No more guessing if automation is working.

### 4. Industry Templates

Start with proven rules for your industry:

**E-commerce:**
- Return/refund automation
- Shipping escalations
- VIP customer routing

**SaaS:**
- Technical vs. non-technical split
- Trial user prioritization
- Integration support routing

**Healthcare:**
- HIPAA-compliant routing
- Appointment scheduling
- Prescription requests

## Architecture

```
Historical Tickets (90 days)
    ↓
[1] ML Pattern Discovery (DSPy-based)
    ↓
Rule Suggestions (plain English)
    ↓
[2] User Approval (one-click) OR Natural Language Input
    ↓
[3] LLM Translation (GPT-4: natural language → workflow JSON)
    ↓
AutomationRule (stored in database)
    ↓
[4] Workflow Engine (executes with OTel tracing)
    ↓
[5] ROI Tracking (time/cost/accuracy metrics)
```

## Key Components

### 1. Pattern Discovery Service (`src/automation/discovery.py`)

**Purpose:** Analyze historical tickets and identify automation opportunities

**How it works:**
- Analyzes routing patterns across 90-day ticket history
- Uses DSPy to extract common patterns (e.g., "billing emails → Sarah 87% of the time")
- Generates plain English suggestions ranked by confidence and impact
- Estimates time savings for each suggested rule

**Example output:**
```python
{
    "suggestion_id": "suggest-001",
    "confidence": 0.87,
    "pattern": "Billing questions are routed to Sarah",
    "plain_english": "I noticed 87% of billing-related tickets get assigned to Sarah. Want me to automate this?",
    "estimated_time_saved_per_week": "4.5 hours",
    "estimated_cost_savings_per_month": "$720",
    "sample_tickets": ["ticket-123", "ticket-456", "ticket-789"]
}
```

**Implementation:**
- Uses DSPy signature: `TicketPatternExtractor`
- Compiled module: `dspy_artifacts/pattern_discovery_compiled.pkl`
- Runs as scheduled Celery task: `automation.discover_patterns`
- Suggests 3-5 highest-impact rules per account

### 2. Natural Language Parser (`src/automation/nl_parser.py`)

**Purpose:** Convert user's natural language input → structured workflow JSON

**How it works:**
- User types: *"Send refund requests over $500 to billing team"*
- LLM (GPT-4) parses intent and extracts:
  - **Trigger:** Ticket created
  - **Conditions:** `category contains 'refund'` AND `amount > 500`
  - **Actions:** `assign to team: billing`
- Validates generated workflow (checks field names, operators)
- Returns structured JSON ready for execution

**Example:**

Input:
```
"Flag tickets mentioning 'lawsuit' or 'attorney' as urgent and notify legal team"
```

Output:
```json
{
    "name": "Legal escalation",
    "trigger": {"event": "ticket.created", "object": "ticket"},
    "conditions": [
        {"field": "body", "operator": "contains", "value": "lawsuit"},
        {"field": "body", "operator": "contains", "value": "attorney"}
    ],
    "condition_logic": "OR",
    "actions": [
        {"type": "update_field", "config": {"field": "priority", "value": "urgent"}},
        {"type": "notify", "config": {"channel": "slack", "recipient": "#legal-alerts"}}
    ]
}
```

**Implementation:**
- Uses OpenAI GPT-4 with structured output (function calling)
- Validates against AutomationRule schema
- Returns user-friendly error messages for invalid rules
- Supports context-aware suggestions (e.g., knows your team names, custom fields)

### 3. One-Click Approval Flow

**UI Flow:**

```
┌────────────────────────────────────────────────────────┐
│ 💡 Suggested Automation                                │
│                                                         │
│ "I noticed 87% of billing tickets get assigned to      │
│ Sarah. Want me to automate this?"                      │
│                                                         │
│ ⏱️  Saves ~4.5 hours/week                              │
│ 💰 Saves ~$720/month                                   │
│                                                         │
│ [✓ Activate Rule]  [View Details]  [Dismiss]          │
└────────────────────────────────────────────────────────┘
```

When user clicks "Activate Rule":
1. Creates `AutomationRule` record (enabled=True)
2. Starts tracking executions immediately
3. Shows in dashboard with real-time metrics

### 4. Workflow Engine (`src/automation/workflow_engine.py`) ✅ **IMPLEMENTED**

**Purpose:** Execute automation rules with full observability

**Already implemented features:**
- Dynamic workflow execution (ANY user-created rule)
- Full OpenTelemetry instrumentation (trace every execution)
- Security: PII redaction, credential filtering
- Execution history with trace IDs

See [Workflow Engine Implementation](#workflow-engine-implementation) below.

### 5. ROI Calculator (`src/automation/roi_calculator.py`)

**Purpose:** Calculate and display real-time ROI metrics for each rule

**Metrics tracked:**

1. **Time Saved**
   - Baseline: Average time to manually route ticket (e.g., 3 minutes)
   - Calculation: `executions_count × 3 minutes`
   - Display: "Saved 32 hours this month"

2. **Cost Reduction**
   - Baseline: Average cost per manual action (e.g., $15/hour → $0.75/ticket)
   - Calculation: `executions_count × $0.75`
   - Display: "Saved $4,800 this quarter"

3. **Accuracy Rate**
   - Tracks: How many auto-routed tickets stayed in assigned team vs. reassigned
   - Calculation: `(tickets_stayed / total_executions) × 100`
   - Display: "94% accuracy (847/900 tickets)"

4. **Response Time Impact**
   - Tracks: Average time-to-first-response before/after automation
   - Calculation: Compare pre-automation vs. post-automation SLA metrics
   - Display: "Response time improved by 23%"

**Database schema additions needed:**

```python
class AutomationRule(db.Model):
    # ... existing fields ...

    # ROI tracking (added)
    baseline_time_per_execution = db.Column(db.Integer, default=180)  # seconds
    baseline_cost_per_execution = db.Column(db.Numeric(10, 2), default=0.75)  # dollars
    total_time_saved_seconds = db.Column(db.Integer, default=0)
    total_cost_saved = db.Column(db.Numeric(10, 2), default=0)
    accuracy_rate = db.Column(db.Numeric(5, 2))  # percentage

class AutomationRuleExecution(db.Model):
    # ... existing fields ...

    # ROI tracking (added)
    ticket_reassigned = db.Column(db.Boolean, default=False)  # for accuracy tracking
    reassignment_timestamp = db.Column(db.DateTime)
```

### 6. Industry Templates (`src/automation/templates/`)

**Purpose:** Pre-built automation rules for different industries

**Structure:**
```
src/automation/templates/
├── ecommerce.json        # Returns, refunds, shipping, VIP routing
├── saas.json             # Tech support, trial users, integrations
├── healthcare.json       # HIPAA routing, appointments, prescriptions
├── financial.json        # Fraud alerts, compliance, escalations
└── education.json        # Student support, enrollment, IT requests
```

**Example template (SaaS):**
```json
{
    "templates": [
        {
            "id": "saas-technical-split",
            "name": "Route technical questions to engineering",
            "description": "Automatically identifies technical support requests and routes to your engineering team",
            "trigger": {"event": "ticket.created"},
            "conditions": [
                {"field": "body", "operator": "contains", "value": "API"},
                {"field": "body", "operator": "contains", "value": "integration"},
                {"field": "body", "operator": "contains", "value": "webhook"},
                {"field": "body", "operator": "contains", "value": "authentication"}
            ],
            "condition_logic": "OR",
            "actions": [
                {"type": "assign", "config": {"team": "engineering"}},
                {"type": "tag", "config": {"tags": ["technical", "engineering"]}}
            ],
            "estimated_time_saved_per_week": "8 hours",
            "estimated_accuracy": "91%"
        }
    ]
}
```

**User activation:**
- Browse templates by industry
- One-click to activate
- Templates auto-configure with your team names/fields

## Workflow Engine Implementation

### Database Models ✅ **IMPLEMENTED**

**AutomationRule** - Stores automation rules
```python
class AutomationRule(db.Model):
    id = db.Column(db.String(64), primary_key=True)
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"))
    name = db.Column(db.String(255))
    trigger = db.Column(db.JSON)  # {"event": "ticket.created"}
    conditions = db.Column(db.JSON)  # [{"field": "priority", "operator": "equals", "value": "P1"}]
    condition_logic = db.Column(db.String(16))  # "AND" or "OR"
    actions = db.Column(db.JSON)  # [{"type": "assign", "config": {...}}]
    enabled = db.Column(db.Boolean, default=True)

    # Analytics (calculated from executions)
    total_executions = db.Column(db.Integer, default=0)
    successful_executions = db.Column(db.Integer, default=0)
    avg_execution_time_ms = db.Column(db.Integer)

    # Discovery metadata
    source = db.Column(db.String(32))  # "ai_suggested", "user_created", "template"
    suggestion_id = db.Column(db.String(64))  # links back to suggestion
```

**AutomationRuleExecution** - Stores execution history with trace IDs
```python
class AutomationRuleExecution(db.Model):
    id = db.Column(db.String(64), primary_key=True)
    rule_id = db.Column(db.String(64), db.ForeignKey("automation_rules.id"))
    trace_id = db.Column(db.String(32), index=True)  # OpenTelemetry trace ID

    triggered_by = db.Column(db.String(32))  # "email", "webhook", "manual"
    trigger_context_sanitized = db.Column(db.JSON)  # sanitized trigger data

    conditions_matched = db.Column(db.Boolean)
    conditions_detail = db.Column(db.JSON)  # which conditions passed/failed

    executed = db.Column(db.Boolean)
    success = db.Column(db.Boolean)
    actions_detail = db.Column(db.JSON)  # action execution results

    execution_time_ms = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
```

### Core Functions ✅ **IMPLEMENTED**

See `src/automation/workflow_engine.py`:

- `execute_automation_workflow(workflow_id, trigger_context, trigger_event)` - Main entry point
- `evaluate_workflow_conditions(workflow, context, parent_span)` - Evaluates conditions with tracing
- `execute_workflow_actions(workflow, context, parent_span)` - Executes actions with tracing

### OpenTelemetry Tracing ✅ **IMPLEMENTED**

Every workflow execution creates hierarchical traces:

```
automation.workflow (trace_id: abc123...)
├── automation.evaluate_conditions
│   ├── condition.field_match (priority equals P1) ✅ matched
│   └── condition.field_match (category equals billing) ✅ matched
└── automation.execute_actions
    ├── action.assign (team: finance) ✅ success (145ms)
    └── action.notify (slack: #urgent-billing) ✅ success (89ms)
```

Users can view traces in Phoenix UI to debug why rules didn't fire or actions failed.

### Security ✅ **IMPLEMENTED**

- PII redaction in spans (emails, phones, SSN, credit cards)
- Credential filtering (API keys, tokens, passwords)
- Sanitized trigger context (email bodies NOT stored)

## Implementation Roadmap

### Phase 1: Pattern Discovery (Not Yet Implemented)
**Goal:** AI analyzes tickets and suggests automation rules

**Files to create:**
- `src/automation/discovery.py` - ML pattern detection
- `src/automation/dspy/pattern_extractor.py` - DSPy signature for pattern extraction
- `src/tasks/automation_discovery.py` - Celery task to run discovery daily
- `src/api/v1/automation_suggestions.py` - API to fetch/approve suggestions

**Key functions:**
```python
def discover_automation_patterns(account_id, lookback_days=90):
    """Analyze ticket routing patterns and suggest automation rules"""
    pass

def rank_suggestions_by_impact(suggestions):
    """Rank suggestions by estimated time/cost savings"""
    pass
```

**Database additions:**
```python
class AutomationSuggestion(db.Model):
    id = db.Column(db.String(64), primary_key=True)
    account_id = db.Column(db.Integer)
    pattern_type = db.Column(db.String(64))  # "routing", "prioritization", "tagging"
    plain_english = db.Column(db.Text)  # Human-readable suggestion
    confidence = db.Column(db.Numeric(5, 2))  # 0.0-1.0
    estimated_time_saved_per_week = db.Column(db.Integer)  # minutes
    estimated_cost_savings_per_month = db.Column(db.Numeric(10, 2))
    sample_ticket_ids = db.Column(db.JSON)  # Example tickets matching pattern
    status = db.Column(db.String(16))  # "pending", "approved", "dismissed"
    workflow_json = db.Column(db.JSON)  # Generated workflow structure
```

### Phase 2: Natural Language Parser (Not Yet Implemented)
**Goal:** Convert user's natural language → executable workflow

**Files to create:**
- `src/automation/nl_parser.py` - LLM-based NL→JSON conversion
- `src/automation/validators.py` - Validate generated workflows
- `src/api/v1/automation_nl.py` - API endpoint for NL rule creation

**Key functions:**
```python
def parse_natural_language_rule(user_input, account_context):
    """Convert natural language → AutomationRule JSON using GPT-4"""
    pass

def validate_workflow_structure(workflow_json, account_id):
    """Validate workflow has valid fields/operators/actions"""
    pass
```

**Example usage:**
```python
workflow = parse_natural_language_rule(
    user_input="Send refund requests over $500 to billing team",
    account_context={
        "teams": ["billing", "support", "sales"],
        "custom_fields": ["refund_amount", "customer_tier"],
        "priorities": ["P0", "P1", "P2", "P3"]
    }
)
# Returns validated AutomationRule JSON ready for storage
```

### Phase 3: ROI Calculator (Not Yet Implemented)
**Goal:** Track and display real-time ROI metrics

**Files to create:**
- `src/automation/roi_calculator.py` - Calculate time/cost savings
- `src/tasks/automation_metrics.py` - Daily metrics aggregation
- `src/api/v1/automation_analytics.py` - API for ROI dashboard

**Key functions:**
```python
def calculate_rule_roi(rule_id, time_period="month"):
    """Calculate time saved, cost reduction, accuracy rate for a rule"""
    pass

def track_ticket_reassignment(ticket_id, automation_execution_id):
    """Mark execution as inaccurate if ticket was manually reassigned"""
    pass
```

**Database migrations needed:**
```bash
flask db migrate -m "Add ROI tracking fields to AutomationRule and AutomationRuleExecution"
```

### Phase 4: Industry Templates (Not Yet Implemented)
**Goal:** Pre-built rules for different industries

**Files to create:**
- `src/automation/templates/*.json` - Template definitions
- `src/automation/template_installer.py` - Install templates for account
- `src/api/v1/automation_templates.py` - Browse/activate templates

**Template structure:**
```json
{
    "industry": "ecommerce",
    "templates": [
        {
            "id": "ecommerce-returns",
            "name": "Automate return requests",
            "description": "Routes return/refund requests to appropriate team based on order value",
            "trigger": {"event": "ticket.created"},
            "conditions": [...],
            "actions": [...]
        }
    ]
}
```

### Phase 5: UI Components (Not Yet Implemented)
**Goal:** User interface for Automation Studio

**Files to create:**
- `src/templates/automation_studio/dashboard.html` - Main dashboard
- `src/templates/automation_studio/suggestions.html` - AI suggestions list
- `src/templates/automation_studio/nl_builder.html` - Natural language input
- `src/templates/automation_studio/analytics.html` - ROI metrics
- `src/settings/automation_routes.py` - Flask routes

**UI pages needed:**
1. **Suggestions Dashboard** - Show AI-discovered patterns with one-click approval
2. **Natural Language Builder** - Text input for custom rules
3. **Rule List** - All active rules with enable/disable toggles
4. **Execution History** - Per-rule execution log with trace links
5. **Analytics Dashboard** - Time saved, cost reduction, accuracy charts

## Testing Strategy

### 1. Pattern Discovery Tests
```python
def test_discover_billing_routing_pattern():
    # Given: 90 days of tickets where 87% of billing tickets → Sarah
    # When: discover_automation_patterns(account_id=1)
    # Then: Should suggest "Route billing tickets to Sarah"
    pass
```

### 2. Natural Language Parser Tests
```python
def test_parse_refund_rule():
    input = "Send refund requests over $500 to billing team"
    workflow = parse_natural_language_rule(input, account_context)

    assert workflow["conditions"] == [
        {"field": "category", "operator": "contains", "value": "refund"},
        {"field": "amount", "operator": "greater_than", "value": 500}
    ]
    assert workflow["actions"] == [
        {"type": "assign", "config": {"team": "billing"}}
    ]
```

### 3. ROI Calculator Tests
```python
def test_calculate_time_savings():
    # Given: Rule executed 120 times this month, baseline 3 min/ticket
    # When: calculate_rule_roi(rule_id, time_period="month")
    # Then: Should return "6 hours saved"
    pass
```

### 4. Workflow Engine Tests ✅ **IMPLEMENTED**
See existing tests in `src/automation/workflow_engine.py`

## Migration

To add the database tables:

```bash
flask db migrate -m "Add AutomationRule and AutomationRuleExecution models"
flask db upgrade
```

To add ROI tracking fields (Phase 3):

```bash
flask db migrate -m "Add ROI tracking fields to automation models"
flask db upgrade
```

## API Endpoints (To Be Implemented)

### Suggestions API
- `GET /api/v1/automation/suggestions` - List AI-discovered patterns
- `POST /api/v1/automation/suggestions/{id}/approve` - Activate suggested rule
- `POST /api/v1/automation/suggestions/{id}/dismiss` - Dismiss suggestion

### Natural Language API
- `POST /api/v1/automation/rules/from-natural-language` - Create rule from NL input
- `POST /api/v1/automation/rules/validate` - Validate workflow structure

### Rules Management API
- `GET /api/v1/automation/rules` - List all rules
- `GET /api/v1/automation/rules/{id}` - Get rule details
- `PATCH /api/v1/automation/rules/{id}` - Update rule (enable/disable)
- `DELETE /api/v1/automation/rules/{id}` - Delete rule

### Analytics API
- `GET /api/v1/automation/analytics/overview` - Overall ROI metrics
- `GET /api/v1/automation/rules/{id}/analytics` - Per-rule ROI metrics
- `GET /api/v1/automation/rules/{id}/executions` - Execution history with traces

### Templates API
- `GET /api/v1/automation/templates` - Browse industry templates
- `POST /api/v1/automation/templates/{id}/install` - Install template

## References

- **Observability Implementation Plan**: Phase 3.5 - Dynamic workflow tracing
- **OpenTelemetry**: Full instrumentation for debugging automation rules
- **Phoenix UI**: `http://phoenix.kaley.svc.cluster.local:6006` for trace visualization
- **DSPy Documentation**: https://dspy-docs.vercel.app/ for pattern extraction
- **Project Instructions**: `/Users/kofi/inboxiq/CLAUDE.md` - coding standards and patterns

## Summary: What Makes InboxIQ Different

**Traditional automation:**
- Weeks to implement
- Requires engineers to code rules
- Static logic that doesn't learn
- No visibility into ROI

**InboxIQ automation:**
- 3-minute setup
- AI suggests rules, you click "Yes"
- ML gets smarter with every ticket (data moat)
- Real-time ROI metrics (time/cost/accuracy)

**The result:** Manual support triage becomes as obsolete as manual data entry. InboxIQ is the solution that makes it happen.
