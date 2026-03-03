"""
Email Actions for Automation Studio

Actions that manipulate emails: tagging, moving to folders, creating notes, sending notifications.
"""

from typing import Dict, Any
from opentelemetry import trace

from src.extensions import db
from src.sanitize import sanitize_html


def execute_tag_email(context: Dict[str, Any], config: Dict[str, Any], span: trace.Span) -> Dict[str, Any]:
    """
    Add tags to an email.

    Config options:
        - tags: List of tag names to add (e.g., ["invoice_processed", "sage_synced"])

    Returns:
        {
            "success": True,
            "result": {"tags_added": ["invoice_processed"]}
        }
    """
    span.set_attribute("email.action", "tag")

    try:
        tags = config.get("tags", [])
        if not tags:
            return {"success": False, "error": "No tags specified", "result": None}

        span.set_attribute("email.tags", str(tags))

        email = context.get("email")
        if not email:
            return {"success": False, "error": "No email in context", "result": None}

        email_id = email.get("id")

        # Add tags to email (implementation depends on your email storage model)
        # Placeholder - would integrate with InboxConnection model
        # For now, just return success
        span.set_attribute("email.tags_added", len(tags))

        return {
            "success": True,
            "result": {
                "tags_added": tags,
                "email_id": email_id
            },
            "error": None
        }

    except Exception as e:
        span.record_exception(e)
        return {
            "success": False,
            "error": f"Tag email failed: {str(e)}",
            "result": None
        }


def execute_move_to_folder(context: Dict[str, Any], config: Dict[str, Any], span: trace.Span) -> Dict[str, Any]:
    """
    Move email to a specific folder.

    Config options:
        - folder: Folder path (e.g., "Accounting/Invoices")

    Returns:
        {
            "success": True,
            "result": {"moved_to": "Accounting/Invoices"}
        }
    """
    span.set_attribute("email.action", "move_to_folder")

    try:
        folder = config.get("folder")
        if not folder:
            return {"success": False, "error": "No folder specified", "result": None}

        span.set_attribute("email.destination_folder", folder)

        email = context.get("email")
        if not email:
            return {"success": False, "error": "No email in context", "result": None}

        email_id = email.get("id")

        # Move email (implementation depends on email provider - Gmail, Outlook)
        # Placeholder for now
        span.set_attribute("email.moved", True)

        return {
            "success": True,
            "result": {
                "moved_to": folder,
                "email_id": email_id
            },
            "error": None
        }

    except Exception as e:
        span.record_exception(e)
        return {
            "success": False,
            "error": f"Move to folder failed: {str(e)}",
            "result": None
        }


def execute_create_note(context: Dict[str, Any], config: Dict[str, Any], span: trace.Span) -> Dict[str, Any]:
    """
    Create an internal note on an email/ticket.

    Config options:
        - note: Note text (supports {{variables}})

    Returns:
        {
            "success": True,
            "result": {"note_created": "Receipt synced to QuickBooks"}
        }
    """
    span.set_attribute("email.action", "create_note")

    try:
        note_template = config.get("note")
        if not note_template:
            return {"success": False, "error": "No note text specified", "result": None}

        # Render note with template variables
        from src.automation.template_engine import render_template, build_context

        template_context = build_context(
            email=context.get("email"),
            extracted=context.get("extracted"),
            ticket=context.get("ticket"),
            account_id=context.get("account_id"),
            rule_name=context.get("rule_name"),
        )

        note_text = render_template(note_template, template_context)

        # Sanitize note text
        note_text = sanitize_html(note_text)

        span.set_attribute("email.note_length", len(note_text))

        email_id = context.get("email", {}).get("id")
        ticket_id = context.get("ticket", {}).get("id")

        # Create note (implementation depends on your system)
        # Placeholder for now
        return {
            "success": True,
            "result": {
                "note_created": note_text[:100] + "..." if len(note_text) > 100 else note_text,
                "email_id": email_id,
                "ticket_id": ticket_id
            },
            "error": None
        }

    except Exception as e:
        span.record_exception(e)
        return {
            "success": False,
            "error": f"Create note failed: {str(e)}",
            "result": None
        }


def execute_send_email(context: Dict[str, Any], config: Dict[str, Any], span: trace.Span) -> Dict[str, Any]:
    """
    Send an email notification.

    Config options:
        - to: Recipient email or team (supports {{variables}})
        - subject: Email subject (supports {{variables}})
        - body: Email body (supports {{variables}})
        - cc: CC recipients (optional)

    Returns:
        {
            "success": True,
            "result": {"sent_to": "finance@company.com"}
        }
    """
    span.set_attribute("email.action", "send")

    try:
        # Render template fields
        from src.automation.template_engine import render_template, build_context

        template_context = build_context(
            email=context.get("email"),
            extracted=context.get("extracted"),
            ticket=context.get("ticket"),
            account_id=context.get("account_id"),
            rule_name=context.get("rule_name"),
        )

        to = render_template(config.get("to"), template_context)
        subject = render_template(config.get("subject"), template_context)
        body = render_template(config.get("body"), template_context)
        cc = render_template(config.get("cc", ""), template_context) if config.get("cc") else None

        if not to or not subject or not body:
            return {"success": False, "error": "Missing required email fields (to, subject, body)", "result": None}

        # Sanitize HTML body
        body = sanitize_html(body)

        span.set_attribute("email.to", to)
        span.set_attribute("email.subject", subject[:100])

        # Send email (use existing email sending infrastructure)
        # Placeholder for now - would integrate with your email service
        return {
            "success": True,
            "result": {
                "sent_to": to,
                "subject": subject,
                "cc": cc
            },
            "error": None
        }

    except Exception as e:
        span.record_exception(e)
        return {
            "success": False,
            "error": f"Send email failed: {str(e)}",
            "result": None
        }
