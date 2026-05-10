"""Shared base for all InboxIQ DSPy ReAct agents."""
from __future__ import annotations

import logging
import time
import dspy  # type: ignore  # noqa: F401 — must be module-level for test patching via src.agents.base.dspy
from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone
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
    max_iters: int = 25

    # Class-level throttle for SMTPHandler-routed agent failure emails. The
    # crash_report SMTPHandler fires on log.error(...) — without throttling,
    # a stuck agent could send hundreds of emails per hour. Keyed by agent_name
    # so unrelated agents do not silence each other.
    _last_error_email_sent: Dict[str, datetime] = {}
    _ERROR_EMAIL_COOLDOWN: timedelta = timedelta(minutes=60)

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
            react_agent = dspy.ReAct(self._get_signature(dspy), tools=tools, max_iters=self.max_iters)
            prediction = react_agent(goal=goal)
            result_text = prediction.result or ""
            success, failure_reason = self._evaluate_success(result_text)
            if not success:
                error_msg = failure_reason
            self.log(f"Completed (success={success}): {result_text[:200]}")

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

    def _get_signature(self, dspy: Any) -> type:
        """Return the DSPy Signature class to use for ReAct. Subclasses can override."""
        return AgentGoalSignature

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
            client = PersistentMCPClient(command, server_label=label)
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
    # Success evaluation
    # -------------------------------------------------------------------------

    _FAILURE_PHRASES = (
        "unable to retrieve",
        "could not retrieve",
        "despite persistent efforts",
        "i was unable",
        "no qualifying leads found",
    )

    def _evaluate_success(self, result_text: str) -> tuple[bool, str | None]:
        """Return (success, failure_reason). Conservative: any failure phrase => False."""
        lowered = (result_text or "").lower()
        for phrase in self._FAILURE_PHRASES:
            if phrase in lowered:
                return False, f"llm_admitted_failure: {phrase}"
        if len(self.tool_calls) >= self.max_iters:
            return False, f"max_iters_hit ({self.max_iters})"
        return True, None

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

        # Emit Prometheus metrics
        try:
            from src.monitoring.metrics import agent_status, agent_react_max_iters_hit
            if success:
                status_label = "success"
            elif error_msg and "max_iters" in error_msg:
                status_label = "max_iters"
            elif error_msg and "llm_admitted_failure" in error_msg:
                status_label = "llm_give_up"
            else:
                status_label = "error"
            agent_status.labels(agent_name=self.agent_name, status=status_label).inc()
            if status_label == "max_iters":
                agent_react_max_iters_hit.labels(agent_name=self.agent_name).inc()
        except Exception:
            log.warning("[%s] failed to emit prometheus metric", self.agent_name)

        # Route agent failures into the SMTPHandler-backed crash_report logger.
        # log.error(...) propagates to the root SMTPHandler attached in
        # src/monitoring/crash_report.py, which emails kofuafor@gmail.com.
        # Throttled per agent_name with a 60-min cooldown to prevent flooding.
        if not success:
            now = datetime.now(timezone.utc)
            last = BaseAgent._last_error_email_sent.get(self.agent_name)
            if last is None or (now - last) >= BaseAgent._ERROR_EMAIL_COOLDOWN:
                log.error(
                    "agent %s failed: %s | goal=%r | tool_calls=%d | latency_ms=%d",
                    self.agent_name,
                    error_msg,
                    self.goal[:200],
                    len(self.tool_calls),
                    latency_ms,
                )
                BaseAgent._last_error_email_sent[self.agent_name] = now

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
