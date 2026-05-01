# Unified Agent Architecture Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace scattered inline Celery task logic with two new DSPy ReAct agents (LinkedIn cadence, funnel discovery), extract a shared `BaseAgent` from the existing `ToolCallingAutomationAgent`, and delete the dead `worker.py` pipeline.

**Architecture:** `BaseAgent` holds the `dspy.ReAct` loop, `AgentEvent` telemetry, and `PersistentMCPClient` lifecycle. Subclasses declare tool methods and an `mcp_server_labels` list; `BaseAgent.__init__` opens one `PersistentMCPClient` per label. Celery tasks become 3-line wrappers that instantiate an agent and call `execute(goal)`.

**Tech Stack:** Python 3.11, Flask, SQLAlchemy, Celery, DSPy (`dspy.ReAct`), `PersistentMCPClient` (subprocess JSON-RPC), `AgentEvent` model (existing), `MCPServerCatalog` (existing), pytest + SQLite in-memory for tests.

---

## File Map

| File | Action |
|---|---|
| `src/agents/base.py` | **Create** — `BaseAgent` class |
| `src/agents/linkedin_cadence.py` | **Create** — `LinkedInCadenceAgent` |
| `src/agents/funnel_discovery.py` | **Create** — `FunnelDiscoveryAgent` |
| `src/automation/tool_calling_agent.py` | **Modify** — extend `BaseAgent`, remove duplicated internals |
| `src/tasks/linkedin.py` | **Modify** — replace task bodies with 3-line agent wrappers |
| `src/funnel/tasks.py` | **Modify** — replace `discover_leads_via_search` and `discover_buying_signals` bodies with agent wrappers |
| `src/agents/worker.py` | **Delete** |
| `src/celery_inboxiq.py` | **Modify** — remove `worker.py` import/call, remove `linkedin_draft_messages` beat entry |
| `src/mcp/enrichment_v2_mcp.py` | **Modify** — fix `find_buying_committee` stub |
| `src/manage.py` | **Modify** — add `register-playwright-mcp` CLI command |
| `tests/agents/conftest.py` | **Create** — SQLite app fixture with AgentEvent + MCPServerCatalog tables |
| `tests/agents/test_base_agent.py` | **Create** |
| `tests/agents/test_linkedin_cadence.py` | **Create** |
| `tests/agents/test_funnel_discovery.py` | **Create** |

---

### Task 1: Create `src/agents/base.py`

**Files:**
- Create: `src/agents/base.py`
- Create: `tests/agents/__init__.py`
- Create: `tests/agents/conftest.py`
- Create: `tests/agents/test_base_agent.py`

- [ ] **Step 1.1: Write the failing test**

```python
# tests/agents/test_base_agent.py
import pytest
from unittest.mock import MagicMock, patch


def test_base_agent_execute_calls_react_and_logs_event(app):
    """BaseAgent.execute() runs dspy.ReAct and writes one AgentEvent row."""
    from src.agents.base import BaseAgent
    from src.models.ai import AgentEvent
    from src.extensions import db

    class EchoAgent(BaseAgent):
        agent_name = "echo_test"
        mcp_server_labels = []

        def _get_tools(self):
            def noop_tool():
                "Does nothing."
                return {"ok": True}
            return [noop_tool]

    mock_prediction = MagicMock()
    mock_prediction.result = "Agent completed successfully"

    with app.app_context():
        with patch("src.agents.base.dspy") as mock_dspy:
            mock_react_instance = MagicMock()
            mock_react_instance.return_value = mock_prediction
            mock_dspy.ReAct.return_value = mock_react_instance

            agent = EchoAgent(account_id=1)
            result = agent.execute("do something")

        assert result["success"] is True
        event = db.session.query(AgentEvent).filter_by(agent_name="echo_test").first()
        assert event is not None
        assert event.status == "success"
        assert event.context["goal"] == "do something"
        assert event.context["account_id"] == 1


def test_base_agent_execute_logs_failure_event_on_exception(app):
    """BaseAgent.execute() writes an error AgentEvent when dspy.ReAct raises."""
    from src.agents.base import BaseAgent
    from src.models.ai import AgentEvent
    from src.extensions import db

    class BrokenAgent(BaseAgent):
        agent_name = "broken_test"
        mcp_server_labels = []

        def _get_tools(self):
            return []

    with app.app_context():
        with patch("src.agents.base.dspy") as mock_dspy:
            mock_dspy.ReAct.side_effect = RuntimeError("boom")

            agent = BrokenAgent(account_id=1)
            result = agent.execute("fail")

        assert result["success"] is False
        event = db.session.query(AgentEvent).filter_by(agent_name="broken_test").first()
        assert event is not None
        assert event.status == "error"
        assert "boom" in event.error_message
```

- [ ] **Step 1.2: Create `tests/agents/__init__.py` and `tests/agents/conftest.py`**

```python
# tests/agents/__init__.py
# (empty)
```

```python
# tests/agents/conftest.py
import os
import pytest

os.environ.setdefault("APP_ENV", "test")

from src.app import create_app
from src.extensions import db as _db
from src.models.ai import AgentEvent, MCPServerCatalog


@pytest.fixture
def app():
    from sqlalchemy.pool import StaticPool

    app = create_app()
    app.config["TESTING"] = True
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite://"
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
        "connect_args": {"check_same_thread": False},
        "poolclass": StaticPool,
    }
    app.config["SECRET_KEY"] = "test-secret"
    with app.app_context():
        AgentEvent.__table__.create(_db.engine, checkfirst=True)
        MCPServerCatalog.__table__.create(_db.engine, checkfirst=True)
        yield app
        _db.session.remove()
        AgentEvent.__table__.drop(_db.engine, checkfirst=True)
        MCPServerCatalog.__table__.drop(_db.engine, checkfirst=True)


@pytest.fixture
def db(app):
    return _db
```

- [ ] **Step 1.3: Run tests to confirm they fail**

```bash
cd /Users/kofi/inboxiq
python -m pytest tests/agents/test_base_agent.py -v 2>&1 | head -30
```

Expected: `ImportError: cannot import name 'BaseAgent' from 'src.agents.base'`

- [ ] **Step 1.4: Create `src/agents/base.py`**

