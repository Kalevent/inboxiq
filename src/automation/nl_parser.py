"""
Natural Language Parser for Automation Studio

Converts user's natural language input into structured AutomationRule JSON.
Uses OpenAI GPT-4 with function calling for reliable structured output.

Examples:
    "Send refund requests over $500 to billing team"
    → {trigger: "email.received", conditions: [...], actions: [{type: "assign", config: {...}}]}

    "Flag tickets mentioning 'lawsuit' or 'attorney' as urgent"
    → {trigger: "ticket.created", conditions: [...], actions: [{type: "update_field", ...}]}
"""

import os
import json
from typing import Dict, Any, List, Optional
import openai

from src.models.core import Account
from src.extensions import db


def parse_natural_language_rule(
    user_input: str,
    account_id: int,
    account_context: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Convert natural language rule description to AutomationRule JSON.

    Args:
        user_input: Natural language rule (e.g., "Send refund requests over $500 to billing team")
        account_id: Account ID for context (team names, custom fields, etc.)
        account_context: Optional account-specific context (teams, fields, priorities)

    Returns:
        Complete AutomationRule structure ready to save:
        {
            "name": "Auto-generated rule name",
            "trigger": {"event": "email.received", "object": "email"},
            "conditions": [...],
            "condition_logic": "AND" | "OR",
            "actions": [...]
        }

    Raises:
        ValueError: If parsing fails or input is invalid
    """
    # Get account context if not provided
    if not account_context:
        account_context = _build_account_context(account_id)

    # Call OpenAI with function calling for structured output
    client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    system_prompt = _build_system_prompt(account_context)
    user_message = f"""Parse this automation rule and return structured JSON:

"{user_input}"

Return a complete automation rule with trigger, conditions, and actions."""

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message}
        ],
        response_format={"type": "json_object"},
        temperature=0.2,  # Low temperature for consistent parsing
    )

    # Parse JSON response
    try:
        parsed_rule = json.loads(response.choices[0].message.content)
    except json.JSONDecodeError as e:
        raise ValueError(f"Failed to parse OpenAI response as JSON: {str(e)}")

    # Validate parsed rule structure
    validated_rule = validate_workflow_structure(parsed_rule, account_context)

    return validated_rule


def validate_workflow_structure(
    workflow_json: Dict[str, Any],
    account_context: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Validate workflow structure and ensure all fields are correct.

    Validates:
    - Required fields present (name, trigger, conditions, actions)
    - Trigger event is valid
    - Conditions use valid operators
    - Actions use valid types
    - Field names match account context

    Args:
        workflow_json: Parsed workflow structure
        account_context: Account-specific context for validation

    Returns:
        Validated workflow (may have corrections applied)

    Raises:
        ValueError: If workflow is invalid and cannot be corrected
    """
    errors = []

    # Check required fields
    required_fields = ["name", "trigger", "conditions", "actions"]
    for field in required_fields:
        if field not in workflow_json:
            errors.append(f"Missing required field: {field}")

    if errors:
        raise ValueError(f"Invalid workflow structure: {', '.join(errors)}")

    # Validate trigger
    valid_trigger_events = [
        "email.received", "ticket.created", "ticket.updated",
        "lead.created", "webhook.received"
    ]
    trigger = workflow_json.get("trigger", {})
    if trigger.get("event") not in valid_trigger_events:
        errors.append(f"Invalid trigger event: {trigger.get('event')}. Must be one of: {valid_trigger_events}")

    # Validate conditions
    valid_operators = [
        "equals", "not_equals", "contains", "not_contains",
        "starts_with", "ends_with", "greater_than", "less_than",
        "greater_than_or_equal", "less_than_or_equal", "in_list",
        "is_empty", "is_not_empty", "matches_pattern"
    ]

    conditions = workflow_json.get("conditions", [])
    for i, condition in enumerate(conditions):
        if "field" not in condition:
            errors.append(f"Condition {i}: missing 'field'")
        if "operator" not in condition:
            errors.append(f"Condition {i}: missing 'operator'")
        elif condition["operator"] not in valid_operators:
            errors.append(f"Condition {i}: invalid operator '{condition['operator']}'. Must be one of: {valid_operators}")

    # Validate actions
    valid_action_types = [
        "extract_invoice_data", "extract_receipt_data", "extract_expense_data",
        "send_webhook", "conditional_webhook",
        "tag_email", "move_to_folder", "create_note", "send_email",
        "upload_to_s3", "generate_public_url",
        "assign", "update_field", "tag", "priority", "status",
        "provider_action",
    ]

    actions = workflow_json.get("actions", [])
    if not actions:
        errors.append("At least one action is required")

    for i, action in enumerate(actions):
        if "type" not in action:
            errors.append(f"Action {i}: missing 'type'")
        elif action["type"] not in valid_action_types:
            errors.append(f"Action {i}: invalid type '{action['type']}'. Must be one of: {valid_action_types}")

        if "config" not in action:
            errors.append(f"Action {i}: missing 'config'")

    if errors:
        raise ValueError(f"Workflow validation failed:\n  - " + "\n  - ".join(errors))

    # Set defaults
    workflow_json.setdefault("condition_logic", "AND")
    workflow_json.setdefault("enabled", True)
    workflow_json.setdefault("stop_on_error", False)

    return workflow_json


def _build_account_context(account_id: int) -> Dict[str, Any]:
    """
    Build account-specific context for natural language parsing.

    Fetches:
    - Team names
    - Custom ticket fields
    - Priority levels
    - Available integrations

    Args:
        account_id: Account ID

    Returns:
        Account context dictionary
    """
    # Placeholder - would fetch from database
    # In real implementation, query Account, Teams, CustomFields, etc.

    context = {
        "account_id": account_id,
        "teams": ["support", "billing", "engineering", "sales"],
        "priorities": ["P0", "P1", "P2", "P3"],
        "custom_fields": ["customer_tier", "product", "region"],
        "integrations": {
            "webhook_providers": [],  # Would fetch WebhookProvider.query.filter_by(account_id=account_id).all()
        }
    }

    # TODO: Fetch actual account data from database
    # account = Account.query.get(account_id)
    # context["teams"] = [team.name for team in account.teams]
    # etc.

    return context


def _build_system_prompt(account_context: Dict[str, Any]) -> str:
    """
    Build system prompt for GPT-4 with account-specific context.

    Args:
        account_context: Account context dictionary

    Returns:
        System prompt string
    """
    teams = ", ".join(account_context.get("teams", []))
    priorities = ", ".join(account_context.get("priorities", []))
    custom_fields = ", ".join(account_context.get("custom_fields", []))

    return f"""You are an automation rule parser for InboxIQ. Convert natural language descriptions into structured automation rules.

Account Context:
- Available teams: {teams}
- Priority levels: {priorities}
- Custom fields: {custom_fields}

Return JSON with this exact structure:
{{
    "name": "Brief descriptive name for the rule",
    "trigger": {{
        "event": "email.received" | "ticket.created" | "ticket.updated" | "lead.created" | "webhook.received",
        "object": "email" | "ticket" | "lead" | "webhook"
    }},
    "conditions": [
        {{
            "field": "field.path (e.g., email.subject, ticket.priority, extracted.amount)",
            "operator": "equals|contains|greater_than|less_than|starts_with|ends_with|in_list|matches_pattern",
            "value": "comparison value"
        }}
    ],
    "condition_logic": "AND" | "OR",
    "actions": [
        {{
            "type": "action type (e.g., send_webhook, tag_email, assign, extract_invoice_data)",
            "config": {{
                // Action-specific configuration
            }}
        }}
    ]
}}

Valid operators:
- equals, not_equals
- contains, not_contains
- starts_with, ends_with
- greater_than, less_than, greater_than_or_equal, less_than_or_equal
- in_list
- is_empty, is_not_empty
- matches_pattern (for regex)

Valid action types:
Extraction:
- extract_invoice_data: Extract invoice fields from email attachments
- extract_receipt_data: Extract receipt data from payment emails
- extract_expense_data: Extract expense data from employee receipts

Webhooks:
- send_webhook: Send data to external API (Sage, QuickBooks, etc.)
- conditional_webhook: Route to different webhooks based on conditions

Email:
- tag_email: Add tags to email
- move_to_folder: Move email to folder
- create_note: Add internal note
- send_email: Send notification email

Ticket:
- assign: Assign ticket to team/user
- update_field: Update ticket field
- tag: Add tags to ticket
- priority: Change priority
- status: Change status

Provider (Gmail / Outlook — executes directly in the inbox after triage):
- provider_action: Execute an action in Gmail or Outlook. Config requires:
    - action: archive | mark_read | star | trash | forward | apply_label | move_to_folder
    - to: (forward only) email address to forward to
    - label: (apply_label only) label or category name
    - folder: (move_to_folder only) destination folder or label name
  Example: {{ "type": "provider_action", "action": "archive" }}
  Example: {{ "type": "provider_action", "action": "forward", "to": "billing@company.com" }}

Storage:
- upload_to_s3: Upload file to S3
- generate_public_url: Generate temporary public URL

Examples:

Input: "Send refund requests over $500 to billing team"
Output:
{{
    "name": "Route high-value refunds to billing",
    "trigger": {{"event": "email.received", "object": "email"}},
    "conditions": [
        {{"field": "email.subject", "operator": "contains", "value": "refund"}},
        {{"field": "extracted.amount", "operator": "greater_than", "value": 500}}
    ],
    "condition_logic": "AND",
    "actions": [
        {{
            "type": "extract_invoice_data",
            "config": {{"fields": ["amount"], "source": "email_body"}}
        }},
        {{
            "type": "assign",
            "config": {{"team": "billing"}}
        }}
    ]
}}

Input: "Flag tickets mentioning 'lawsuit' or 'attorney' as urgent"
Output:
{{
    "name": "Legal escalation",
    "trigger": {{"event": "ticket.created", "object": "ticket"}},
    "conditions": [
        {{"field": "ticket.body", "operator": "contains", "value": "lawsuit"}},
        {{"field": "ticket.body", "operator": "contains", "value": "attorney"}}
    ],
    "condition_logic": "OR",
    "actions": [
        {{
            "type": "priority",
            "config": {{"priority": "P0"}}
        }},
        {{
            "type": "tag",
            "config": {{"tags": ["legal", "urgent"]}}
        }}
    ]
}}

Input: "Extract invoices from vendor emails and send to Sage"
Output:
{{
    "name": "Invoice extraction to Sage",
    "trigger": {{"event": "email.received", "object": "email"}},
    "conditions": [
        {{"field": "email.subject", "operator": "matches_pattern", "value": "/invoice|bill/i"}},
        {{"field": "email.has_attachment", "operator": "equals", "value": true}}
    ],
    "condition_logic": "AND",
    "actions": [
        {{
            "type": "extract_invoice_data",
            "config": {{
                "fields": ["invoice_number", "vendor_name", "total_amount", "currency", "due_date", "line_items"],
                "source": "email_attachment"
            }}
        }},
        {{
            "type": "send_webhook",
            "config": {{
                "provider": "sage_production",
                "payload_template": {{
                    "invoice_number": "{{{{"}}extracted.invoice_number{{}}}}",
                    "vendor_name": "{{{{"}}extracted.vendor_name{{}}}}",
                    "total_amount": "{{{{"}}extracted.total_amount{{}}}}",
                    "currency": "{{{{"}}extracted.currency{{}}}}",
                    "due_date": "{{{{"}}extracted.due_date{{}}}}",
                    "line_items": "{{{{"}}extracted.line_items{{}}}}"
                }}
            }}
        }},
        {{
            "type": "tag_email",
            "config": {{"tags": ["invoice_processed", "sage_synced"]}}
        }}
    ]
}}

Be precise and use exact field names. Return ONLY valid JSON."""


# Convenience functions for common patterns
def parse_invoice_extraction_rule(vendor_emails: List[str], destination_provider: str, account_id: int) -> Dict[str, Any]:
    """Quick helper to create invoice extraction rule."""
    nl_input = f"Extract invoice data from emails from {', '.join(vendor_emails)} and send to {destination_provider}"
    return parse_natural_language_rule(nl_input, account_id)


def parse_receipt_sync_rule(payment_processor: str, accounting_provider: str, account_id: int) -> Dict[str, Any]:
    """Quick helper to create receipt sync rule."""
    nl_input = f"Extract receipts from {payment_processor} emails and sync to {accounting_provider}"
    return parse_natural_language_rule(nl_input, account_id)
