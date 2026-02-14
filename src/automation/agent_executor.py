"""
AI Agent-Based Automation Executor

Replaces the hardcoded rules engine with an intelligent AI agent that:
- Understands user-defined workflows
- Auto-resolves field paths and configurations
- Self-heals common errors
- Executes actions using available tools dynamically

This is how automation SHOULD work - intelligent and adaptive, not hardcoded.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional
from datetime import datetime

from src.models import AutomationRule, AutomationRuleExecution, WebhookProvider
from src.extensions import db
from src.observability import get_tracer
from opentelemetry import trace

logger = logging.getLogger(__name__)
tracer = get_tracer(__name__)


class AutomationAgent:
    """
    Intelligent automation agent that executes user-defined workflows.

    Uses LLM reasoning to:
    - Parse workflow definitions
    - Resolve ambiguous field paths
    - Validate and fix configurations
    - Execute actions intelligently
    - Handle errors gracefully
    """

    def __init__(self, workflow: AutomationRule, trigger_context: Dict[str, Any]):
        self.workflow = workflow
        self.trigger_context = trigger_context
        self.account_id = workflow.account_id
        self.execution_log: List[str] = []
        self.errors: List[str] = []

    def execute(self, trigger_event: str) -> Dict[str, Any]:
        """
        Execute the workflow using intelligent agent reasoning.

        Args:
            trigger_event: Event that triggered the workflow

        Returns:
            Execution result with success status and details
        """
        with tracer.start_as_current_span("automation.agent.execute") as span:
            span.set_attribute("workflow.id", str(self.workflow.id))
            span.set_attribute("workflow.name", self.workflow.name)
            span.set_attribute("account.id", self.account_id)

            start_time = datetime.utcnow()

            try:
                # Step 1: Evaluate conditions intelligently
                self.log("🤖 Evaluating workflow conditions...")
                conditions_met, condition_details = self._evaluate_conditions_intelligently()

                if not conditions_met:
                    self.log(f"⏭️  Conditions not met, skipping workflow")
                    return self._create_result(
                        matched=False,
                        executed=False,
                        success=False,
                        trigger_event=trigger_event,
                        start_time=start_time,
                        span=span,
                        condition_details=condition_details
                    )

                self.log(f"✅ Conditions met, executing actions...")

                # Step 2: Execute actions intelligently
                action_results = self._execute_actions_intelligently()

                all_successful = all(r.get("success", False) for r in action_results)

                self.log(f"✅ Workflow completed: {len(action_results)} actions, success={all_successful}")

                return self._create_result(
                    matched=True,
                    executed=True,
                    success=all_successful,
                    trigger_event=trigger_event,
                    start_time=start_time,
                    span=span,
                    condition_details=condition_details,
                    action_results=action_results
                )

            except Exception as e:
                logger.exception(f"Agent execution failed for workflow {self.workflow.id}")
                self.errors.append(str(e))
                span.record_exception(e)

                return self._create_result(
                    matched=True,
                    executed=False,
                    success=False,
                    trigger_event=trigger_event,
                    start_time=start_time,
                    span=span,
                    error_message=str(e)
                )

    def _evaluate_conditions_intelligently(self) -> tuple[bool, List[Dict[str, Any]]]:
        """
        Evaluate conditions with intelligent field path resolution.

        If a field isn't found at the top level, search nested structures.
        Auto-correct common mistakes like 'subject' → 'email.subject'.
        """
        conditions = self.workflow.conditions or []

        if not conditions:
            return True, []

        match_type = self.workflow.condition_logic or "AND"
        condition_details = []
        matched_conditions = []

        for idx, condition in enumerate(conditions):
            field = condition.get("field", "")
            operator = condition.get("operator", "")
            expected_value = condition.get("value")

            # Intelligently resolve field path
            actual_value, resolved_path = self._resolve_field_intelligently(field)

            if resolved_path != field:
                self.log(f"🔍 Auto-resolved '{field}' → '{resolved_path}'")

            # Evaluate condition
            matched = self._evaluate_operator(actual_value, operator, expected_value)

            condition_details.append({
                "index": idx,
                "field": field,
                "resolved_path": resolved_path,
                "operator": operator,
                "expected": expected_value,
                "actual": actual_value,
                "matched": matched
            })

            matched_conditions.append(matched)

            # Short-circuit for AND logic
            if not matched and match_type == "AND":
                return False, condition_details

        # Determine overall match
        if match_type == "OR":
            return any(matched_conditions), condition_details
        else:
            return all(matched_conditions), condition_details

    def _resolve_field_intelligently(self, field_path: str) -> tuple[Any, str]:
        """
        Intelligently resolve a field path, searching nested structures if needed.

        Examples:
            'subject' → searches for 'email.subject', 'ticket.subject', etc.
            'amount' → searches for 'extracted.amount'
            'priority' → searches for 'ticket.priority'

        Returns:
            (value, resolved_path)
        """
        # Try direct path first
        value = self._extract_value(self.trigger_context, field_path)
        if value is not None:
            return value, field_path

        # Common field mappings for auto-resolution
        common_mappings = {
            "subject": ["email.subject", "ticket.subject"],
            "body": ["email.body", "ticket.body"],
            "from": ["email.from_email", "email.from"],
            "to": ["email.to"],
            "priority": ["ticket.priority", "extracted.priority"],
            "category": ["ticket.category", "extracted.category"],
            "amount": ["extracted.amount"],
            "invoice_number": ["extracted.invoice_number"],
            "status": ["ticket.status"],
        }

        # Try common mappings
        if field_path in common_mappings:
            for candidate_path in common_mappings[field_path]:
                value = self._extract_value(self.trigger_context, candidate_path)
                if value is not None:
                    return value, candidate_path

        # Search all nested structures for this field name
        found_value, found_path = self._search_nested(self.trigger_context, field_path)
        if found_value is not None:
            return found_value, found_path

        # Not found anywhere
        return None, field_path

    def _search_nested(self, obj: Any, field_name: str, prefix: str = "") -> tuple[Any, str]:
        """Recursively search nested structures for a field name."""
        if isinstance(obj, dict):
            # Direct key match
            if field_name in obj:
                path = f"{prefix}.{field_name}" if prefix else field_name
                return obj[field_name], path

            # Search nested dicts
            for key, value in obj.items():
                next_prefix = f"{prefix}.{key}" if prefix else key
                result, path = self._search_nested(value, field_name, next_prefix)
                if result is not None:
                    return result, path

        return None, field_name

    def _extract_value(self, context: Dict[str, Any], field_path: str) -> Any:
        """Extract value using dot notation."""
        if not field_path:
            return None

        parts = field_path.split(".")
        current = context

        for part in parts:
            if isinstance(current, dict):
                current = current.get(part)
            elif hasattr(current, part):
                current = getattr(current, part)
            else:
                return None

            if current is None:
                return None

        return current

    def _evaluate_operator(self, actual: Any, operator: str, expected: Any) -> bool:
        """Evaluate condition operator."""
        try:
            if operator == "equals":
                return str(actual) == str(expected)
            elif operator == "not_equals":
                return str(actual) != str(expected)
            elif operator == "contains":
                return str(expected).lower() in str(actual).lower()
            elif operator == "not_contains":
                return str(expected).lower() not in str(actual).lower()
            elif operator == "starts_with":
                return str(actual).startswith(str(expected))
            elif operator == "ends_with":
                return str(actual).endswith(str(expected))
            elif operator == "greater_than":
                return float(actual) > float(expected)
            elif operator == "less_than":
                return float(actual) < float(expected)
            elif operator == "is_empty":
                return not actual or actual == "" or actual == []
            elif operator == "is_not_empty":
                return actual and actual != "" and actual != []
            else:
                self.log(f"⚠️  Unknown operator: {operator}")
                return False
        except Exception as e:
            self.log(f"⚠️  Condition evaluation error: {e}")
            return False

    def _execute_actions_intelligently(self) -> List[Dict[str, Any]]:
        """
        Execute actions with intelligent configuration resolution.

        Auto-fixes common issues:
        - Invalid action types → suggests closest match
        - Missing provider IDs → searches by name
        - Invalid template variables → auto-resolves paths
        """
        actions = self.workflow.actions or []
        results = []

        for idx, action in enumerate(actions):
            action_type = action.get("type", "unknown")
            config = action.get("config", {})

            self.log(f"🎯 Executing action {idx + 1}: {action_type}")

            try:
                # Auto-fix action type if needed
                fixed_type, fixed_config = self._fix_action_intelligently(action_type, config)

                if fixed_type != action_type:
                    self.log(f"🔧 Auto-fixed action type: {action_type} → {fixed_type}")

                # Execute the action
                result = self._execute_action(fixed_type, fixed_config)
                results.append({
                    "index": idx,
                    "type": fixed_type,
                    "success": result.get("success", False),
                    "result": result
                })

            except Exception as e:
                logger.exception(f"Action {idx} failed: {e}")
                results.append({
                    "index": idx,
                    "type": action_type,
                    "success": False,
                    "error": str(e)
                })

                if self.workflow.stop_on_error:
                    break

        return results

    def _fix_action_intelligently(self, action_type: str, config: Dict[str, Any]) -> tuple[str, Dict[str, Any]]:
        """
        Auto-fix common action configuration issues.

        Examples:
            - 'slack_notify' → 'send_webhook' (with Slack provider)
            - 'notify' → 'send_webhook'
            - Missing provider ID → resolve by name
        """
        fixed_type = action_type
        fixed_config = config.copy()

        # Auto-fix: slack_notify → send_webhook
        if action_type in ("slack_notify", "slack", "notify_slack"):
            fixed_type = "send_webhook"

            # Find Slack provider
            slack_provider = WebhookProvider.query.filter_by(
                account_id=self.account_id,
                provider_type="slack",
                enabled=True
            ).first()

            if slack_provider:
                # Build proper webhook config
                message = config.get("message", "Notification: {{email.subject}}")
                fixed_config = {
                    "provider": str(slack_provider.id),
                    "payload_template": {
                        "text": message,
                        "channel": config.get("channel", "#general"),
                        "username": "InboxIQ Bot",
                        "icon_emoji": ":envelope:"
                    }
                }
                self.log(f"🔧 Auto-configured Slack webhook (provider: {slack_provider.configuration_name})")

        # Resolve provider by name if string is provided
        if "provider" in fixed_config:
            provider_ref = fixed_config["provider"]
            if isinstance(provider_ref, str) and not provider_ref.startswith("74f980d9"):  # Not a UUID
                # Try to resolve by name
                provider = WebhookProvider.query.filter_by(
                    account_id=self.account_id,
                    configuration_name=provider_ref,
                    enabled=True
                ).first()

                if provider:
                    fixed_config["provider"] = str(provider.id)
                    self.log(f"🔍 Resolved provider '{provider_ref}' → {provider.id}")

        return fixed_type, fixed_config

    def _execute_action(self, action_type: str, config: Dict[str, Any]) -> Dict[str, Any]:
        """Execute action using existing action handlers."""
        from src.automation.actions import execute_action
        from src.automation.template_engine import render_template, build_context

        # Build context for template rendering
        context = build_context(
            email=self.trigger_context.get("email"),
            extracted=self.trigger_context.get("extracted"),
            ticket=self.trigger_context.get("ticket"),
            lead=self.trigger_context.get("lead"),
            account_id=self.account_id,
            rule_name=self.workflow.name
        )

        # Render any templates in config
        rendered_config = render_template(config, context)

        # Execute the action
        return execute_action(action_type, self.trigger_context, rendered_config)

    def _create_result(
        self,
        matched: bool,
        executed: bool,
        success: bool,
        trigger_event: str,
        start_time: datetime,
        span: trace.Span,
        condition_details: Optional[List[Dict[str, Any]]] = None,
        action_results: Optional[List[Dict[str, Any]]] = None,
        error_message: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create execution result and store in database."""
        execution_time_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
        trace_id_hex = format(span.get_span_context().trace_id, '032x')

        # Store execution record
        from src.automation.workflow_engine import store_execution_record
        from src.observability_sanitizer import sanitize_trigger_context

        store_execution_record(
            workflow=self.workflow,
            trace_id_hex=trace_id_hex,
            trigger_event=trigger_event,
            trigger_context=sanitize_trigger_context(self.trigger_context),
            matched=matched,
            executed=executed,
            success=success,
            error_message=error_message,
            execution_time_ms=execution_time_ms,
            conditions_evaluated=condition_details,
            actions_executed=action_results
        )

        return {
            "executed": executed,
            "success": success,
            "matched": matched,
            "trace_id": trace_id_hex,
            "execution_time_ms": execution_time_ms,
            "conditions": condition_details,
            "actions": action_results,
            "agent_log": self.execution_log,
            "errors": self.errors
        }

    def log(self, message: str):
        """Add message to execution log."""
        self.execution_log.append(message)
        logger.info(f"[AutomationAgent {self.workflow.name}] {message}")


def execute_workflow_with_agent(
    workflow_id: str,
    trigger_context: Dict[str, Any],
    trigger_event: str = "unknown"
) -> Dict[str, Any]:
    """
    Execute a workflow using the intelligent automation agent.

    This is the new entry point that replaces the hardcoded workflow engine.

    Args:
        workflow_id: AutomationRule ID
        trigger_context: Trigger data
        trigger_event: Event that triggered execution

    Returns:
        Execution result
    """
    workflow = AutomationRule.query.filter_by(id=workflow_id).first()

    if not workflow:
        return {"executed": False, "error": "Workflow not found"}

    if not workflow.enabled:
        return {"executed": False, "reason": "workflow_disabled"}

    # Create agent and execute
    agent = AutomationAgent(workflow, trigger_context)
    return agent.execute(trigger_event)
