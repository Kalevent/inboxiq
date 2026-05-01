# Unified Agent Architecture

**Date:** 2026-04-30
**Status:** Approved

---

## Problem

The codebase has three separate patterns for agentic work:

1. **Celery tasks** — `src/tasks/linkedin.py` runs multi-step enrichment + discovery inline, duplicating agent-loop logic in procedural task code.
2. **DSPy ReAct agent** — `src/automation/tool_calling_agent.py` (`ToolCallingAutomationAgent`) has a clean ReAct loop, MCP awareness, and execution logging but is automation-specific.
3. **Legacy pipeline** — `src/agents/worker.py` calls an external HTTP API (`/api/v1/agents/{id}/invoke`) that no longer exists and has been superseded for over a year.

The result: LinkedIn enrichment is brittle inline code, MCP servers registered in `MCPServerCatalog` are disconnected from the task layer, `AgentModel.mcp_servers` is written but never read, and `worker.py` is a landmine.

---

## Design

### Boundary Rule

> **If the task requires reasoning across multiple steps or tools → use an agent.**
> **If the task is a single deterministic operation → use a plain Celery task.**

Celery tasks fire the agent. They do not contain agent logic.

---

## Section 1: BaseAgent

Extract the reusable core from `ToolCallingAutomationAgent` into `src/agents/base.py`.

### What BaseAgent provides

```python
class BaseAgent:
    agent_name: str          # Used in logs and AgentEvent records
    account_id: int
    goal: str                # Set per execute() call

    def execute(self, goal: str) -> dict: ...   # Entry point
    def log(self, message: str) -> None: ...    # Appends to execution_log
    def _get_tools(self) -> list: ...           # Subclass overrides
    def _store_event(self, success, result, error): ...  # Writes AgentEvent row
```

### AgentEvent logging

`BaseAgent._store_event()` writes one `AgentEvent` row per execution:

| Field | Value |
|---|---|
| `agent_name` | e.g. `"linkedin_cadence"` |
| `account_id` | scoped to account |
| `goal` | the goal string passed to `execute()` |
| `success` | bool |
| `result_summary` | first 500 chars of agent output |
| `tool_calls_count` | number of tool invocations |
| `error_message` | on failure |
| `created_at` | UTC timestamp |

### MCP tool loading

`BaseAgent.__init__` reads `MCPServerCatalog` rows for the servers listed in `mcp_server_labels` (a class-level attribute on each subclass) and opens a `PersistentMCPClient` per server. These clients are accessible as `self._mcp[label]` inside tool methods.

Clients are closed after `execute()` returns (context manager on the agent).

### ToolCallingAutomationAgent

Refactored to extend `BaseAgent` instead of being self-contained. Its existing tools (`_tool_get_context_summary`, `_tool_evaluate_condition`, etc.) stay unchanged — they just live on a class that now inherits `execute()`, `log()`, and `_store_event()` from `BaseAgent`.

---

## Section 2: Two New Agents

### LinkedInCadenceAgent (`src/agents/linkedin_cadence.py`)

Replaces `linkedin.enrich_linkedin_urls`, `linkedin.discover_prospects`, `linkedin.draft_messages`, and `linkedin.send_digest` — four Celery tasks that today contain all the logic.

**Static tools** (plain Python callables, no MCP):

| Tool | What it does |
|---|---|
| `get_qualifying_leads` | Query `Lead` where `fit_score >= 7`, `linkedin_url IS NULL` |
| `add_to_prospect_queue` | Create `LinkedInProspect` rows from qualifying leads |
| `get_pending_prospects` | Query prospects with `status=pending`, `msg_1_draft IS NULL` |
| `save_drafted_messages` | Write `msg_1_draft`, `msg_2_draft`, `msg_3_draft` to prospect |
| `send_digest_email` | Call `send_linkedin_digest()` with due prospects |

**MCP tools** (via `PersistentMCPClient`, loaded from `MCPServerCatalog`):

| Tool | MCP server label | What it does |
|---|---|---|
| `find_decision_makers` | `lead-discovery` | SearXNG search for LinkedIn profiles |
| `browser_navigate` | `playwright-mcp` | Navigate to a URL |
| `browser_snapshot` | `playwright-mcp` | Extract page text for verification |

**Goal strings** (passed by Celery wrappers):
- `"Enrich qualifying leads with LinkedIn URLs"` → enrichment pass
- `"Promote qualified leads to prospect queue and draft outreach messages"` → discovery + drafting
- `"Send today's LinkedIn action digest"` → digest pass

