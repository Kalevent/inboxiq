# DSPy Implementation for Unified Support Agent

This document outlines a DSPy program design that supports unified intake across
voice, social, email, forms, chat, and CRM events. It also includes evaluation
schema, deployment notes, and labeling guidance aligned to current targets.

Targets:
- Success rate >= 95%
- Error rate <= 5%

## Table of contents
1. Canonical case object
2. DSPy signatures
3. Program composition
4. Tool-using version (optional)
5. Compilation (examples + metric)
6. Cross-channel usage
7. Before vs after (example flow)
8. Eval dataset schema
9. Deployment notes
10. Metrics report format
11. Data labeling guidelines

---

## 1) Canonical case object

Normalize every channel into the same schema before DSPy runs:

```python
case = {
  "channel": "email" | "voice" | "social" | "chat" | "form" | "crm",
  "text": "...",                 # transcript/body/message
  "metadata": {...},             # subject, timestamps, language, etc.
  "crm_snapshot": {...},         # customer profile, plan, open tickets, SLA tier
  "history": [...],              # prior turns/messages if any
}
```

DSPy modules take this and produce structured outputs.

---

## 2) DSPy signatures

DSPy’s strength is explicit input/output contracts.

### A) ExtractEntities

```python
import dspy

class ExtractEntitiesSig(dspy.Signature):
    case_json: str = dspy.InputField(desc="JSON of normalized case payload")

    entities_json: str = dspy.OutputField(desc="""
    JSON with keys:
      customer: {email?, phone?, crm_id?, name?}
      identifiers: {order_id?, invoice_id?, ticket_id?}
      product: {name?, sku?}
      intent: one of [refund, delivery_issue, login_issue, bug, billing, cancellation, other]
      sentiment: one of [positive, neutral, negative, angry, frustrated]
      urgency: one of [low, medium, high, critical]
      missing_info: [strings]
    Must be valid JSON only.
    """)
```

### B) RouteCase

```python
class RouteCaseSig(dspy.Signature):
    case_json: str = dspy.InputField()
    entities_json: str = dspy.InputField()

    route_json: str = dspy.OutputField(desc="""
    Valid JSON:
      queue: one of [billing, support_l1, support_l2, accounts, ops, fraud]
      priority: one of [P4, P3, P2, P1]
      sla_minutes: int
      tags: [strings]
      rationale: string
    """)
```

### C) SelectWorkflow

```python
class SelectWorkflowSig(dspy.Signature):
    case_json: str = dspy.InputField()
    entities_json: str = dspy.InputField()
    route_json: str = dspy.InputField()

    workflow_json: str = dspy.OutputField(desc="""
    Valid JSON:
      workflow_key: string   # e.g. "refund_standard", "delivery_tracking", "login_reset"
      required_tools: [strings]  # e.g. ["crm_lookup", "order_lookup", "refund_tool"]
      next_questions: [strings]  # if missing info
    """)
```

### D) EscalationDecision

```python
class EscalationDecisionSig(dspy.Signature):
    case_json: str = dspy.InputField()
    entities_json: str = dspy.InputField()
    route_json: str = dspy.InputField()
    workflow_json: str = dspy.InputField()

    escalation_json: str = dspy.OutputField(desc="""
    Valid JSON:
      decision: one of [auto_resolve, ask_clarifying, escalate_human, escalate_on_reply]
      reason: string
      required_role: one of [none, agent_l1, agent_l2, supervisor]
    """)
```

### E) DraftReply

```python
class DraftReplySig(dspy.Signature):
    case_json: str = dspy.InputField()
    entities_json: str = dspy.InputField()
    workflow_json: str = dspy.InputField()
    escalation_json: str = dspy.InputField()

    reply_text: str = dspy.OutputField(desc="""
    A customer-facing response suited to the channel.
    Voice: short sentences + confirmations.
    Social: concise, empathetic, request key ID.
    Email: structured, step-by-step, include next actions.
    Chat: conversational, ask 1-2 questions max.
    """)
```

---