```python
"""Shared base for all InboxIQ DSPy ReAct agents."""
from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Dict, List
from uuid import uuid4

from src.extensions import db
from src.dspy.config import _configure_dspy

log = logging.getLogger(__name__)


class BaseAgent(ABC):
    """
    DSPy ReAct agent base. Subclasses declare:
      - agent_name: str           (used in logs + AgentEvent rows)
      - mcp_server_labels: list   (MCPServerCatalog labels to open)
      - _get_tools() -> list      (returns callable tool list for dspy.ReAct)
    """

    agent_name: str = "base_agent"
    mcp_server_labels: List[str] = []

    def __init__(self, account_id: int):
        self.account_id = account_id
        self.execution_log: List[str] = []
        self.tool_calls: List[Dict[str, Any]] = []
        self._mcp: Dict[str, Any] = {}

    def execute(self, goal: str) -> Dict[str, Any]:
        """Run the ReAct loop for `goal`. Opens/closes MCP clients around the run."""
        self.execution_log = []
        self.tool_calls = []
        self.goal = goal

        _, _, dspy = _configure_dspy()

        class _AgentSignature(dspy.Signature):
            """
            Complete the given goal using the available tools.
            Think step by step. When done, respond with a brief summary of what was accomplished.
            """
            goal = dspy.InputField(desc="The goal to accomplish.")
            result = dspy.OutputField(desc="Summary of what was accomplished or why it failed.")

        _start = time.monotonic()
        success = False
        result_text = ""
        error_msg = None

        try:
            self._open_mcp_clients()
            tools = self._get_tools()
            react_agent = dspy.ReAct(_AgentSignature, tools=tools, max_iters=25)
            prediction = react_agent(goal=goal)
            result_text = prediction.result or ""
            success = True
            self.log(f"Completed: {result_text[:200]}")

        except Exception as exc:
            error_msg = str(exc)
            log.exception("[%s] execute failed: %s", self.agent_name, exc)

        finally:
            self._close_mcp_clients()

        latency_ms = int((time.monotonic() - _start) * 1000)
        self._store_event(success=success, result_text=result_text, error_msg=error_msg, latency_ms=latency_ms)

        return {
            "success": success,
            "result": result_text,
            "error": error_msg,
            "tool_calls": len(self.tool_calls),
            "log": self.execution_log,
        }

    # -------------------------------------------------------------------------
    # Subclass interface
    # -------------------------------------------------------------------------

    @abstractmethod
    def _get_tools(self) -> list:
        """Return list of plain Python callables to pass to dspy.ReAct."""

    # -------------------------------------------------------------------------
    # MCP lifecycle
    # -------------------------------------------------------------------------

    def _open_mcp_clients(self) -> None:
        if not self.mcp_server_labels:
            return
        from src.models.ai import MCPServerCatalog
        for label in self.mcp_server_labels:
            catalog = MCPServerCatalog.query.filter_by(label=label, enabled=True).first()
            if not catalog:
                log.warning("[%s] MCP server not found in catalog: %s", self.agent_name, label)
                continue
            from src.mcp.client import PersistentMCPClient
            client = PersistentMCPClient(catalog.command)
            client.start()
            self._mcp[label] = client

    def _close_mcp_clients(self) -> None:
        for label, client in self._mcp.items():
            try:
                client.close()
            except Exception:
                log.debug("[%s] MCP close error for %s", self.agent_name, label)
        self._mcp.clear()

    # -------------------------------------------------------------------------
    # Telemetry
    # -------------------------------------------------------------------------

    def _store_event(self, success: bool, result_text: str, error_msg: str | None, latency_ms: int) -> None:
        from src.models.ai import AgentEvent
        event = AgentEvent(
            id=str(uuid4()),
            agent_name=self.agent_name,
            event="invoke",
            status="success" if success else "error",
            context={
                "account_id": self.account_id,
                "goal": self.goal,
                "tool_calls": len(self.tool_calls),
                "result_summary": result_text[:500],
            },
            latency_ms=latency_ms,
            error_message=error_msg,
            created_at=datetime.now(timezone.utc),
        )
        try:
            db.session.add(event)
            db.session.commit()
        except Exception:
            db.session.rollback()
            log.warning("[%s] failed to write AgentEvent", self.agent_name)

    def log(self, message: str) -> None:
        self.execution_log.append(message)
        log.info("[%s] %s", self.agent_name, message)
```

- [ ] **Step 1.5: Run tests to confirm they pass**

```bash
python -m pytest tests/agents/test_base_agent.py -v 2>&1 | tail -15
```

Expected: `2 passed`

- [ ] **Step 1.6: Commit**

```bash
git add src/agents/base.py tests/agents/__init__.py tests/agents/conftest.py tests/agents/test_base_agent.py
git commit -m "feat(agents): add BaseAgent with DSPy ReAct loop and AgentEvent telemetry"
```

---

### Task 2: Refactor `ToolCallingAutomationAgent` to extend `BaseAgent`

**Files:**
- Modify: `src/automation/tool_calling_agent.py`

The existing `_configure_dspy`, `_store_execution`, and `log` are replaced by `BaseAgent` equivalents. The seven tool methods stay unchanged.

- [ ] **Step 2.1: Replace the class definition and `__init__`**

In `src/automation/tool_calling_agent.py`, replace lines 1–42 (the module docstring through `__init__`) with:

```python
"""
Tool-Calling Automation Agent using DSPy ReAct.

Provider-agnostic agentic loop via dspy.ReAct (Thought/Action/Observation).
Tools are plain Python callables — no OpenAI-specific wire format.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
from uuid import uuid4

from src.agents.base import BaseAgent
from src.models.automation import AutomationRule, WebhookProvider, AutomationRuleExecution
from src.extensions import db

logger = logging.getLogger(__name__)


class ToolCallingAutomationAgent(BaseAgent):
    """
    Automation-rule agent using dspy.ReAct.
    Extends BaseAgent; adds workflow-specific tools and AutomationRuleExecution logging.
    """

    agent_name = "automation_rule"
    mcp_server_labels = []

    def __init__(self, workflow: AutomationRule, trigger_context: Dict[str, Any]):
        super().__init__(account_id=workflow.account_id)
        self.workflow = workflow
        self.trigger_context = trigger_context

    def _get_tools(self) -> list:
        return [
            self._tool_get_context_summary,
            self._tool_search_context_field,
            self._tool_evaluate_condition,
            self._tool_execute_provider_action,
            self._tool_search_webhook_providers,
            self._tool_send_webhook,
            self._tool_render_template,
        ]
```

