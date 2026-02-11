"""
Automation Studio - Dynamic workflow engine with OpenTelemetry instrumentation.

This package provides:
- Dynamic workflow execution with full tracing
- Condition evaluation with per-condition spans
- Action execution with per-action spans
- User-facing execution history with trace IDs
"""

from src.automation.workflow_engine import (
    execute_automation_workflow,
    evaluate_workflow_conditions,
    execute_workflow_actions,
)

__all__ = [
    "execute_automation_workflow",
    "evaluate_workflow_conditions",
    "execute_workflow_actions",
]
