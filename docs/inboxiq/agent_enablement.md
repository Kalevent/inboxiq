## InboxIQ AI Agent Enablement (MVP)

Goal: have a working AI triage agent (LLM-first, optional MCP) that takes inbound emails, classifies/structures them, and writes tickets. Uses only current codepaths.

### 1) Prereqs + config
- Env in pod: `DATABASE_URL`, `SECRET_KEY`, `JWT_SECRET_KEY`, `OPENAI_API_KEY` (optional `OLLAMA_*`), Redis (`REDIS_URL`).
- DB migrations applied to head: `flask db upgrade -d src/migrations`.
- Pod healthy: `kubectl logs -n kaley deploy/inboxiq -f` and `curl /health`.

### 2) Agent creation (LLM path, no MCP required)
- Create an agent (no auth enforced by default):
  ```bash
  BASE_URL=https://kalevent.com
  curl -s -X POST "$BASE_URL/api/v1/agents" \
    -H "Content-Type: application/json" \
    -d '{
      "name": "InboxIQ Triage",
      "description": "Classifies emails and creates tickets",
      "status": "published",
      "mcp_servers": [],
      "capabilities": ["triage"],
      "triggers": []
    }'
  ```
- Verify: `curl -s "$BASE_URL/api/v1/agents" | jq .`

### 3) Invoke the agent on an email (LLM mode)
- Use the built-in LLM path (`use_llm=true`); this uses `src/llm_client.py` with OpenAI primary, Ollama fallback.
  ```bash
  AGENT_ID=<returned_id>
  curl -s -X POST "$BASE_URL/api/v1/agents/$AGENT_ID/invoke" \
    -H "Content-Type: application/json" \
    -d '{
      "input": "Customer says they were double-charged on invoice #8831",
      "use_llm": true
    }' | jq .
  ```
- Expected: JSON with `llm_result` containing classification/summary.

### 4) Create tickets from emails (existing InboxIQ flow)
- For direct triage + ticket creation via LLM decisioning: use `/api/v1/inboxiq/triage` with a message payload or `seed_demo=true`.
  ```bash
  curl -s -X POST "$BASE_URL/api/v1/inboxiq/triage" \
    -H "Content-Type: application/json" \
    -d '{
      "messages": [{
        "subject": "Charged twice on invoice",
        "from_email": "customer@example.com",
        "body": "I was billed twice this month",
        "provider": "demo",
        "message_id": "demo-123"
      }]
    }' | jq .
  ```
- Expected: `summary.created` increments and a ticket record is returned.

### 5) Optional: add an MCP server command
- If you have a real MCP server, attach it to the agent via `mcp_servers`:
  ```bash
  curl -s -X POST "$BASE_URL/api/v1/agents/$AGENT_ID" -H "Content-Type: application/json" \
    -d '{
      "mcp_servers": [
        {"label": "triage", "command": ["python", "-m", "your_mcp_module"], "enabled": true}
      ]
    }'
  ```
- The invoke endpoint will prefer MCP when `tool`/`arguments` are provided and `use_llm` is not set.

### 6) Smoke checklist before inviting users
- `GET /health` returns 200.
- `GET /api/v1/agents` shows your agent with `status: published`.
- LLM invoke (step 3) returns 200 with content.
- Triage endpoint (step 4) creates a ticket (`tickets` table populated).
- Logs clean: `kubectl logs -n kaley deploy/inboxiq -f` shows no crash/traceback during invokes.

### 7) Optional: multi-agent collaboration (MVP orchestration)
- Define small, single-purpose agents:
  - **Intake (LLM-only):** normalize raw emails, extract intent/priority/sentiment/entities; return a structured payload; call the next agent.
  - **Triage/classifier (LLM + optional MCP):** enforce category/priority policy, dedup on `message_id/provider`, map to account/user, write tickets (primary agent).
  - **Knowledge/enrichment (optional MCP):** fetch account/customer context, past tickets, SLA; enrich decision.
  - **Action (optional MCP):** assignment, escalation, notifications (or keep in-app).
  - **Supervisor/router:** rule-based splitter (by provider/type) in the worker that chooses which agent to call next.
