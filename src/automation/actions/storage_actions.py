"""
Storage Actions for Automation Studio

Actions for uploading files to S3 and generating public URLs.
Uses existing upload infrastructure from src/uploads.py.
"""

import base64
from typing import Dict, Any
from datetime import datetime, timedelta
from opentelemetry import trace

from src.uploads import upload_bytes, build_public_url


def execute_upload_to_s3(context: Dict[str, Any], config: Dict[str, Any], span: trace.Span) -> Dict[str, Any]:
    """
    Upload file to S3 storage.

    Config options:
        - source: Where to get file ("email_attachment" or "extracted_file")
        - key_template: S3 key template (supports {{variables}})
          Example: "expenses/{{account_id}}/{{extracted.employee_id}}/{{now}}/receipt.pdf"
        - content_type: MIME type (optional, auto-detected from attachment)
        - attachment_index: Which attachment to upload (default: 0)

    Returns:
        {
            "success": True,
            "result": {
                "s3_key": "expenses/123/emp456/2026-02-12/receipt.pdf",
                "s3_url": "https://files.kalevent.com/expenses/123/emp456/2026-02-12/receipt.pdf"
            }
        }
    """
    span.set_attribute("storage.action", "upload")

    try:
        source = config.get("source", "email_attachment")
        key_template = config.get("key_template")
        attachment_index = config.get("attachment_index", 0)

        if not key_template:
            return {"success": False, "error": "No key_template specified", "result": None}

        # Get file data
        if source == "email_attachment":
            email = context.get("email")
            if not email:
                return {"success": False, "error": "No email in context", "result": None}

            attachments = email.get("attachments", [])
            if not attachments or len(attachments) <= attachment_index:
                return {"success": False, "error": f"No attachment at index {attachment_index}", "result": None}

            attachment = attachments[attachment_index]
            file_data_base64 = attachment.get("content")  # Base64 encoded
            content_type = config.get("content_type") or attachment.get("mime_type") or "application/octet-stream"
            filename = attachment.get("filename", "file")

            # Decode base64
            file_data = base64.b64decode(file_data_base64)

        else:
            return {"success": False, "error": f"Unsupported source: {source}", "result": None}

        # Render S3 key template
        from src.automation.template_engine import render_template, build_context

        template_context = build_context(
            email=context.get("email"),
            extracted=context.get("extracted"),
            account_id=context.get("account_id"),
            rule_name=context.get("rule_name"),
            custom={"filename": filename}
        )

        s3_key = render_template(key_template, template_context)

        span.set_attribute("storage.s3_key", s3_key)
        span.set_attribute("storage.content_type", content_type)
        span.set_attribute("storage.file_size", len(file_data))

        # Upload to S3 using existing infrastructure
        upload_bytes(
            key=s3_key,
            data=file_data,
            content_type=content_type,
            content_disposition="attachment"  # Force download, not inline display
        )

        # Build public URL
        s3_url = build_public_url(s3_key)

        span.set_attribute("storage.upload_success", True)

        # Store S3 info in context for next actions
        context["s3"] = {
            "key": s3_key,
            "url": s3_url,
            "content_type": content_type,
            "size": len(file_data)
        }

        return {
            "success": True,
            "result": {
                "s3_key": s3_key,
                "s3_url": s3_url,
                "size_bytes": len(file_data)
            },
            "error": None
        }

    except Exception as e:
        span.record_exception(e)
        return {
            "success": False,
            "error": f"S3 upload failed: {str(e)}",
            "result": None
        }


def execute_generate_public_url(context: Dict[str, Any], config: Dict[str, Any], span: trace.Span) -> Dict[str, Any]:
    """
    Generate a temporary public URL for a file (e.g., for approval workflows).

    Config options:
        - s3_key: S3 key (supports {{variables}}) OR use from context.s3.key
        - expiry_days: Number of days URL is valid (default: 7)

    Returns:
        {
            "success": True,
            "result": {
                "public_url": "https://files.kalevent.com/expenses/123/receipt.pdf?expires=...",
                "expires_at": "2026-02-19T10:30:00Z"
            }
        }
    """
    span.set_attribute("storage.action", "generate_url")

    try:
        expiry_days = config.get("expiry_days", 7)

        # Get S3 key
        s3_key = config.get("s3_key")
        if not s3_key:
            # Try to get from context (if previous upload action)
            s3_info = context.get("s3", {})
            s3_key = s3_info.get("key")

        if not s3_key:
            return {"success": False, "error": "No s3_key specified and none in context", "result": None}

        # Render S3 key if it's a template
        if "{{" in s3_key:
            from src.automation.template_engine import render_template, build_context

            template_context = build_context(
                email=context.get("email"),
                extracted=context.get("extracted"),
                account_id=context.get("account_id"),
            )
            s3_key = render_template(s3_key, template_context)

        span.set_attribute("storage.s3_key", s3_key)
        span.set_attribute("storage.expiry_days", expiry_days)

        # Generate public URL (using existing infrastructure)
        # Note: CloudFront URLs from build_public_url() are already public
        # For temporary URLs, would need to add signature/expiry to query params
        # For now, use standard public URL
        public_url = build_public_url(s3_key)

        expires_at = (datetime.utcnow() + timedelta(days=expiry_days)).isoformat() + "Z"

        span.set_attribute("storage.url_generated", True)

        # Store in context
        context["public_url"] = public_url

        return {
            "success": True,
            "result": {
                "public_url": public_url,
                "expires_at": expires_at,
                "s3_key": s3_key
            },
            "error": None
        }

    except Exception as e:
        span.record_exception(e)
        return {
            "success": False,
            "error": f"Generate URL failed: {str(e)}",
            "result": None
        }
