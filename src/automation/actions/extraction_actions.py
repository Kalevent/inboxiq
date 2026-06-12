"""
Data Extraction Actions for Automation Studio

Uses AI/OCR to extract structured data from invoices, receipts, and expense documents.
Leverages OpenAI GPT-4 Vision for document understanding.
"""

import json as _json
import logging
import os
from typing import Dict, Any, List, Optional
from opentelemetry import trace

from src.dspy.config import _configure_dspy
from src.dspy.signatures import build_document_extractor

logger = logging.getLogger(__name__)


def execute_extract_invoice_data(context: Dict[str, Any], config: Dict[str, Any], span: trace.Span) -> Dict[str, Any]:
    """
    Extract invoice data from email attachments or body using AI.

    Config options:
        - fields: List of fields to extract (default: ["invoice_number", "vendor_name", "total_amount", "currency", "due_date", "line_items"])
        - source: "email_attachment" or "email_body" (default: "email_attachment")
        - confidence_threshold: Minimum confidence (0.0-1.0, default: 0.85)

    Returns:
        {
            "success": True,
            "result": {
                "invoice_number": "INV-001",
                "vendor_name": "Acme Corp",
                "total_amount": 500.00,
                "currency": "USD",
                "due_date": "2026-03-09",
                "line_items": [...]
            }
        }
    """
    span.set_attribute("extraction.type", "invoice")

    # Get configuration
    fields = config.get("fields", [
        "invoice_number", "vendor_name", "total_amount",
        "currency", "due_date", "line_items"
    ])
    source = config.get("source", "email_attachment")
    confidence_threshold = config.get("confidence_threshold", 0.85)

    span.set_attribute("extraction.fields", str(fields))
    span.set_attribute("extraction.source", source)

    try:
        # Get email data
        email = context.get("email")
        if not email:
            return {"success": False, "error": "No email data in context", "result": None}

        # Extract text content based on source
        if source == "email_attachment":
            # Get first PDF/image attachment
            attachments = email.get("attachments", [])
            if not attachments:
                return {"success": False, "error": "No attachments found", "result": None}

            attachment = attachments[0]  # Use first attachment
            content = attachment.get("content")  # Base64 encoded
            mime_type = attachment.get("mime_type")

            span.set_attribute("extraction.attachment.name", attachment.get("filename", "unknown"))
            span.set_attribute("extraction.attachment.type", mime_type)

        else:  # email_body
            content = email.get("body", "")
            mime_type = "text/plain"

        # Call OpenAI for extraction
        extracted_data = _extract_with_openai(content, mime_type, fields, "invoice")

        span.set_attribute("extraction.success", True)
        span.set_attribute("extraction.fields_found", len(extracted_data))

        # Store extracted data in context for next actions
        context["extracted"] = extracted_data

        return {
            "success": True,
            "result": extracted_data,
            "error": None
        }

    except Exception as e:
        span.record_exception(e)
        return {
            "success": False,
            "error": f"Invoice extraction failed: {str(e)}",
            "result": None
        }


def execute_extract_receipt_data(context: Dict[str, Any], config: Dict[str, Any], span: trace.Span) -> Dict[str, Any]:
    """
    Extract receipt data from payment processor emails (Stripe, Square, PayPal).

    Config options:
        - fields: List of fields to extract (default: ["receipt_number", "customer_email", "payment_amount", "payment_method", "payment_date", "transaction_id"])
        - provider: Payment processor (stripe, square, paypal, braintree, authorize_net)

    Returns:
        {
            "success": True,
            "result": {
                "receipt_number": "RCP-123",
                "customer_email": "customer@example.com",
                "payment_amount": 250.00,
                "payment_method": "Credit Card",
                "payment_date": "2026-02-09",
                "transaction_id": "ch_3AbCdEf123"
            }
        }
    """
    span.set_attribute("extraction.type", "receipt")

    fields = config.get("fields", [
        "receipt_number", "customer_email", "payment_amount",
        "payment_method", "payment_date", "transaction_id"
    ])
    provider = config.get("provider", "auto-detect")

    span.set_attribute("extraction.provider", provider)

    try:
        email = context.get("email")
        if not email:
            return {"success": False, "error": "No email data in context", "result": None}

        # Auto-detect provider from email sender
        from_email = email.get("from", "").lower()
        if "stripe" in from_email:
            provider = "stripe"
        elif "square" in from_email:
            provider = "square"
        elif "paypal" in from_email:
            provider = "paypal"
        elif "braintree" in from_email:
            provider = "braintree"
        elif "authorize.net" in from_email:
            provider = "authorize_net"

        span.set_attribute("extraction.provider_detected", provider)

        # Extract from email body (payment emails are usually HTML)
        email_body = email.get("body", "")

        # Call OpenAI for extraction
        extracted_data = _extract_with_openai(email_body, "text/html", fields, "receipt", provider)

        span.set_attribute("extraction.success", True)

        # Store in context
        context["extracted"] = extracted_data

        return {
            "success": True,
            "result": extracted_data,
            "error": None
        }

    except Exception as e:
        span.record_exception(e)
        return {
            "success": False,
            "error": f"Receipt extraction failed: {str(e)}",
            "result": None
        }


