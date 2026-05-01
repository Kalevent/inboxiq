"""Shared base for all InboxIQ DSPy ReAct agents."""
from __future__ import annotations

import logging
import time
import dspy  # type: ignore  # noqa: F401 — must be module-level for test patching via src.agents.base.dspy
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Dict, List
from uuid import uuid4

from src.extensions import db
from src.dspy.config import _configure_dspy

log = logging.getLogger(__name__)


class AgentGoalSignature(dspy.Signature):
    """
    Complete the given goal using the available tools.
    Think step by step. When done, respond with a brief summary of what was accomplished.
    """
    goal = dspy.InputField(desc="The goal to accomplish.")
    result = dspy.OutputField(desc="Summary of what was accomplished or why it failed.")


class BaseAgent(ABC):
    """
    DSPy ReAct agent base. Subclasses declare:
      - agent_name: str           (used in logs + AgentEvent rows)
      - mcp_server_labels: list   (MCPServerCatalog labels to open)
      - _get_tools() -> list      (returns callable tool list for dspy.ReAct)

    Instance attributes set during execute():
      - execution_log: list — append-only log of human-readable progress messages
      - tool_calls: list — subclasses should append {"tool": name, "input": args} in each tool method
      - goal: str — the goal passed to execute()
    """

    agent_name: str = "base_agent"
    mcp_server_labels: List[str] = []

    def __init__(self, account_id: int):
        self.account_id = account_id
        self.goal: str = ""
        self.execution_log: List[str] = []
        self.tool_calls: List[Dict[str, Any]] = []
        self._mcp: Dict[str, Any] = {}

    def execute(self, goal: str) -> Dict[str, Any]:
        """Run the ReAct loop for `goal`. Opens/closes MCP clients around the run."""
        self.execution_log = []
        self.tool_calls = []
        self.goal = goal

        # Call _configure_dspy() to initialise the LM settings; we use the
        # module-level `dspy` import so that tests can patch src.agents.base.dspy.
        try:
            _configure_dspy()
        except Exception as cfg_exc:
            log.warning("[%s] DSPy not configured (%s); proceeding with patched/mock LM", self.agent_name, cfg_exc)

        _start = time.monotonic()
        success = False
        result_text = ""
        error_msg = None

        try:
            self._open_mcp_clients()
            tools = self._get_tools()
            react_agent = dspy.ReAct(AgentGoalSignature, tools=tools, max_iters=25)
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
        self._store_event(
            success=success,
            result_text=result_text,
            error_msg=error_msg,
            latency_ms=latency_ms,
        )

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
                log.warning(
                    "[%s] MCP server not found in catalog: %s", self.agent_name, label
                )
                continue
            from src.mcp.client import PersistentMCPClient
            command = catalog.command
            if isinstance(command, str):
                command = command.split()
            client = PersistentMCPClient(command)
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

    def _store_event(
        self,
        success: bool,
        result_text: str,
        error_msg: str | None,
        latency_ms: int,
    ) -> None:
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
            error_message=error_msg[:512] if error_msg else None,
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
