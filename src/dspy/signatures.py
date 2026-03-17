"""
DSPy signature and module builders.

Defines DSPy signatures for triage and decision workflows.
"""
from __future__ import annotations

from typing import Any, Dict
from src.dspy.formatting import label_desc


def build_triage_module(dspy: Any, label_config: Dict[str, Any]) -> Any:
    """
    Build simple triage module with basic classification.

    Used as fallback when DecisionProgram fails or for simpler use cases.

    Args:
        dspy: DSPy module reference
        label_config: Label configuration with categories, priorities, etc.

    Returns:
        TriageModule instance
    """
    class TriageSignature(dspy.Signature):
        """Classify inbound support content for triage. Identify spam, marketing, and auto-replies for auto-handling."""

        content = dspy.InputField(desc="Inbound payload with subject, body, sender, source, and context.")
        category = dspy.OutputField(desc=label_desc(label_config, "categories", "Provide a concise category label."))
        priority = dspy.OutputField(desc=label_desc(label_config, "priorities", "Provide a priority label."))
        sentiment = dspy.OutputField(desc=label_desc(label_config, "sentiments", "Provide a sentiment label."))
        intent = dspy.OutputField(desc=label_desc(label_config, "intents", "Provide an intent label."))

        # NEW: Email type classification for auto-handling
        email_type = dspy.OutputField(
            desc=label_desc(label_config, "email_types", "Email type for routing and handling")
        )
        is_automated = dspy.OutputField(
            desc="true if this is an automated email (auto-reply, system notification, no-reply sender, newsletter), false if from a human requiring response"
        )
        action_required = dspy.OutputField(
            desc="false for spam/marketing/newsletter/auto_reply/transactional emails. true for support requests needing human response. optional for low-priority items."
        )
        ai_reason = dspy.OutputField(desc="Short reason for the decision.")
        team = dspy.OutputField(desc=label_desc(label_config, "teams", "Suggested team name for assignment."))
        assigned_to = dspy.OutputField(desc="Suggested queue or owner identifier.")
        owner = dspy.OutputField(desc="Suggested owner/team lead name.")

    class TriageModule(dspy.Module):
        def __init__(self) -> None:
            super().__init__()
            self.predict = dspy.Predict(TriageSignature)

        def forward(self, content: str) -> Any:
            return self.predict(content=content)

    return TriageModule()


