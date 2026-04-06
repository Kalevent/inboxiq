# Prior Authorisation in InboxIQ

## What it is

Prior authorisation (prior auth) is a gate: before a high-stakes action executes — an email auto-sends, an automation rule fires, a refund is processed — a named authority must review and approve it. The condition that triggers the gate, the identity of the approver, and the audit trail of what was approved are all first-class data.

The concept comes from healthcare and insurance, where payers require clinical evidence before approving a procedure or medication. In InboxIQ the same pattern applies any time a founder or team lead wants to delegate *most* email handling to AI but stay in control of the high-stakes exceptions.

---

## Why InboxIQ needs it

The Business plan's auto-send feature is where this becomes load-bearing. Auto-send is currently binary — on or off per account. In practice, a user wants:

- Auto-send for routine replies (pricing questions, password resets, order confirmations)
- Hold for human approval on refunds, legal claims, churn risks, escalations, and anything with negative sentiment

Prior auth resolves that tension without requiring the user to turn off auto-send entirely. It is also what prevents the "AI sent a bad refund reply at 11pm" incident that would permanently damage trust in the product.

---

## General implementation (cross-industry)

### New model: `ApprovalPolicy`

```python
# src/models/automation.py

class ApprovalPolicy(db.Model):
    __tablename__ = "approval_policies"

    id             = db.Column(db.String(64), primary_key=True, default=lambda: str(uuid4()))
    account_id     = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=False)
    name           = db.Column(db.String(255), nullable=False)
    # Condition expression — same DSL as AutomationRule conditions
    condition_json = db.Column(db.JSON, nullable=False, default=dict)
    # Approver: user_id or a role string ("admin", "owner")
    approver_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    approver_role  = db.Column(db.String(64), nullable=True)
    # How long to wait before escalating or voiding the hold
    timeout_hours  = db.Column(db.Integer, nullable=False, default=4)
    timeout_action = db.Column(db.String(32), nullable=False, default="hold")  # hold | escalate | reject
    is_active      = db.Column(db.Boolean, nullable=False, default=True)
    created_at     = db.Column(db.DateTime(timezone=True), server_default=func.now())
    updated_at     = db.Column(db.DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
```

### New model: `ApprovalRequest`

```python
class ApprovalRequest(db.Model):
    __tablename__ = "approval_requests"

    id             = db.Column(db.String(64), primary_key=True, default=lambda: str(uuid4()))
    account_id     = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=False)
    policy_id      = db.Column(db.String(64), db.ForeignKey("approval_policies.id"), nullable=False)
    ticket_id      = db.Column(db.String(64), db.ForeignKey("inboxiq_tickets.id"), nullable=True)
    # Snapshot of the draft that is being held
    draft_snapshot = db.Column(db.Text, nullable=True)
    status         = db.Column(db.String(32), nullable=False, default="pending")  # pending | approved | rejected | expired
    approver_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    decided_at     = db.Column(db.DateTime(timezone=True), nullable=True)
    decision_note  = db.Column(db.Text, nullable=True)
    expires_at     = db.Column(db.DateTime(timezone=True), nullable=False)
    created_at     = db.Column(db.DateTime(timezone=True), server_default=func.now())
```

### Where the gate sits in the pipeline

```
Email arrives
    → DSPy triage (category, sentiment, risk_flag)
    → AutomationRule evaluation
    → [NEW] ApprovalPolicy check
          ↓ matches policy condition?
          YES → create ApprovalRequest, hold draft, notify approver
          NO  → proceed to auto-send as normal
    → Approver approves/modify/discard via gmail or outlook inbox native UI
    → If approved: send draft
    → If rejected or expired: route to inbox for manual handling
```

### Condition DSL (same as AutomationRule)

Conditions are evaluated against the ticket view dict. Examples:

```json
{"and": [
  {"field": "category", "op": "eq", "value": "billing"},
  {"field": "sentiment", "op": "eq", "value": "negative"}
]}
```

```json
{"or": [
  {"field": "risk_flag", "op": "eq", "value": true},
  {"field": "draft_body", "op": "contains", "value": "refund"}
]}
```

### Notification channel

Slack is the right first target — the approver receives a message with:

- Subject and sender of the held email
- The AI-generated draft reply
- Approve / Reject buttons (signed one-time URLs, TTL = `timeout_hours`)