**Celery wrappers** (replace existing tasks, keep the same task names for beat compatibility):

```python
@shared_task(name="linkedin.enrich_linkedin_urls")
def enrich_linkedin_urls():
    LinkedInCadenceAgent(account_id=_default_account()).execute(
        "Enrich qualifying leads with LinkedIn URLs"
    )

@shared_task(name="linkedin.discover_prospects")
def discover_prospects():
    LinkedInCadenceAgent(account_id=_default_account()).execute(
        "Promote qualified leads to prospect queue and draft outreach messages"
    )

@shared_task(name="linkedin.send_digest")
def send_digest_task():
    LinkedInCadenceAgent(account_id=_default_account()).execute(
        "Send today's LinkedIn action digest"
    )
```

`linkedin.draft_messages` beat entry is removed (merged into `discover_prospects` goal).

`_default_account()` iterates all `Account` rows and fires one agent per account — the same pattern used by the existing `discover_prospects` task which also loops all accounts implicitly through the `Lead` query.

---

### FunnelDiscoveryAgent (`src/agents/funnel_discovery.py`)

Replaces `funnel.discover_leads_via_search` and `funnel.discover_buying_signals`.

**Static tools**:

| Tool | What it does |
|---|---|
| `get_existing_companies` | Return company names already in `Lead` (dedup check) |
| `save_lead` | Write a verified `Lead` row after ICP scoring |
| `get_icp_config` | Load `ICPConfig` for the account (titles, industries, size, geographies) |

**MCP tools**:

| Tool | MCP server label |
|---|---|
| `discover_companies` | `lead-discovery` |
| `find_decision_makers` | `lead-discovery` |
| `find_buying_signals` | `lead-discovery` |
| `enrich_company` | `enrichment-v2` |
| `search` | `searxng` |

**Goal strings**:
- `"Discover new B2B SaaS companies matching ICP and add as leads"`
- `"Find buying signals (hiring, funding, expansion) and surface matching leads"`

---

## Section 3: Cleanup

### Delete `src/agents/worker.py`

The file has an embedded `DEPRECATION NOTICE` and calls an HTTP endpoint (`/api/v1/agents/{id}/invoke`) that no longer exists. Zero live callers — confirmed by grep. Remove the import from `celery_inboxiq.py` and delete the file.

### Register `playwright-mcp` in MCPServerCatalog

A data migration (not a schema migration) inserts one row:

```python
MCPServerCatalog(
    label="playwright-mcp",
    description="Playwright browser automation for profile verification and web research",
    command=["npx", "@playwright/mcp@latest"],
    env={},
    enabled=True,
)
```

This makes the Playwright server visible in Settings → Developer and loadable by `BaseAgent`.

### Fix `find_buying_committee` stub in `enrichment_v2_mcp.py`

The stub currently raises `NotImplementedError`. Replace with a real SearXNG search using the same pattern as `find_decision_makers`.

### AgentModel + AgentRegistry

These stay as-is. `BaseAgent.__init__` reads `MCPServerCatalog` directly by label — it does not go through `AgentRegistry`. `AgentModel` is used by the UI (Settings → Agents tab) and is not part of this change.

---

## File Map

| File | Action |
|---|---|
| `src/agents/base.py` | **New** — BaseAgent |
| `src/agents/linkedin_cadence.py` | **New** — LinkedInCadenceAgent |
| `src/agents/funnel_discovery.py` | **New** — FunnelDiscoveryAgent |
| `src/automation/tool_calling_agent.py` | **Refactor** — extend BaseAgent, remove duplicated internals |
| `src/tasks/linkedin.py` | **Simplify** — 3-line Celery wrappers only |
| `src/agents/worker.py` | **Delete** |
| `src/celery_inboxiq.py` | Remove `worker.py` import; remove `draft_messages` beat entry |
| `enrichment_v2_mcp.py` | Fix `find_buying_committee` stub |
| Data migration script | Insert `playwright-mcp` into `MCPServerCatalog` |

---

## What This Does Not Change

- Beat schedule timing (5am, 7am, 8am) — same task names, same crontab entries
- `AutomationRule` / Automation Studio — same execution path, just via extended `ToolCallingAutomationAgent`
- `AgentModel` and Settings → Agents UI — no change
- DSPy modules (`MessageDrafterModule`, `BlogPostMatcherModule`) — called from agent tools, not replaced
- MCP server implementations — no changes to `lead_discovery_mcp.py` or `enrichment_v2_mcp.py` beyond the stub fix