## 3) Program composition

```python
class UnifiedSupportProgram(dspy.Module):
    def __init__(self):
        super().__init__()
        self.extract = dspy.ChainOfThought(ExtractEntitiesSig)
        self.route = dspy.Predict(RouteCaseSig)
        self.select = dspy.Predict(SelectWorkflowSig)
        self.escalate = dspy.Predict(EscalationDecisionSig)
        self.draft = dspy.ChainOfThought(DraftReplySig)

    def forward(self, case_json: str):
        entities_json = self.extract(case_json=case_json).entities_json
        route_json = self.route(case_json=case_json, entities_json=entities_json).route_json
        workflow_json = self.select(
            case_json=case_json, entities_json=entities_json, route_json=route_json
        ).workflow_json
        escalation_json = self.escalate(
            case_json=case_json,
            entities_json=entities_json,
            route_json=route_json,
            workflow_json=workflow_json,
        ).escalation_json
        reply_text = self.draft(
            case_json=case_json,
            entities_json=entities_json,
            workflow_json=workflow_json,
            escalation_json=escalation_json,
        ).reply_text

        return dspy.Prediction(
            entities_json=entities_json,
            route_json=route_json,
            workflow_json=workflow_json,
            escalation_json=escalation_json,
            reply_text=reply_text,
        )
```

---

## 4) Tool-using version (optional)

Use DSPy ReAct with tools like `crm_lookup()`, `order_lookup()`, or `kb_search()`.
Typically, `SelectWorkflow` or `EscalationDecision` becomes a ReAct module so
the agent can pull the data it needs before deciding.

---

## 5) Compilation: examples + metric

### A) Training examples

```python
trainset = [
  dspy.Example(
    case_json="...json...",
    gold_route_queue="billing",
    gold_priority="P2",
    gold_workflow_key="refund_standard",
    gold_escalation="ask_clarifying",
    resolved_in_turns=2,
  ).with_inputs("case_json"),
]
```

### B) Metric (routing + JSON validity + resolution)

```python
import json

def is_valid_json(s: str) -> bool:
    try:
        json.loads(s)
        return True
    except Exception:
        return False

def support_metric(gold, pred, N=3):
    score = 0.0

    json_ok = all([
        is_valid_json(pred.entities_json),
        is_valid_json(pred.route_json),
        is_valid_json(pred.workflow_json),
        is_valid_json(pred.escalation_json),
    ])
    if not json_ok:
        return 0.0

    ent = json.loads(pred.entities_json)
    route = json.loads(pred.route_json)
    wf = json.loads(pred.workflow_json)
    esc = json.loads(pred.escalation_json)

    if route.get("queue") == gold.gold_route_queue:
        score += 0.35
    if route.get("priority") == gold.gold_priority:
        score += 0.15
    if wf.get("workflow_key") == gold.gold_workflow_key:
        score += 0.30
    if esc.get("decision") == gold.gold_escalation:
        score += 0.10

    if getattr(gold, "resolved_in_turns", None) is not None:
        score += 0.10 if gold.resolved_in_turns <= N else 0.0

    return score
```

### C) Compile with BootstrapFewShot

```python
from dspy.teleprompt import BootstrapFewShot

optimizer = BootstrapFewShot(metric=support_metric, max_bootstrapped_demos=4)
compiled_program = optimizer.compile(UnifiedSupportProgram(), trainset=trainset)
```

---

## 6) Cross-channel usage

You do not need separate prompts per channel:

1) Normalize input to `case_json`
2) Run `compiled_program(case_json=...)`
3) Orchestrate tool calls and workflows based on outputs

The adaptive behavior comes from:
- Periodically recompiling with new labeled outcomes
- Using `SelectWorkflow` + `EscalationDecision` as the core decision points

---

## 7) Before vs after (example flow)

Example ticket: "I was charged twice this month. Please refund me."

### Before (heuristics / ad hoc prompts)
- Input: raw email body + subject
- Classification logic: prompt + scattered heuristics
- Output: fields may vary; errors are harder to trace
- Tuning: manual prompt edits, difficult to measure impact