In-app notification (InAppMessage) as a fallback if Slack is not connected.

### Celery task: expiry enforcement

```python
# src/tasks/approval.py

@celery.task
def expire_approval_requests():
    """Run every 30 minutes. Mark timed-out requests as expired and re-route tickets."""
    now = datetime.now(timezone.utc)
    expired = ApprovalRequest.query.filter(
        ApprovalRequest.status == "pending",
        ApprovalRequest.expires_at <= now,
    ).all()
    for req in expired:
        req.status = "expired"
        if req.ticket_id:
            ticket = Ticket.query.get(req.ticket_id)
            if ticket:
                ticket.status = "needs_review"
    db.session.commit()
```

### Audit trail

Every decision (approved / rejected / expired) is written to the existing `AuthEvent` / audit log table with `resource_type="approval_request"`, capturing who decided, when, and what was in the draft at the time of decision.

---

## Healthcare extension: FHIR-backed prior auth

In healthcare the prior auth flow is the same pattern with an additional retrieval step: clinical evidence must be fetched from the patient's EHR before the approval gate can be evaluated.

### Prerequisites

- FHIR R4 integration (Epic/Cerner/Athena SMART on FHIR OAuth 2.0)
- HIPAA Business Associate Agreements (BAAs) with AWS and all data subprocessors
- PHI handling policy: data must not be stored in plain text; encrypt at rest using existing `src/crypto.py`

### The agent chain

```
Payer prior auth request arrives via email
    → InboxIQ ingests and triages (category: "prior_auth_request")
    → EHR Retrieval Agent:
          - Extracts patient identifiers from email (name, DOB, MRN if present)
          - FHIR queries:
              GET /Patient?identifier=<mrn>
              GET /Condition?patient=<id>          # diagnosis / ICD-10
              GET /Procedure?patient=<id>          # procedure history / CPT
              GET /Observation?patient=<id>        # lab results
              GET /DocumentReference?patient=<id> # clinical notes
    → Reasoning Agent (DSPy):
          - Inputs: retrieved FHIR resources + payer coverage criteria (from KB)
          - Outputs: clinical justification narrative, supporting evidence citations
    → Draft reply generated with justification pre-populated
    → Guardrail evaluation (autonomous — no human gate):
          - Confidence score ≥ 0.85 + all required FHIR resources retrieved → submit immediately
          - Confidence score ≥ 0.85 + high-value claim (> £/$ threshold) → submit + flag in review queue (24h recall window)
          - Missing critical resources (no Condition, no Procedure) → retry with broader FHIR query before submitting
          - Confidence score < 0.85 → hold and surface in inbox for async clinician review (non-blocking)
    → Response submitted to payer autonomously in the majority of cases
```

### FHIR resources used

| Resource | Purpose |
|---|---|
| `Patient` | Resolve patient identity from request |
| `Condition` | ICD-10 diagnosis codes supporting medical necessity |
| `Procedure` | CPT codes, prior treatment history |
| `Observation` | Lab results, vitals supporting the request |
| `DocumentReference` | Clinical notes, referral letters |
| `CoverageEligibilityRequest` | Da Vinci Prior Auth IG — structured auth request |
| `ClaimResponse` | Payer's structured approval/denial response |

### EHR connection model

```python
# Extension to InboxConnection — provider = "fhir_ehr"
# config_json stores:
{
    "fhir_base_url": "https://fhir.epic.com/interconnect-fhir-oauth/api/FHIR/R4",
    "client_id": "...",
    "access_token_enc": "...",   # encrypted via src/crypto.py
    "refresh_token_enc": "...",
    "smart_scope": "patient/*.read",
    "ehr_vendor": "epic"         # epic | cerner | athena
}
```

### DSPy signature for clinical justification

```python
# src/dspy/signatures.py

class PriorAuthJustification(dspy.Signature):
    """Generate a clinical prior authorisation justification letter from retrieved EHR evidence."""
    payer_request: str = dspy.InputField(desc="The payer's prior auth request text")
    diagnosis_codes: str = dspy.InputField(desc="ICD-10 codes and descriptions from patient record")
    procedure_history: str = dspy.InputField(desc="Relevant prior procedures and outcomes")
    lab_results: str = dspy.InputField(desc="Supporting lab results and observations")
    coverage_criteria: str = dspy.InputField(desc="Payer's specific coverage criteria for this procedure")
    justification_letter: str = dspy.OutputField(desc="Clinical justification letter meeting payer criteria")
    supporting_citations: str = dspy.OutputField(desc="Specific evidence items cited from the patient record")
```

