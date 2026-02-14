"""
Shared automation utilities.

Functions used across multiple automation components.
"""

from typing import Any, Dict
import logging

logger = logging.getLogger(__name__)


def evaluate_condition(
    condition: Dict[str, Any],
    context: Dict[str, Any]
) -> bool:
    """
    Evaluate a single condition against context.

    Supports operators: equals, not_equals, contains, not_contains, starts_with,
    ends_with, greater_than, less_than, in_list, is_empty, is_not_empty
    """
    field = condition.get("field")
    operator = condition.get("operator")
    expected_value = condition.get("value")

    if not field or not operator:
        logger.warning(f"Invalid condition: missing field or operator: {condition}")
        return False

    actual_value = extract_field_value(context, field)

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
    Extract value from context using dot notation (e.g., 'email.subject', 'ticket.priority').

    Args:
        context: Context dictionary
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
        elif hasattr(value, part):
            value = getattr(value, part)
        else:
            return None

        if value is None:
            return None

    return value
