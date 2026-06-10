"""
Automation Studio workflow engine with full OpenTelemetry instrumentation.

This module automatically traces ALL user-created workflows, providing:
- Workflow execution visibility
- Condition evaluation tracing
- Action execution tracing
- User-facing trace IDs for debugging
- SECURE: All sensitive data sanitized before tracing

Users create workflows through the UI (stored as JSON in AutomationRule model),
and this engine dynamically executes ANY workflow they create with full observability.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import uuid4

from src.extensions import db
from src.models.automation import AutomationRule, AutomationRuleExecution
from src.monitoring.observability import get_tracer
from src.monitoring.metrics import record_task_cost
from src.monitoring.sanitizer import (
    safe_span_attribute,
    sanitize_trigger_context,
    sanitize_value,
)

logger = logging.getLogger(__name__)
tracer = get_tracer(__name__)


def execute_automation_workflow(
    workflow_id: str,
    trigger_context: Dict[str, Any],
    trigger_event: str = "unknown"
) -> Dict[str, Any]:
    """
    Execute a user-defined automation workflow with full tracing.

    This is the main entry point for executing dynamic user-created workflows.
    Every workflow execution is traced with OpenTelemetry, regardless of what
    the user configured in their workflow.

    Args:
        workflow_id: UUID of the automation rule
        trigger_context: Dict with trigger data (email, webhook, event)
        trigger_event: Event that triggered the workflow (e.g., "ticket.created")

    Returns:
        Dict with execution results and trace_id

    Example:
        result = execute_automation_workflow(
            workflow_id="abc-123",
            trigger_context={"type": "email", "email": {...}},
            trigger_event="ticket.created"
        )
        # result = {
        #     "executed": True,
        #     "trace_id": "a1b2c3d4e5f6...",
        #     "results": [...],
        #     "success": True
        # }
    """
    start_time = time.time()

    with tracer.start_as_current_span("automation.workflow") as workflow_span:
        # Load workflow definition
        workflow = AutomationRule.query.filter_by(id=workflow_id).first()

        if not workflow:
            workflow_span.set_attribute("error", True)
            workflow_span.add_event("workflow_not_found", {"workflow_id": str(workflow_id)})
            logger.warning(f"Workflow not found: {workflow_id}")
            return {"executed": False, "error": "Workflow not found"}

        if not workflow.enabled:
            workflow_span.set_attribute("workflow.enabled", False)
            workflow_span.add_event("workflow_disabled")
            logger.info(f"Workflow disabled: {workflow_id}")
            return {"executed": False, "reason": "workflow_disabled"}

        # Add workflow metadata (safe - no PII)
        workflow_span.set_attribute("workflow.id", str(workflow_id))
        workflow_span.set_attribute("workflow.name", workflow.name)
        workflow_span.set_attribute("workflow.account_id", workflow.account_id)
        if workflow.created_by_user_id:
            workflow_span.set_attribute("workflow.created_by_user_id", workflow.created_by_user_id)

        safe_span_attribute(workflow_span, "trigger.type", trigger_context.get("type", "unknown"))
        safe_span_attribute(workflow_span, "trigger.source", trigger_context.get("source", "unknown"))
        workflow_span.set_attribute("trigger.event", trigger_event)

        # Evaluate conditions (IF section)
        try:
            conditions_met, conditions_detail = evaluate_workflow_conditions(
                workflow, trigger_context, workflow_span
            )
        except Exception as e:
            logger.exception(f"Condition evaluation failed for workflow {workflow_id}: {e}")
            workflow_span.set_attribute("error", True)
            workflow_span.record_exception(e)

            # Record failed execution
            execution_time_ms = (time.time() - start_time) * 1000
            trace_id_hex = format(workflow_span.get_span_context().trace_id, '032x')

            store_execution_record(
                workflow=workflow,
                trace_id_hex=trace_id_hex,
                trigger_event=trigger_event,
                trigger_context=trigger_context,
                matched=False,
                executed=False,
                success=False,
                error_message=str(e),
                execution_time_ms=execution_time_ms,
                conditions_evaluated=None,
                actions_executed=None,
            )

            return {"executed": False, "error": str(e), "trace_id": trace_id_hex}

        if not conditions_met:
            workflow_span.add_event("workflow_skipped", {"reason": "conditions_not_met"})
            logger.debug(f"Workflow {workflow_id} skipped: conditions not met")

            # Store execution record (skipped)
            execution_time_ms = (time.time() - start_time) * 1000
            trace_id_hex = format(workflow_span.get_span_context().trace_id, '032x')

            store_execution_record(
                workflow=workflow,
                trace_id_hex=trace_id_hex,
                trigger_event=trigger_event,
                trigger_context=trigger_context,
                matched=False,
                executed=False,
                success=False,
                error_message=None,
                execution_time_ms=execution_time_ms,
                conditions_evaluated=conditions_detail,
                actions_executed=[],
            )

            return {
                "executed": False,
                "reason": "conditions_not_met",
                "trace_id": trace_id_hex,
                "conditions_detail": conditions_detail,
            }

        # Execute actions (THEN section)
        try:
            results, actions_detail = execute_workflow_actions(
                workflow, trigger_context, workflow_span
            )
        except Exception as e:
            logger.exception(f"Action execution failed for workflow {workflow_id}: {e}")
            workflow_span.set_attribute("error", True)
            workflow_span.record_exception(e)

            # Record failed execution
            execution_time_ms = (time.time() - start_time) * 1000
            trace_id_hex = format(workflow_span.get_span_context().trace_id, '032x')

            store_execution_record(
                workflow=workflow,
                trace_id_hex=trace_id_hex,
                trigger_event=trigger_event,
                trigger_context=trigger_context,
                matched=True,
                executed=False,
                success=False,
                error_message=str(e),
                execution_time_ms=execution_time_ms,
                conditions_evaluated=conditions_detail,
                actions_executed=None,
            )

            return {"executed": False, "error": str(e), "trace_id": trace_id_hex}

        # Record trace ID for user visibility
        trace_id = workflow_span.get_span_context().trace_id
        trace_id_hex = format(trace_id, '032x')
        execution_time_ms = (time.time() - start_time) * 1000

        all_successful = all(r.get("success", False) for r in results)

        workflow_span.set_attribute("trace.id", trace_id_hex)
        workflow_span.set_attribute("workflow.execution_time_ms", execution_time_ms)
        workflow_span.add_event("workflow_completed", {
            "workflow_id": str(workflow_id),
            "actions_executed": len(results),
            "all_successful": all_successful,
            "execution_time_ms": execution_time_ms,
        })

        # Store execution history
        store_execution_record(
            workflow=workflow,
            trace_id_hex=trace_id_hex,
            trigger_event=trigger_event,
            trigger_context=trigger_context,
            matched=True,
            executed=True,
            success=all_successful,
            error_message=None,
            execution_time_ms=execution_time_ms,
            conditions_evaluated=conditions_detail,
            actions_executed=actions_detail,
        )

        logger.info(
            f"Workflow {workflow_id} executed: {len(results)} actions, "
            f"success={all_successful}, trace_id={trace_id_hex}"
        )

        record_task_cost(
            "automation.workflow",
            account_id=workflow.account_id,
            duration_seconds=execution_time_ms / 1000,
            status="success" if all_successful else "failure",
        )

        return {
            "executed": True,
            "trace_id": trace_id_hex,
            "results": results,
            "success": all_successful,
            "execution_time_ms": execution_time_ms,
            "conditions_detail": conditions_detail,
            "actions_detail": actions_detail,
        }


def evaluate_workflow_conditions(
    workflow: AutomationRule,
    trigger_context: Dict[str, Any],
    parent_span
) -> tuple[bool, List[Dict[str, Any]]]:
    """
    Evaluate all workflow conditions with tracing.

    Creates a span for each individual condition to provide granular visibility
    into which conditions matched/failed and why.

    Args:
        workflow: AutomationRule instance
        trigger_context: Trigger data
        parent_span: Parent OpenTelemetry span

    Returns:
        Tuple of (conditions_met: bool, conditions_detail: list)
    """
    with tracer.start_as_current_span("automation.evaluate_conditions") as cond_span:
        conditions = workflow.conditions or []
        match_type = workflow.condition_logic or "AND"

        cond_span.set_attribute("conditions.count", len(conditions))
        cond_span.set_attribute("conditions.match_type", match_type)

        if not conditions:
            cond_span.set_attribute("workflow.matched", True)
            return True, []

        matched_conditions = []
        conditions_detail = []

        for idx, condition in enumerate(conditions):
            # Create span for each condition
            condition_type = condition.get("type", "field_match")
            field = condition.get("field", "")

            with tracer.start_as_current_span(f"condition.{condition_type}") as c_span:
                c_span.set_attribute("condition.index", idx)
                safe_span_attribute(c_span, "condition.field", field)
                safe_span_attribute(c_span, "condition.operator", condition.get("operator", ""))
                safe_span_attribute(c_span, "condition.expected_value", str(condition.get("value", "")))

                # Evaluate condition
                matched = evaluate_single_condition(condition, trigger_context)
                actual_value = extract_field_value(trigger_context, field)

                # SAFE: Sanitize actual value before logging (may contain PII)
                safe_span_attribute(c_span, "condition.actual_value", actual_value)
                c_span.set_attribute("condition.matched", matched)

                # Add event for audit trail
                c_span.add_event("condition_evaluated", {
                    "matched": matched,
                    "field": field,
                    "operator": condition.get("operator", ""),
                })

                # Store detailed result
                conditions_detail.append({
                    "index": idx,
                    "field": field,
                    "operator": condition.get("operator"),
                    "expected": condition.get("value"),
                    "actual": sanitize_value(actual_value, field, max_length=100),
                    "matched": matched,
                })

                matched_conditions.append(matched)

                # Short-circuit if match_type is "AND" and condition failed
                if not matched and match_type == "AND":
                    cond_span.set_attribute("workflow.matched", False)
                    cond_span.add_event("workflow_skipped", {
                        "reason": "condition_not_matched",
                        "failed_condition_index": idx,
                        "failed_condition_field": field,
                    })
                    logger.debug(
                        f"Workflow condition failed (AND): field={field}, "
                        f"operator={condition.get('operator')}, expected={condition.get('value')}, "
                        f"actual={sanitize_value(actual_value, field, max_length=50)}"
                    )
                    return False, conditions_detail

        # Determine overall match based on match_type
        if match_type == "OR":
            all_matched = any(matched_conditions)
        else:  # "AND"
            all_matched = all(matched_conditions)

        cond_span.set_attribute("workflow.matched", all_matched)
        cond_span.set_attribute("conditions.matched_count", sum(matched_conditions))

        return all_matched, conditions_detail


def execute_workflow_actions(
    workflow: AutomationRule,
    trigger_context: Dict[str, Any],
    parent_span
) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Execute all workflow actions with tracing.

    Creates a span for each individual action to provide granular visibility
    into action execution success/failure.

    Args:
        workflow: AutomationRule instance
        trigger_context: Trigger data
        parent_span: Parent OpenTelemetry span

    Returns:
        Tuple of (results: list, actions_detail: list)
    """
    with tracer.start_as_current_span("automation.execute_actions") as actions_span:
        actions = workflow.actions or []
        actions_span.set_attribute("actions.count", len(actions))

        results = []
        actions_detail = []

        for idx, action in enumerate(actions):
            action_type = action.get("type", "unknown")
            action_start_time = time.time()

            # Create span for each action
            with tracer.start_as_current_span(f"action.{action_type}") as a_span:
                a_span.set_attribute("action.index", idx)
                a_span.set_attribute("action.type", action_type)

                # SAFE: Do NOT log full config (may contain API keys)
                # Only log safe metadata
                action_config = action.get("config", {})
                if "provider" in action_config:
                    safe_span_attribute(a_span, "action.provider", action_config.get("provider"))
                if "destination" in action_config:
                    safe_span_attribute(a_span, "action.destination", action_config.get("destination"))

                try:
                    # Execute the action (route to appropriate handler)
                    result = execute_single_action(action, trigger_context, a_span)
                    action_duration_ms = (time.time() - action_start_time) * 1000

                    a_span.set_attribute("action.success", True)
                    a_span.set_attribute("action.duration_ms", action_duration_ms)

                    # Add action-specific attributes
                    add_action_attributes(a_span, action_type, result)

                    # Add success event
                    a_span.add_event("action_completed", {
                        "type": action_type,
                        "success": True,
                        "duration_ms": action_duration_ms,
                    })

                    result_detail = {
                        "action": action_type,
                        "action_index": idx,
                        "success": True,
                        "result": result,
                        "duration_ms": action_duration_ms,
                    }

                    results.append(result_detail)
                    actions_detail.append({
                        "index": idx,
                        "type": action_type,
                        "success": True,
                        "duration_ms": action_duration_ms,
                        "result_summary": str(result).get("summary", str(result))[:200] if result else "OK",
                    })

                    logger.info(
                        f"Action {idx} ({action_type}) executed successfully in {action_duration_ms:.2f}ms"
                    )

                except Exception as e:
                    action_duration_ms = (time.time() - action_start_time) * 1000

                    # Record failure
                    a_span.set_attribute("action.success", False)
                    a_span.set_attribute("error.message", str(e))
                    a_span.set_attribute("error.type", type(e).__name__)
                    a_span.set_attribute("action.duration_ms", action_duration_ms)
                    a_span.record_exception(e)

                    a_span.add_event("action_failed", {
                        "type": action_type,
                        "error": str(e),
                        "error_type": type(e).__name__,
                        "duration_ms": action_duration_ms,
                    })

                    result_detail = {
                        "action": action_type,
                        "action_index": idx,
                        "success": False,
                        "error": str(e),
                        "error_type": type(e).__name__,
                        "duration_ms": action_duration_ms,
                    }

                    results.append(result_detail)
                    actions_detail.append({
                        "index": idx,
                        "type": action_type,
                        "success": False,
                        "error": str(e)[:200],
                        "duration_ms": action_duration_ms,
                    })

                    logger.error(
                        f"Action {idx} ({action_type}) failed after {action_duration_ms:.2f}ms: {e}"
                    )

                    # Stop execution if configured to stop on error
                    if workflow.stop_on_error:
                        actions_span.set_attribute("workflow.stopped_on_error", True)
                        actions_span.set_attribute("failed_action_index", idx)
                        logger.warning("Workflow stopped due to action failure (stop_on_error=True)")
                        break

        actions_span.set_attribute("actions.executed", len(results))
        actions_span.set_attribute("actions.successful", sum(1 for r in results if r.get("success")))
        actions_span.set_attribute("actions.failed", sum(1 for r in results if not r.get("success")))

        return results, actions_detail