def execute_extract_expense_data(context: Dict[str, Any], config: Dict[str, Any], span: trace.Span) -> Dict[str, Any]:
    """
    Extract expense data from employee-submitted receipt images.

    Config options:
        - fields: List of fields (default: ["merchant", "category", "amount", "date"])
        - categories: List of valid expense categories (for validation)

    Returns:
        {
            "success": True,
            "result": {
                "merchant": "Starbucks",
                "category": "meals",
                "amount": 15.50,
                "date": "2026-02-09",
                "employee_email": "employee@company.com"
            }
        }
    """
    span.set_attribute("extraction.type", "expense")

    fields = config.get("fields", ["merchant", "category", "amount", "date"])
    valid_categories = config.get("categories", ["meals", "travel", "office_supplies", "software", "other"])

    try:
        email = context.get("email")
        if not email:
            return {"success": False, "error": "No email data in context", "result": None}

        # Get receipt image attachment
        attachments = email.get("attachments", [])
        if not attachments:
            return {"success": False, "error": "No receipt image found", "result": None}

        attachment = attachments[0]
        content = attachment.get("content")  # Base64 encoded image
        mime_type = attachment.get("mime_type")

        # Extract employee email from sender
        employee_email = email.get("from", "")

        # Call OpenAI for extraction
        extracted_data = _extract_with_openai(content, mime_type, fields, "expense")

        # Add employee email
        extracted_data["employee_email"] = employee_email

        # Validate category
        if "category" in extracted_data:
            if extracted_data["category"] not in valid_categories:
                extracted_data["category"] = "other"

        span.set_attribute("extraction.success", True)
        span.set_attribute("extraction.merchant", extracted_data.get("merchant", "unknown"))
        span.set_attribute("extraction.category", extracted_data.get("category", "unknown"))

        # Store in context
        context["extracted"] = extracted_data

        return {
            "success": True,
            "result": extracted_data,
            "error": None
        }

    except Exception as e:
        span.record_exception(e)
        return {
            "success": False,
            "error": f"Expense extraction failed: {str(e)}",
            "result": None
        }


def _extract_with_openai(
    content: str,
    mime_type: str,
    fields: List[str],
    document_type: str,
    provider: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Extract structured data from a document using DSPy (text) or vision API (image/PDF).

    For text content, uses the DSPy DocumentExtractor signature so the extraction
    prompt is provider-agnostic and optimisable.
    For image/PDF content, falls back to the OpenAI vision API (no DSPy equivalent yet).
    """
    is_visual = mime_type.startswith("image/") or "pdf" in mime_type

    if not is_visual:
        # --- DSPy path for text documents ---
        try:
            _, _, dspy = _configure_dspy()
            extractor = build_document_extractor(dspy)
            result = extractor(
                document_type=document_type,
                fields_requested=", ".join(fields),
                provider_context=provider or "",
                document_content=content[:5000],
            )
            raw = result.extracted_json.strip()
            # Strip markdown fences if present
            import re
            raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.IGNORECASE)
            raw = re.sub(r"\s*```$", "", raw)
            return _json.loads(raw)
        except Exception as exc:
            logger.warning("DSPy document extraction failed, returning empty: %s", exc)
            return {}

    # --- Vision path for images/PDFs — requires OpenAI vision API ---
    import openai
    client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    if not client.api_key:
        logger.warning("OPENAI_API_KEY not set; cannot extract from visual document")
        return {}

    prompt = (
        f"Extract the following {document_type} data from this document: {', '.join(fields)}. "
        "Return ONLY valid JSON with these exact field names. Use null if not found. "
        "For amounts use numbers without currency symbols. For dates use ISO format (YYYY-MM-DD)."
    )
    messages = [{
        "role": "user",
        "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{content}"}},
        ],
    }]
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=messages,
        response_format={"type": "json_object"},
        temperature=0.1,
    )
    return _json.loads(response.choices[0].message.content)
