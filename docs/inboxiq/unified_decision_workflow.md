# Unified Decision Workflow (Production‑Ready)

This is the agreed end‑to‑end flow for multi‑channel intake and decisioning.

## 1) Polling Task (Source Fetch)
**Responsibility:** Connect + fetch raw messages only.  
**Does NOT decide anything.**

- Pulls from Gmail/Outlook (or other sources).
- Normalizes into a common payload shape (subject, body, sender, channel, metadata).
- Runs as a scheduled **Celery beat** job executed by the **Celery worker**.
- Enqueues to Intake (or directly to the triage queue when intake is already the canonical gateway).

## 2) Intake Agent (Normalization + Routing)
**Responsibility:** Clean, validate, enrich, then hand off.  
**Does NOT decide anything.**

- Validates required fields.
- Adds channel/source metadata (email/voice/chat/forms/CRM).
- Creates a canonical case JSON.
- Sends to Triage Agent queue (e.g., `triage.queue`).

## 3) Triage Agent (DSPy Decision Engine)
**Responsibility:** All decisions happen here.  
**DSPy is the only decision engine.**

- Runs `dspy_triage` / `DecisionProgram`.
- Outputs decision JSON: category, priority, intent, action_required, reason, workflow, escalation, owner/team, etc.
- If DSPy fails → return error (or fallback only if you allow it explicitly).

## 4) Ticket Creation (Post‑Decision)
**Responsibility:** Persist decision results.

- Create or update ticket **after** DSPy result exists.
- Save the decision JSON alongside the ticket for audit.

## Why this fixes the issue
Polling currently calls `triage_email()` (heuristics), which short‑circuits DSPy.  
Marketing emails get mis‑routed because DSPy never runs in that path.

## Explicit rule
We will remove heuristic decisioning from polling/intake.  
Only DSPy returns decisions. Heuristics are fallback only if explicitly allowed.
