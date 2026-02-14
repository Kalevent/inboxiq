"""
Webhook Actions for Automation Studio

Send data to external APIs (Sage, QuickBooks, Slack, Microsoft Teams, custom webhooks).
Handles authentication, payload rendering, and error handling.
"""

import os
import json
import requests
from typing import Dict, Any
from datetime import datetime
from opentelemetry import trace

from src.models import WebhookProvider, db
from src.automation.template_engine import render_template, build_context
from src.observability import safe_span_attribute


def execute_send_webhook(context: Dict[str, Any], config: Dict[str, Any], span: trace.Span) -> Dict[str, Any]:
    """
    Send data to a configured webhook provider (Sage, QuickBooks, Slack, etc.).

    Config options:
        - provider: Provider ID or name (e.g., "sage_production", provider_id)
        - payload_template: Payload template with {{variables}}
        - method: HTTP method (default: POST)
        - headers: Additional headers (optional)
        - timeout: Request timeout in seconds (default: 30)

    Returns:
        {
            "success": True,
            "result": {
                "status_code": 200,
                "response": {...},
                "provider": "sage_production"
            }
        }
    """
    span.set_attribute("webhook.action", "send")

    try:
        # Get provider configuration
        provider_id = config.get("provider")
        if not provider_id:
            return {"success": False, "error": "No provider specified", "result": None}

        account_id = context.get("account_id")
        provider = WebhookProvider.query.filter_by(
            id=provider_id,
            account_id=account_id,
            enabled=True
        ).first()

        if not provider and isinstance(provider_id, str):
            # Try by configuration name
            provider = WebhookProvider.query.filter_by(
                configuration_name=provider_id,
                account_id=account_id,
                enabled=True
            ).first()

        if not provider:
            return {"success": False, "error": f"Provider not found: {provider_id}", "result": None}

        span.set_attribute("webhook.provider", provider.configuration_name)
        span.set_attribute("webhook.provider_type", provider.provider_type)

        # Decrypt credentials using existing crypto utility
        from src.crypto import decrypt_value
        credentials = json.loads(decrypt_value(provider.credentials_encrypted))

        # Get webhook URL based on provider type
        webhook_url = _get_webhook_url(provider.provider_type, credentials)
        span.set_attribute("webhook.url", safe_span_attribute(webhook_url))

        # Build template context
        template_context = build_context(
            email=context.get("email"),
            extracted=context.get("extracted"),
            ticket=context.get("ticket"),
            lead=context.get("lead"),
            account_id=account_id,
            rule_name=context.get("rule_name"),
        )

        # Render payload template
        payload_template = config.get("payload_template", {})
        rendered_payload = render_template(payload_template, template_context)

        span.set_attribute("webhook.payload_size", len(json.dumps(rendered_payload)))

        # Prepare request
        method = config.get("method", "POST").upper()
        headers = _build_headers(provider.provider_type, credentials, config.get("headers", {}))
        timeout = config.get("timeout", 30)

        span.set_attribute("webhook.method", method)

        # Send webhook request
        response = requests.request(
            method=method,
            url=webhook_url,
            json=rendered_payload,
            headers=headers,
            timeout=timeout
        )

        # Update provider usage
        provider.last_used_at = datetime.utcnow()
        provider.total_requests += 1

        if response.status_code >= 400:
            provider.failed_requests += 1
            db.session.commit()

            span.set_attribute("webhook.success", False)
            span.set_attribute("webhook.status_code", response.status_code)

            return {
                "success": False,
                "error": f"Webhook failed with status {response.status_code}: {response.text[:200]}",
                "result": {
                    "status_code": response.status_code,
                    "response": response.text[:500],
                    "provider": provider.configuration_name
                }
            }

        db.session.commit()

        span.set_attribute("webhook.success", True)
        span.set_attribute("webhook.status_code", response.status_code)

        return {
            "success": True,
            "result": {
                "status_code": response.status_code,
                "response": response.json() if response.headers.get("content-type", "").startswith("application/json") else response.text[:500],
                "provider": provider.configuration_name,
                "url": webhook_url
            },
            "error": None
        }

    except Exception as e:
        span.record_exception(e)
        return {
            "success": False,
            "error": f"Webhook execution failed: {str(e)}",
            "result": None
        }


