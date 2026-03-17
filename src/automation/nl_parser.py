"""
Natural Language Parser for Automation Studio

Converts natural language input into structured AutomationRule JSON using DSPy,
respecting DSPY_PROVIDER and DSPY_MODEL env vars like the rest of the pipeline.
"""

import ipaddress
import json
import re
import logging
from typing import Dict, Any, List, Optional

from src.dspy.config import _configure_dspy
from src.dspy.signatures import build_nl_rule_parser

logger = logging.getLogger(__name__)

_EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]+\.[^@\s]+$")
_PRIVATE_NETS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),  # AWS metadata
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
]


def _is_private_ip(host: str) -> bool:
    try:
        addr = ipaddress.ip_address(host)
        return any(addr in net for net in _PRIVATE_NETS)
    except ValueError:
        return False


def parse_natural_language_rule(
    user_input: str,
    account_id: int,
    account_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Convert natural language rule description to AutomationRule JSON via DSPy.

    Uses the configured DSPY_PROVIDER/DSPY_MODEL — same LLM backend as triage.
    The DSPy ChainOfThought module reasons through trigger → conditions → actions
    before producing the final JSON.

    Returns:
        Validated AutomationRule structure ready for the create_rule endpoint.

    Raises:
        ValueError: If parsing or validation fails.
    """
    if not account_context:
        account_context = _build_account_context(account_id)

    _, _, dspy = _configure_dspy()
    parser = build_nl_rule_parser(dspy)

    context_json = json.dumps({
        "teams": account_context.get("teams", []),
        "priorities": account_context.get("priorities", []),
        "custom_fields": account_context.get("custom_fields", []),
    })

    try:
        result = parser(description=user_input, account_context=context_json)
        raw_json = result.rule_json
    except Exception as e:
        logger.error("DSPy NL rule parser failed: %s", e, exc_info=True)
        raise ValueError(f"Failed to generate rule: {e}") from e

    # Strip markdown fences if the model wrapped the output
    raw_json = re.sub(r"^```(?:json)?\s*", "", raw_json.strip(), flags=re.IGNORECASE)
    raw_json = re.sub(r"\s*```$", "", raw_json.strip())

    try:
        parsed_rule = json.loads(raw_json)
    except json.JSONDecodeError as e:
        raise ValueError(f"Model returned invalid JSON: {e}") from e

    # DSPy sometimes double-encodes the output (returns a JSON string instead of object).
    # If json.loads gave us a string, try one more decode.
    if isinstance(parsed_rule, str):
        try:
            parsed_rule = json.loads(parsed_rule)
        except json.JSONDecodeError as e:
            raise ValueError(f"Model returned double-encoded JSON that could not be parsed: {e}") from e

    if not isinstance(parsed_rule, dict):
        raise ValueError(f"Model returned unexpected type {type(parsed_rule).__name__}, expected a JSON object.")

    return validate_workflow_structure(parsed_rule, account_context)


def validate_workflow_structure(
    workflow_json: Dict[str, Any],
    account_context: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Validate workflow structure and ensure all fields are correct.

    Raises:
        ValueError: If workflow is invalid.
    """
    errors = []

    required_fields = ["name", "trigger", "conditions", "actions"]
    for field in required_fields:
        if field not in workflow_json:
            errors.append(f"Missing required field: {field}")

    if errors:
        raise ValueError(f"Invalid workflow structure: {', '.join(errors)}")

    valid_trigger_events = [
        "email.received", "ticket.created", "ticket.updated",
        "lead.created", "webhook.received",
    ]
    trigger = workflow_json.get("trigger", {})
    # Normalise: model sometimes returns trigger as a bare string e.g. "email.received"
    if isinstance(trigger, str):
        trigger = {"event": trigger}
        workflow_json["trigger"] = trigger
    # Fill in missing 'object' from the event name (e.g. "email.received" → "email")
    if isinstance(trigger, dict) and not trigger.get("object") and trigger.get("event"):
        trigger.setdefault("object", trigger["event"].split(".")[0])
    if trigger.get("event") not in valid_trigger_events:
        errors.append(
            f"Invalid trigger event: {trigger.get('event')}. "
            f"Must be one of: {valid_trigger_events}"
        )

    valid_operators = [
        "equals", "not_equals", "contains", "not_contains",
        "starts_with", "ends_with", "greater_than", "less_than",
        "greater_than_or_equal", "less_than_or_equal", "in_list",
        "is_empty", "is_not_empty", "matches_pattern",
    ]
    for i, condition in enumerate(workflow_json.get("conditions", [])):
        if "field" not in condition:
            errors.append(f"Condition {i}: missing 'field'")
        if "operator" not in condition:
            errors.append(f"Condition {i}: missing 'operator'")
        elif condition["operator"] not in valid_operators:
            errors.append(
                f"Condition {i}: invalid operator '{condition['operator']}'. "
                f"Must be one of: {valid_operators}"
            )

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
            errors.append(
                f"Action {i}: invalid type '{action['type']}'. "
                f"Must be one of: {valid_action_types}"
            )
        if "config" not in action:
            errors.append(f"Action {i}: missing 'config'")

    for i, action in enumerate(actions):
        errors.extend(_validate_action_config(i, action))

    if errors:
        raise ValueError("Workflow validation failed: " + "; ".join(errors))

    workflow_json.setdefault("condition_logic", "AND")
    workflow_json.setdefault("enabled", True)
    workflow_json.setdefault("stop_on_error", False)

    return workflow_json


def _validate_action_config(index: int, action: Dict[str, Any]) -> List[str]:
    """
    Security-focused validation of action config fields.

    Blocks:
    - SSRF via internal/private URLs in webhook actions
    - Email exfiltration via unvalidated 'to' addresses
    - Path traversal in folder/label names
    - provider_action executing an unrecognised inbox operation
    """
    errors: List[str] = []
    action_type = action.get("type", "")
    config = action.get("config", {})

    if not isinstance(config, dict):
        errors.append(f"Action {index}: 'config' must be an object")
        return errors

    if action_type == "provider_action":
        valid_provider_actions = {"archive", "mark_read", "star", "trash", "forward", "apply_label", "move_to_folder"}
        pa = config.get("action")
        if pa is None:
            errors.append(f"Action {index} (provider_action): 'config.action' is required")
        elif pa not in valid_provider_actions:
            errors.append(f"Action {index} (provider_action): invalid action '{pa}'")
        if pa == "forward":
            to = config.get("to", "")
            if not _EMAIL_RE.match(str(to)):
                errors.append(f"Action {index} (provider_action/forward): 'config.to' must be a valid email address")
        folder = config.get("folder", "")
        if folder and (".." in str(folder) or str(folder).startswith("/")):
            errors.append(f"Action {index} (provider_action): 'config.folder' must not contain path traversal")
        label = config.get("label", "")
        if label and (".." in str(label) or str(label).startswith("/")):
            errors.append(f"Action {index} (provider_action): 'config.label' must not contain path traversal")

    elif action_type in ("send_webhook", "conditional_webhook"):
        url = config.get("url", "")
        if url:
            if not str(url).startswith("https://"):
                errors.append(f"Action {index} ({action_type}): webhook URL must use HTTPS")
            try:
                from urllib.parse import urlparse
                host = urlparse(str(url)).hostname or ""
                if host.lower() in ("localhost", "127.0.0.1", "::1") or _is_private_ip(host):
                    errors.append(f"Action {index} ({action_type}): webhook URL must not target internal/private addresses")
            except Exception:
                errors.append(f"Action {index} ({action_type}): webhook URL is invalid")

    elif action_type == "send_email":
        to = config.get("to", "")
        if to and not _EMAIL_RE.match(str(to)):
            errors.append(f"Action {index} (send_email): 'config.to' must be a valid email address")
        subject = config.get("subject", "")
        if subject and ("\n" in str(subject) or "\r" in str(subject)):
            errors.append(f"Action {index} (send_email): 'config.subject' must not contain newlines")

    elif action_type == "move_to_folder":
        folder = config.get("folder", "")
        if folder and (".." in str(folder) or str(folder).startswith("/")):
            errors.append(f"Action {index} (move_to_folder): 'config.folder' must not contain path traversal")

    return errors


def _build_account_context(account_id: int) -> Dict[str, Any]:
    """Build account-specific context for rule parsing."""
    from src.models.core import Account
    from src.extensions import db

    context: Dict[str, Any] = {
        "account_id": account_id,
        "teams": ["support", "billing", "engineering", "sales"],
        "priorities": ["P0", "P1", "P2", "P3"],
        "custom_fields": ["customer_tier", "product", "region"],
        "integrations": {"webhook_providers": []},
    }

    try:
        account = db.session.get(Account, account_id)
        if account and hasattr(account, "teams"):
            context["teams"] = [t.name for t in account.teams]
    except Exception:
        pass

    return context