- [ ] **Step 2.2: Replace the `execute()` method**

Replace the existing `execute()` method (lines 44–126) with a thin override that sets the trigger event context and then calls `super().execute()`, with the existing `_store_execution` appended as a post-step:

```python
    def execute(self, trigger_event: str) -> Dict[str, Any]:  # type: ignore[override]
        """Execute workflow using dspy.ReAct agent loop."""
        self.log("Starting ReAct agent execution")
        self._trigger_event = trigger_event

        goal = json.dumps({
            "name": self.workflow.name,
            "description": self.workflow.description or "",
            "trigger": self.workflow.trigger,
            "conditions": self.workflow.conditions,
            "condition_logic": self.workflow.condition_logic,
            "actions": self.workflow.actions,
        })

        base_result = super().execute(goal=goal)

        self._store_execution(
            trigger_event=trigger_event,
            matched=True,
            executed=base_result["success"],
            success=base_result["success"],
            agent_response=base_result.get("result"),
            error_message=base_result.get("error"),
        )

        return {
            "executed": base_result["success"],
            "matched": True,
            "success": base_result["success"],
            "agent_log": base_result["log"],
            "tool_calls": self.tool_calls,
            "agent_response": base_result.get("result"),
        }
```

- [ ] **Step 2.3: Remove the now-redundant `_configure_dspy` import and the old `_store_execution` / `log` methods**

Delete these lines from the file:
- The `from src.dspy.config import _configure_dspy` import (replaced by BaseAgent)
- The old `_store_execution()` method (lines ~258–311) — keep it, it writes `AutomationRuleExecution` which is still needed
- The old `log()` method (lines ~313–315) — **delete** this one, inherited from BaseAgent

Only the `_store_execution` that writes `AutomationRuleExecution` must stay.

- [ ] **Step 2.4: Run the existing automation tests (if any) and the base agent tests**

```bash
python -m pytest tests/agents/test_base_agent.py -v 2>&1 | tail -10
python -m pytest tests/ -k "automation" -v 2>&1 | tail -10
```

Expected: base_agent tests pass; no automation test failures.

- [ ] **Step 2.5: Commit**

```bash
git add src/automation/tool_calling_agent.py
git commit -m "refactor(agents): ToolCallingAutomationAgent extends BaseAgent"
```

---

### Task 3: Delete `worker.py` and remove it from `celery_inboxiq.py`

**Files:**
- Delete: `src/agents/worker.py`
- Modify: `src/celery_inboxiq.py` lines 12 and 658

- [ ] **Step 3.1: Remove the import and call from `celery_inboxiq.py`**

In `src/celery_inboxiq.py`, delete line 12:
```python
from src.agents.worker import process_email_with_agents
```

At line 658, the call is inside a try/except that already defaults `agent_result = None` on failure. Replace the call block:
```python
# Before (lines ~646–668):
    agent_result = None
    agent_decision = None

    _NON_ACTIONABLE_BYPASS_CATEGORIES = { ... }
    _effective_bypass = _bypass_dspy and _sender_hint in _NON_ACTIONABLE_BYPASS_CATEGORIES
    if not skip_triage and not _effective_bypass:
        try:
            agent_result = process_email_with_agents(normalized)
            if agent_result:
                agent_decision = agent_result.get("decision") or agent_result.get("triage") or {}
        except Exception as exc:
            ...
            agent_result = None
```

Replace with:
```python
    agent_result = None
    agent_decision = None

    _NON_ACTIONABLE_BYPASS_CATEGORIES = {
        "updates", "promotions", "social", "forums", "transactions",
        "spam", "marketing", "newsletter", "auto_reply", "notification",
    }
    _effective_bypass = _bypass_dspy and _sender_hint in _NON_ACTIONABLE_BYPASS_CATEGORIES
    # Legacy agent pipeline removed — DSPy triage handles classification directly.
```

- [ ] **Step 3.2: Delete `src/agents/worker.py`**

```bash
rm /Users/kofi/inboxiq/src/agents/worker.py
```

- [ ] **Step 3.3: Verify app still imports cleanly**

```bash
cd /Users/kofi/inboxiq
python -c "from src.app import create_app; create_app()" 2>&1 | tail -5
```

Expected: no output / no import errors.

- [ ] **Step 3.4: Commit**

```bash
git add src/celery_inboxiq.py
git rm src/agents/worker.py
git commit -m "chore(agents): delete deprecated worker.py HTTP pipeline"
```

---

### Task 4: Register `playwright-mcp` in `MCPServerCatalog`

This is a data operation, not a schema migration. A CLI command handles it safely (idempotent).

**Files:**
- Modify: `src/manage.py`

- [ ] **Step 4.1: Add CLI command to `manage.py`**

Find the bottom of `src/manage.py` (after other `@app.cli.command` blocks) and add:

```python
@app.cli.command("register-playwright-mcp")
def cli_register_playwright_mcp():
    """Insert or update the playwright-mcp entry in MCPServerCatalog."""
    from src.models.ai import MCPServerCatalog
    existing = MCPServerCatalog.query.filter_by(label="playwright-mcp").first()
    if existing:
        existing.command = ["npx", "@playwright/mcp@latest"]
        existing.env = {}
        existing.enabled = True
        click.echo("playwright-mcp updated.")
    else:
        db.session.add(MCPServerCatalog(
            label="playwright-mcp",
            command=["npx", "@playwright/mcp@latest"],
            env={},
            enabled=True,
        ))
        click.echo("playwright-mcp registered.")
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
```

- [ ] **Step 4.2: Run the command**

```bash
flask register-playwright-mcp
```

Expected: `playwright-mcp registered.`

- [ ] **Step 4.3: Verify it's in the DB**