---

---

## Async guardrails instead of blocking approval gates

A hard synchronous gate (stop → wait for clinician → proceed) is the wrong design for claims and prior auth. It creates bottlenecks that replicate the exact administrative delay the product is meant to eliminate.

The better model is **confidence-gated async behaviour**:

| DSPy confidence score | Risk level | Action |
|---|---|---|
| High (> 0.85) | Low (routine denial, known CPT code) | Send automatically, log for 24h async review |
| High (> 0.85) | High (large dollar amount, complex appeal) | Send automatically, flag in review queue, 24h recall window |
| Low (< 0.85) | Any | Hold, notify clinician asynchronously, process other items |

The confidence score from the DSPy `PriorAuthJustification` module is the guardrail. Phoenix already captures these scores per trace — the threshold is configurable per `ApprovalPolicy`. This means:

- `timeout_action` becomes `proceed_and_flag | proceed_and_notify | hold` rather than `hold | escalate | reject`
- The default for most clinical workflows is `proceed_and_flag`
- The agent acts; a human can intervene within the review window
- Nothing blocks the pipeline unless the model explicitly signals low confidence

---

## Observability, evaluation and optimisation

*Based on the AgentOps Dashboard pattern (Clinical Documentation Agent → Payer Authorization Agent). Stack: Phoenix (Arize) via OTEL, Prometheus, DSPy native tracing — all self-hosted in the `kaley` namespace.*

### Agent architecture

```
Email (payer request)
    → Clinical Documentation Agent   [Phoenix span: clinical_doc_agent]
          ↓ FHIR queries to EHR
          ↓ produces: structured evidence bundle
    → Payer Authorization Agent      [Phoenix span: payer_auth_agent]
          ↓ DSPy: PriorAuthJustification
          ↓ ApprovalPolicy confidence check (autonomous guardrail)
    → Insurer portal submission / draft reply
```

The A2A handoff between the two agents is a discrete OTEL span. Phoenix captures both under the same root trace ID — full E2E duration visible at `phoenix.kalevent.com`.

---

### OBSERVABILITY — ready now, zero extra work

All four metrics are available immediately once `OTEL_ENABLED=true` and agent spans are instrumented. Phoenix already groups child spans under a root trace and displays per-tool latency breakdowns.

| Metric | What it measures | How captured | Status |
|---|---|---|---|
| **E2E Trace Duration** | Total time from email ingestion to submission | Phoenix root span duration | ✅ Ready — enable `OTEL_ENABLED=true` |
| **A2A Handoff Latency** | Time between Clinical Doc Agent completing and Payer Auth Agent starting | Delta between two child spans | ✅ Ready — falls out of Phoenix automatically |
| **Tool Execution Latency** | Per-FHIR-query latency (Patient, Condition, Procedure, etc.) | Phoenix tool call spans | ✅ Ready — each FHIR call is a tool span |
| **Cost per Authorization** | Token cost of both agents combined per request | Phoenix token counters → `DspyTrainingMetric` | ✅ Ready — `DspyTrainingMetric` already exists |

**Prometheus metrics to add to `src/monitoring/observability.py`:**

```python
prior_auth_e2e_duration = Histogram(
    "prior_auth_e2e_seconds",
    "End-to-end duration for prior auth pipeline",
    buckets=[1, 5, 10, 30, 60, 120, 300],
)
prior_auth_tool_latency = Histogram(
    "prior_auth_fhir_tool_latency_seconds",
    "Per-FHIR-resource query latency",
    ["resource_type"],  # Patient, Condition, Procedure, Observation
)
```

---

### EVALUATION — quality signals