- Orchestrate in your worker (or a new handler): call agents sequentially, pass the enriched payload along, then create/update the ticket via existing `/api/v1/inboxiq/triage` logic. On any failure, fall back to the primary triage agent with `use_llm=true` to avoid drops.

### 8) MCP server considerations (optional)
- The repo does **not** ship an MCP server. If you want MCP-backed tools, you must provide a real command (Python, Node, etc.) in `mcp_servers`, e.g.:
  ```json
  "mcp_servers": [
    {"label": "triage-tools", "command": ["python", "-m", "your_mcp_module"], "enabled": true}
  ]
  ```
- If you do not have an MCP server, leave `mcp_servers` empty and rely on the LLM path (`use_llm=true` when invoking).
- When you add an MCP server, test it with the agent invoke endpoint (`tool` + `arguments`) and watch logs for errors.

### 9) Example payloads and routing pseudocode
- Create agents (examples):
  ```bash
  curl -s -X POST "$BASE_URL/api/v1/agents" -H "Content-Type: application/json" -d '{"name":"Intake","status":"published","mcp_servers":[]}'
  curl -s -X POST "$BASE_URL/api/v1/agents" -H "Content-Type: application/json" -d '{"name":"Triage","status":"published","mcp_servers":[]}'
  curl -s -X POST "$BASE_URL/api/v1/agents" -H "Content-Type: application/json" -d '{"name":"Enrichment","status":"published","mcp_servers":[]}'
  curl -s -X POST "$BASE_URL/api/v1/agents" -H "Content-Type: application/json" -d '{"name":"Action","status":"published","mcp_servers":[]}'
  ```
  Current prod agent IDs (captured from API responses):
  - Intake: `40e0e370-7ae0-4889-9486-1ab4a953193d`
  - Triage: `998cb300-a53a-49e0-9ed4-35c39076e88d`
  - Enrichment: `eccbe17f-ef77-48b0-9390-ec58d39d475e`

- Invoke intake (LLM mode):
  ```bash
  curl -s -X POST "$BASE_URL/api/v1/agents/<INTAKE_ID>/invoke" \
    -H "Content-Type: application/json" \
    -d '{"input":"Customer says they were double charged on invoice #8831","use_llm":true}'
  ```
- Invoke triage (LLM mode, expects normalized input):
  ```bash
  curl -s -X POST "$BASE_URL/api/v1/agents/<TRIAGE_ID>/invoke" \
    -H "Content-Type: application/json" \
    -d '{"input":"Normalized payload here","use_llm":true}'
  ```
- Pseudocode orchestrator (worker):
  ```python
  def process_email(raw_email):
      # Intake
      intake = invoke_agent(INTAKE_ID, input=raw_email, use_llm=True)
      normalized = intake.get("result") or intake.get("llm_result") or {}

      # Enrichment (optional)
      enriched = normalized
      try:
          enrich = invoke_agent(ENRICH_ID, input=str(normalized), use_llm=True)
          enriched = {**normalized, "context": enrich.get("result") or enrich.get("llm_result")}
      except Exception:
          pass  # fallback to normalized

      # Triage
      triage = invoke_agent(TRIAGE_ID, input=str(enriched), use_llm=True)
      decision = triage.get("result") or triage.get("llm_result") or {}

      # Persist ticket via existing endpoint
      create_ticket(enriched, decision)
  ```
  Keep a fallback: if any step fails, call the triage agent directly with `use_llm=true` on the raw email.

### 10) Plugging in the built-in MCP triage server (optional)
- We ship a minimal MCP server at `src/mcp/server.py` (requires `fastmcp`).
- Start it for local testing:
  ```bash
  python -m src.mcp.server   # transport=stdio
  ```
- Attach it to your Triage agent by updating `mcp_servers` with a real command:
  ```json
  "mcp_servers": [
    {"label": "triage-tools", "command": ["python", "-m", "src.mcp.server"], "enabled": true}
  ]
  ```
- Then invoke without `use_llm` (or with a specific `tool`/`arguments`) to hit MCP; otherwise keep `use_llm=true` for the LLM path.
