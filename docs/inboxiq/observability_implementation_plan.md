# InboxIQ Observability Implementation Plan

## Executive Summary

This document outlines the implementation of production-grade observability for InboxIQ's AI agents using OpenTelemetry (OTel), OTel Collector, and Phoenix UI. The architecture is designed to be **non-breaking**, **lightweight**, and **gradually deployable**.

**Key Goals:**
- ✅ Full trace visibility into AI agent decisions (DSPy, triage, automation)
- ✅ Audit trail for compliance (ticket processing, invoice extraction)
- ✅ Performance monitoring (latency, token usage, cost tracking)
- ✅ Evaluation feedback loop (accuracy metrics, drift detection)
- ✅ Zero breaking changes to existing application

**Timeline:** 3-5 days for full implementation
**Overhead:** <5ms per request, <2% CPU increase

---

## Architecture Components

```
┌─────────────────────────────────────────────────────────────────┐
│ Kubernetes Cluster                                               │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ InboxIQ Pod                                              │   │
│  │                                                           │   │
│  │  ┌──────────────┐              ┌──────────────┐         │   │
│  │  │ Flask App    │              │ Celery Worker│         │   │
│  │  │              │              │              │         │   │
│  │  │ OTel SDK     │              │ OTel SDK     │         │   │
│  │  │ (Python)     │              │ (Python)     │         │   │
│  │  └──────┬───────┘              └──────┬───────┘         │   │
│  │         │                             │                 │   │
│  │         │    ┌────────────────────────┘                 │   │
│  │         │    │                                          │   │
│  │         ▼    ▼                                          │   │
│  │  ┌──────────────────┐                                  │   │
│  │  │ OTel Collector   │                                  │   │
│  │  │ (sidecar)        │                                  │   │
│  │  │                  │                                  │   │
│  │  │ localhost:4317   │                                  │   │
│  │  └────────┬─────────┘                                  │   │
│  └───────────┼──────────────────────────────────────────────   │
│              │                                                  │
│              ▼                                                  │
│  ┌──────────────────────────────────────────────────────┐     │
│  │ Phoenix Pod                                           │     │
│  │                                                        │     │
│  │  • UI: http://phoenix.inboxiq.svc.cluster.local:6006 │     │
│  │  • OTel receiver: 0.0.0.0:6006                       │     │
│  │  • Storage: SQLite (or PostgreSQL for prod)          │     │
│  │                                                        │     │
│  └────────────────────────────────────────────────────────     │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

### Component Roles

| Component | Purpose | Deployment |
|-----------|---------|------------|
| **OTel SDK (Python)** | In-app instrumentation, creates spans | Embedded in Flask/Celery |
| **OTel Collector** | Aggregates, batches, filters traces | Sidecar container in pod |
| **Phoenix** | Trace viewer, search, analytics | Separate pod + service |

---

## Phase 1: Infrastructure Setup

### 1.1 Python Dependencies

Add to `requirements.txt`:

```txt
# OpenTelemetry core
opentelemetry-api==1.23.0
opentelemetry-sdk==1.23.0
opentelemetry-exporter-otlp==1.23.0

# Auto-instrumentation
opentelemetry-instrumentation-flask==0.44b0
opentelemetry-instrumentation-sqlalchemy==0.44b0
opentelemetry-instrumentation-celery==0.44b0
opentelemetry-instrumentation-redis==0.44b0
opentelemetry-instrumentation-requests==0.44b0

# Distro (convenience wrapper)
opentelemetry-distro==0.44b0
```

**Install:**
```bash
pip install -r requirements.txt
```

---

### 1.2 OTel Collector Configuration

Create `k8s/otel-collector-config.yaml`:

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: otel-collector-config
  namespace: inboxiq
data:
  otel-collector-config.yaml: |
    receivers:
      otlp:
        protocols:
          grpc:
            endpoint: 0.0.0.0:4317
          http:
            endpoint: 0.0.0.0:4318

    processors:
      # Batch spans for efficiency
      batch:
        timeout: 10s
        send_batch_size: 100

      # Sample high-volume, low-value endpoints
      probabilistic_sampler:
        sampling_percentage: 10
        hash_seed: 22

      # Add resource attributes
      resource:
        attributes:
          - key: service.name
            value: inboxiq
            action: upsert
          - key: deployment.environment
            value: ${ENVIRONMENT}
            action: upsert

    exporters:
      # Export to Phoenix
      otlp:
        endpoint: phoenix.inboxiq.svc.cluster.local:6006
        tls:
          insecure: true

      # Debug logging (disable in prod)
      logging:
        loglevel: info

    service:
      pipelines:
        traces:
          receivers: [otlp]
          processors: [batch, resource]
          exporters: [otlp, logging]
```

---

### 1.3 Phoenix Deployment

Create `k8s/phoenix-deployment.yaml`:

```yaml
apiVersion: v1
kind: Service
metadata:
  name: phoenix
  namespace: inboxiq
spec:
  selector:
    app: phoenix
  ports:
    - name: http
      port: 6006
      targetPort: 6006
    - name: grpc
      port: 4317
      targetPort: 4317
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: phoenix
  namespace: inboxiq
spec:
  replicas: 1
  selector:
    matchLabels:
      app: phoenix
  template:
    metadata:
      labels:
        app: phoenix
    spec:
      containers:
        - name: phoenix
          image: arizephoenix/phoenix:latest
          ports:
            - containerPort: 6006
              name: http
            - containerPort: 4317
              name: grpc
          env:
            - name: PHOENIX_PORT
              value: "6006"
            - name: PHOENIX_GRPC_PORT
              value: "4317"
            # For production, use PostgreSQL
            # - name: PHOENIX_DATABASE_URL
            #   value: postgresql://user:pass@postgres:5432/phoenix
          volumeMounts:
            - name: phoenix-data
              mountPath: /phoenix/data
          resources:
            requests:
              memory: "512Mi"
              cpu: "250m"
            limits:
              memory: "1Gi"
              cpu: "500m"
      volumes:
        - name: phoenix-data
          persistentVolumeClaim:
            claimName: phoenix-pvc
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: phoenix-pvc
  namespace: inboxiq
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 10Gi
```

---

### 1.4 Update InboxIQ Deployment

Modify `k8s/inboxiq-deployment.yaml` to add OTel Collector sidecar:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: inboxiq
  namespace: inboxiq
spec:
  template:
    spec:
      containers:
        # Existing Flask app container
        - name: inboxiq-app
          image: inboxiq:latest
          env:
            # ... existing env vars ...

            # OpenTelemetry configuration
            - name: OTEL_ENABLED
              value: "true"
            - name: OTEL_SERVICE_NAME
              value: "inboxiq-app"
            - name: OTEL_EXPORTER_OTLP_ENDPOINT
              value: "http://localhost:4317"
            - name: OTEL_EXPORTER_OTLP_INSECURE
              value: "true"
            - name: OTEL_TRACES_SAMPLER
              value: "parentbased_traceidratio"
            - name: OTEL_TRACES_SAMPLER_ARG
              value: "1.0"  # 100% sampling (adjust in prod)

        # OTel Collector sidecar
        - name: otel-collector
          image: otel/opentelemetry-collector-contrib:0.96.0
          args:
            - --config=/conf/otel-collector-config.yaml
          ports:
            - containerPort: 4317  # OTLP gRPC
            - containerPort: 4318  # OTLP HTTP
          volumeMounts:
            - name: otel-collector-config
              mountPath: /conf
          resources:
            requests:
              memory: "128Mi"
              cpu: "100m"
            limits:
              memory: "256Mi"
              cpu: "200m"

      volumes:
        - name: otel-collector-config
          configMap:
            name: otel-collector-config