| Metric | What it measures | How captured | Status |
|---|---|---|---|
| **Task completion rate** | % of requests that result in a submission (not abandoned) | `ApprovalRequest.status` distribution query | ✅ Ready — model exists, query is trivial |
| **Guardrail violations** | Low-confidence drafts recalled after auto-send | Count of `proceed_and_flag` decisions later recalled | ✅ Ready — derivable from `ApprovalRequest` + recall event |
| **Factual accuracy** | Does the justification letter correctly cite retrieved evidence? | DSPy `Assess` module comparing output citations to FHIR source | ⏳ Needs FHIR integration (Phase 4) |
| **Clinical appropriateness** | Did the payer accept the submission? | Payer response outcome logged back to `ApprovalRequest` | ⏳ Needs live payer responses (Phase 5) |
| **First-pass approval rate** | % approved by payer without appeal | `ApprovalRequest` outcome tracking over time | ⏳ Needs live payer responses (Phase 5) |

`DspyTrainingMetric` already stores per-module evaluation scores. Extend with a `context` field for `prior_auth` to isolate these from inbox triage metrics.

**Prometheus metric to add:**

```python
prior_auth_guardrail_violations = Counter(
    "prior_auth_guardrail_violations_total",
    "Low-confidence drafts recalled after auto-send",
    ["account_id"],
)
```

---

### OPTIMISATION — improvement loop

**Prompt token efficiency and flow step efficiency are not separate instrumentation tasks — they are natural outputs of MIPROv2 recompilation.** DSPy's optimisers rewrite and compress prompts to use fewer tokens while maintaining output quality. If FHIR queries are defined as `Tool` calls inside a `ReAct` or `ChainOfThought` module, the optimiser also learns over runs which tool calls are necessary for which input patterns — redundant calls are pruned from the reasoning trace automatically in each compiled artifact. Phoenix token counts then confirm the improvement after each recompilation.

The only prerequisite for both is a labelled corpus of prior auth outcomes (~50–100 runs where the payer response is known).

| Metric | What it measures | How captured | Status |
|---|---|---|---|
| **Prompt token efficiency** | Tokens used per successful authorisation | Implicit output of MIPROv2 recompilation — Phoenix token counts confirm improvement | ⏳ Automatic once corpus of ~50–100 labelled payer outcomes exists |
| **Flow step efficiency** | Redundant FHIR tool calls pruned per input pattern | Implicit output of MIPROv2 — ReAct/ChainOfThought learns which tools to skip | ⏳ Automatic once corpus of ~50–100 labelled payer outcomes exists |
| **Retrieval precision** | % of retrieved FHIR resources actually cited in output | `PriorAuthJustification.supporting_citations` vs bundle size | ⏳ Actionable from first FHIR runs (Phase 4) |
| **Handoff success rate** | % of Clinical Doc Agent outputs usable by Payer Auth Agent without fallback | Child span error rate in Phoenix | ⏳ Needs both agents live (Phase 4) |
| **Improvement velocity** | Rate of first-pass approval rate improvement per DSPy recompilation | `DspyTrainingMetric` trend over compiled artifact versions | ⏳ Lagging indicator — meaningful after Phase 5 |

MIPROv2 is run explicitly when the corpus is ready — it is not a background process. It rewrites the `PriorAuthJustification` prompts, produces a new compiled artifact in `dspy_artifacts/`, and is deployed like any other artifact. The training signal is `first_pass_approval_rate` — payer approvals are the ground truth labels.

**Prometheus metric to add:**

```python
prior_auth_first_pass_approvals = Counter(
    "prior_auth_first_pass_approvals_total",
    "Prior auth requests approved by payer on first submission",
    ["account_id", "payer"],
)
```

---

## Sequencing

| Phase | Scope | Prerequisite |
|---|---|---|
| Phase 1 | ApprovalPolicy + ApprovalRequest models, condition evaluation, in-app hold UI | None — builds on existing AutomationRule infrastructure |
| Phase 2 | Slack approval notifications with signed approve/reject URLs | Slack InboxConnection |
| Phase 3 | Expiry enforcement Celery task, audit trail, escalation routing | Phase 1 |
| Phase 4 | Healthcare: FHIR EHR retrieval agent | FHIR integration + HIPAA BAAs |
| Phase 5 | Da Vinci Prior Auth IG compliance, structured payer submission | Phase 4 + payer API agreements |

Phases 1–3 are purely general-purpose and can ship as part of Automation Studio without any healthcare-specific work. Phase 4 depends on completing the FHIR integration that is already flagged as a prerequisite for healthcare features.
