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
            desc=label_desc(label_config, "email_types", "Type of email (e.g. support_request, billing, sales_inquiry, etc.)")
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
        entities_json = dspy.OutputField(
            desc=f"JSON with: intent, sentiment, urgency, identifiers, missing_info, "
                 f"email_type ({label_desc(label_config, 'email_types', 'type of email')}), "
                 f"is_automated (true/false), requires_human_response (true/false). "
                 f"Set email_type appropriately and is_automated=true for non-actionable emails."
        )

    class RouteCaseSig(dspy.Signature):
        case_json = dspy.InputField()
        entities_json = dspy.InputField()
        route_json = dspy.OutputField(desc="JSON with queue, priority, sla_minutes, tags, rationale.")

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
        """Generate customer-ready draft reply based on triage context and knowledge base."""
        case_json = dspy.InputField(desc="Customer case details including email content and metadata")
        entities_json = dspy.InputField(desc="Extracted entities: intent, sentiment, urgency")
        workflow_json = dspy.InputField(desc="Selected workflow and required tools")
        escalation_json = dspy.InputField(desc="Escalation decision and reasoning")
        kb_context = dspy.InputField(desc="Relevant knowledge base articles for context (JSON array)")
        reply_text = dspy.OutputField(desc="Draft reply for human review. Be helpful, concise, and professional. Reference KB articles when applicable.")

    class DecisionProgram(dspy.Module):
        def __init__(self) -> None:
            super().__init__()
            self.extract = dspy.ChainOfThought(ExtractEntitiesSig)
            self.route = dspy.Predict(RouteCaseSig)
            self.select = dspy.Predict(SelectWorkflowSig)
            self.escalate = dspy.Predict(EscalationDecisionSig)
            self.draft = dspy.ChainOfThought(DraftReplySig)

        def forward(self, case_json: str, draft_enabled: bool = False, kb_context: str = "[]") -> Any:
            entities_json = self.extract(case_json=case_json).entities_json
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
                reply_text = self.draft(
                    case_json=case_json,
                    entities_json=entities_json,
                    workflow_json=workflow_json,
                    escalation_json=escalation_json,
                    kb_context=kb_context,
                ).reply_text
            return dspy.Prediction(
                entities_json=entities_json,
                route_json=route_json,
                workflow_json=workflow_json,
                escalation_json=escalation_json,
                reply_text=reply_text,
            )

    return DecisionProgram()
