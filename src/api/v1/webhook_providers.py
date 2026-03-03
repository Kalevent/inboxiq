"""
Automation Studio - Webhook Providers API

Endpoints for managing webhook provider credentials (Sage, QuickBooks, Stripe, etc.)
"""

import json
from flask import request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity

from src.api.v1 import v1
from src.models.automation import WebhookProvider
from src.extensions import db
from src.crypto import encrypt_value, decrypt_value
from uuid import uuid4





@v1.route("/webhook-providers", methods=["GET"])
@jwt_required()
def list_providers():
    """
    List all configured webhook providers for current account.

    Returns:
        {
            "providers": [
                {
                    "id": "provider-123",
                    "provider_type": "sage",
                    "configuration_name": "Production Sage",
                    "environment": "production",
                    "enabled": true,
                    ...
                }
            ]
        }

    Note: Credentials are NOT included in response for security
    """
    account_id = get_jwt_identity()

    providers = WebhookProvider.query.filter_by(account_id=account_id).order_by(
        WebhookProvider.created_at.desc()
    ).all()

    return jsonify({
        "providers": [p.to_dict(include_credentials=False) for p in providers]
    }), 200


@v1.route("/webhook-providers", methods=["POST"])
@jwt_required()
def create_provider():
    """
    Create a new webhook provider configuration.

    Body:
        {
            "provider_type": "sage" | "quickbooks" | "stripe" | "square" | "paypal" | "slack" | "custom",
            "configuration_name": "Production Sage",
            "environment": "production" | "sandbox",
            "credentials": {
                // Provider-specific credentials (will be encrypted)
                // For Sage: {"api_key": "xxx", "company_id": "123", "endpoint": "..."}
                // For QuickBooks: {"client_id": "xxx", "client_secret": "yyy", "realm_id": "zzz"}
                // For Stripe: {"webhook_signing_secret": "whsec_xxx", "api_key": "sk_live_xxx"}
            },
            "destination_provider_id": "provider-456" // Optional, for source providers like Stripe
        }

    Returns:
        {
            "id": "provider-123",
            "provider_type": "sage",
            ...
        }
    """
    account_id = get_jwt_identity()
    data = request.get_json()

    # Validate required fields
    required = ["provider_type", "configuration_name", "credentials"]
    for field in required:
        if field not in data:
            return jsonify({"error": f"Missing required field: {field}"}), 400

    provider_type = data["provider_type"]
    valid_types = ["sage", "quickbooks", "stripe", "square", "paypal", "slack", "custom"]
    if provider_type not in valid_types:
        return jsonify({"error": f"Invalid provider_type. Must be one of: {valid_types}"}), 400

    # Encrypt credentials
    credentials = data["credentials"]
    credentials_json = json.dumps(credentials)
    credentials_encrypted = encrypt_value(credentials_json)

    # Create provider
    provider = WebhookProvider(
        id=str(uuid4()),
        account_id=account_id,
        provider_type=provider_type,
        configuration_name=data["configuration_name"],
        environment=data.get("environment", "production"),
        credentials_encrypted=credentials_encrypted,
        destination_provider_id=data.get("destination_provider_id"),
        enabled=data.get("enabled", True),
    )

    # Handle webhook signing secrets for source providers (Stripe, Square, PayPal)
    if "webhook_signing_secret" in credentials:
        provider.webhook_signing_secret_encrypted = encrypt_value(credentials["webhook_signing_secret"])

    if "api_key" in credentials and provider_type in ["stripe", "square"]:
        provider.api_key_encrypted = encrypt_value(credentials["api_key"])

    db.session.add(provider)
    db.session.commit()

    return jsonify(provider.to_dict(include_credentials=False)), 201


@v1.route("/webhook-providers/<provider_id>", methods=["GET"])
@jwt_required()
def get_provider(provider_id):
    """
    Get a single webhook provider.

    Note: Credentials are NOT included for security.
    Use the test endpoint to verify credentials work.
    """
    account_id = get_jwt_identity()

    provider = WebhookProvider.query.filter_by(id=provider_id, account_id=account_id).first()
    if not provider:
        return jsonify({"error": "Provider not found"}), 404

    return jsonify(provider.to_dict(include_credentials=False)), 200