def add_action_attributes(span, action_type: str, result: Dict[str, Any]):
    """Add action-specific attributes to span based on action type."""

    if not result or not isinstance(result, dict):
        return

    # Common action types with safe attributes
    if action_type == "assign":
        if "team" in result:
            safe_span_attribute(span, "assign.team", result.get("team"))
        if "user" in result:
            safe_span_attribute(span, "assign.user", result.get("user"))

    elif action_type == "update_field":
        safe_span_attribute(span, "update.field", result.get("field"))
        # Value may contain PII - sanitize
        safe_span_attribute(span, "update.value", result.get("value"))

    elif action_type == "notify":
        safe_span_attribute(span, "notify.channel", result.get("channel"))
        safe_span_attribute(span, "notify.recipient", result.get("recipient"))

    elif action_type == "webhook":
        if "status_code" in result:
            span.set_attribute("webhook.status_code", result.get("status_code"))
        if "response_time_ms" in result:
            span.set_attribute("webhook.response_time_ms", result.get("response_time_ms"))


def store_execution_record(
    workflow: AutomationRule,
    trace_id_hex: str,
    trigger_event: str,
    trigger_context: Dict[str, Any],
    matched: bool,
    executed: bool,
    success: bool,
    error_message: Optional[str],
    execution_time_ms: float,
    conditions_evaluated: Optional[List[Dict[str, Any]]],
    actions_executed: Optional[List[Dict[str, Any]]],
):
    """
    Store execution record in database for user-facing history.

    CRITICAL: Sanitizes trigger context before storing (may contain PII, email bodies, etc.)
    """
    # CRITICAL: Sanitize trigger context before storing (may contain PII, email bodies, etc.)
    sanitized_context = sanitize_trigger_context(trigger_context) if trigger_context else None

    # Extract ticket_id and lead_id if present
    ticket_id = None
    lead_id = None
    if trigger_context:
        if "ticket_id" in trigger_context:
            ticket_id = trigger_context.get("ticket_id")
        elif "ticket" in trigger_context and isinstance(trigger_context["ticket"], dict):
            ticket_id = trigger_context["ticket"].get("id")

        if "lead_id" in trigger_context:
            lead_id = trigger_context.get("lead_id")
        elif "lead" in trigger_context and isinstance(trigger_context["lead"], dict):
            lead_id = trigger_context["lead"].get("id")

    execution_record = AutomationRuleExecution(
        id=str(uuid4()),
        rule_id=workflow.id,
        account_id=workflow.account_id,
        trace_id=trace_id_hex,
        ticket_id=ticket_id,
        lead_id=lead_id,
        trigger_event=trigger_event,
        trigger_type=trigger_context.get("type") if trigger_context else None,
        trigger_context=sanitized_context,  # SAFE: Sanitized version
        matched=matched,
        executed=executed,
        success=success,
        error_message=error_message,
        execution_time_ms=execution_time_ms,
        conditions_evaluated=conditions_evaluated,
        actions_executed=actions_executed,
    )

    db.session.add(execution_record)

    # Update workflow analytics
    workflow.execution_count = (workflow.execution_count or 0) + 1
    if success:
        workflow.success_count = (workflow.success_count or 0) + 1
    if error_message:
        workflow.error_count = (workflow.error_count or 0) + 1
    workflow.last_executed_at = datetime.utcnow()

    # Update average execution time (rolling average)
    if workflow.avg_execution_time_ms:
        workflow.avg_execution_time_ms = (
            workflow.avg_execution_time_ms * 0.9 + execution_time_ms * 0.1
        )
    else:
        workflow.avg_execution_time_ms = execution_time_ms

    db.session.commit()


