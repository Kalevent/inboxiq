"""
Data sanitization for OpenTelemetry traces.

This module prevents sensitive data leakage in traces by:
- Redacting PII (emails, phone numbers, SSN, credit cards)
- Filtering credentials (API keys, tokens, passwords)
- Sanitizing trigger contexts (email bodies, webhook payloads)
- Hashing sensitive identifiers for tracking without exposure

Compliance:
- GDPR: No PII in traces without explicit consent
- PCI-DSS: No payment card data in logs/traces
- SOC 2: Access controls and audit trails
- HIPAA: No PHI in traces (if applicable)

Usage:
    from src.monitoring.sanitizer import safe_span_attribute, sanitize_trigger_context

    # Safe attribute setting
    safe_span_attribute(span, "email.subject", email.subject)  # PII auto-redacted

    # Safe context storage
    sanitized = sanitize_trigger_context(trigger_context)
    execution.trigger_context = sanitized  # Safe to store in DB
"""
import re
import hashlib
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


# ============================================================================
# PII Detection Patterns
# ============================================================================

EMAIL_PATTERN = re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b')
PHONE_PATTERN = re.compile(r'\b(?:\+?1[-.]?)?\(?([0-9]{3})\)?[-.]?([0-9]{3})[-.]?([0-9]{4})\b')
SSN_PATTERN = re.compile(r'\b\d{3}-\d{2}-\d{4}\b')
CREDIT_CARD_PATTERN = re.compile(r'\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b')

# API key patterns (common formats)
API_KEY_PATTERN = re.compile(r'\b[A-Za-z0-9]{32,}\b')  # Generic long alphanumeric strings
BEARER_TOKEN_PATTERN = re.compile(r'Bearer\s+[A-Za-z0-9\-._~+/]+=*', re.IGNORECASE)


# ============================================================================
# Sensitive Field Names (case-insensitive)
# ============================================================================

SENSITIVE_FIELDS = {
    # Authentication & Authorization
    'password', 'secret', 'api_key', 'access_token', 'refresh_token',
    'client_secret', 'webhook_secret', 'private_key', 'auth_token',
    'bearer_token', 'oauth_token', 'session_token', 'jwt', 'api_secret',

    # Payment Data
    'credit_card', 'card_number', 'cvv', 'cvv2', 'cvc', 'card_exp',
    'bank_account', 'routing_number', 'account_number', 'iban',
    'swift', 'sort_code', 'card_holder',

    # Personal Identifiable Information
    'ssn', 'social_security', 'social_security_number', 'national_id',
    'passport', 'drivers_license', 'license_number',

    # Other Sensitive
    'encryption_key', 'signing_key', 'master_key', 'seed_phrase',
    'recovery_code', 'backup_code', 'verification_code', 'otp',
}


# ============================================================================
# Safe Fields (allowlist - can be logged without redaction)
# ============================================================================

SAFE_FIELDS = {
    # IDs (UUIDs, hashes)
    'id', 'uuid', 'ticket_id', 'account_id', 'user_id', 'workflow_id',
    'execution_id', 'trace_id', 'span_id', 'request_id',

    # Metadata
    'status', 'type', 'category', 'priority', 'stage', 'state',
    'success', 'error_type', 'action_type', 'trigger_type',
    'provider', 'integration_type', 'source', 'destination',
    'environment', 'version', 'deployment',

    # Metrics
    'count', 'total', 'duration_ms', 'execution_time_ms',
    'confidence', 'score', 'rating', 'percentage',

    # Timestamps
    'created_at', 'updated_at', 'executed_at', 'timestamp',

    # Lengths (safe metadata)
    'body_length', 'subject_length', 'content_length', 'payload_size',

    # Boolean flags
    'enabled', 'matched', 'executed', 'has_attachments',
}


# ============================================================================
# Core Sanitization Functions
# ============================================================================

def sanitize_value(value: Any, field_name: Optional[str] = None, max_length: int = 200) -> str:
    """
    Sanitize a value for safe tracing.

    Args:
        value: The value to sanitize
        field_name: Optional field name for context-aware sanitization
        max_length: Maximum length for truncation (default: 200)

    Returns:
        str: Sanitized string safe for tracing

    Examples:
        sanitize_value("user@example.com", "email")  # → "[EMAIL_REDACTED]"
        sanitize_value("sk_live_abc123", "api_key")  # → "[REDACTED:api_key]"
        sanitize_value(42, "count")  # → "42"
    """
    if value is None:
        return ""

    # Convert to string
    str_value = str(value)

    # Check if field name is sensitive (full redaction)
    if field_name and field_name.lower() in SENSITIVE_FIELDS:
        return f"[REDACTED:{field_name}]"

    # If field is in safe list, return as-is (truncated)
    if field_name and field_name.lower() in SAFE_FIELDS:
        return str_value[:max_length]

    # Redact PII patterns
    str_value = redact_pii(str_value)

    # Truncate
    if len(str_value) > max_length:
        str_value = str_value[:max_length] + "..."

    return str_value


