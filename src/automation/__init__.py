"""
Automation Studio - Intelligent agents with tool calling.

This package provides:
- Tool-calling agent (autonomous, like Claude Code)
- DSPy agent (structured LLM reasoning)
- Shared utilities for condition evaluation
- Action handlers for webhooks, email, storage
"""

# Main entry points for automation
from src.automation.tool_calling_agent import execute_workflow_with_tool_calling_agent
from src.automation.dspy_agent import execute_workflow_with_dspy_agent
from src.automation.utils import evaluate_condition, extract_field_value

__all__ = [
    "execute_workflow_with_tool_calling_agent",
    "execute_workflow_with_dspy_agent",
    "evaluate_condition",
    "extract_field_value",
]