# ============================================================================
# Condition Evaluation Logic
# ============================================================================


def evaluate_single_condition(
    condition: Dict[str, Any],
    trigger_context: Dict[str, Any]
) -> bool:
    """
    Evaluate a single condition against trigger context.

    Supports operators: equals, not_equals, contains, not_contains, starts_with,
    ends_with, greater_than, less_than, in_list, matches_regex, is_empty, is_not_empty
    """
    field = condition.get("field")
    operator = condition.get("operator")
    expected_value = condition.get("value")

    if not field or not operator:
        logger.warning(f"Invalid condition: missing field or operator: {condition}")
        return False

    actual_value = extract_field_value(trigger_context, field)

    try:
        if operator == "equals":
            return str(actual_value) == str(expected_value)
        elif operator == "not_equals":
            return str(actual_value) != str(expected_value)
        elif operator == "contains":
            return str(expected_value).lower() in str(actual_value).lower()
        elif operator == "not_contains":
            return str(expected_value).lower() not in str(actual_value).lower()
        elif operator == "starts_with":
            return str(actual_value).startswith(str(expected_value))
        elif operator == "ends_with":
            return str(actual_value).endswith(str(expected_value))
        elif operator == "greater_than":
            return float(actual_value) > float(expected_value)
        elif operator == "less_than":
            return float(actual_value) < float(expected_value)
        elif operator == "greater_than_or_equal":
            return float(actual_value) >= float(expected_value)
        elif operator == "less_than_or_equal":
            return float(actual_value) <= float(expected_value)
        elif operator == "in_list":
            # expected_value should be a list
            if isinstance(expected_value, list):
                return actual_value in expected_value
            return False
        elif operator == "is_empty":
            return not actual_value or actual_value == "" or actual_value == []
        elif operator == "is_not_empty":
            return actual_value and actual_value != "" and actual_value != []
        else:
            logger.warning(f"Unknown operator: {operator}")
            return False
    except Exception as e:
        logger.warning(f"Condition evaluation error: {e}")
        return False


