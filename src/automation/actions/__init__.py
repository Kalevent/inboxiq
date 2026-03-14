"""
Automation Studio Action Handlers

This module contains all action handlers that can be executed by automation rules.
Each action type is implemented in a separate file.

Action Handler Interface:
    def execute_ACTION_TYPE(context: dict, config: dict, span: Span) -> dict:
        '''
        Execute an action with OpenTelemetry tracing.

        Args:
            context: Execution context (email, extracted data, ticket, etc.)
            config: Action-specific configuration
            span: OpenTelemetry span for tracing

        Returns:
            dict with:
                - success: bool
                - result: Any (action-specific result data)
                - error: str (if failed)
        '''
        pass
"""

from typing import Dict, Any, Callable
from opentelemetry import trace

# Import action handlers
from src.automation.actions.extraction_actions import (
    execute_extract_invoice_data,
    execute_extract_receipt_data,
    execute_extract_expense_data,
)
from src.automation.actions.webhook_actions import (
    execute_send_webhook,
    execute_conditional_webhook,
)
from src.automation.actions.email_actions import (
    execute_tag_email,
    execute_move_to_folder,
    execute_create_note,
    execute_send_email,
)
from src.automation.actions.storage_actions import (
    execute_upload_to_s3,
    execute_generate_public_url,
)
from src.automation.actions.provider_actions import (
    execute_provider_action,
)


# Action registry: maps action type to handler function
ACTION_HANDLERS: Dict[str, Callable] = {
    # Extraction actions
    "extract_invoice_data": execute_extract_invoice_data,
    "extract_receipt_data": execute_extract_receipt_data,
    "extract_expense_data": execute_extract_expense_data,

    # Webhook actions
    "send_webhook": execute_send_webhook,
    "conditional_webhook": execute_conditional_webhook,

    # Email actions
    "tag_email": execute_tag_email,
    "move_to_folder": execute_move_to_folder,
    "create_note": execute_create_note,
    "send_email": execute_send_email,

    # Storage actions
    "upload_to_s3": execute_upload_to_s3,
    "generate_public_url": execute_generate_public_url,

    # Provider actions — execute directly in Gmail / Outlook after triage
    "provider_action": execute_provider_action,
}


def execute_action(action_type: str, context: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Execute an action by type.

    Args:
        action_type: Action type string (e.g., "extract_invoice_data")
        context: Execution context
        config: Action configuration

    Returns:
        Action result dict with success, result, error

    Raises:
        ValueError: If action type is not registered
    """
    if action_type not in ACTION_HANDLERS:
        available = ", ".join(ACTION_HANDLERS.keys())
        raise ValueError(f"Unknown action type: {action_type}. Available: {available}")

    handler = ACTION_HANDLERS[action_type]

    # Create OpenTelemetry span for action
    tracer = trace.get_tracer(__name__)
    with tracer.start_as_current_span(f"action.{action_type}") as span:
        span.set_attribute("action.type", action_type)
        span.set_attribute("action.config", str(config))

        try:
            result = handler(context, config, span)
            span.set_attribute("action.success", result.get("success", False))
            return result
        except Exception as e:
            span.set_attribute("action.success", False)
            span.set_attribute("action.error", str(e))
            span.record_exception(e)
            return {
                "success": False,
                "error": f"{action_type} failed: {str(e)}",
                "result": None
            }


__all__ = [
    "execute_action",
    "ACTION_HANDLERS",
    # Extraction
    "execute_extract_invoice_data",
    "execute_extract_receipt_data",
    "execute_extract_expense_data",
    # Webhooks
    "execute_send_webhook",
    "execute_conditional_webhook",
    # Email
    "execute_tag_email",
    "execute_move_to_folder",
    "execute_create_note",
    "execute_send_email",
    # Storage
    "execute_upload_to_s3",
    "execute_generate_public_url",
    # Provider
    "execute_provider_action",
]