def redact_pii(text: str) -> str:
    """
    Redact PII from text using regex patterns.

    Args:
        text: Text potentially containing PII

    Returns:
        str: Text with PII redacted

    Examples:
        redact_pii("Contact me at user@example.com")  # → "Contact me at [EMAIL_REDACTED]"
        redact_pii("Call 555-123-4567")  # → "Call [PHONE_REDACTED]"
    """
    # Redact emails
    text = EMAIL_PATTERN.sub('[EMAIL_REDACTED]', text)

    # Redact phone numbers
    text = PHONE_PATTERN.sub('[PHONE_REDACTED]', text)

    # Redact SSN
    text = SSN_PATTERN.sub('[SSN_REDACTED]', text)

    # Redact credit cards
    text = CREDIT_CARD_PATTERN.sub('[CARD_REDACTED]', text)

    # Redact Bearer tokens
    text = BEARER_TOKEN_PATTERN.sub('Bearer [TOKEN_REDACTED]', text)

    return text


def hash_sensitive_value(value: Any, salt: str = "") -> str:
    """
    Hash a sensitive value for tracking without exposing plaintext.

    Useful for:
    - Tracking unique users without storing emails
    - Tracking transactions without storing amounts
    - Deduplication without exposing data

    Args:
        value: Value to hash
        salt: Optional salt for additional security

    Returns:
        str: SHA-256 hash (first 16 chars for brevity)

    Examples:
        hash_sensitive_value("user@example.com")  # → "a3c8f9e1b2d4e5f6"
        hash_sensitive_value("transaction_123")  # → "b4d9e8f2c3a1e5d7"
    """
    str_value = str(value) + salt
    hash_obj = hashlib.sha256(str_value.encode('utf-8'))
    return hash_obj.hexdigest()[:16]


def sanitize_dict(
    data: Dict[str, Any],
    max_depth: int = 3,
    current_depth: int = 0
) -> Dict[str, Any]:
    """
    Recursively sanitize a dictionary for safe tracing.

    Args:
        data: Dictionary to sanitize
        max_depth: Maximum recursion depth (prevents deep nesting)
        current_depth: Current recursion level (internal use)

    Returns:
        dict: Sanitized dictionary

    Examples:
        sanitize_dict({"api_key": "secret", "count": 5})
        # → {"api_key": "[REDACTED]", "count": 5}
    """
    if current_depth >= max_depth:
        return {"_truncated": "max_depth_reached"}

    sanitized = {}

    for key, value in data.items():
        # Check if key is sensitive
        if key.lower() in SENSITIVE_FIELDS:
            sanitized[key] = "[REDACTED]"
            continue

        # Recursively sanitize nested dicts
        if isinstance(value, dict):
            sanitized[key] = sanitize_dict(value, max_depth, current_depth + 1)
        # Sanitize lists (limit to 10 items)
        elif isinstance(value, list):
            sanitized[key] = [sanitize_value(item, key) for item in value[:10]]
            if len(value) > 10:
                sanitized[key].append(f"... ({len(value) - 10} more items)")
        else:
            sanitized[key] = sanitize_value(value, key)

    return sanitized


# ============================================================================
# OpenTelemetry Span Helpers
# ============================================================================

def safe_span_attribute(span, key: str, value: Any, allow_pii: bool = False):
    """
    Safely set span attribute with automatic sanitization.

    This is the primary function for setting span attributes safely.

    Args:
        span: OpenTelemetry span
        key: Attribute key
        value: Attribute value (will be sanitized)
        allow_pii: If True, skip PII redaction (use carefully!)

    Examples:
        safe_span_attribute(span, "email.subject", email.subject)
        # → PII redacted automatically

        safe_span_attribute(span, "invoice.amount", 500.00)
        # → Numeric values are safe unless field name is sensitive

        safe_span_attribute(span, "api_key", key)
        # → Automatically redacted to "[REDACTED:api_key]"

    Security Notes:
        - NEVER set allow_pii=True for user-provided content
        - Use allow_pii=True ONLY for internal system values you control
        - Numeric values (int, float, bool) are safe unless field name is sensitive
    """
    # Special handling for safe numeric values
    if isinstance(value, (int, float, bool)):
        # Numeric values are safe unless field name is sensitive
        if key.lower() in SENSITIVE_FIELDS:
            span.set_attribute(key, "[REDACTED]")
        else:
            span.set_attribute(key, value)
        return

    # Sanitize string values
    if allow_pii:
        sanitized = str(value)[:200]  # Just truncate, no PII redaction
    else:
        sanitized = sanitize_value(value, key, max_length=200)

    span.set_attribute(key, sanitized)