def execute_conditional_webhook(context: Dict[str, Any], config: Dict[str, Any], span: trace.Span) -> Dict[str, Any]:
    """
    Route to different webhooks based on conditions (e.g., amount thresholds).

    Config options:
        - conditions: List of {condition, provider, payload_template}
        - default_provider: Fallback provider if no conditions match

    Example:
        {
            "conditions": [
                {
                    "condition": {"field": "extracted.amount", "operator": "greater_than", "value": 100},
                    "provider": "slack_approval_channel",
                    "payload_template": {...}
                },
                {
                    "condition": {"field": "extracted.amount", "operator": "less_than_or_equal", "value": 100},
                    "provider": "quickbooks_auto_approve",
                    "payload_template": {...}
                }
            ]
        }

    Returns:
        Result from matched webhook execution
    """
    span.set_attribute("webhook.action", "conditional")

    try:
        conditions = config.get("conditions", [])

        # Evaluate conditions to find match
        from src.automation.utils import evaluate_condition

        for condition_block in conditions:
            condition = condition_block.get("condition")
            if evaluate_condition(condition, context):
                # Condition matched - execute this webhook
                webhook_config = {
                    "provider": condition_block.get("provider"),
                    "payload_template": condition_block.get("payload_template"),
                    "method": condition_block.get("method", "POST"),
                    "headers": condition_block.get("headers", {}),
                }

                span.set_attribute("webhook.condition_matched", True)
                span.set_attribute("webhook.matched_provider", condition_block.get("provider"))

                return execute_send_webhook(context, webhook_config, span)

        # No conditions matched - use default if specified
        default_provider = config.get("default_provider")
        if default_provider:
            span.set_attribute("webhook.condition_matched", False)
            span.set_attribute("webhook.using_default", True)

            webhook_config = {
                "provider": default_provider,
                "payload_template": config.get("default_payload_template", {}),
            }
            return execute_send_webhook(context, webhook_config, span)

        # No match and no default
        return {
            "success": False,
            "error": "No conditions matched and no default provider specified",
            "result": None
        }

    except Exception as e:
        span.record_exception(e)
        return {
            "success": False,
            "error": f"Conditional webhook failed: {str(e)}",
            "result": None
        }


def _get_webhook_url(provider_type: str, credentials: Dict[str, Any]) -> str:
    """Get webhook URL based on provider type and credentials."""
    if provider_type == "sage":
        endpoint = credentials.get("endpoint", "https://api.sage.com/v3")
        company_id = credentials.get("company_id")
        return f"{endpoint}/companies/{company_id}/invoices"

    elif provider_type == "quickbooks":
        realm_id = credentials.get("realm_id")
        environment = credentials.get("environment", "production")
        base_url = "https://quickbooks.api.intuit.com" if environment == "production" else "https://sandbox-quickbooks.api.intuit.com"
        return f"{base_url}/v3/company/{realm_id}/invoice"

    elif provider_type == "slack":
        # Slack incoming webhook URL
        return credentials.get("webhook_url")

    elif provider_type == "teams":
        # Microsoft Teams incoming webhook URL
        return credentials.get("webhook_url")

    elif provider_type == "custom":
        return credentials.get("webhook_url")

    else:
        raise ValueError(f"Unsupported provider type: {provider_type}")


def _build_headers(provider_type: str, credentials: Dict[str, Any], custom_headers: Dict[str, str]) -> Dict[str, str]:
    """Build HTTP headers with authentication based on provider type."""
    headers = {"Content-Type": "application/json"}

    if provider_type == "sage":
        api_key = credentials.get("api_key")
        headers["Authorization"] = f"Bearer {api_key}"

    elif provider_type == "quickbooks":
        # QuickBooks uses OAuth 2.0 - would need token refresh logic
        access_token = credentials.get("access_token")
        headers["Authorization"] = f"Bearer {access_token}"

    elif provider_type == "slack":
        # Slack webhook uses URL-based auth (no header needed)
        pass

    elif provider_type == "teams":
        # Microsoft Teams webhook uses URL-based auth (no header needed)
        pass

    elif provider_type == "custom":
        # Custom webhooks may have authorization header
        auth_header = credentials.get("authorization_header")
        if auth_header:
            headers["Authorization"] = auth_header

    # Merge custom headers (can override)
    headers.update(custom_headers)

    return headers