```

---

## Phase 2: Application Integration

### 2.1 Initialize OTel SDK in Flask App

Create `src/observability.py`:

```python
"""
OpenTelemetry initialization and utilities.
"""
import os
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.instrumentation.flask import FlaskInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.instrumentation.celery import CeleryInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor


def is_otel_enabled():
    """Check if OpenTelemetry is enabled via environment variable."""
    return os.getenv("OTEL_ENABLED", "false").lower() == "true"


def init_otel(app=None, service_name="inboxiq"):
    """
    Initialize OpenTelemetry SDK and auto-instrumentation.

    Args:
        app: Flask application instance (optional, for Flask instrumentation)
        service_name: Service name for traces

    Returns:
        Tracer instance for custom spans
    """
    if not is_otel_enabled():
        print("OpenTelemetry is disabled (OTEL_ENABLED=false)")
        return trace.get_tracer(__name__)  # Return no-op tracer

    # Create resource with service metadata
    resource = Resource.create({
        "service.name": service_name,
        "service.version": os.getenv("APP_VERSION", "unknown"),
        "deployment.environment": os.getenv("ENVIRONMENT", "development"),
    })

    # Create tracer provider
    provider = TracerProvider(resource=resource)

    # Configure OTLP exporter
    otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
    exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True)

    # Add batch processor (async export)
    processor = BatchSpanProcessor(exporter)
    provider.add_span_processor(processor)

    # Set as global tracer provider
    trace.set_tracer_provider(provider)

    # Auto-instrument libraries
    if app:
        FlaskInstrumentor().instrument_app(app)

    SQLAlchemyInstrumentor().instrument()
    CeleryInstrumentor().instrument()
    RedisInstrumentor().instrument()
    RequestsInstrumentor().instrument()

    print(f"OpenTelemetry initialized: {service_name} → {otlp_endpoint}")

    return trace.get_tracer(__name__)


def get_tracer(name=__name__):
    """Get a tracer instance for creating custom spans."""
    return trace.get_tracer(name)
```

---

### 2.2 Update Flask App Initialization

Modify `src/app.py`:

```python
from src.observability import init_otel

def create_app():
    app = Flask(__name__)

    # ... existing initialization ...

    # Initialize OpenTelemetry (must be after Flask app creation)
    init_otel(app, service_name="inboxiq-flask")

    # ... rest of initialization ...

    return app
```

---

### 2.3 Update Celery Worker Initialization

Modify `src/celery_worker.py` or wherever Celery is initialized:

```python
from src.observability import init_otel

# Initialize Celery
celery = Celery(__name__)

# Initialize OpenTelemetry for Celery workers
init_otel(service_name="inboxiq-celery")
```

---

## Phase 3: Custom Spans for AI Operations

### 3.1 DSPy Triage Instrumentation

Modify `src/dspy_triage.py`:

```python
from src.observability import get_tracer

tracer = get_tracer(__name__)

def triage_ticket(ticket_id, ticket_text, account_id):
    """Triage a support ticket using DSPy."""

    with tracer.start_as_current_span("dspy.triage_ticket") as span:
        # Add context attributes
        span.set_attribute("ticket.id", ticket_id)
        span.set_attribute("ticket.length", len(ticket_text))
        span.set_attribute("account.id", account_id)

        # Load compiled artifact
        artifact_path = "dspy_artifacts/triage_v3.json"
        span.set_attribute("dspy.artifact_path", artifact_path)

        try:
            # Execute DSPy module
            with tracer.start_as_current_span("dspy.forward_pass"):
                result = triage_module(ticket_text)

            # Record results
            span.set_attribute("triage.category", result.category)
            span.set_attribute("triage.priority", result.priority)
            span.set_attribute("triage.confidence", result.confidence)
            span.set_attribute("triage.reasoning", result.reasoning[:200])  # Truncate

            # Add event for audit trail
            span.add_event("triage_completed", {
                "category": result.category,
                "confidence": result.confidence,
            })

            return result

        except Exception as e:
            span.set_attribute("error", True)
            span.record_exception(e)
            raise
```

---

### 3.2 Email Processing Instrumentation

Modify `src/tasks/email_processor.py`:

```python
from src.observability import get_tracer

tracer = get_tracer(__name__)

@celery.task
def process_email(email_id):
    """Process incoming email."""

    with tracer.start_as_current_span("email.process") as span:
        span.set_attribute("email.id", email_id)

        # Fetch email
        with tracer.start_as_current_span("email.fetch"):
            email = Email.query.get(email_id)
            span.set_attribute("email.from", email.from_address)
            span.set_attribute("email.subject", email.subject)
            span.set_attribute("email.has_attachments", bool(email.attachments))

        # Extract attachments
        if email.attachments:
            with tracer.start_as_current_span("email.extract_attachments") as att_span:
                att_span.set_attribute("attachment.count", len(email.attachments))

                for attachment in email.attachments:
                    extract_attachment(attachment, span)

        # Run automation rules
        with tracer.start_as_current_span("automation.evaluate_rules") as rule_span:
            matched_rules = evaluate_rules(email)
            rule_span.set_attribute("rules.matched", len(matched_rules))

            for rule in matched_rules:
                rule_span.add_event("rule_matched", {
                    "rule.id": rule.id,
                    "rule.name": rule.name,
                })
```

---

### 3.3 Invoice/Receipt Extraction Instrumentation

Modify `src/extraction/invoice_extractor.py`:

```python
from src.observability import get_tracer

tracer = get_tracer(__name__)

def extract_invoice_data(pdf_path, ticket_id):
    """Extract structured data from invoice PDF."""

    with tracer.start_as_current_span("extraction.invoice") as span:
        span.set_attribute("ticket.id", ticket_id)
        span.set_attribute("file.path", pdf_path)

        # Parse PDF
        with tracer.start_as_current_span("pdf.parse"):
            text = extract_text_from_pdf(pdf_path)
            span.set_attribute("pdf.text_length", len(text))

        # AI extraction
        with tracer.start_as_current_span("ai.extract_invoice_fields") as ai_span:
            ai_span.set_attribute("model", "gpt-4")

            result = openai_extract_invoice(text)

            # Record extracted fields
            ai_span.set_attribute("invoice.number", result.get("invoice_number"))
            ai_span.set_attribute("invoice.amount", result.get("amount"))
            ai_span.set_attribute("invoice.vendor", result.get("vendor"))
            ai_span.set_attribute("extraction.confidence", result.get("confidence"))

        # Send to accounting software
        if result.get("confidence", 0) > 0.8:
            with tracer.start_as_current_span("integration.send_to_sage") as sage_span:
                send_to_sage(result)
                sage_span.add_event("invoice_exported", {
                    "invoice.number": result["invoice_number"],
                    "destination": "sage",
                })

        return result