# ============================================================================
# Context-Specific Sanitizers
# ============================================================================

def sanitize_trigger_context(context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Sanitize trigger context before storing in trace/database.

    This is CRITICAL for workflow execution tracing where trigger context
    may contain entire email bodies, webhook payloads, payment data, etc.

    Args:
        context: Raw trigger context

    Returns:
        dict: Sanitized context safe for storage

    Examples:
        # Email trigger
        context = {
            "type": "email",
            "email": {
                "from": "user@example.com",
                "subject": "Refund request",
                "body": "I want a refund for order #12345..."
            }
        }
        sanitized = sanitize_trigger_context(context)
        # → Stores only metadata, not full body

        # Webhook trigger
        context = {
            "type": "webhook",
            "webhook": {
                "provider": "stripe",
                "payload": {"card_number": "4242..."}
            }
        }
        sanitized = sanitize_trigger_context(context)
        # → Payload NOT stored, only metadata
    """
    sanitized = {
        "type": context.get("type", "unknown"),
        "source": context.get("source", "unknown"),
        "timestamp": context.get("timestamp"),
    }

    # Email triggers: Only store metadata (NOT full body)
    if context.get("type") == "email":
        email_data = context.get("email", {})
        sanitized["email"] = {
            "id": email_data.get("id"),
            "from_domain": extract_domain(email_data.get("from", "")),
            "subject_length": len(email_data.get("subject", "")),
            "body_length": len(email_data.get("body", "")),
            "has_attachments": email_data.get("has_attachments", False),
            "attachment_count": len(email_data.get("attachments", [])),
        }

    # Webhook triggers: Sanitize payload (NO sensitive data)
    elif context.get("type") == "webhook":
        webhook_data = context.get("webhook", {})
        sanitized["webhook"] = {
            "provider": webhook_data.get("provider"),
            "event_type": webhook_data.get("event_type"),
            "payload_size": len(str(webhook_data.get("payload", {}))),
            # Do NOT store full payload (may contain PII, payment data)
        }

    # Payment processor triggers: Hash transaction IDs, redact card data
    elif context.get("type") in ["stripe", "square", "paypal"]:
        payment_data = context.get(context["type"], {})
        sanitized[context["type"]] = {
            "transaction_id_hash": hash_sensitive_value(payment_data.get("transaction_id", "")),
            "amount_cents": payment_data.get("amount_cents"),  # OK - numeric
            "currency": payment_data.get("currency"),
            "status": payment_data.get("status"),
            # Do NOT store: card details, customer emails, billing addresses
        }

    # Ticket triggers: Sanitize ticket data
    elif context.get("type") == "ticket":
        ticket_data = context.get("ticket", {})
        sanitized["ticket"] = {
            "id": ticket_data.get("id"),
            "category": ticket_data.get("category"),
            "priority": ticket_data.get("priority"),
            "status": ticket_data.get("status"),
            "subject_length": len(ticket_data.get("subject", "")),
            # Do NOT store full subject/body (may contain PII)
        }

    # Generic fallback: Sanitize all fields
    else:
        for key, value in context.items():
            if key not in ["type", "source", "timestamp"]:
                if isinstance(value, dict):
                    sanitized[key] = sanitize_dict(value, max_depth=2)
                else:
                    sanitized[key] = sanitize_value(value, key, max_length=100)

    return sanitized


def extract_domain(email: str) -> str:
    """
    Extract domain from email address (safe to store).

    Args:
        email: Email address

    Returns:
        str: Domain part (e.g., "example.com") or "[NO_EMAIL]"

    Examples:
        extract_domain("user@example.com")  # → "example.com"
        extract_domain("invalid")  # → "[NO_EMAIL]"
    """
    match = EMAIL_PATTERN.search(email)
    if match:
        email_str = match.group(0)
        if '@' in email_str:
            return email_str.split('@')[1]
    return "[NO_EMAIL]"


# ============================================================================
# Validation Helpers
# ============================================================================

def contains_pii(text: str) -> bool:
    """
    Check if text contains PII patterns.

    Args:
        text: Text to check

    Returns:
        bool: True if PII detected

    Examples:
        contains_pii("Contact me at user@example.com")  # → True
        contains_pii("Ticket #12345")  # → False
    """
    if EMAIL_PATTERN.search(text):
        return True
    if PHONE_PATTERN.search(text):
        return True
    if SSN_PATTERN.search(text):
        return True
    if CREDIT_CARD_PATTERN.search(text):
        return True
    return False


def is_sensitive_field(field_name: str) -> bool:
    """
    Check if a field name is sensitive.

    Args:
        field_name: Field name to check

    Returns:
        bool: True if sensitive

    Examples:
        is_sensitive_field("api_key")  # → True
        is_sensitive_field("count")  # → False
    """
    return field_name.lower() in SENSITIVE_FIELDS