def extract_field_value(context: Dict[str, Any], field_path: str) -> Any:
    """
    Extract value from trigger context using dot notation (e.g., 'email.subject', 'ticket.priority').

    Args:
        context: Trigger context dictionary
        field_path: Dot-notation path to field

    Returns:
        Extracted value or None
    """
    if not field_path:
        return None

    parts = field_path.split(".")
    value = context

    for part in parts:
        if isinstance(value, dict):
            value = value.get(part)
        else:
            return None

        if value is None:
            return None

    return value


# ============================================================================
# Action Execution Logic
# ============================================================================


def execute_single_action(
    action: Dict[str, Any],
    trigger_context: Dict[str, Any],
    span
) -> Dict[str, Any]:
    """
    Execute a single action using registered action handlers.

    Supports all action types defined in src/automation/actions/:
    - Data extraction: extract_invoice_data, extract_receipt_data, extract_expense_data
    - Webhooks: send_webhook, conditional_webhook
    - Email: tag_email, move_to_folder, create_note, send_email
    - Storage: upload_to_s3, generate_public_url
    - Ticket: assign, update_field, tag, priority, status

    Args:
        action: Action definition dict with 'type' and 'config'
        trigger_context: Execution context (email, extracted, ticket, lead, account_id)
        span: OpenTelemetry span for recording attributes

    Returns:
        Dict with execution result
    """
    action_type = action.get("type")
    config = action.get("config", {})

    logger.debug(f"Executing action: type={action_type}, config keys={list(config.keys())}")

    # Import action executor
    from src.automation.actions import execute_action

    try:
        # Execute action using registered handler
        result = execute_action(action_type, trigger_context, config)

        # Add result attributes to span
        if result.get("success"):
            span.set_attribute("action.success", True)
            # Add action-specific metrics if available
            if "duration_ms" in result.get("result", {}):
                span.set_attribute("action.duration_ms", result["result"]["duration_ms"])
        else:
            span.set_attribute("action.success", False)
            span.set_attribute("action.error", result.get("error", "Unknown error"))

        return result.get("result", {})

    except ValueError as e:
        # Unknown action type
        logger.warning(f"Unknown action type: {action_type} - {str(e)}")
        span.set_attribute("action.success", False)
        span.set_attribute("action.error", str(e))
        return {
            "summary": f"Action type '{action_type}' not supported",
            "error": str(e)
        }

    except Exception as e:
        # Action execution failed
        logger.error(f"Action execution failed: {action_type} - {str(e)}", exc_info=True)
        span.set_attribute("action.success", False)
        span.set_attribute("action.error", str(e))
        span.record_exception(e)
        return {
            "summary": f"Action '{action_type}' failed",
            "error": str(e)
        }