```

---

### 3.4 Webhook Intake Instrumentation

Modify `src/api/v1/intake.py`:

```python
from src.observability import get_tracer

tracer = get_tracer(__name__)

@bp.route("/intake", methods=["POST"])
@limiter.limit("30 per minute")
def submit_form():
    """Webhook intake endpoint."""

    with tracer.start_as_current_span("webhook.intake") as span:
        payload = request.get_json()

        # Record webhook metadata
        span.set_attribute("webhook.source", payload.get("source", "unknown"))
        span.set_attribute("webhook.provider", request.headers.get("X-Provider"))
        span.set_attribute("request.ip", request.remote_addr)

        # Validate signature (if payment processor)
        if payload.get("source") == "stripe":
            with tracer.start_as_current_span("webhook.verify_signature") as sig_span:
                is_valid = verify_stripe_signature(request)
                sig_span.set_attribute("signature.valid", is_valid)

                if not is_valid:
                    sig_span.add_event("signature_verification_failed")
                    return jsonify({"error": "Invalid signature"}), 401

        # Create ticket
        with tracer.start_as_current_span("ticket.create"):
            ticket = create_ticket_from_webhook(payload)
            span.set_attribute("ticket.id", ticket.id)

        span.add_event("webhook_processed", {
            "ticket.id": ticket.id,
            "source": payload.get("source"),
        })

        return jsonify({"ticket_id": ticket.id}), 201
```

---

## Phase 3.5: Automation Studio Instrumentation (CRITICAL FOR LAUNCH)

**⚠️ This is the most critical instrumentation** - Automation Studio is your core product feature. Without this, customers have zero visibility into their custom workflows.

### 3.5.1 Why This Matters

Users create **dynamic, custom workflows** through Automation Studio:
- "When email has invoice PDF → Extract data → Send to Sage"
- "When Stripe payment → Create receipt → Export to QuickBooks"
- "When ticket priority = high → Notify Slack → Assign to team"

**Without tracing, customers are blind:**
- ❌ "Why didn't my workflow run?" - Can't see if conditions matched
- ❌ "Which action failed?" - No visibility into execution flow
- ❌ "Why was invoice sent to wrong system?" - No audit trail
- ❌ "Is my automation slow?" - No performance metrics

**With tracing, customers have full transparency:**
- ✅ Self-service debugging via trace IDs
- ✅ Audit compliance (who, what, when)
- ✅ Performance visibility
- ✅ Support can debug via trace links

---

### 3.5.1 Data Sanitization & Security (CRITICAL)

**⚠️ SECURITY WARNING:** Tracing can leak sensitive user data if not properly sanitized!

**Data at risk:**
- 🚨 PII: Email addresses, names, phone numbers, addresses
- 🚨 Payment data: Credit card numbers, amounts, transaction IDs, invoice details
- 🚨 Credentials: API keys, OAuth tokens, webhook secrets, passwords
- 🚨 Business data: Email bodies, customer lists, proprietary information

**Compliance requirements:**
- GDPR (EU): No PII in traces without consent + encryption
- PCI-DSS: No payment card data in logs/traces
- SOC 2: Access controls + audit trails for sensitive data
- HIPAA (if applicable): No PHI in traces

---

#### Sanitization Strategy

Create `src/observability_sanitizer.py`:

```python
"""
Data sanitization for OpenTelemetry traces.

Redacts sensitive information before storing in spans to prevent:
- PII leakage (GDPR violation)
- Payment data exposure (PCI-DSS violation)
- Credential leakage (security breach)
"""

import re
import hashlib
from typing import Any, Dict, Optional


# Patterns for PII detection
EMAIL_PATTERN = re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-z.-]+\.[A-Z|a-z]{2,}\b')
PHONE_PATTERN = re.compile(r'\b(?:\+?1[-.]?)?\(?([0-9]{3})\)?[-.]?([0-9]{3})[-.]?([0-9]{4})\b')
SSN_PATTERN = re.compile(r'\b\d{3}-\d{2}-\d{4}\b')
CREDIT_CARD_PATTERN = re.compile(r'\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b')

# Sensitive field names (case-insensitive)
SENSITIVE_FIELDS = {
    'password', 'secret', 'api_key', 'access_token', 'refresh_token',
    'client_secret', 'webhook_secret', 'private_key', 'auth_token',
    'credit_card', 'card_number', 'cvv', 'ssn', 'social_security',
    'bank_account', 'routing_number', 'api_secret', 'bearer_token'
}

# Safe fields that can be logged (allowlist)
SAFE_FIELDS = {
    'workflow_id', 'account_id', 'trigger_type', 'action_type',
    'status', 'success', 'error_type', 'duration_ms', 'count',
    'provider', 'environment', 'version', 'category', 'priority'
}


def sanitize_value(value: Any, field_name: Optional[str] = None, max_length: int = 100) -> str:
    """
    Sanitize a value for safe tracing.

    Args:
        value: The value to sanitize
        field_name: Optional field name for context-aware sanitization
        max_length: Maximum length for truncation

    Returns:
        Sanitized string safe for tracing
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
        Text with PII redacted
    """
    # Redact emails
    text = EMAIL_PATTERN.sub('[EMAIL_REDACTED]', text)

    # Redact phone numbers
    text = PHONE_PATTERN.sub('[PHONE_REDACTED]', text)

    # Redact SSN
    text = SSN_PATTERN.sub('[SSN_REDACTED]', text)

    # Redact credit cards
    text = CREDIT_CARD_PATTERN.sub('[CARD_REDACTED]', text)

    return text


def hash_sensitive_value(value: Any) -> str:
    """
    Hash a sensitive value for tracking without exposing plaintext.

    Useful for:
    - Tracking unique users without storing emails
    - Tracking transactions without storing amounts
    - Deduplication without exposing data

    Args:
        value: Value to hash

    Returns:
        SHA-256 hash (first 16 chars for brevity)
    """
    str_value = str(value)
    hash_obj = hashlib.sha256(str_value.encode('utf-8'))
    return hash_obj.hexdigest()[:16]


def sanitize_dict(data: Dict[str, Any], max_depth: int = 3, current_depth: int = 0) -> Dict[str, Any]:
    """
    Recursively sanitize a dictionary for safe tracing.

    Args:
        data: Dictionary to sanitize
        max_depth: Maximum recursion depth
        current_depth: Current recursion level

    Returns:
        Sanitized dictionary
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
        # Sanitize lists
        elif isinstance(value, list):
            sanitized[key] = [sanitize_value(item, key) for item in value[:10]]  # Limit to 10 items
        else:
            sanitized[key] = sanitize_value(value, key)

    return sanitized


def safe_span_attribute(span, key: str, value: Any, allow_pii: bool = False):
    """
    Safely set span attribute with automatic sanitization.

    Usage:
        safe_span_attribute(span, "email.subject", email.subject)
        safe_span_attribute(span, "invoice.amount", 500.00)  # OK - numeric
        safe_span_attribute(span, "api_key", key)  # Automatically redacted

    Args:
        span: OpenTelemetry span
        key: Attribute key
        value: Attribute value (will be sanitized)
        allow_pii: If True, skip PII redaction (use carefully!)
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