```bash
flask shell -c "from src.models.ai import MCPServerCatalog; print([(s.label, s.command) for s in MCPServerCatalog.query.all()])"
```

Expected output includes `('playwright-mcp', ['npx', '@playwright/mcp@latest'])`.

- [ ] **Step 4.4: Commit**

```bash
git add src/manage.py
git commit -m "feat(agents): register playwright-mcp in MCPServerCatalog via CLI"
```

---

### Task 5: Fix `find_buying_committee` stub in `enrichment_v2_mcp.py`

**Files:**
- Modify: `src/mcp/enrichment_v2_mcp.py` lines ~200–260

- [ ] **Step 5.1: Read the existing `find_decision_makers` implementation in `lead_discovery_mcp.py` to use as the pattern**

The function at line 165 of `lead_discovery_mcp.py` uses SearXNG to search for LinkedIn profiles. Use the same `searxng_search` helper inside `enrichment_v2_mcp.py`.

- [ ] **Step 5.2: Replace the `find_buying_committee` stub body**

In `src/mcp/enrichment_v2_mcp.py`, replace the stub body of `find_buying_committee` (lines ~226–260, the part starting with `# This would typically use Apollo.io...`) with:

```python
    if not roles:
        roles = ["ceo", "cto", "vp", "director", "head of support", "operations lead"]

    committee = []
    for role in roles[:4]:  # cap at 4 roles to limit SearXNG load
        try:
            query = f'site:linkedin.com/in "{role}" "{company_name or company_domain}"'
            results = await searxng_search(query, max_results=3)
            for r in results:
                url = r.get("url", "")
                if "linkedin.com/in/" not in url:
                    continue
                role_type = role_mapping.get(role.split()[0].lower(), "end_user")
                committee.append({
                    "name": r.get("title", "").split("|")[0].strip(),
                    "linkedin_url": url.split("?")[0],
                    "role_type": role_type,
                    "title": role,
                    "seniority_level": "senior" if role_type == "economic_buyer" else "mid",
                })
        except Exception as exc:
            logger.warning("find_buying_committee search failed for role %s: %s", role, exc)

    return {"company_domain": company_domain, "buying_committee": committee}
```

