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

from src.dspy.config import _configure_dspy
from src.models.automation import AutomationRule, WebhookProvider, AutomationRuleExecution
from src.extensions import db

logger = logging.getLogger(__name__)


class ToolCallingAutomationAgent:
    """
    Provider-agnostic automation agent using dspy.ReAct.

    Tools are registered as plain Python callables with docstrings —
    no OpenAI function-calling schema required.
    """

    def __init__(self, workflow: AutomationRule, trigger_context: Dict[str, Any]):
        self.workflow = workflow
        self.trigger_context = trigger_context
        self.account_id = workflow.account_id
        self.execution_log: List[str] = []
        self.tool_calls: List[Dict[str, Any]] = []

        _, _, self._dspy = _configure_dspy()

    # =========================================================================
    # Public entry point
    # =========================================================================

    def execute(self, trigger_event: str) -> Dict[str, Any]:
        """Execute workflow using dspy.ReAct agent loop."""
        self.log("Starting ReAct agent execution")

        # Build the DSPy ReAct agent with tools as callables
        tools = [
            self._tool_get_context_summary,
            self._tool_search_context_field,
            self._tool_evaluate_condition,
            self._tool_search_webhook_providers,
            self._tool_send_webhook,
            self._tool_render_template,
        ]

        class WorkflowAgentSignature(self._dspy.Signature):
            """
            Execute an automation workflow step by step using the available tools.
            First summarise the context, then evaluate conditions, then execute actions.
            When done respond with 'Workflow execution completed successfully' or
            'Workflow execution failed: <reason>'.
            """
            workflow_description = self._dspy.InputField(
                desc="The automation workflow definition as JSON."
            )
            result = self._dspy.OutputField(
                desc="Final execution result: success or failure with reason."
            )

        try:
            agent = self._dspy.ReAct(WorkflowAgentSignature, tools=tools, max_iters=20)
            workflow_desc = json.dumps({
                "name": self.workflow.name,
                "description": self.workflow.description or "",
                "trigger": self.workflow.trigger,
                "conditions": self.workflow.conditions,
                "condition_logic": self.workflow.condition_logic,
                "actions": self.workflow.actions,
            })

            prediction = agent(workflow_description=workflow_desc)
            final_text = prediction.result or ""
            self.log(f"Agent result: {final_text[:200]}")

            success = (
                "success" in final_text.lower()
                and "fail" not in final_text.lower()
            )

            self._store_execution(
                trigger_event=trigger_event,
                matched=True,
                executed=True,
                success=success,
                agent_response=final_text,
            )

            return {
                "executed": True,
                "matched": True,
                "success": success,
                "agent_log": self.execution_log,
                "tool_calls": self.tool_calls,
                "agent_response": final_text,
            }

        except Exception as e:
            logger.exception("ToolCallingAutomationAgent failed: %s", e)
            self.log(f"Agent failed: {e}")
            self._store_execution(
                trigger_event=trigger_event,
                matched=True,
                executed=False,
                success=False,
                error_message=str(e),
            )
            return {
                "executed": False,
                "matched": True,
                "success": False,
                "error": str(e),
                "agent_log": self.execution_log,
            }

    # =========================================================================
    # Tools — plain callables; docstrings are the tool descriptions for ReAct
    # =========================================================================

    def _tool_get_context_summary(self) -> Dict[str, Any]:
        """Get a summary of all available trigger context data (email, ticket, extracted fields)."""
        self.tool_calls.append({"tool": "get_context_summary", "input": {}})
        summary: Dict[str, Any] = {"available_fields": []}

        if "email" in self.trigger_context:
            email = self.trigger_context["email"]
            summary["email"] = {
                "subject": email.get("subject", "")[:100],
                "from": email.get("from_email", ""),
                "has_body": bool(email.get("body")),
            }
            summary["available_fields"].extend([
                "email.subject", "email.body", "email.from_email", "email.provider",
            ])

        if "ticket" in self.trigger_context:
            ticket = self.trigger_context["ticket"]
            summary["ticket"] = (
                {k: str(v)[:100] for k, v in ticket.items() if k != "body"}
                if isinstance(ticket, dict) else {}
            )
            summary["available_fields"].extend([
                "ticket.category", "ticket.priority", "ticket.status",
            ])

        if "extracted" in self.trigger_context:
            extracted = self.trigger_context["extracted"]
            if isinstance(extracted, dict):
                summary["extracted_fields"] = list(extracted.keys())
                summary["available_fields"].extend([f"extracted.{k}" for k in extracted])

        return summary

    def _tool_search_context_field(self, field_path: str) -> Any:
        """Search for a field in the trigger context using dot-notation (e.g. email.subject)."""
        self.tool_calls.append({"tool": "search_context_field", "input": {"field_path": field_path}})
        parts = field_path.split(".")
        current = self.trigger_context
        for part in parts:
            if isinstance(current, dict):
                current = current.get(part)
            elif hasattr(current, part):
                current = getattr(current, part)
            else:
                return {"error": f"Field not found: {field_path}"}
            if current is None:
                return {"error": f"Field not found: {field_path}"}
        return {"value": current, "found": True}

    def _tool_evaluate_condition(self, field_path: str, operator: str, value: str) -> Dict[str, Any]:
        """Evaluate a condition against context data. operator: equals|contains|not_contains|greater_than|less_than|is_empty|is_not_empty."""
        self.tool_calls.append({"tool": "evaluate_condition", "input": {"field_path": field_path, "operator": operator, "value": value}})
        field_result = self._tool_search_context_field(field_path)
        if "error" in field_result:
            return {"matched": False, "error": field_result["error"]}
        actual = field_result["value"]
        try:
            if operator == "equals":
                matched = str(actual) == str(value)
            elif operator == "contains":
                matched = str(value).lower() in str(actual).lower()
            elif operator == "not_contains":
                matched = str(value).lower() not in str(actual).lower()
            elif operator == "greater_than":
                matched = float(actual) > float(value)
            elif operator == "less_than":
                matched = float(actual) < float(value)
            elif operator == "is_empty":
                matched = not actual
            elif operator == "is_not_empty":
                matched = bool(actual)
            else:
                return {"matched": False, "error": f"Unknown operator: {operator}"}
            return {"matched": matched, "actual_value": actual, "expected_value": value, "operator": operator}
        except Exception as e:
            return {"matched": False, "error": str(e)}

    def _tool_search_webhook_providers(self, query: str) -> List[Dict[str, Any]]:
        """Search for webhook providers by name or type (slack, teams, sage, quickbooks, custom)."""
        self.tool_calls.append({"tool": "search_webhook_providers", "input": {"query": query}})
        query_lower = query.lower()
        providers = WebhookProvider.query.filter_by(account_id=self.account_id, enabled=True).all()
        return [
            {"id": str(p.id), "name": p.configuration_name, "type": p.provider_type}
            for p in providers
            if query_lower in p.configuration_name.lower() or query_lower in p.provider_type.lower()
        ]

    def _tool_send_webhook(self, provider_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Send a webhook to a provider (Slack, Teams, custom). provider_id from search_webhook_providers."""
        self.tool_calls.append({"tool": "send_webhook", "input": {"provider_id": provider_id}})
        from src.automation.actions import execute_action
        return execute_action("send_webhook", self.trigger_context, {"provider": provider_id, "payload_template": payload})

    def _tool_render_template(self, template: str) -> Dict[str, Any]:
        """Render a template string with trigger context variables using {{variable}} syntax."""
        self.tool_calls.append({"tool": "render_template", "input": {"template": template[:100]}})
        from src.automation.template_engine import render_template, build_context
        context = build_context(
            email=self.trigger_context.get("email"),
            extracted=self.trigger_context.get("extracted"),
            ticket=self.trigger_context.get("ticket"),
            lead=self.trigger_context.get("lead"),
            account_id=self.account_id,
            rule_name=self.workflow.name,
        )
        try:
            return {"rendered": render_template(template, context)}
        except Exception as e:
            return {"error": str(e)}

    # =========================================================================
    # Internals
    # =========================================================================

    def _store_execution(
        self,
        trigger_event: str,
        matched: bool,
        executed: bool,
        success: bool,
        agent_response: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> None:
        from src.monitoring.sanitizer import sanitize_trigger_context

        ticket_id = None
        lead_id = None
        ticket = self.trigger_context.get("ticket")
        lead = self.trigger_context.get("lead")
        if isinstance(ticket, dict):
            ticket_id = ticket.get("id")
        elif hasattr(ticket, "id"):
            ticket_id = ticket.id
        if isinstance(lead, dict):
            lead_id = lead.get("id")
        elif hasattr(lead, "id"):
            lead_id = lead.id

        execution = AutomationRuleExecution(
            id=str(uuid4()),
            rule_id=self.workflow.id,
            account_id=self.account_id,
            trace_id="agent-" + str(uuid4())[:8],
            ticket_id=ticket_id,
            lead_id=lead_id,
            trigger_event=trigger_event,
            trigger_type=self.trigger_context.get("type", "email"),
            trigger_context=sanitize_trigger_context(self.trigger_context),
            matched=matched,
            executed=executed,
            success=success,
            error_message=error_message or agent_response,
            execution_time_ms=0,
            conditions_evaluated=None,
            actions_executed=[{"type": "react_agent", "tool_calls": len(self.tool_calls)}],
        )

        try:
            db.session.add(execution)
            self.workflow.execution_count = (self.workflow.execution_count or 0) + 1
            if success:
                self.workflow.success_count = (self.workflow.success_count or 0) + 1
            if error_message:
                self.workflow.error_count = (self.workflow.error_count or 0) + 1
            self.workflow.last_executed_at = datetime.now(timezone.utc)
            db.session.commit()
        except Exception:
            db.session.rollback()

    def log(self, message: str) -> None:
        self.execution_log.append(message)
        logger.info("[ToolCallingAgent %s] %s", self.workflow.name, message)


def execute_workflow_with_tool_calling_agent(
    workflow_id: str,
    trigger_context: Dict[str, Any],
    trigger_event: str = "unknown",
) -> Dict[str, Any]:
    """
    Execute an AutomationRule using the DSPy ReAct tool-calling agent.

    Drop-in replacement for execute_workflow_with_dspy_agent — same signature,
    same return shape, different execution strategy.
    """
    from src.models.automation import AutomationRule

    workflow = AutomationRule.query.filter_by(id=workflow_id).first()
    if not workflow:
        return {"executed": False, "error": "Workflow not found"}
    if not workflow.enabled:
        return {"executed": False, "reason": "workflow_disabled"}

    agent = ToolCallingAutomationAgent(workflow=workflow, trigger_context=trigger_context)
    return agent.execute(trigger_event=trigger_event)