def sanitize_trigger_context(context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Sanitize trigger context before storing in trace/database.

    This is critical for workflow execution tracing where trigger context
    may contain entire email bodies, webhook payloads, etc.

    Args:
        context: Raw trigger context

    Returns:
        Sanitized context safe for storage
    """
    sanitized = {
        "type": context.get("type", "unknown"),
        "source": context.get("source", "unknown"),
        "timestamp": context.get("timestamp"),
    }

    # For email triggers, only store metadata (not full body)
    if context.get("type") == "email":
        email_data = context.get("email", {})
        sanitized["email"] = {
            "id": email_data.get("id"),
            "from_domain": extract_domain(email_data.get("from", "")),  # Hash or domain only
            "subject_length": len(email_data.get("subject", "")),
            "body_length": len(email_data.get("body", "")),
            "has_attachments": email_data.get("has_attachments", False),
            "attachment_count": len(email_data.get("attachments", [])),
        }

    # For webhook triggers, sanitize payload
    elif context.get("type") == "webhook":
        webhook_data = context.get("webhook", {})
        sanitized["webhook"] = {
            "provider": webhook_data.get("provider"),
            "event_type": webhook_data.get("event_type"),
            "payload_size": len(str(webhook_data.get("payload", {}))),
            # Do NOT store full payload
        }

    # For payment processor triggers, hash transaction IDs
    elif context.get("type") in ["stripe", "square", "paypal"]:
        payment_data = context.get(context["type"], {})
        sanitized[context["type"]] = {
            "transaction_id_hash": hash_sensitive_value(payment_data.get("transaction_id", "")),
            "amount_cents": payment_data.get("amount_cents"),  # OK - numeric
            "currency": payment_data.get("currency"),
            "status": payment_data.get("status"),
            # Do NOT store card details, customer emails, etc.
        }

    return sanitized


def extract_domain(email: str) -> str:
    """Extract domain from email address."""
    match = EMAIL_PATTERN.search(email)
    if match:
        return match.group(0).split('@')[1] if '@' in match.group(0) else "[INVALID]"
    return "[NO_EMAIL]"
```

---

#### Security Checklist for Tracing

Before deploying, verify:

- [ ] **No credentials in spans**: API keys, tokens, passwords always redacted
- [ ] **No full email bodies**: Only metadata (length, has_attachments, etc.)
- [ ] **No credit card data**: PCI-DSS compliance (never log card numbers, CVV)
- [ ] **No full webhook payloads**: Sanitize before storing in trigger_context
- [ ] **PII redaction**: Email addresses, phone numbers, SSN redacted
- [ ] **Account scoping**: Traces only accessible to owning account
- [ ] **Phoenix access control**: VPN-only or authentication required
- [ ] **Encryption at rest**: Phoenix database encrypted (PostgreSQL with encryption)
- [ ] **Retention limits**: Auto-delete traces after 30 days (GDPR compliance)
- [ ] **Audit logging**: Track who accessed which traces

---

#### Example: Safe vs Unsafe Tracing

**❌ UNSAFE (current plan):**
```python
# This leaks PII and sensitive data!
span.set_attribute("condition.actual_value", str(email.subject))  # May contain names, emails
span.set_attribute("action.config", str(action_config))  # May contain API keys
span.set_attribute("email.body", email.body)  # Full email body!
```

**✅ SAFE (updated approach):**
```python
from src.observability_sanitizer import safe_span_attribute, sanitize_trigger_context, hash_sensitive_value

# Safe: Sanitized automatically
safe_span_attribute(span, "condition.actual_value", email.subject)  # PII redacted

# Safe: Only non-sensitive config
safe_span_attribute(span, "action.provider", action_config.get("provider"))  # OK
# API key is redacted automatically:
safe_span_attribute(span, "action.api_key", action_config.get("api_key"))  # → "[REDACTED:api_key]"

# Safe: Only metadata
span.set_attribute("email.subject_length", len(email.subject))
span.set_attribute("email.body_length", len(email.body))
# Full body never logged

# Safe: Hash instead of plaintext
span.set_attribute("customer.email_hash", hash_sensitive_value(customer_email))
```

---

### 3.5.2 Workflow Engine Instrumentation (Updated with Sanitization)

Create `src/automation/workflow_engine.py`:

```python
"""
Automation Studio workflow engine with full OpenTelemetry instrumentation.

This module automatically traces ALL user-created workflows, providing:
- Workflow execution visibility
- Condition evaluation tracing
- Action execution tracing
- User-facing trace IDs for debugging
- SECURE: All sensitive data sanitized before tracing
"""

from datetime import datetime
from uuid import uuid4
from opentelemetry import trace
from src.observability import get_tracer
from src.observability_sanitizer import (
    safe_span_attribute,
    sanitize_trigger_context,
    sanitize_value,
    hash_sensitive_value,
)
from src.models import AutomationRule, AutomationExecution, db

tracer = get_tracer(__name__)


def execute_automation_workflow(workflow_id, trigger_context):
    """
    Execute a user-defined automation workflow with full tracing.

    Args:
        workflow_id: UUID of the automation rule
        trigger_context: Dict with trigger data (email, webhook, event)

    Returns:
        Dict with execution results and trace_id
    """

    with tracer.start_as_current_span("automation.workflow") as workflow_span:
        # Load workflow definition
        workflow = AutomationRule.query.get(workflow_id)

        if not workflow:
            workflow_span.set_attribute("error", True)
            workflow_span.add_event("workflow_not_found", {"workflow_id": str(workflow_id)})
            return {"executed": False, "error": "Workflow not found"}

        # Add workflow metadata
        workflow_span.set_attribute("workflow.id", str(workflow_id))
        workflow_span.set_attribute("workflow.name", workflow.name)
        workflow_span.set_attribute("workflow.owner_account_id", str(workflow.account_id))
        workflow_span.set_attribute("workflow.created_by", str(workflow.created_by_user_id))
        workflow_span.set_attribute("trigger.type", trigger_context.get("type", "unknown"))
        workflow_span.set_attribute("trigger.source", trigger_context.get("source", "unknown"))

        # Evaluate conditions (IF section)
        conditions_met = evaluate_workflow_conditions(workflow, trigger_context, workflow_span)

        if not conditions_met:
            workflow_span.add_event("workflow_skipped", {"reason": "conditions_not_met"})

            # Store execution record (skipped)
            trace_id_hex = format(workflow_span.get_span_context().trace_id, '032x')
            store_execution_record(workflow, trace_id_hex, matched=False, results=[])

            return {"executed": False, "reason": "conditions_not_met", "trace_id": trace_id_hex}

        # Execute actions (THEN section)
        results = execute_workflow_actions(workflow, trigger_context, workflow_span)

        # Record trace ID for user visibility
        trace_id = workflow_span.get_span_context().trace_id
        trace_id_hex = format(trace_id, '032x')

        workflow_span.set_attribute("trace.id", trace_id_hex)
        workflow_span.add_event("workflow_completed", {
            "workflow_id": str(workflow_id),
            "actions_executed": len(results),
            "all_successful": all(r.get("success", False) for r in results),
        })

        # Store execution history
        store_execution_record(
            workflow,
            trace_id_hex,
            matched=True,
            results=results,
            trigger_context=trigger_context
        )

        return {
            "executed": True,
            "trace_id": trace_id_hex,
            "results": results,
            "success": all(r.get("success", False) for r in results),
        }


def evaluate_workflow_conditions(workflow, trigger_context, parent_span):
    """
    Evaluate all workflow conditions with tracing.

    Returns:
        bool: True if conditions are met, False otherwise
    """
    with tracer.start_as_current_span("automation.evaluate_conditions") as cond_span:
        conditions = workflow.conditions_json or []
        cond_span.set_attribute("conditions.count", len(conditions))
        cond_span.set_attribute("conditions.match_type", workflow.match_type or "all")

        if not conditions:
            cond_span.set_attribute("workflow.matched", True)
            return True

        matched_conditions = []

        for idx, condition in enumerate(conditions):
            # Create span for each condition
            condition_type = condition.get("type", "unknown")

            with tracer.start_as_current_span(f"condition.{condition_type}") as c_span:
                c_span.set_attribute("condition.index", idx)
                c_span.set_attribute("condition.field", condition.get("field", ""))
                c_span.set_attribute("condition.operator", condition.get("operator", ""))
                c_span.set_attribute("condition.expected_value", str(condition.get("value", "")))

                # Evaluate condition
                matched = evaluate_single_condition(condition, trigger_context)
                actual_value = extract_field_value(trigger_context, condition.get("field"))

                # SAFE: Sanitize actual value before logging (may contain PII)
                safe_span_attribute(c_span, "condition.actual_value", actual_value)
                c_span.set_attribute("condition.matched", matched)

                # Add event for audit trail
                c_span.add_event("condition_evaluated", {
                    "matched": matched,
                    "field": condition.get("field"),
                    "operator": condition.get("operator"),
                })

                matched_conditions.append(matched)

                # Short-circuit if match_type is "all" and condition failed
                if not matched and workflow.match_type == "all":
                    cond_span.set_attribute("workflow.matched", False)
                    cond_span.add_event("workflow_skipped", {
                        "reason": "condition_not_matched",
                        "failed_condition_index": idx,
                        "failed_condition_field": condition.get("field"),
                    })
                    return False

        # Determine overall match based on match_type
        if workflow.match_type == "all":
            all_matched = all(matched_conditions)
        else:  # "any"
            all_matched = any(matched_conditions)

        cond_span.set_attribute("workflow.matched", all_matched)
        cond_span.set_attribute("conditions.matched_count", sum(matched_conditions))

        return all_matched


def execute_workflow_actions(workflow, trigger_context, parent_span):
    """
    Execute all workflow actions with tracing.

    Returns:
        List of action results
    """
    with tracer.start_as_current_span("automation.execute_actions") as actions_span:
        actions = workflow.actions_json or []
        actions_span.set_attribute("actions.count", len(actions))

        results = []

        for idx, action in enumerate(actions):
            action_type = action.get("type", "unknown")

            # Create span for each action
            with tracer.start_as_current_span(f"action.{action_type}") as a_span:
                a_span.set_attribute("action.index", idx)
                a_span.set_attribute("action.type", action_type)

                # SAFE: Do NOT log full config (may contain API keys)
                # Only log safe metadata
                action_config = action.get("config", {})
                if "provider" in action_config:
                    a_span.set_attribute("action.provider", action_config.get("provider"))
                if "destination" in action_config:
                    a_span.set_attribute("action.destination", action_config.get("destination"))

                try:
                    # Execute the action (route to appropriate handler)
                    result = execute_single_action(action, trigger_context, a_span)

                    a_span.set_attribute("action.success", True)
                    a_span.set_attribute("action.duration_ms", result.get("duration_ms", 0))

                    # Add action-specific attributes
                    add_action_attributes(a_span, action_type, result)

                    # Add success event
                    a_span.add_event("action_completed", {
                        "type": action_type,
                        "success": True,
                    })

                    results.append({
                        "action": action_type,
                        "action_index": idx,
                        "success": True,
                        "result": result
                    })

                except Exception as e:
                    # Record failure
                    a_span.set_attribute("action.success", False)
                    a_span.set_attribute("error.message", str(e))
                    a_span.set_attribute("error.type", type(e).__name__)
                    a_span.record_exception(e)

                    a_span.add_event("action_failed", {
                        "type": action_type,
                        "error": str(e),
                        "error_type": type(e).__name__,
                    })

                    results.append({
                        "action": action_type,
                        "action_index": idx,
                        "success": False,
                        "error": str(e)
                    })

                    # Stop execution if configured to stop on error
                    if workflow.stop_on_error:
                        actions_span.set_attribute("workflow.stopped_on_error", True)
                        actions_span.set_attribute("failed_action_index", idx)
                        break

        actions_span.set_attribute("actions.executed", len(results))
        actions_span.set_attribute("actions.successful", sum(1 for r in results if r.get("success")))
        actions_span.set_attribute("actions.failed", sum(1 for r in results if not r.get("success")))

        return results


def add_action_attributes(span, action_type, result):
    """Add action-specific attributes to span based on action type."""

    if action_type == "extract_invoice":
        span.set_attribute("invoice.number", result.get("invoice_number", ""))
        span.set_attribute("invoice.amount", result.get("amount", 0))
        span.set_attribute("invoice.vendor", result.get("vendor", ""))
        span.set_attribute("extraction.confidence", result.get("confidence", 0))

    elif action_type == "extract_receipt":
        span.set_attribute("receipt.number", result.get("receipt_number", ""))
        span.set_attribute("receipt.amount", result.get("amount", 0))
        span.set_attribute("extraction.confidence", result.get("confidence", 0))

    elif action_type == "send_to_sage":
        span.set_attribute("destination.provider", "sage")
        span.set_attribute("sage.response_id", result.get("external_id", ""))
        span.set_attribute("sage.company_id", result.get("company_id", ""))

    elif action_type == "send_to_quickbooks":
        span.set_attribute("destination.provider", "quickbooks")
        span.set_attribute("quickbooks.response_id", result.get("external_id", ""))
        span.set_attribute("quickbooks.realm_id", result.get("realm_id", ""))

    elif action_type == "notify_slack":
        span.set_attribute("slack.channel", result.get("channel", ""))
        span.set_attribute("slack.message_id", result.get("message_id", ""))

    elif action_type == "tag_email":
        span.set_attribute("email.tags", ",".join(result.get("tags", [])))

    elif action_type == "assign_ticket":
        span.set_attribute("ticket.assigned_to", result.get("assigned_to", ""))
        span.set_attribute("ticket.team", result.get("team", ""))


def store_execution_record(workflow, trace_id_hex, matched, results, trigger_context=None):
    """Store execution record in database for user-facing history."""

    # CRITICAL: Sanitize trigger context before storing (may contain PII, email bodies, etc.)
    sanitized_context = sanitize_trigger_context(trigger_context) if trigger_context else None

    execution_record = AutomationExecution(
        id=uuid4(),
        workflow_id=workflow.id,
        account_id=workflow.account_id,
        trace_id=trace_id_hex,
        executed_at=datetime.utcnow(),
        matched=matched,
        actions_executed=len(results) if matched else 0,
        success=all(r.get("success", False) for r in results) if matched else False,
        trigger_type=trigger_context.get("type") if trigger_context else None,
        trigger_context=sanitized_context,  # SAFE: Sanitized version
        results_json=results if matched else None,
    )

    db.session.add(execution_record)
    db.session.commit()


def evaluate_single_condition(condition, trigger_context):
    """Evaluate a single condition. Implement your condition logic here."""
    # Placeholder - implement based on your condition types
    field = condition.get("field")
    operator = condition.get("operator")
    expected_value = condition.get("value")

    actual_value = extract_field_value(trigger_context, field)

    # Implement operator logic (contains, equals, greater_than, etc.)
    if operator == "contains":
        return str(expected_value).lower() in str(actual_value).lower()
    elif operator == "equals":
        return str(actual_value) == str(expected_value)
    elif operator == "greater_than":
        return float(actual_value) > float(expected_value)
    # Add more operators as needed

    return False


def extract_field_value(context, field_path):
    """Extract value from trigger context using dot notation (e.g., 'email.subject')."""
    # Placeholder - implement nested field extraction
    parts = field_path.split(".")
    value = context

    for part in parts:
        if isinstance(value, dict):
            value = value.get(part)
        else:
            return None

    return value


def execute_single_action(action, trigger_context, span):
    """Execute a single action. Route to appropriate handler based on action type."""
    # Placeholder - implement based on your action types
    action_type = action.get("type")

    # Import and call the appropriate action handler
    # Example:
    # if action_type == "extract_invoice":
    #     from src.extraction.invoice_extractor import extract_invoice_data
    #     return extract_invoice_data(trigger_context)

    return {"success": True, "duration_ms": 100}
```

---

### 3.5.3 Database Model for Execution History

Add to `src/models.py`:

```python
class AutomationExecution(db.Model):
    """
    Store automation workflow execution history with trace IDs.

    This provides:
    - User-facing execution history
    - Audit trail for compliance
    - Link to OpenTelemetry traces for debugging
    """
    __tablename__ = "automation_executions"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    workflow_id = db.Column(UUID(as_uuid=True), db.ForeignKey("automation_rules.id"), nullable=False, index=True)
    account_id = db.Column(UUID(as_uuid=True), db.ForeignKey("accounts.id"), nullable=False, index=True)

    # OpenTelemetry trace ID (hex string, 32 chars)
    trace_id = db.Column(String(32), nullable=False, index=True)

    executed_at = db.Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    # Execution results
    matched = db.Column(Boolean, nullable=False)  # Did conditions match?
    actions_executed = db.Column(Integer, default=0)
    success = db.Column(Boolean, nullable=False)  # All actions succeeded?

    # Trigger context
    trigger_type = db.Column(String(50))  # email, webhook, stripe, manual, etc.
    trigger_context = db.Column(JSON)  # Original trigger data

    # Action results
    results_json = db.Column(JSON)  # List of action results with success/failure

    # Relationships
    workflow = db.relationship("AutomationRule", backref="executions")
    account = db.relationship("Account")

    def __repr__(self):
        return f"<AutomationExecution {self.id} workflow={self.workflow_id} success={self.success}>"
```

**Migration:**
```bash
flask db migrate -m "Add automation_executions table for trace history"
flask db upgrade
```

---

### 3.5.4 User-Facing Execution History UI

Create `src/templates/automation_studio/execution_history.html`:

```html
{% extends "base.html" %}

{% block content %}
<div class="max-w-6xl mx-auto px-4 py-8">
  <div class="mb-6">
    <h1 class="text-2xl font-bold text-slate-100">Workflow Execution History</h1>
    <p class="text-sm text-slate-400 mt-2">
      View all executions of your automation workflows with full trace details.
    </p>
  </div>

  <!-- Workflow Info -->
  <div class="bg-slate-900/70 border border-slate-800 rounded-lg p-4 mb-6">
    <h2 class="text-lg font-semibold text-slate-100">{{ workflow.name }}</h2>
    <p class="text-sm text-slate-400 mt-1">{{ workflow.description }}</p>
  </div>

  <!-- Execution Records -->
  <div class="space-y-4">
    {% for execution in executions %}
    <div class="bg-slate-900/70 border border-slate-800 rounded-lg p-5">
      <div class="flex items-start justify-between mb-4">
        <div class="flex-1">
          <div class="flex items-center gap-3">
            <span class="text-sm text-slate-400">
              {{ execution.executed_at.strftime('%Y-%m-%d %H:%M:%S UTC') }}
            </span>

            <!-- Status Badge -->
            {% if execution.success %}
              <span class="inline-flex items-center gap-1 px-2 py-1 rounded-full bg-emerald-500/10 text-emerald-300 text-xs font-medium">
                <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
                  <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd"/>
                </svg>
                Success
              </span>
            {% elif not execution.matched %}
              <span class="inline-flex items-center gap-1 px-2 py-1 rounded-full bg-slate-500/10 text-slate-300 text-xs font-medium">
                <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
                  <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clip-rule="evenodd"/>
                </svg>
                Skipped (conditions not met)
              </span>
            {% else %}
              <span class="inline-flex items-center gap-1 px-2 py-1 rounded-full bg-red-500/10 text-red-300 text-xs font-medium">
                <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
                  <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clip-rule="evenodd"/>
                </svg>
                Failed
              </span>
            {% endif %}
          </div>

          <!-- Execution Details -->
          <div class="mt-3 space-y-2 text-sm">
            {% if execution.matched %}
              <div class="text-slate-300">
                <span class="text-slate-500">Actions executed:</span> {{ execution.actions_executed }}
              </div>
            {% endif %}

            {% if execution.trigger_type %}
              <div class="text-slate-300">
                <span class="text-slate-500">Triggered by:</span> {{ execution.trigger_type }}
              </div>
            {% endif %}
          </div>
        </div>

        <!-- Trace ID Section -->
        <div class="ml-4 bg-slate-950/60 border border-slate-700 rounded-lg px-4 py-3">
          <div class="text-xs text-slate-500 mb-1">🔍 Trace ID</div>
          <code class="text-xs text-indigo-300 font-mono">{{ execution.trace_id }}</code>

          {% if phoenix_url %}
          <a href="{{ phoenix_url }}/traces/{{ execution.trace_id }}"
             target="_blank"
             class="mt-2 inline-flex items-center gap-1 text-xs text-indigo-400 hover:text-indigo-300">
            View detailed trace
            <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"/>
            </svg>
          </a>
          {% endif %}
        </div>
      </div>

      <!-- Action Results (if executed) -->
      {% if execution.matched and execution.results_json %}
      <details class="mt-4">
        <summary class="text-sm text-slate-400 cursor-pointer hover:text-slate-300">
          View action results
        </summary>
        <div class="mt-3 space-y-2">
          {% for result in execution.results_json %}
          <div class="bg-slate-950/40 border border-slate-800 rounded px-3 py-2 text-sm">
            <div class="flex items-center gap-2">
              {% if result.success %}
                <span class="text-emerald-400">✓</span>
              {% else %}
                <span class="text-red-400">✗</span>
              {% endif %}
              <span class="text-slate-300">{{ result.action }}</span>
            </div>

            {% if not result.success and result.error %}
            <div class="mt-1 text-xs text-red-300">
              Error: {{ result.error }}
            </div>
            {% endif %}
          </div>
          {% endfor %}
        </div>
      </details>
      {% endif %}
    </div>
    {% endfor %}

    {% if not executions %}
    <div class="bg-slate-900/70 border border-slate-800 rounded-lg p-8 text-center">
      <p class="text-slate-400">No executions yet. This workflow hasn't been triggered.</p>
    </div>
    {% endif %}
  </div>
</div>
{% endblock %}
```

---

### 3.5.5 Add Route for Execution History

Add to `src/automation_studio/routes.py`:

```python
from src.observability import get_tracer

tracer = get_tracer(__name__)

@bp.route("/workflows/<workflow_id>/history")
@login_required
def workflow_history(workflow_id):
    """Show execution history for a workflow with trace links."""

    account_id = g.current_account_id

    # Fetch workflow
    workflow = AutomationRule.query.filter_by(
        id=workflow_id,
        account_id=account_id
    ).first_or_404()

    # Fetch execution history (last 100 executions)
    executions = AutomationExecution.query.filter_by(
        workflow_id=workflow_id,
        account_id=account_id
    ).order_by(
        AutomationExecution.executed_at.desc()
    ).limit(100).all()

    # Phoenix URL (configurable)
    phoenix_url = os.getenv("PHOENIX_UI_URL", "http://localhost:6006")

    return render_template(
        "automation_studio/execution_history.html",
        workflow=workflow,
        executions=executions,
        phoenix_url=phoenix_url,
    )
```

---

### 3.5.6 Integration Points

**Trigger workflow execution from existing code:**

```python
# src/tasks/email_processor.py

from src.automation.workflow_engine import execute_automation_workflow

@celery.task
def process_email(email_id):
    """Process incoming email and trigger matching workflows."""

    email = Email.query.get(email_id)

    # Find matching workflows
    workflows = AutomationRule.query.filter_by(
        account_id=email.account_id,
        trigger_type="email",
        active=True
    ).all()

    for workflow in workflows:
        # Execute workflow with tracing
        trigger_context = {
            "type": "email",
            "source": "inbox",
            "email": {
                "id": str(email.id),
                "from": email.from_address,
                "subject": email.subject,
                "body": email.body,
                "has_attachments": bool(email.attachments),
            }
        }

        result = execute_automation_workflow(workflow.id, trigger_context)

        # Log result
        if result.get("executed"):
            print(f"Workflow {workflow.id} executed. Trace ID: {result['trace_id']}")
```

---

## Phase 4: Deployment & Testing

### 4.1 Deploy to Kubernetes

```bash
# Deploy Phoenix
kubectl apply -f k8s/phoenix-deployment.yaml

# Deploy OTel Collector config
kubectl apply -f k8s/otel-collector-config.yaml

# Update InboxIQ deployment (with OTel sidecar)
kubectl apply -f k8s/inboxiq-deployment.yaml

# Verify pods are running
kubectl get pods -n inboxiq

# Check logs
kubectl logs -n inboxiq -l app=phoenix
kubectl logs -n inboxiq -l app=inboxiq -c otel-collector
```

---

### 4.2 Access Phoenix UI

```bash
# Port-forward Phoenix UI to local machine
kubectl port-forward -n inboxiq svc/phoenix 6006:6006

# Open browser
open http://localhost:6006
```

---

### 4.3 Validation Tests

**Test 1: Auto-instrumentation**
```bash
# Send test request to Flask app
curl -X POST https://127.0.0.1:8000/api/v1/intake \
  -H "X-Intake-Token: $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"subject": "Test trace", "body": "Verify OTel is working"}'

# Check Phoenix UI for trace:
# - Should see HTTP POST /api/v1/intake span
# - Should see SQLAlchemy query spans
# - Should see Redis operations
```

**Test 2: Custom Spans**
```bash
# Trigger email processing (Celery task)
# Should see:
# - celery.task span
# - email.process span
# - email.fetch span
# - automation.evaluate_rules span
```

**Test 3: DSPy Tracing**
```bash
# Upload a support ticket that triggers triage
# Should see:
# - dspy.triage_ticket span
# - dspy.forward_pass span
# - Attributes: category, confidence, artifact_path
```

---

## Phase 5: Production Configuration

### 5.1 Sampling Strategy

For high-volume production, adjust sampling:

```yaml
# k8s/otel-collector-config.yaml
processors:
  # Sample health checks, keep all errors
  tail_sampling:
    decision_wait: 10s
    policies:
      # Always sample errors
      - name: errors
        type: status_code
        status_code:
          status_codes: [ERROR]

      # Always sample slow requests (>1s)
      - name: slow-requests
        type: latency
        latency:
          threshold_ms: 1000

      # Sample 10% of successful requests
      - name: probabilistic
        type: probabilistic
        probabilistic:
          sampling_percentage: 10
```

---

### 5.2 Cost Optimization

**Estimate trace volume:**
- 1000 requests/day × 10 spans/request = 10,000 spans/day
- Phoenix storage: ~1KB/span = 10MB/day = 300MB/month
- Retention: 30 days = ~10GB storage

**Reduce costs:**
1. Sample low-value endpoints (health checks, static files)
2. Drop spans for known successful patterns
3. Compress attributes (truncate long strings)
4. Export to cheaper storage (S3) for long-term retention

---

### 5.3 Alerting (Optional)

Export metrics from Phoenix to Prometheus:

```python
# src/observability.py
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.exporter.prometheus import PrometheusMetricReader
from prometheus_client import start_http_server

def init_metrics():
    """Initialize Prometheus metrics export."""
    start_http_server(port=8000, addr="0.0.0.0")

    reader = PrometheusMetricReader()
    provider = MeterProvider(metric_readers=[reader])

    # Create custom metrics
    meter = provider.get_meter(__name__)

    # Track DSPy confidence scores
    dspy_confidence = meter.create_histogram(
        "dspy.confidence",
        description="DSPy model confidence scores",
    )

    return meter
```

---

## Success Metrics

### Week 1: Foundation
- ✅ All HTTP requests traced (100% coverage)
- ✅ All Celery tasks traced
- ✅ Phoenix UI accessible and functional
- ✅ OTel Collector running without errors

### Week 2: AI Operations
- ✅ DSPy operations have custom spans with confidence scores
- ✅ Invoice extraction traced end-to-end
- ✅ Webhook intake traced with signature verification
- ✅ **Automation Studio workflows traced (CRITICAL for launch)**
- ✅ **User-facing execution history UI live**

### Week 3: User Visibility
- ✅ **Users can view trace IDs for their workflow executions**
- ✅ **Trace links working (UI → Phoenix)**
- ✅ Condition evaluation visibility (which conditions matched/failed)
- ✅ Action execution visibility (which actions succeeded/failed)
- ✅ Cost analysis: <$50/month for storage

### Pre-Launch (Week 4)
- ✅ **100% of automation workflows have full trace coverage**
- ✅ **Support team trained on using traces for debugging**
- ✅ Evaluation dataset exported from traces
- ✅ Alerts configured for low confidence scores
- ✅ Documentation for customers on using execution history

### Month 1 Post-Launch
- ✅ 95% of AI decisions have audit trail
- ✅ Mean time to debug reduced by 50%
- ✅ 3+ production issues identified and fixed via traces
- ✅ **Customer success: Users debugging their own workflows via traces**
- ✅ **Support efficiency: Average ticket resolution time reduced by 30%**

---

## Troubleshooting

### Issue: No traces in Phoenix

**Check:**
1. Is `OTEL_ENABLED=true` in env vars?
2. Are Flask/Celery processes restarted?
3. Is OTel Collector running? `kubectl logs -c otel-collector`
4. Is Phoenix reachable? `kubectl get svc phoenix`

**Debug:**
```bash
# Enable verbose logging
export OTEL_LOG_LEVEL=debug

# Check collector logs
kubectl logs -n inboxiq -l app=inboxiq -c otel-collector

# Verify Phoenix is receiving spans
kubectl logs -n inboxiq -l app=phoenix | grep "trace"
```

---

### Issue: High overhead (>5ms latency)

**Solutions:**
1. Reduce sampling rate (sample 10% of successful requests)
2. Disable auto-instrumentation for specific libraries
3. Increase batch size in collector (batch 500 spans before export)
4. Use async export (default, but verify)

---

### Issue: Phoenix storage growing too fast

**Solutions:**
1. Reduce retention period (default 30 days → 7 days)
2. Enable compression in Phoenix config
3. Export old traces to S3 for archival
4. Drop unimportant spans in collector

---

## Rollback Plan

If issues arise, disable OTel without code changes:

```bash
# Set env var to disable
kubectl set env deployment/inboxiq OTEL_ENABLED=false

# Or remove OTel collector sidecar entirely
kubectl apply -f k8s/inboxiq-deployment-no-otel.yaml
```

**Zero code changes needed** - all instrumentation is wrapped in `if is_otel_enabled()` checks.

---

## Next Steps After Implementation

1. **Build Evaluation Pipeline**
   - Export traces to database
   - Label examples (correct/incorrect)
   - Trigger DSPy recompilation when accuracy < 90%

2. **Cost Attribution**
   - Track token usage per customer
   - Alert on anomalous usage spikes
   - Optimize prompts based on cost/quality tradeoff

3. **Custom Dashboards**
   - Build Grafana dashboards for key metrics
   - Export Phoenix data to Prometheus
   - Create SLOs (e.g., 95% of triages complete in <2s)

4. **Incident Response**
   - Use traces to debug production issues
   - Create runbooks linking symptoms → trace queries
   - Post-mortems reference specific trace IDs

---

## Appendix A: File Structure

```
/Users/kofi/inboxiq/
├── src/
│   ├── observability.py              # NEW: OTel initialization
│   ├── app.py                         # MODIFIED: Add init_otel()
│   ├── celery_worker.py              # MODIFIED: Add init_otel()
│   ├── models.py                      # MODIFIED: Add AutomationExecution model
│   ├── dspy_triage.py                # MODIFIED: Add custom spans
│   │
│   ├── automation/
│   │   └── workflow_engine.py        # NEW: Workflow execution with tracing (CRITICAL)
│   │
│   ├── automation_studio/
│   │   └── routes.py                 # MODIFIED: Add execution history route
│   │
│   ├── tasks/
│   │   └── email_processor.py        # MODIFIED: Add custom spans + workflow triggers
│   │
│   ├── extraction/
│   │   └── invoice_extractor.py      # MODIFIED: Add custom spans
│   │
│   ├── api/v1/
│   │   └── intake.py                 # MODIFIED: Add custom spans + workflow triggers
│   │
│   └── templates/
│       └── automation_studio/
│           └── execution_history.html  # NEW: User-facing execution history
│
├── k8s/
│   ├── otel-collector-config.yaml    # NEW: Collector configuration
│   ├── phoenix-deployment.yaml       # NEW: Phoenix UI deployment
│   └── inboxiq-deployment.yaml       # MODIFIED: Add OTel sidecar
│
├── migrations/versions/
│   └── xxx_add_automation_executions.py  # NEW: Migration for execution history
│
├── requirements.txt                  # MODIFIED: Add OTel packages
│
└── docs/inboxiq/
    └── observability_implementation_plan.md  # This document
```

---

## Appendix B: Environment Variables Reference

| Variable | Default | Description |
|----------|---------|-------------|
| `OTEL_ENABLED` | `false` | Master switch for OpenTelemetry |
| `OTEL_SERVICE_NAME` | `inboxiq` | Service name in traces |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `http://localhost:4317` | OTel Collector endpoint |
| `OTEL_TRACES_SAMPLER` | `always_on` | Sampling strategy |
| `OTEL_TRACES_SAMPLER_ARG` | `1.0` | Sampling rate (1.0 = 100%) |
| `OTEL_LOG_LEVEL` | `info` | Logging verbosity |

---

## Appendix C: Phoenix Alternatives

| Tool | Pros | Cons | Use Case |
|------|------|------|----------|
| **Phoenix** | Lightweight, DSPy-native, local | Limited evaluation features | Quick setup, DSPy workflows |
| **Langfuse** | Full evaluation suite, feedback loops | More complex, requires PostgreSQL | Production-grade, ML teams |
| **Jaeger** | Industry standard, mature | No AI-specific features | Generic tracing only |
| **Custom DB** | Full control, cheap | Build everything yourself | Specific requirements |

**Recommendation:** Start with Phoenix, migrate to Langfuse if evaluation features needed.

---

## Questions for Review

### Infrastructure Decisions

1. **Sampling rate:** Start with 100% or sample from day 1?
   - Recommendation: 100% for Automation Studio workflows (critical), 10% for health checks

2. **Phoenix storage:** SQLite (default) or PostgreSQL for production?
   - Recommendation: PostgreSQL for production (better for concurrent writes)

3. **Retention:** 7 days, 30 days, or 90 days?
   - Recommendation: 30 days for compliance/audit trail

4. **Deployment:** Single Phoenix instance or HA setup (3 replicas)?
   - Recommendation: Start with single instance, scale if needed

5. **Access control:** Phoenix UI public or VPN-only?
   - Recommendation: VPN-only for internal use, but expose execution history UI to customers

### Automation Studio Specific

6. **User-facing traces:** Should customers see raw Phoenix traces or simplified execution history only?
   - Option A: Show trace IDs + link to Phoenix (full transparency)
   - Option B: Build custom UI that consumes trace data (more polished)
   - Recommendation: Start with Option A (faster), build Option B post-launch

7. **Execution history retention:** How long to keep `AutomationExecution` records in database?
   - Recommendation: 90 days in database, archive older to S3

8. **Real-time notifications:** Should users get notified when workflows fail?
   - Recommendation: Yes, add webhook/email alerts for failed workflow executions

9. **Performance SLAs:** What's acceptable latency for workflow execution tracing?
   - Recommendation: <10ms overhead per workflow execution

10. **Launch blocker:** Is Automation Studio tracing required before launch or post-launch feature?
    - **CRITICAL:** This should be pre-launch - it's your core product feature!

---

**End of Plan**

Review this plan and let me know if you want to proceed, adjust, or have questions about any section.
