"""
Template Variable Engine for Automation Studio

Supports dynamic variable substitution in webhook payloads and action configurations.
Syntax: {{variable.path}} or {{variable}}

Examples:
    {{email.from}} → "customer@example.com"
    {{extracted.invoice_number}} → "INV-001"
    {{extracted.line_items[0].description}} → "Consulting services"
    {{now}} → "2026-02-12T10:30:00Z"
    {{account_id}} → "123"
"""

import re
from datetime import datetime
from typing import Any, Dict, Optional


def render_template(template: Any, context: Dict[str, Any]) -> Any:
    """
    Recursively render template variables in any data structure.

    Supports:
    - Strings with {{variable}} syntax
    - Nested dictionaries
    - Lists
    - Primitives (numbers, booleans) passed through unchanged

    Args:
        template: Template data (string, dict, list, or primitive)
        context: Variable context dictionary

    Returns:
        Rendered data with all {{variables}} replaced

    Examples:
        >>> context = {"extracted": {"amount": 500}, "email": {"from": "test@example.com"}}
        >>> render_template("Amount: {{extracted.amount}}", context)
        "Amount: 500"

        >>> render_template({"to": "{{email.from}}"}, context)
        {"to": "test@example.com"}
    """
    if isinstance(template, str):
        return _render_string(template, context)
    elif isinstance(template, dict):
        return {key: render_template(value, context) for key, value in template.items()}
    elif isinstance(template, list):
        return [render_template(item, context) for item in template]
    else:
        # Numbers, booleans, None - pass through unchanged
        return template


def _render_string(template_str: str, context: Dict[str, Any]) -> Any:
    """
    Render a single template string.

    If the entire string is just one variable (e.g., "{{extracted.amount}}"),
    return the actual value (preserving type - number, boolean, etc.)

    If string contains multiple parts or text + variables, return string.

    Args:
        template_str: Template string with {{variable}} placeholders
        context: Variable context dictionary

    Returns:
        Rendered value (string, number, boolean, etc.)
    """
    # Pattern to match {{variable.path}} or {{variable}}
    pattern = r'\{\{([^}]+)\}\}'

    # Check if entire string is single variable (preserve type)
    single_var_match = re.fullmatch(pattern, template_str.strip())
    if single_var_match:
        var_path = single_var_match.group(1).strip()
        value = _resolve_variable(var_path, context)
        return value  # Return actual type (number, boolean, etc.)

    # Multiple variables or text + variables - replace all and return string
    def replacer(match):
        var_path = match.group(1).strip()
        value = _resolve_variable(var_path, context)
        # Convert to string for concatenation
        return str(value) if value is not None else ""

    return re.sub(pattern, replacer, template_str)


def _resolve_variable(var_path: str, context: Dict[str, Any]) -> Any:
    """
    Resolve a variable path like "email.from" or "extracted.line_items[0].amount"

    Supports:
    - Dot notation: email.from
    - Array indexing: line_items[0]
    - Nested paths: extracted.line_items[0].description
    - System variables: now, account_id, rule_name

    Args:
        var_path: Variable path (e.g., "email.from", "extracted.amount")
        context: Variable context dictionary

    Returns:
        Resolved value or None if not found
    """
    # System variables
    if var_path == "now":
        return datetime.utcnow().isoformat() + "Z"
    elif var_path == "today":
        return datetime.utcnow().date().isoformat()

    # Split path into parts (handle both dots and brackets)
    # Example: "extracted.line_items[0].description" → ["extracted", "line_items", "0", "description"]
    parts = re.split(r'\.|\[|\]', var_path)
    parts = [p for p in parts if p]  # Remove empty strings

    # Traverse context
    current = context
    for part in parts:
        if current is None:
            return None

        # Try array index first
        if part.isdigit():
            index = int(part)
            if isinstance(current, (list, tuple)) and 0 <= index < len(current):
                current = current[index]
            else:
                return None
        # Dictionary key
        elif isinstance(current, dict):
            current = current.get(part)
        # Object attribute
        elif hasattr(current, part):
            current = getattr(current, part)
        else:
            return None

    return current


def build_context(
    email: Optional[Dict[str, Any]] = None,
    extracted: Optional[Dict[str, Any]] = None,
    ticket: Optional[Dict[str, Any]] = None,
    lead: Optional[Dict[str, Any]] = None,
    account_id: Optional[int] = None,
    rule_name: Optional[str] = None,
    custom: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Build template context from available data sources.

    Args:
        email: Email data (from, to, subject, body, etc.)
        extracted: AI-extracted data (invoice_number, amount, etc.)
        ticket: Ticket data
        lead: Lead data
        account_id: Current account ID
        rule_name: Automation rule name
        custom: Additional custom variables

    Returns:
        Complete context dictionary for template rendering

    Example:
        >>> context = build_context(
        ...     email={"from": "customer@example.com", "subject": "Invoice"},
        ...     extracted={"invoice_number": "INV-001", "amount": 500},
        ...     account_id=123,
        ...     rule_name="Extract Invoices to Sage"
        ... )
        >>> render_template("{{email.from}}: {{extracted.amount}}", context)
        "customer@example.com: 500"
    """
    context = {}

    if email:
        context["email"] = email
    if extracted:
        context["extracted"] = extracted
    if ticket:
        context["ticket"] = ticket
    if lead:
        context["lead"] = lead
    if account_id:
        context["account_id"] = account_id
    if rule_name:
        context["rule_name"] = rule_name

    # Merge custom variables (can override)
    if custom:
        context.update(custom)

    return context


# Convenience function for common use case
def render_webhook_payload(
    payload_template: Dict[str, Any],
    email: Optional[Dict[str, Any]] = None,
    extracted: Optional[Dict[str, Any]] = None,
    **kwargs
) -> Dict[str, Any]:
    """
    Render a webhook payload template with extracted data and email context.

    Args:
        payload_template: Payload template with {{variables}}
        email: Email data
        extracted: Extracted data
        **kwargs: Additional context (ticket, lead, account_id, etc.)

    Returns:
        Fully rendered payload ready to send

    Example:
        >>> payload_template = {
        ...     "invoice_number": "{{extracted.invoice_number}}",
        ...     "amount": "{{extracted.amount}}",
        ...     "customer_email": "{{email.from}}",
        ...     "processed_at": "{{now}}"
        ... }
        >>> extracted = {"invoice_number": "INV-001", "amount": 500.00}
        >>> email = {"from": "customer@example.com"}
        >>> render_webhook_payload(payload_template, email, extracted)
        {
            "invoice_number": "INV-001",
            "amount": 500.00,
            "customer_email": "customer@example.com",
            "processed_at": "2026-02-12T10:30:00Z"
        }
    """
    context = build_context(email=email, extracted=extracted, **kwargs)
    return render_template(payload_template, context)
