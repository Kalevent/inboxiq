"""
OpenTelemetry initialization and utilities for InboxIQ.

This module provides:
- OTel SDK initialization for Flask and Celery
- Auto-instrumentation for Flask, SQLAlchemy, Celery, Redis, Requests
- Tracer instance for creating custom spans
- Feature flag control via OTEL_ENABLED environment variable
"""
import os
import logging
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

logger = logging.getLogger(__name__)


def is_otel_enabled():
    """
    Check if OpenTelemetry is enabled via environment variable.

    Returns:
        bool: True if OTEL_ENABLED=true, False otherwise
    """
    return os.getenv("OTEL_ENABLED", "false").lower() == "true"


def init_otel(app=None, service_name="inboxiq"):
    """
    Initialize OpenTelemetry SDK and auto-instrumentation.

    This function:
    1. Creates a TracerProvider with service metadata
    2. Configures OTLP exporter to send traces to OTel Collector
    3. Enables auto-instrumentation for Flask, SQLAlchemy, Celery, Redis, Requests
    4. Returns a Tracer instance for custom spans

    Safe to call multiple times - will only initialize once.

    Args:
        app: Flask application instance (optional, for Flask instrumentation)
        service_name: Service name for traces (default: "inboxiq")

    Returns:
        Tracer: OpenTelemetry tracer instance for creating custom spans

    Environment Variables:
        OTEL_ENABLED: Master switch (default: false)
        OTEL_SERVICE_NAME: Override service name (default: from service_name arg)
        OTEL_EXPORTER_OTLP_ENDPOINT: OTel Collector endpoint (default: http://localhost:4317)
        OTEL_EXPORTER_OTLP_INSECURE: Use insecure connection (default: true for dev)
        OTEL_TRACES_SAMPLER: Sampling strategy (default: always_on)
        OTEL_TRACES_SAMPLER_ARG: Sampling rate (default: 1.0 = 100%)
        APP_VERSION: Application version for resource attributes
        ENVIRONMENT: Deployment environment (development, staging, production)

    Example:
        # In Flask app initialization
        from src.observability import init_otel

        app = Flask(__name__)
        tracer = init_otel(app, service_name="inboxiq-flask")

        # Create custom spans
        with tracer.start_as_current_span("my_operation") as span:
            span.set_attribute("user.id", user_id)
            do_work()
    """
    if not is_otel_enabled():
        logger.info("OpenTelemetry is disabled (OTEL_ENABLED=false)")
        return trace.get_tracer(__name__)  # Return no-op tracer

    # Override service name from env if provided
    service_name = os.getenv("OTEL_SERVICE_NAME", service_name)

    # Create resource with service metadata
    resource = Resource.create({
        "service.name": service_name,
        "service.version": os.getenv("APP_VERSION", "unknown"),
        "deployment.environment": os.getenv("ENVIRONMENT", "development"),
    })

    # Create tracer provider
    provider = TracerProvider(resource=resource)

    # Configure OTLP exporter (sends traces to OTel Collector)
    otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
    insecure = os.getenv("OTEL_EXPORTER_OTLP_INSECURE", "true").lower() == "true"

    try:
        exporter = OTLPSpanExporter(
            endpoint=otlp_endpoint,
            insecure=insecure
        )

        # Add batch processor (async export for performance)
        processor = BatchSpanProcessor(exporter)
        provider.add_span_processor(processor)

        logger.info(f"OTLP exporter configured: {otlp_endpoint} (insecure={insecure})")
    except Exception as e:
        logger.error(f"Failed to configure OTLP exporter: {e}")
        # Continue without exporter - spans will still be created but not exported

    # Set as global tracer provider
    trace.set_tracer_provider(provider)

    # Auto-instrument libraries
    try:
        # Flask instrumentation (HTTP requests, routes)
        if app:
            FlaskInstrumentor().instrument_app(app)
            logger.info("Flask auto-instrumentation enabled")

        # SQLAlchemy instrumentation (database queries)
        SQLAlchemyInstrumentor().instrument()
        logger.info("SQLAlchemy auto-instrumentation enabled")

        # Celery instrumentation (background tasks)
        CeleryInstrumentor().instrument()
        logger.info("Celery auto-instrumentation enabled")

        # Redis instrumentation (cache operations)
        RedisInstrumentor().instrument()
        logger.info("Redis auto-instrumentation enabled")

        # Requests instrumentation (HTTP client calls)
        RequestsInstrumentor().instrument()
        logger.info("Requests auto-instrumentation enabled")

    except Exception as e:
        logger.warning(f"Failed to enable some auto-instrumentation: {e}")
        # Continue - partial instrumentation is better than none

    logger.info(f"OpenTelemetry initialized: {service_name} → {otlp_endpoint}")

    return trace.get_tracer(__name__)


def get_tracer(name=__name__):
    """
    Get a tracer instance for creating custom spans.

    Args:
        name: Tracer name (typically __name__ of calling module)

    Returns:
        Tracer: OpenTelemetry tracer instance

    Example:
        from src.observability import get_tracer

        tracer = get_tracer(__name__)

        with tracer.start_as_current_span("process_ticket") as span:
            span.set_attribute("ticket.id", ticket_id)
            process_ticket(ticket_id)
    """
    return trace.get_tracer(name)


def get_current_trace_id():
    """
    Get the current trace ID as a hex string.

    Useful for linking user-facing logs/records to detailed traces.

    Returns:
        str: Trace ID in hex format (32 chars), or empty string if no active span

    Example:
        trace_id = get_current_trace_id()
        execution_record.trace_id = trace_id
        # User can search Phoenix UI for this trace_id
    """
    span = trace.get_current_span()
    if span and span.get_span_context().is_valid:
        trace_id = span.get_span_context().trace_id
        return format(trace_id, '032x')  # Convert to 32-char hex string
    return ""


def get_current_span_id():
    """
    Get the current span ID as a hex string.

    Returns:
        str: Span ID in hex format (16 chars), or empty string if no active span
    """
    span = trace.get_current_span()
    if span and span.get_span_context().is_valid:
        span_id = span.get_span_context().span_id
        return format(span_id, '016x')  # Convert to 16-char hex string
    return ""