@v1.route("/webhook-providers/<provider_id>", methods=["PATCH"])
@jwt_required()
def update_provider(provider_id):
    """
    Update a webhook provider.

    Body:
        {
            "configuration_name": "New name",
            "enabled": false,
            "credentials": {...} // Optional - only if updating credentials
        }
    """
    account_id = get_jwt_identity()
    data = request.get_json()

    provider = WebhookProvider.query.filter_by(id=provider_id, account_id=account_id).first()
    if not provider:
        return jsonify({"error": "Provider not found"}), 404

    # Update fields
    if "configuration_name" in data:
        provider.configuration_name = data["configuration_name"]
    if "environment" in data:
        provider.environment = data["environment"]
    if "enabled" in data:
        provider.enabled = data["enabled"]
    if "destination_provider_id" in data:
        provider.destination_provider_id = data["destination_provider_id"]

    # Update credentials if provided
    if "credentials" in data:
        credentials_json = json.dumps(data["credentials"])
        provider.credentials_encrypted = encrypt_value(credentials_json)

        # Update webhook secrets if present
        if "webhook_signing_secret" in data["credentials"]:
            provider.webhook_signing_secret_encrypted = encrypt_value(data["credentials"]["webhook_signing_secret"])

        if "api_key" in data["credentials"]:
            provider.api_key_encrypted = encrypt_value(data["credentials"]["api_key"])

    db.session.commit()

    return jsonify(provider.to_dict(include_credentials=False)), 200


@v1.route("/webhook-providers/<provider_id>", methods=["DELETE"])
@jwt_required()
def delete_provider(provider_id):
    """
    Delete a webhook provider.

    WARNING: This will break any automation rules using this provider.
    """
    account_id = get_jwt_identity()

    provider = WebhookProvider.query.filter_by(id=provider_id, account_id=account_id).first()
    if not provider:
        return jsonify({"error": "Provider not found"}), 404

    db.session.delete(provider)
    db.session.commit()

    return jsonify({"message": "Provider deleted"}), 200


@v1.route("/webhook-providers/<provider_id>/test", methods=["POST"])
@jwt_required()
def test_provider(provider_id):
    """
    Test webhook provider credentials by making a test API call.

    Returns:
        {
            "success": true,
            "message": "Connection successful",
            "response_time_ms": 245
        }
    """
    account_id = get_jwt_identity()

    provider = WebhookProvider.query.filter_by(id=provider_id, account_id=account_id).first()
    if not provider:
        return jsonify({"error": "Provider not found"}), 404

    try:
        # Decrypt credentials
        credentials = json.loads(decrypt_value(provider.credentials_encrypted))

        # Test connection based on provider type
        import requests
        import time

        start = time.time()

        if provider.provider_type == "sage":
            # Test Sage API connection
            endpoint = credentials.get("endpoint", "https://api.sage.com/v3")
            api_key = credentials.get("api_key")
            response = requests.get(
                f"{endpoint}/health",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=10
            )
            response.raise_for_status()

        elif provider.provider_type == "quickbooks":
            # Test QuickBooks connection (would need OAuth token refresh logic)
            return jsonify({
                "success": True,
                "message": "QuickBooks test not implemented (requires OAuth flow)",
                "response_time_ms": 0
            }), 200

        elif provider.provider_type == "slack":
            # Test Slack webhook
            webhook_url = credentials.get("webhook_url")
            response = requests.post(
                webhook_url,
                json={"text": "InboxIQ test message - connection successful!"},
                timeout=10
            )
            response.raise_for_status()

        elif provider.provider_type == "custom":
            # Test custom webhook
            webhook_url = credentials.get("webhook_url")
            response = requests.post(
                webhook_url,
                json={"test": True, "source": "inboxiq"},
                timeout=10
            )
            response.raise_for_status()

        else:
            return jsonify({
                "success": False,
                "error": f"Test not implemented for provider type: {provider.provider_type}"
            }), 400

        duration_ms = (time.time() - start) * 1000

        return jsonify({
            "success": True,
            "message": "Connection successful",
            "response_time_ms": round(duration_ms, 2)
        }), 200

    except requests.exceptions.RequestException as e:
        return jsonify({
            "success": False,
            "error": f"Connection failed: {str(e)}"
        }), 400
    except Exception as e:
        return jsonify({
            "success": False,
            "error": f"Test failed: {str(e)}"
        }), 500