def build_decision_program(dspy: Any, label_config: Dict[str, Any]) -> Any:
    """
    Build complex decision program with multi-stage reasoning.

    Pipeline:
    1. ExtractEntities - Parse intent, sentiment, email type, urgency
    2. RouteCase - Determine queue, priority, SLA
    3. SelectWorkflow - Choose automation workflow
    4. EscalationDecision - Auto-resolve vs escalate vs clarify
    5. DraftReply - Generate customer-facing draft (optional)

    Args:
        dspy: DSPy module reference
        label_config: Label configuration (currently unused but kept for consistency)

    Returns:
        DecisionProgram instance
    """
    class ExtractEntitiesSig(dspy.Signature):
        """Extract entities and classify email type. Identify spam, marketing, newsletters, and auto-replies for auto-handling."""
        case_json = dspy.InputField(desc="JSON of normalized case payload.")
        sender_hint = dspy.InputField(
            desc="Optional prior classification for this sender's domain, e.g. "
                 "'Transactions (confidence: 0.72, sample_size: 8)'. "
                 "Use as a starting point — confirm or override based on the actual email content."
        )
        entities_json = dspy.OutputField(
            desc=f"JSON with: intent, sentiment, urgency, identifiers, missing_info, "
                 f"email_type ({label_desc(label_config, 'email_types', 'type of email')}), "
                 f"is_automated (true/false), requires_human_response (true/false), "
                 f"order_id (string or null — order/transaction ID if present in subject or body), "
                 f"invoice_number (string or null — invoice or receipt number if present), "
                 f"renewal_date (string or null — subscription renewal or expiry date if present, ISO format), "
                 f"unsubscribe_present (true/false — true if an unsubscribe link or opt-out instruction is present), "
                 f"is_automated_sender (true/false — true if sender is noreply/donotreply/automated system)."
        )

    class RouteCaseSig(dspy.Signature):
        """Route the email to the correct queue using extracted entities and commerce signals.
        If entities_json contains order_id or invoice_number, queue MUST be 'transactions'.
        If entities_json contains renewal_date, queue MUST be 'updates'.
        If entities_json has unsubscribe_present=true and is_automated_sender=true with no human question, queue MUST be 'promotions' or 'updates'.
        """
        case_json = dspy.InputField()
        entities_json = dspy.InputField(
            desc="Extracted entities including commerce signals: order_id, invoice_number, renewal_date, "
                 "unsubscribe_present, is_automated_sender. Use these as deterministic routing signals."
        )
        route_json = dspy.OutputField(
            desc=f"JSON with queue ({label_desc(label_config, 'categories', 'support/billing/transactions/updates/promotions/social/forums')}), "
                 f"priority ({label_desc(label_config, 'priorities', 'P1/P2/P3/P4')}), sla_minutes, tags, rationale."
        )

    class SelectWorkflowSig(dspy.Signature):
        case_json = dspy.InputField()
        entities_json = dspy.InputField()
        route_json = dspy.InputField()
        workflow_json = dspy.OutputField(desc="JSON with workflow_key, required_tools, next_questions.")

    class EscalationDecisionSig(dspy.Signature):
        """Decide whether to escalate, auto-resolve, or request clarification. Auto-resolve spam, marketing, newsletters, and auto-replies."""
        case_json = dspy.InputField()
        entities_json = dspy.InputField()
        route_json = dspy.InputField()
        workflow_json = dspy.InputField()
        escalation_json = dspy.OutputField(
            desc="JSON with decision (auto_resolve|escalate|ask_clarifying|escalate_on_reply), reason, required_role. "
                 "Use auto_resolve for spam, marketing, newsletters, auto-replies, transactional emails, and low-priority informational content."
        )

    class DraftReplySig(dspy.Signature):
        """Generate customer-ready draft reply based on triage context, thread history, and knowledge base."""
        case_json = dspy.InputField(desc="Customer case details including the latest email content and metadata")
        thread_history = dspy.InputField(
            desc="Prior messages in this email thread, oldest-first (JSON array). "
                 "Each entry has: from_email, body, received_at, is_outbound (true = sent by Oliver's team). "
                 "Use this to: avoid repeating questions already asked, reference what was previously said, "
                 "understand the full context of the conversation, and continue naturally from the last reply."
        )
        entities_json = dspy.InputField(desc="Extracted entities: intent, sentiment, urgency")
        workflow_json = dspy.InputField(desc="Selected workflow and required tools")
        escalation_json = dspy.InputField(desc="Escalation decision and reasoning")
        kb_context = dspy.InputField(desc="Relevant knowledge base articles for context (JSON array)")
        reply_text = dspy.OutputField(desc="Draft reply for human review. Be helpful, concise, and professional. Reference KB articles when applicable. Continue naturally from the thread history — do not repeat questions already asked.")

    class DecisionProgram(dspy.Module):
        def __init__(self) -> None:
            super().__init__()
            self.extract = dspy.ChainOfThought(ExtractEntitiesSig)
            self.route = dspy.Predict(RouteCaseSig)
            self.select = dspy.Predict(SelectWorkflowSig)
            self.escalate = dspy.Predict(EscalationDecisionSig)
            self.draft = dspy.ChainOfThought(DraftReplySig)

        def forward(self, case_json: str, draft_enabled: bool = False, kb_context: str = "[]", sender_hint: str = "", thread_history: str = "[]") -> Any:
            entities_json = self.extract(case_json=case_json, sender_hint=sender_hint).entities_json
            route_json = self.route(case_json=case_json, entities_json=entities_json).route_json
            workflow_json = self.select(
                case_json=case_json, entities_json=entities_json, route_json=route_json
            ).workflow_json
            escalation_json = self.escalate(
                case_json=case_json,
                entities_json=entities_json,
                route_json=route_json,
                workflow_json=workflow_json,
            ).escalation_json
            reply_text = None
            if draft_enabled:
                try:
                    reply_text = self.draft(
                        case_json=case_json,
                        thread_history=thread_history,
                        entities_json=entities_json,
                        workflow_json=workflow_json,
                        escalation_json=escalation_json,
                        kb_context=kb_context,
                    ).reply_text
                    import logging as _log
                    _log.getLogger(__name__).info(
                        "DraftReplySig succeeded: reply_text_len=%s",
                        len(reply_text) if reply_text else 0,
                    )
                except Exception as _draft_exc:
                    import logging as _log
                    _log.getLogger(__name__).warning("DraftReplySig failed (non-fatal): %s", _draft_exc, exc_info=True)
            return dspy.Prediction(
                entities_json=entities_json,
                route_json=route_json,
                workflow_json=workflow_json,
                escalation_json=escalation_json,
                reply_text=reply_text,
            )

    return DecisionProgram()


def build_nl_rule_parser(dspy: Any) -> Any:
    """
    Build a DSPy module that converts natural language into an AutomationRule JSON structure.

    Uses ChainOfThought so the model reasons through trigger → conditions → actions
    before committing to a structure, improving accuracy on ambiguous descriptions.
    """
    class NLRuleParserSignature(dspy.Signature):
        """
        Convert a natural language automation rule description into a structured JSON rule.

        The rule must have:
        - trigger: one of email.received, ticket.created, ticket.updated, lead.created, webhook.received
        - conditions: list of {field, operator, value} objects (may be empty)
        - condition_logic: AND or OR
        - actions: list of {type, config} objects using valid action types
        - name: short descriptive name

        Valid action types: send_webhook, conditional_webhook, tag_email, move_to_folder,
        create_note, send_email, upload_to_s3, generate_public_url, assign, update_field,
        tag, priority, status, provider_action, extract_invoice_data, extract_receipt_data,
        extract_expense_data.

        For provider_action the config must include an 'action' key:
        archive, mark_read, star, trash, forward, apply_label, move_to_folder.

        Return only valid JSON — no markdown, no explanation.
        """
        description = dspy.InputField(desc="Natural language automation rule written by the user.")
        account_context = dspy.InputField(desc="JSON with available teams, priorities, and custom fields for this account.")
        rule_json = dspy.OutputField(desc="Complete AutomationRule JSON with name, trigger, conditions, condition_logic, and actions.")

    class NLRuleParserModule(dspy.Module):
        def __init__(self) -> None:
            super().__init__()
            self.parse = dspy.ChainOfThought(NLRuleParserSignature)

        def forward(self, description: str, account_context: str) -> Any:
            return self.parse(description=description, account_context=account_context)

    return NLRuleParserModule()