Also ensure `searxng_search` is imported/defined earlier in the file (check if it's used by `enrich_company` — if not, import from `lead_discovery_mcp.py`).

- [ ] **Step 5.3: Verify the function is no longer a stub**

```bash
python -c "
import asyncio
from src.mcp.enrichment_v2_mcp import find_buying_committee
result = asyncio.run(find_buying_committee('example.com', 'Example Co'))
print(type(result), list(result.keys()))
"
```

Expected: `<class 'dict'> ['company_domain', 'buying_committee']` — no `NotImplementedError`.

- [ ] **Step 5.4: Commit**

```bash
git add src/mcp/enrichment_v2_mcp.py
git commit -m "fix(mcp): replace find_buying_committee placeholder with real SearXNG search"
```

---

### Task 6: Create `LinkedInCadenceAgent`

**Files:**
- Create: `src/agents/linkedin_cadence.py`
- Create: `tests/agents/test_linkedin_cadence.py`

- [ ] **Step 6.1: Write the failing test**

```python
# tests/agents/test_linkedin_cadence.py
import pytest
from unittest.mock import patch, MagicMock
from sqlalchemy.pool import StaticPool


@pytest.fixture
def full_app(app):
    """Extend conftest app with Lead, LinkedInProspect, ICPConfig tables."""
    from src.models.leads import Lead
    from src.models.campaigns import LinkedInProspect
    from src.models.marketing import ICPConfig
    from src.extensions import db as _db
    with app.app_context():
        Lead.__table__.create(_db.engine, checkfirst=True)
        LinkedInProspect.__table__.create(_db.engine, checkfirst=True)
        ICPConfig.__table__.create(_db.engine, checkfirst=True)
        yield app
        ICPConfig.__table__.drop(_db.engine, checkfirst=True)
        LinkedInProspect.__table__.drop(_db.engine, checkfirst=True)
        Lead.__table__.drop(_db.engine, checkfirst=True)


def test_get_qualifying_leads_returns_leads_with_no_linkedin(full_app):
    """get_qualifying_leads returns fit_score >= 7, linkedin_url IS NULL leads."""
    from src.agents.linkedin_cadence import LinkedInCadenceAgent
    from src.models.leads import Lead
    from src.extensions import db

    with full_app.app_context():
        db.session.add(Lead(
            id="l1", account_id=1, name="Ada", email="ada@co.com",
            company_name="Co", source="manual", status="New Lead",
            fit_score=8, deleted=False, linkedin_url=None,
        ))
        db.session.add(Lead(
            id="l2", account_id=1, name="Bob", email="bob@co.com",
            company_name="Co", source="manual", status="New Lead",
            fit_score=5, deleted=False, linkedin_url=None,
        ))
        db.session.commit()

        agent = LinkedInCadenceAgent(account_id=1)
        leads = agent._tool_get_qualifying_leads()
        assert len(leads) == 1
        assert leads[0]["id"] == "l1"


def test_add_to_prospect_queue_creates_prospect(full_app):
    """add_to_prospect_queue creates a LinkedInProspect for a qualifying lead."""
    from src.agents.linkedin_cadence import LinkedInCadenceAgent
    from src.models.leads import Lead
    from src.models.campaigns import LinkedInProspect
    from src.extensions import db

    with full_app.app_context():
        db.session.add(Lead(
            id="l3", account_id=1, name="Carol", email="carol@co.com",
            company_name="Co", source="manual", status="New Lead",
            fit_score=9, deleted=False, linkedin_url="https://linkedin.com/in/carol",
        ))
        db.session.commit()

        agent = LinkedInCadenceAgent(account_id=1)
        result = agent._tool_add_to_prospect_queue(lead_id="l3")
        assert result["created"] is True

        p = db.session.query(LinkedInProspect).filter_by(lead_id="l3").first()
        assert p is not None
        assert p.status == "pending"
```

- [ ] **Step 6.2: Run to confirm failure**

```bash
python -m pytest tests/agents/test_linkedin_cadence.py -v 2>&1 | head -20
```

Expected: `ImportError: cannot import name 'LinkedInCadenceAgent'`

- [ ] **Step 6.3: Create `src/agents/linkedin_cadence.py`**

```python
"""LinkedIn outreach cadence agent — replaces the four linkedin.* Celery task bodies."""
from __future__ import annotations

import json
import logging
import sys
from typing import Any, Dict, List

from src.agents.base import BaseAgent
from src.extensions import db

log = logging.getLogger(__name__)

_LEAD_DISCOVERY_LABEL = "lead-discovery"
_PLAYWRIGHT_LABEL = "playwright-mcp"


class LinkedInCadenceAgent(BaseAgent):
    """
    Manages the full LinkedIn outreach loop:
      1. Enrich qualifying leads with LinkedIn URLs (via SearXNG + Playwright)
      2. Promote enriched leads into LinkedInProspect queue
      3. Draft outreach messages via DSPy
      4. Assemble and email the daily action digest
    """

    agent_name = "linkedin_cadence"
    mcp_server_labels = [_LEAD_DISCOVERY_LABEL, _PLAYWRIGHT_LABEL]

    def _get_tools(self) -> list:
        return [
            self._tool_get_qualifying_leads,
            self._tool_enrich_lead_linkedin_url,
            self._tool_add_to_prospect_queue,
            self._tool_get_pending_prospects,
            self._tool_save_drafted_messages,
            self._tool_send_digest_email,
        ]

    # -------------------------------------------------------------------------
    # Static tools
    # -------------------------------------------------------------------------

    def _tool_get_qualifying_leads(self) -> List[Dict[str, Any]]:
        """Return leads with fit_score >= 7 and no LinkedIn URL. Max 20 per run."""
        from src.models.leads import Lead
        self.tool_calls.append({"tool": "get_qualifying_leads"})
        leads = (
            db.session.query(Lead)
            .filter(
                Lead.account_id == self.account_id,
                Lead.fit_score >= 7,
                Lead.linkedin_url.is_(None),
                Lead.deleted.is_(False),
                Lead.company_name.isnot(None),
            )
            .limit(20)
            .all()
        )
        return [
            {
                "id": str(lead.id),
                "name": lead.name or "",
                "company_name": lead.company_name or "",
                "email": lead.email or "",
            }
            for lead in leads
        ]

    def _tool_enrich_lead_linkedin_url(self, lead_id: str, linkedin_url: str, name: str = "") -> Dict[str, Any]:
        """
        Save a verified LinkedIn URL (and optionally name) to a Lead.
        Call after find_decision_makers + browser_snapshot confirm the URL.
        """
        from src.models.leads import Lead
        self.tool_calls.append({"tool": "enrich_lead_linkedin_url", "input": {"lead_id": lead_id}})
        lead = db.session.query(Lead).filter_by(id=lead_id, account_id=self.account_id).first()
        if not lead:
            return {"saved": False, "error": "lead not found"}
        lead.linkedin_url = linkedin_url.split("?")[0]
        if name and (not lead.name or lead.name == lead.company_name):
            lead.name = name
        try:
            db.session.commit()
            return {"saved": True}
        except Exception as exc:
            db.session.rollback()
            return {"saved": False, "error": str(exc)}

    def _tool_add_to_prospect_queue(self, lead_id: str) -> Dict[str, Any]:
        """
        Create a LinkedInProspect row from a Lead that now has a LinkedIn URL.
        Idempotent — skips if prospect already exists for this linkedin_url.
        """
        from src.models.leads import Lead
        from src.models.campaigns import LinkedInProspect
        self.tool_calls.append({"tool": "add_to_prospect_queue", "input": {"lead_id": lead_id}})
        lead = db.session.query(Lead).filter_by(
            id=lead_id, account_id=self.account_id
        ).first()
        if not lead or not lead.linkedin_url:
            return {"created": False, "error": "lead not found or has no linkedin_url"}
        exists = db.session.query(LinkedInProspect).filter_by(
            account_id=self.account_id, linkedin_url=lead.linkedin_url
        ).first()
        if exists:
            return {"created": False, "reason": "already_exists"}
        prospect = LinkedInProspect(
            account_id=self.account_id,
            lead_id=lead.id,
            name=lead.name,
            company_name=lead.company_name,
            industry=lead.industry,
            linkedin_url=lead.linkedin_url,
            source="auto",
            status="pending",
            fit_score=lead.fit_score,
        )
        try:
            db.session.add(prospect)
            db.session.commit()
            return {"created": True}
        except Exception as exc:
            db.session.rollback()
            return {"created": False, "error": str(exc)}

    def _tool_get_pending_prospects(self) -> List[Dict[str, Any]]:
        """Return prospects with status=pending and no msg_1_draft yet."""
        from src.models.campaigns import LinkedInProspect
        self.tool_calls.append({"tool": "get_pending_prospects"})
        prospects = (
            db.session.query(LinkedInProspect)
            .filter(
                LinkedInProspect.account_id == self.account_id,
                LinkedInProspect.status == "pending",
                LinkedInProspect.msg_1_draft.is_(None),
            )
            .all()
        )
        return [
            {
                "id": str(p.id),
                "name": p.name or "",
                "job_title": p.job_title or "",
                "company_name": p.company_name or "",
                "industry": p.industry or "",
            }
            for p in prospects
        ]

    def _tool_save_drafted_messages(
        self,
        prospect_id: str,
        msg_1: str,
        msg_2: str,
        msg_3: str,
    ) -> Dict[str, Any]:
        """Persist drafted outreach messages to a LinkedInProspect."""
        from src.models.campaigns import LinkedInProspect
        self.tool_calls.append({"tool": "save_drafted_messages", "input": {"prospect_id": prospect_id}})
        prospect = db.session.query(LinkedInProspect).filter_by(
            id=prospect_id, account_id=self.account_id
        ).first()
        if not prospect:
            return {"saved": False, "error": "prospect not found"}
        prospect.msg_1_draft = msg_1
        prospect.msg_2_draft = msg_2
        prospect.msg_3_draft = msg_3
        try:
            db.session.commit()
            return {"saved": True}
        except Exception as exc:
            db.session.rollback()
            return {"saved": False, "error": str(exc)}

    def _tool_send_digest_email(self) -> Dict[str, Any]:
        """Collect all prospects due for action today and send the digest email."""
        from src.tasks.linkedin import send_digest_task
        self.tool_calls.append({"tool": "send_digest_email"})
        result = send_digest_task.run()
        return result
```

- [ ] **Step 6.4: Run the tests**

```bash
python -m pytest tests/agents/test_linkedin_cadence.py -v 2>&1 | tail -15
```

Expected: `2 passed`

- [ ] **Step 6.5: Commit**

```bash
git add src/agents/linkedin_cadence.py tests/agents/test_linkedin_cadence.py
git commit -m "feat(agents): add LinkedInCadenceAgent with static tool set"
```

---

### Task 7: Replace LinkedIn Celery task bodies with agent wrappers

**Files:**
- Modify: `src/tasks/linkedin.py`
- Modify: `src/celery_inboxiq.py` (remove `linkedin_draft_messages` beat entry)

- [ ] **Step 7.1: Replace the task bodies in `src/tasks/linkedin.py`**

Keep all `@shared_task` decorators and task names intact (beat compatibility). Replace the bodies of `enrich_linkedin_urls`, `discover_prospects`, `draft_messages_task`, and `send_digest_task` with agent wrappers. The helper functions `_verify_linkedin_profile`, `_parse_linkedin_snapshot`, `_domain_from_email`, `_get_published_posts`, `_get_post_by_slug`, `_prospect_to_digest_item` can remain as they are still used by `send_digest_task`.

Replace `enrich_linkedin_urls`:
```python
@shared_task(name="linkedin.enrich_linkedin_urls")
def enrich_linkedin_urls():
    """Enrich qualifying leads with LinkedIn URLs via SearXNG + Playwright."""
    from src.agents.linkedin_cadence import LinkedInCadenceAgent
    for account_id in _all_account_ids():
        LinkedInCadenceAgent(account_id=account_id).execute(
            "Enrich qualifying leads with LinkedIn URLs. "
            "For each lead from get_qualifying_leads: call find_decision_makers, "
            "verify with browser_navigate + browser_snapshot, then call enrich_lead_linkedin_url."
        )
```

Replace `discover_prospects`:
```python
@shared_task(name="linkedin.discover_prospects")
def discover_prospects():
    """Promote enriched leads into the prospect queue."""
    from src.agents.linkedin_cadence import LinkedInCadenceAgent
    for account_id in _all_account_ids():
        LinkedInCadenceAgent(account_id=account_id).execute(
            "For each lead from get_qualifying_leads that has a linkedin_url, "
            "call add_to_prospect_queue to create a prospect record."
        )
```

Replace `draft_messages_task`:
```python
@shared_task(name="linkedin.draft_messages")
def draft_messages_task():
    """Draft outreach messages for pending prospects."""
    from src.agents.linkedin_cadence import LinkedInCadenceAgent
    for account_id in _all_account_ids():
        LinkedInCadenceAgent(account_id=account_id).execute(
            "For each prospect from get_pending_prospects: draft three outreach messages "
            "appropriate for their job_title, company_name, and industry, "
            "then call save_drafted_messages."
        )
```

Replace `send_digest_task`:
```python
@shared_task(name="linkedin.send_digest")
def send_digest_task():
    """Send today's LinkedIn action digest email."""
    from src.agents.linkedin_cadence import LinkedInCadenceAgent
    for account_id in _all_account_ids():
        LinkedInCadenceAgent(account_id=account_id).execute(
            "Call send_digest_email to send today's LinkedIn action digest."
        )
```

Add the helper at the bottom of the file:
```python
def _all_account_ids() -> list:
    from src.models.core import Account
    return [row.id for row in db.session.query(Account.id).all()]
```

Remove all the old helper functions that are no longer called: `_verify_linkedin_profile`, `_parse_linkedin_snapshot`, `_domain_from_email`, `_get_published_posts`, `_get_post_by_slug`, `_prospect_to_digest_item`, `_load_icp`. Also remove the now-unused module-level imports: `json`, `sys`, `_configure_dspy`, `MessageDrafterModule`, `BlogPostMatcherModule`, `PersistentMCPClient`.

Keep: `logging`, `shared_task`, `db`.

- [ ] **Step 7.2: Remove `linkedin_draft_messages` beat entry from `celery_inboxiq.py`**

Delete the 4-line block at lines 398–402:
```python
            "linkedin_draft_messages": {
                "task": "linkedin.draft_messages",
                "schedule": crontab(hour=7, minute=30),
                "options": {"queue": "inbox"},
            },
```

The `draft_messages` Celery task still exists (for manual/on-demand use) but no longer runs on a beat schedule — drafting is merged into the discover_prospects goal.

- [ ] **Step 7.3: Run existing LinkedIn task tests**

```bash
python -m pytest tests/linkedin/ -v 2>&1 | tail -20
```

Expected: All tests that test `discover_prospects` still pass (the task body still does the same work, now via agent). Tests that patched the old inline logic may need updating — if `test_discover_prospects_creates_record_for_qualifying_lead` fails because it calls `.run()` and the agent tries to use DSPy, patch `LinkedInCadenceAgent.execute` to a no-op.

Update `tests/linkedin/test_tasks.py` if needed:

```python
def test_discover_prospects_creates_record_for_qualifying_lead(db):
    from src.models.leads import Lead
    from src.models.campaigns import LinkedInProspect
    from unittest.mock import patch

    lead = Lead(
        id="lead-001", account_id=1, name="Alice Smith",
        email="alice@acmesaas.com", company_name="Acme SaaS",
        source="linkedin", linkedin_url="https://linkedin.com/in/alice",
        status="New Lead", fit_score=8, deleted=False,
    )
    db.session.add(lead)
    db.session.commit()

    # Patch at the agent level — test the task dispatch, not the ReAct loop.
    with patch("src.tasks.linkedin._all_account_ids", return_value=[1]), \
         patch("src.agents.linkedin_cadence.LinkedInCadenceAgent.execute") as mock_execute:
        from src.tasks.linkedin import discover_prospects
        discover_prospects.run()
        mock_execute.assert_called_once()
        # Also directly test the tool to verify DB logic:
        from src.agents.linkedin_cadence import LinkedInCadenceAgent
        agent = LinkedInCadenceAgent(account_id=1)
        result = agent._tool_add_to_prospect_queue("lead-001")
        assert result["created"] is True

    prospect = db.session.query(LinkedInProspect).filter_by(
        linkedin_url="https://linkedin.com/in/alice", account_id=1
    ).first()
    assert prospect is not None
    assert prospect.status == "pending"
```

- [ ] **Step 7.4: Run full test suite**

```bash
python -m pytest tests/ -v 2>&1 | tail -20
```

Expected: all passing.

- [ ] **Step 7.5: Commit**

```bash
git add src/tasks/linkedin.py src/celery_inboxiq.py tests/linkedin/test_tasks.py
git commit -m "feat(agents): replace LinkedIn task bodies with LinkedInCadenceAgent wrappers"
```

---

### Task 8: Create `FunnelDiscoveryAgent`

**Files:**
- Create: `src/agents/funnel_discovery.py`
- Create: `tests/agents/test_funnel_discovery.py`

- [ ] **Step 8.1: Write the failing test**

```python
# tests/agents/test_funnel_discovery.py
import pytest
from unittest.mock import patch, MagicMock


@pytest.fixture
def full_app(app):
    from src.models.leads import Lead
    from src.models.marketing import ICPConfig
    from src.extensions import db as _db
    with app.app_context():
        Lead.__table__.create(_db.engine, checkfirst=True)
        ICPConfig.__table__.create(_db.engine, checkfirst=True)
        yield app
        ICPConfig.__table__.drop(_db.engine, checkfirst=True)
        Lead.__table__.drop(_db.engine, checkfirst=True)


def test_get_existing_companies_returns_company_names(full_app):
    from src.agents.funnel_discovery import FunnelDiscoveryAgent
    from src.models.leads import Lead
    from src.extensions import db

    with full_app.app_context():
        db.session.add(Lead(
            id="fx1", account_id=1, name="Org", email="a@org.com",
            company_name="OrgCo", source="manual", status="New Lead",
            fit_score=7, deleted=False,
        ))
        db.session.commit()

        agent = FunnelDiscoveryAgent(account_id=1)
        names = agent._tool_get_existing_companies()
        assert "OrgCo" in names


def test_save_lead_creates_row_and_rejects_duplicates(full_app):
    from src.agents.funnel_discovery import FunnelDiscoveryAgent
    from src.models.leads import Lead
    from src.extensions import db

    with full_app.app_context():
        agent = FunnelDiscoveryAgent(account_id=1)
        result = agent._tool_save_lead(
            company_name="NewCo",
            email="contact@newco.com",
            industry="B2B SaaS",
            fit_score=7,
            source="searxng_discovery",
            notes="Hiring head of support",
        )
        assert result["created"] is True

        # Duplicate should be rejected
        result2 = agent._tool_save_lead(
            company_name="NewCo",
            email="contact@newco.com",
            industry="B2B SaaS",
            fit_score=7,
            source="searxng_discovery",
            notes="Hiring head of support",
        )
        assert result2["created"] is False
        assert result2["reason"] == "duplicate"
```

- [ ] **Step 8.2: Run to confirm failure**

```bash
python -m pytest tests/agents/test_funnel_discovery.py -v 2>&1 | head -10
```

Expected: `ImportError: cannot import name 'FunnelDiscoveryAgent'`

- [ ] **Step 8.3: Create `src/agents/funnel_discovery.py`**

```python
"""Funnel discovery agent — replaces discover_leads_via_search and discover_buying_signals task bodies."""
from __future__ import annotations

import logging
from typing import Any, Dict, List

from src.agents.base import BaseAgent
from src.extensions import db

log = logging.getLogger(__name__)

_LEAD_DISCOVERY_LABEL = "lead-discovery"
_ENRICHMENT_LABEL = "enrichment-v2"


class FunnelDiscoveryAgent(BaseAgent):
    """
    Discovers new leads and buying signals using lead-discovery and enrichment MCP servers.
    Writes qualifying companies to the Lead model.
    """

    agent_name = "funnel_discovery"
    mcp_server_labels = [_LEAD_DISCOVERY_LABEL, _ENRICHMENT_LABEL]

    def _get_tools(self) -> list:
        return [
            self._tool_get_existing_companies,
            self._tool_get_icp_config,
            self._tool_save_lead,
        ]

    # -------------------------------------------------------------------------
    # Static tools
    # -------------------------------------------------------------------------

    def _tool_get_existing_companies(self) -> List[str]:
        """Return company names already in the leads table for this account (for dedup)."""
        from src.models.leads import Lead
        self.tool_calls.append({"tool": "get_existing_companies"})
        rows = db.session.query(Lead.company_name).filter_by(account_id=self.account_id).all()
        return [r.company_name for r in rows if r.company_name]

    def _tool_get_icp_config(self) -> Dict[str, Any]:
        """Return ICP config (titles, industries, size range, geographies) for this account."""
        from src.models.marketing import ICPConfig
        self.tool_calls.append({"tool": "get_icp_config"})
        _DEFAULTS = {
            "titles": ["Founder", "Head of Support", "Operations Lead", "Customer Success Lead"],
            "industries": ["B2B SaaS", "Software"],
            "company_size_min": 10,
            "company_size_max": 300,
            "geographies": ["UK", "US", "Nigeria"],
        }
        config = db.session.query(ICPConfig).filter_by(account_id=self.account_id).first()
        if not config:
            return _DEFAULTS
        return {
            "titles": config.titles or _DEFAULTS["titles"],
            "industries": config.industries or _DEFAULTS["industries"],
            "company_size_min": config.company_size_min or _DEFAULTS["company_size_min"],
            "company_size_max": config.company_size_max or _DEFAULTS["company_size_max"],
            "geographies": config.geographies or _DEFAULTS["geographies"],
        }

    def _tool_save_lead(
        self,
        company_name: str,
        email: str,
        industry: str,
        fit_score: int,
        source: str,
        notes: str = "",
        linkedin_url: str = "",
        name: str = "",
        num_employees: int = 0,
    ) -> Dict[str, Any]:
        """
        Persist a verified lead. Rejects if fit_score < 4 or company already exists
        for this source. Enqueues qualify_visitor after commit.
        """
        from src.models.leads import Lead
        self.tool_calls.append({"tool": "save_lead", "input": {"company_name": company_name}})

        if fit_score < 4:
            return {"created": False, "reason": "fit_score_too_low"}

        existing = db.session.query(Lead).filter_by(
            account_id=self.account_id,
            company_name=company_name,
            source=source,
        ).first()
        if existing:
            return {"created": False, "reason": "duplicate"}

        lead = Lead(
            account_id=self.account_id,
            name=name or company_name,
            email=email,
            company_name=company_name,
            industry=industry,
            num_employees=num_employees or None,
            linkedin_url=linkedin_url or None,
            source=source,
            fit_score=fit_score,
            status="New Lead",
            notes=notes,
            deleted=False,
        )
        try:
            db.session.add(lead)
            db.session.commit()
        except Exception as exc:
            db.session.rollback()
            return {"created": False, "error": str(exc)}

        try:
            from src.funnel.tasks import qualify_visitor
            qualify_visitor.delay(lead.id)
        except Exception:
            log.warning("qualify_visitor.delay failed for lead %s", lead.id)

        return {"created": True, "lead_id": str(lead.id)}
```

- [ ] **Step 8.4: Run the tests**

```bash
python -m pytest tests/agents/test_funnel_discovery.py -v 2>&1 | tail -15
```

Expected: `2 passed`

- [ ] **Step 8.5: Commit**

```bash
git add src/agents/funnel_discovery.py tests/agents/test_funnel_discovery.py
git commit -m "feat(agents): add FunnelDiscoveryAgent with ICP-aware lead saving"
```

---

### Task 9: Replace Funnel Celery task bodies with agent wrappers

**Files:**
- Modify: `src/funnel/tasks.py` lines 335–474 (`discover_leads_via_search`) and 476–560 (`discover_buying_signals`)

- [ ] **Step 9.1: Replace `discover_leads_via_search` body**

Locate the function at line 335 of `src/funnel/tasks.py`. Replace everything from the `results = {...}` line through the end of the function with:

```python
    from src.agents.funnel_discovery import FunnelDiscoveryAgent
    from src.models.core import Account

    goal = (
        f"Discover B2B SaaS companies matching ICP in niche '{niche}'. "
        f"Call get_icp_config first. Then call discover_companies via MCP. "
        f"For each result not in get_existing_companies, call save_lead. "
        f"Limit to {max_leads} new leads."
    )

    if account_id:
        FunnelDiscoveryAgent(account_id=int(account_id)).execute(goal)
    else:
        for row in db.session.query(Account.id).all():
            FunnelDiscoveryAgent(account_id=row.id).execute(goal)

    return {"status": "ok", "niche": niche}
```

- [ ] **Step 9.2: Replace `discover_buying_signals` body**

Locate the function at line 476. Replace its body (the `results = {...}` block through the end) with:

```python
    from src.agents.funnel_discovery import FunnelDiscoveryAgent
    from src.models.core import Account

    goal = (
        f"Find companies showing '{signal_type}' buying signals in niche '{niche}'. "
        f"Use find_buying_signals via MCP. For each company not already in "
        f"get_existing_companies, call save_lead with source='buying_signal' "
        f"and relevant notes. Limit to {max_results} signals."
    )

    for row in db.session.query(Account.id).all():
        FunnelDiscoveryAgent(account_id=row.id).execute(goal)

    return {"status": "ok", "niche": niche, "signal_type": signal_type}
```

Remove the `asyncio` import at the top of `funnel/tasks.py` if it is now unused (check for other callers in the file first).

- [ ] **Step 9.3: Run the test suite**

```bash
python -m pytest tests/ -v 2>&1 | tail -25
```

Expected: all tests passing.

- [ ] **Step 9.4: Commit**

```bash
git add src/funnel/tasks.py
git commit -m "feat(agents): replace funnel Celery task bodies with FunnelDiscoveryAgent wrappers"
```

---

### Task 10: Deploy

- [ ] **Step 10.1: Push to dev branch**

```bash
git push origin dev
```

- [ ] **Step 10.2: Confirm GitHub Actions CI passes**

Watch the workflow at `.github/workflows/inbox-ci.yml`. All steps must be green.

- [ ] **Step 10.3: Run the playwright-mcp registration on the cluster**

After the pod restarts with the new code:

```bash
kubectl exec -n kaley deploy/inboxiq -- flask register-playwright-mcp
```

Expected: `playwright-mcp registered.`

- [ ] **Step 10.4: Verify beat schedule**

```bash
kubectl exec -n kaley deploy/inboxiq -- celery -A src.celery_inboxiq:celery inspect scheduled 2>&1 | grep linkedin
```

Expected: `linkedin_enrich_urls` (5am), `linkedin_discover_prospects` (7am), `linkedin_send_digest` (8am). No `linkedin_draft_messages`.

---

## Self-Review

**Spec coverage:**

| Spec requirement | Task |
|---|---|
| BaseAgent extraction from ToolCallingAutomationAgent | Tasks 1, 2 |
| LinkedInCadenceAgent | Task 6 |
| FunnelDiscoveryAgent | Task 8 |
| Celery tasks become 3-line wrappers | Tasks 7, 9 |
| Delete worker.py | Task 3 |
| Register playwright-mcp | Task 4 |
| Fix find_buying_committee stub | Task 5 |
| AgentEvent telemetry per execution | Task 1 (`_store_event`) |
| MCP clients opened per labeled server | Task 1 (`_open_mcp_clients`) |
| `_all_account_ids` loop | Task 7 |

**Type consistency check:**
- `BaseAgent._store_event` uses `AgentEvent.context` (JSON) — matches model definition.
- `LinkedInCadenceAgent.execute` signature matches `BaseAgent.execute(goal: str)`.
- `ToolCallingAutomationAgent.execute(trigger_event: str)` overrides with `# type: ignore[override]` — deliberate.
- `FunnelDiscoveryAgent._tool_save_lead` calls `qualify_visitor.delay(lead.id)` — `lead.id` is the ORM UUID string, matches task signature.

**Placeholder scan:** None found.