### After (DSPy pipeline)
- Input: normalized `case_json` (channel + text + metadata)
- Step 1: Extract entities (billing, invoice_id, urgency)
- Step 2: Route case (queue=billing, priority=P2)
- Step 3: Select workflow (refund_standard)
- Step 4: Escalation decision (ask_clarifying if missing info)
- Step 5: Draft reply (request missing invoice ID, confirm refund policy)
- Result: structured, debuggable, measurable outputs with clear metrics

---

## 8) Eval dataset schema (fields + examples)

Target quality:
- >= 95% success
- <= 5% error

### Fields (minimum)
- `case_json` (string): normalized case payload
- `gold_route_queue` (string)
- `gold_priority` (string)
- `gold_workflow_key` (string)
- `gold_escalation` (string)
- `resolved_in_turns` (int, optional)
- `source` (string): email | chat | voice | form | social | crm
- `created_at` (iso8601 string)
- `account_id` (int)
- `ticket_id` (string, optional)

### Example rows

```json
{
  "case_json": "{\"channel\":\"email\",\"text\":\"I was charged twice...\",\"metadata\":{\"subject\":\"Double charge\"}}",
  "gold_route_queue": "billing",
  "gold_priority": "P2",
  "gold_workflow_key": "refund_standard",
  "gold_escalation": "ask_clarifying",
  "resolved_in_turns": 2,
  "source": "email",
  "created_at": "2026-01-24T12:00:00Z",
  "account_id": 20,
  "ticket_id": "a35f31f4-9a82-4aed-9537-93e87708cd5c"
}
```

```json
{
  "case_json": "{\"channel\":\"chat\",\"text\":\"Login error 500\",\"metadata\":{\"lang\":\"en\"}}",
  "gold_route_queue": "support_l2",
  "gold_priority": "P1",
  "gold_workflow_key": "login_reset",
  "gold_escalation": "escalate_human",
  "resolved_in_turns": 1,
  "source": "chat",
  "created_at": "2026-01-24T12:05:00Z",
  "account_id": 20
}
```

---

## 9) Deployment notes (env vars, eval run, retrain cadence)

### Required env vars (current levels)
- `DSPY_ENABLED=1`
- `DSPY_USE_OPENAI=1`
- `DSPY_MODEL=gpt-4o-mini`
- `OPENAI_API_KEY=...`
- `INBOXIQ_POLL_STALE_MINUTES=30` (optional, defaults to 30)

### Eval run

Run from the repo root:

```bash
python src/dspy_eval.py
```

### Retrain cadence
- Weekly for early-stage (fast iteration)
- Monthly once accuracy is stable
- On-demand after major label changes or workflow updates

---

## 10) Metrics report format (log + thresholds)

Recommended log fields:
- `timestamp`, `account_id`, `source`
- `category_acc`, `priority_acc`, `sentiment_acc`, `intent_acc`
- `action_required_acc`
- `routing_acc`, `workflow_acc`, `escalation_acc`
- `json_valid_rate`
- `error_rate`
- `avg_turns`

Thresholds:
- Success rate >= 95%
- Error rate <= 5%
- JSON valid rate >= 99%
- Action-required accuracy >= 90%

---

## 11) Data labeling guidelines (manual override mapping)

Use manual overrides to build gold labels:

- Ticket overrides:
  - `category`, `priority`, `sentiment`, `status` on the ticket become gold fields.
  - `status` maps to `action_required`:
    - `auto_handled` -> false
    - `optional` or `needs_review` -> optional
    - `new` or `open` -> true

- Feedback endpoint:
  - If `correct=false`, use provided fields as gold labels.
  - Use `note` to capture missing info or workflow mismatch.

Labeling tips:
- Prefer account-specific labels if categories differ by tenant.
- When uncertain, mark `escalation` as `ask_clarifying` rather than `auto_resolve`.
- Ensure JSON outputs remain valid (schema compliance is a hard gate in metrics).
