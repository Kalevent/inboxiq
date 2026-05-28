"""
DSPy signature and module builders.

Defines DSPy signatures for triage and decision workflows.
"""
from __future__ import annotations

from typing import Any, Dict

import dspy

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
        """Draft a reply written BY the inbox owner TO the external sender.

        CRITICAL PERSPECTIVE RULE: You are ghostwriting on behalf of inbox_owner_email.
        - Address the external sender (from_email in case_json) — NOT the inbox owner.
        - Sign off as the inbox owner — NOT as the external sender.
        - Never copy the external sender's name, job title, phone number, or signature block into the reply.
        - In thread_history, is_outbound=true means the inbox owner sent that message.
        """
        inbox_owner_email = dspy.InputField(
            desc="Email address of the inbox owner. You are writing this reply ON BEHALF of this person. "
                 "Address the other party in the thread, not this person."
        )
        case_json = dspy.InputField(desc="Customer case details including the latest email content and metadata")
        thread_history = dspy.InputField(
            desc="Prior messages in this email thread, oldest-first (JSON array). "
                 "Each entry has: from_email, body, received_at, is_outbound (true = sent by the inbox owner). "
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

        def forward(self, case_json: str, draft_enabled: bool = False, kb_context: str = "[]", sender_hint: str = "", thread_history: str = "[]", inbox_owner_email: str = "") -> Any:
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
                        inbox_owner_email=inbox_owner_email,
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
        When action is 'forward', config MUST also include a 'to' key with the
        destination email address (e.g. {"action": "forward", "to": "accounting@example.com"}).

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


def build_chat_widget_reply(dspy: Any) -> Any:
    """Reply to a website visitor message on the InboxIQ chat widget."""

    class ChatWidgetReplySignature(dspy.Signature):
        """
        You are Aria, the AI assistant on the InboxIQ website (kalevent.com).
        InboxIQ is an AI-powered email triage and inbox management platform for customer support teams.

        PRODUCT KNOWLEDGE:
        - AI triage: automatically categorises, prioritises and routes incoming emails (support, billing, sales, spam, transactions)
        - Draft replies: Aria drafts contextual responses for agent review and one-click approval
        - Automation rules: no-code workflows triggered by email labels — auto-archive receipts, forward to billing, tag by vendor
        - Shared inbox: multi-agent inbox with real-time assignment, collision detection, and SLA tracking
        - Analytics: triage accuracy, response time breakdowns, category trends, and agent performance reports
        - Finance add-on: detects transaction emails (Stripe, PayPal, bank), exports Intuit-compatible CSV to QuickBooks/Xero
        - BYOL (Bring Your Own LLM): route AI inference to the customer's own OpenAI, Anthropic, or self-hosted Ollama endpoint
        - Integrations: Gmail, Outlook, Slack, Stripe, QuickBooks, Xero, HubSpot, Salesforce, WhatsApp

        PRICING (billed monthly, 7-day free trial on all plans — no credit card required):
        - Starter £19/seat/month: 1 inbox, AI triage, draft replies, basic analytics
        - Pro £49/seat/month: unlimited inboxes, automation rules, advanced analytics, BYOL
        - Enterprise: custom pricing — SSO, dedicated support, custom SLA, fine-tuned AI

        USEFUL LINKS — include in HTML anchor format when relevant:
        - Free trial: https://kalevent.com/signup
        - Pricing: https://kalevent.com/pricing
        - Features overview: https://kalevent.com/features
        - Knowledge base: https://kalevent.com/kb
        - Email triage: https://kalevent.com/features/email-triage
        - Draft replies: https://kalevent.com/features/email-draft-replies
        - Shared inbox: https://kalevent.com/features/shared-inbox
        - Finance use case: https://kalevent.com/use-case/finance
        - E-commerce use case: https://kalevent.com/use-case/ecommerce
        - Sales use case: https://kalevent.com/use-case/sales
        - HR use case: https://kalevent.com/use-case/hr

        REPLY RULES:
        - Keep replies to 2-4 sentences. Use plain prose, not bullet lists or markdown.
        - When a link adds value, include it as an HTML anchor: <a href="URL">link text</a>
        - Branch 'demo': visitor is evaluating the product — answer feature/pricing questions, point to relevant pages, encourage free trial.
        - Branch 'talk': visitor wants human support — first answer their question helpfully, then be warm and conversational.
        - Never say you cannot help — always give a useful answer or point to a relevant resource.
        - Do not mention you are collecting contact details — that is handled separately by the widget.
        When knowledge_base contains articles, use their specific content and URLs in preference to
        the hardcoded product knowledge above. Always link to the article URL when referencing it.

        INTENT OUTPUT RULES — output exactly one value for the intent field:
        - book_demo: visitor expresses interest in a product demo, live walkthrough, or scheduling a call/meeting
        - needs_human: complaint, urgent issue, complex integration question, pricing negotiation, or query beyond self-serve
        - none: general question answered by Aria or no action needed
        Never infer intent from greetings alone. Only set non-none when the message clearly signals it.
        """
        account_name = dspy.InputField(desc="Name of the company whose chat widget this is.")
        visitor_name = dspy.InputField(desc="Name of the website visitor (may be empty).")
        knowledge_base = dspy.InputField(desc="Relevant KB articles for this account (XML-delimited, may be empty). When present, use their content for specific answers and include their URLs as HTML links.")
        branch = dspy.InputField(desc="Widget branch: 'demo' (evaluating the product) or 'talk' (wants human support).")
        conversation_history = dspy.InputField(desc="Prior messages in this chat as a JSON array, oldest first.")
        message = dspy.InputField(desc="The visitor's latest message.")
        reply = dspy.OutputField(desc="A helpful reply of 2-4 sentences. Include a relevant HTML link (<a href='URL'>text</a>) when it adds value. No markdown.")
        intent = dspy.OutputField(desc="Output exactly one of: none | book_demo | needs_human. Use the INTENT OUTPUT RULES above.")

    class ChatWidgetReplyModule(dspy.Module):
        def __init__(self) -> None:
            super().__init__()
            self.predict = dspy.Predict(ChatWidgetReplySignature)

        def forward(self, account_name: str, visitor_name: str, knowledge_base: str, branch: str, conversation_history: str, message: str) -> Any:
            return self.predict(
                account_name=account_name,
                visitor_name=visitor_name,
                knowledge_base=knowledge_base,
                branch=branch,
                conversation_history=conversation_history,
                message=message,
            )

    return ChatWidgetReplyModule()


def build_document_extractor(dspy: Any) -> Any:
    """Extract structured data from invoice, receipt, or expense documents."""

    class DocumentExtractionSignature(dspy.Signature):
        """
        Extract structured data from a document. Return only valid JSON with the requested fields.
        Use null for any field not found. For amounts return numbers without currency symbols.
        For dates use ISO format (YYYY-MM-DD). For line_items return an array of objects.
        For expense category choose from: meals, travel, office_supplies, software, other.
        """
        document_type = dspy.InputField(desc="One of: invoice, receipt, expense.")
        fields_requested = dspy.InputField(desc="Comma-separated list of fields to extract.")
        provider_context = dspy.InputField(desc="Optional payment provider context (e.g. Stripe, PayPal).")
        document_content = dspy.InputField(desc="The document text content to extract from.")
        extracted_json = dspy.OutputField(desc="Valid JSON object with the requested fields. No markdown.")

    class DocumentExtractorModule(dspy.Module):
        def __init__(self) -> None:
            super().__init__()
            self.predict = dspy.Predict(DocumentExtractionSignature)

        def forward(self, document_type: str, fields_requested: str, provider_context: str, document_content: str) -> Any:
            return self.predict(
                document_type=document_type,
                fields_requested=fields_requested,
                provider_context=provider_context,
                document_content=document_content,
            )

    return DocumentExtractorModule()


def build_email_summarizer(dspy: Any) -> Any:
    """Summarise and classify a support email: intent, priority, sentiment, and extracted IDs."""

    class EmailSummarySignature(dspy.Signature):
        """
        Summarise and classify the support email. Extract intent, priority, sentiment, and any IDs.
        If the user requests cancellation mark sentiment as negative/concerned.
        If the message is praise or thanks mark sentiment as positive.
        Respond concisely as a JSON object.
        """
        email_content = dspy.InputField(desc="The raw email content to summarise.")
        context = dspy.InputField(desc="Optional additional context as a JSON object.")
        summary_json = dspy.OutputField(desc="JSON with: intent, priority, sentiment, extracted_ids, summary.")

    class EmailSummarizerModule(dspy.Module):
        def __init__(self) -> None:
            super().__init__()
            self.predict = dspy.Predict(EmailSummarySignature)

        def forward(self, email_content: str, context: str = "{}") -> Any:
            return self.predict(email_content=email_content, context=context)

    return EmailSummarizerModule()


def build_meta_description_generator(dspy: Any) -> Any:
    """Generate a concise SEO meta description for a blog post."""

    class MetaDescriptionSignature(dspy.Signature):
        """Write a compelling SEO meta description for a B2B SaaS blog post.
        Output exactly one sentence, 140-160 characters, no quotes."""

        title = dspy.InputField(desc="Blog post title")
        excerpt = dspy.InputField(desc="First 300 characters of the post body")
        primary_keyword = dspy.InputField(desc="Target SEO keyword (may be empty)")
        meta_description = dspy.OutputField(
            desc="SEO meta description: 140-160 chars, includes the keyword naturally, ends with a period"
        )

    class MetaDescriptionModule(dspy.Module):
        def __init__(self) -> None:
            super().__init__()
            self.predict = dspy.Predict(MetaDescriptionSignature)

        def forward(self, title: str, excerpt: str, primary_keyword: str = "") -> Any:
            return self.predict(title=title, excerpt=excerpt, primary_keyword=primary_keyword)

    return MetaDescriptionModule()


def build_blog_writer(dspy: Any) -> Any:
    """
    Multi-stage B2B SaaS blog writer pipeline.

    Stage 1 — Persona:   ICP + journey_stage + audience → tailored content angle
    Stage 2 — Outline:   angle + title + brief → structured outline
    Stage 3 — Draft:     outline → full Markdown draft
    Stage 4 — Editor:    draft + feedback → polished Markdown
    Stage 5 — SEO:       polished draft → SEO-optimised final article

    journey_stage: awareness | consideration | decision
    - awareness:     educate, no product pitch, problem-focused
    - consideration: compare solutions, light product mention, social proof
    - decision:      proof points, case studies, strong CTA to try/buy
    """

    class PersonaAngleSignature(dspy.Signature):
        """
        Given the target audience, their journey stage, and the ICP, define
        the content angle that will resonate most.

        - awareness:     lead with the problem, build credibility, no pitch
        - consideration: highlight differentiation, include social proof
        - decision:      lead with outcomes, use case studies, strong CTA

        Output a concise angle statement the writer should keep in mind throughout.
        """
        audience = dspy.InputField(desc="Target audience description.")
        journey_stage = dspy.InputField(desc="Where the reader is in their buying journey: awareness | consideration | decision.")
        icp = dspy.InputField(desc="Ideal customer profile context (may be empty).")
        content_angle = dspy.OutputField(desc="Tailored content angle: tone, emphasis, CTA strength, and what to avoid.")

    class OutlineSignature(dspy.Signature):
        """
        Create a detailed blog post outline for a B2B SaaS audience.
        Use the content angle to calibrate the hook, section depth, and CTA.
        Include: hook, 3-5 section headings with bullet points, and a CTA appropriate
        for the journey stage.
        """
        title = dspy.InputField(desc="Article title.")
        audience = dspy.InputField(desc="Target audience.")
        brief = dspy.InputField(desc="Content brief.")
        content_angle = dspy.InputField(desc="Tailored content angle from the persona stage.")
        outline = dspy.OutputField(desc="Structured outline with headings and bullet points.")

    class DraftSignature(dspy.Signature):
        """
        Write a full B2B SaaS blog post in Markdown from the outline.
        Honour the content angle throughout — adjust depth of product mention and CTA
        strength to match the reader's journey stage.
        Tone: confident, direct, helpful. Return Markdown only — no preamble.
        """
        title = dspy.InputField(desc="Article title.")
        audience = dspy.InputField(desc="Target audience.")
        outline = dspy.InputField(desc="The structured outline to expand into prose.")
        content_angle = dspy.InputField(desc="Tailored content angle to honour throughout.")
        article_markdown = dspy.OutputField(desc="Full blog article in Markdown.")

    class EditorSignature(dspy.Signature):
        """
        Edit and polish a B2B SaaS blog post draft.
        Apply feedback, tighten prose, ensure the CTA matches the journey stage,
        and remove anything off-angle. Return polished Markdown only — no commentary.
        """
        draft = dspy.InputField(desc="The blog post draft to edit.")
        content_angle = dspy.InputField(desc="Content angle — use to check CTA strength and tone.")
        feedback = dspy.InputField(desc="Revision notes or feedback (may be empty).")
        article_markdown = dspy.OutputField(desc="Polished final Markdown article.")

    class SEOSignature(dspy.Signature):
        """
        Optimise a polished blog post for search without changing the core content.
        - Add or improve the H1 if missing
        - Suggest and naturally embed 2-3 target keywords
        - Ensure meta-friendly intro (first 150 chars summarise the article)
        - Add internal linking placeholders: [INTERNAL_LINK: topic]
        Return the SEO-optimised Markdown only.
        """
        article_markdown = dspy.InputField(desc="The polished blog post to optimise.")
        target_keywords = dspy.InputField(desc="Optional comma-separated keywords to target (may be empty).")
        seo_markdown = dspy.OutputField(desc="SEO-optimised Markdown article.")

    class ExpandBlogPostSignature(dspy.Signature):
        """
        Expand an existing B2B SaaS blog post to reach a target word count.
        - Preserve all existing headings, structure, and tone exactly
        - Add depth to existing sections: examples, data points, practical steps
        - Add 1-2 new sections if needed to reach the target word count
        - Do not repeat content already present
        - Return the complete expanded article in Markdown — not just the additions
        """
        existing_markdown = dspy.InputField(desc="The existing blog post content in Markdown.")
        current_word_count = dspy.InputField(desc="Current word count of the article.")
        target_word_count = dspy.InputField(desc="Minimum word count to reach.")
        primary_keyword = dspy.InputField(desc="Primary SEO keyword to naturally reinforce (may be empty).")
        expanded_markdown = dspy.OutputField(desc="Complete expanded article in Markdown.")

    class BlogWriterModule(dspy.Module):
        def __init__(self) -> None:
            super().__init__()
            self.persona = dspy.ChainOfThought(PersonaAngleSignature)
            self.outline = dspy.ChainOfThought(OutlineSignature)
            self.draft = dspy.Predict(DraftSignature)
            self.editor = dspy.Predict(EditorSignature)
            self.seo = dspy.Predict(SEOSignature)

        def forward(
            self,
            title: str,
            audience: str,
            brief: str,
            journey_stage: str = "awareness",
            feedback: str = "",
            icp: str = "",
            target_keywords: str = "",
        ) -> Any:
            angle = self.persona(audience=audience, journey_stage=journey_stage, icp=icp)
            outline = self.outline(title=title, audience=audience, brief=brief, content_angle=angle.content_angle)
            draft = self.draft(title=title, audience=audience, outline=outline.outline, content_angle=angle.content_angle)
            edited = self.editor(draft=draft.article_markdown, content_angle=angle.content_angle, feedback=feedback)
            final = self.seo(article_markdown=edited.article_markdown, target_keywords=target_keywords)
            return final  # exposes .seo_markdown

    return BlogWriterModule()


def build_blog_expander(dspy: Any) -> Any:
    """Single-step DSPy module that expands an existing blog post to a target word count."""

    class ExpandBlogPostSignature(dspy.Signature):
        """
        Expand an existing B2B SaaS blog post to reach a target word count.
        - Preserve all existing headings, structure, and tone exactly
        - Add depth to existing sections: examples, data points, practical steps
        - Add 1-2 new sections if needed to reach the target word count
        - Do not repeat content already present
        - Return the complete expanded article in Markdown — not just the additions
        """
        existing_markdown = dspy.InputField(desc="The existing blog post content in Markdown.")
        current_word_count = dspy.InputField(desc="Current word count of the article.")
        target_word_count = dspy.InputField(desc="Minimum word count to reach.")
        primary_keyword = dspy.InputField(desc="Primary SEO keyword to naturally reinforce (may be empty).")
        expanded_markdown = dspy.OutputField(desc="Complete expanded article in Markdown.")

    class BlogExpanderModule(dspy.Module):
        def __init__(self) -> None:
            super().__init__()
            self.expand = dspy.ChainOfThought(ExpandBlogPostSignature)

        def forward(self, existing_markdown: str, current_word_count: str,
                    target_word_count: str, primary_keyword: str = "") -> Any:
            return self.expand(
                existing_markdown=existing_markdown,
                current_word_count=current_word_count,
                target_word_count=target_word_count,
                primary_keyword=primary_keyword,
            )

    return BlogExpanderModule()


def build_newsletter_writer(dspy: Any) -> Any:
    """
    Multi-stage B2B SaaS newsletter pipeline.

    Stage 1 — Strategy:  brief + audience + ICP → messaging angle and key points
    Stage 2 — Draft:     strategy → full newsletter content as JSON
    Stage 3 — Editor:    draft JSON + feedback → polished final JSON for template rendering
    """

    class NewsletterStrategySignature(dspy.Signature):
        """
        Plan the messaging strategy for a B2B SaaS email newsletter.
        Calibrate tone and CTA to the reader's journey stage:
        - awareness:     nurture with value, no hard sell, soft CTA (read more, download)
        - consideration: highlight benefits, include social proof, medium CTA (book a demo)
        - decision:      urgency, proof points, strong CTA (start trial, talk to sales)
        Identify the core value proposition, key points, and the single most important action.
        """
        audience = dspy.InputField(desc="Target audience for this newsletter.")
        journey_stage = dspy.InputField(desc="Reader's journey stage: awareness | consideration | decision.")
        brief = dspy.InputField(desc="Content brief describing the newsletter topic and goals.")
        icp = dspy.InputField(desc="Ideal customer profile context (may be empty).")
        strategy = dspy.OutputField(desc="Messaging strategy: angle, 3-5 key points, CTA type, and tone guidance.")

    class NewsletterDraftSignature(dspy.Signature):
        """
        Write a B2B SaaS email newsletter from the messaging strategy.
        Return a JSON object for template rendering with keys:
        subject, preview_text, headline, body_sections (array of {heading, content}),
        cta_text, cta_url (empty string if unknown).
        Return valid JSON only — no markdown wrapping.
        """
        audience = dspy.InputField(desc="Target audience.")
        strategy = dspy.InputField(desc="Messaging strategy from the planning stage.")
        newsletter_json = dspy.OutputField(desc="Valid JSON object with all newsletter fields.")

    class NewsletterEditorSignature(dspy.Signature):
        """
        Polish a newsletter JSON draft. Apply feedback, sharpen the subject line,
        tighten the CTA, and ensure tone is confident and helpful.
        Return valid JSON only — same structure as the input draft.
        """
        draft_json = dspy.InputField(desc="The newsletter JSON draft to polish.")
        feedback = dspy.InputField(desc="Revision notes (may be empty).")
        newsletter_json = dspy.OutputField(desc="Polished newsletter JSON. No markdown wrapping.")

    class NewsletterWriterModule(dspy.Module):
        def __init__(self) -> None:
            super().__init__()
            self.strategy = dspy.ChainOfThought(NewsletterStrategySignature)
            self.draft = dspy.Predict(NewsletterDraftSignature)
            self.editor = dspy.Predict(NewsletterEditorSignature)

        def forward(self, audience: str, brief: str, journey_stage: str = "awareness", feedback: str = "", icp: str = "") -> Any:
            strategy_result = self.strategy(audience=audience, journey_stage=journey_stage, brief=brief, icp=icp)
            draft_result = self.draft(audience=audience, strategy=strategy_result.strategy)
            edited_result = self.editor(draft_json=draft_result.newsletter_json, feedback=feedback)
            return edited_result

    return NewsletterWriterModule()


def build_whitepaper_writer(dspy: Any) -> Any:
    """
    Multi-stage B2B SaaS whitepaper pipeline.

    Stage 1 — Research plan:  brief + audience + ICP → structure and argument map
    Stage 2 — Draft:          structure → full whitepaper Markdown
    Stage 3 — Editor:         draft → polished, authoritative final Markdown
    """

    class WhitepaperPlanSignature(dspy.Signature):
        """
        Plan a B2B SaaS whitepaper structure calibrated to the reader's journey stage.
        Whitepapers are typically consideration or decision stage assets:
        - consideration: focus on the problem landscape, vendor-neutral findings, thought leadership
        - decision:      include product-specific proof, ROI data, customer outcomes, clear next step
        Map out: central argument, section headings with purpose, evidence points, and CTA.
        """
        audience = dspy.InputField(desc="Target audience for this whitepaper.")
        journey_stage = dspy.InputField(desc="Reader's journey stage: consideration | decision.")
        brief = dspy.InputField(desc="Content brief describing the whitepaper topic.")
        icp = dspy.InputField(desc="Ideal customer profile context (may be empty).")
        structure = dspy.OutputField(desc="Whitepaper structure: central argument, sections with purpose and evidence points.")

    class WhitepaperDraftSignature(dspy.Signature):
        """
        Write a detailed B2B SaaS whitepaper in Markdown from the planned structure.
        Include: executive summary, problem statement, solution overview, key findings,
        and conclusion with CTA. Tone: authoritative and data-driven.
        Return Markdown only — no preamble.
        """
        audience = dspy.InputField(desc="Target audience.")
        structure = dspy.InputField(desc="The planned structure to expand into full prose.")
        whitepaper_markdown = dspy.OutputField(desc="Full whitepaper in Markdown.")

    class WhitepaperEditorSignature(dspy.Signature):
        """
        Edit and polish a whitepaper draft. Strengthen the argument, ensure each section
        flows logically, verify the executive summary captures the key findings, and
        make the conclusion's CTA compelling. Return polished Markdown only.
        """
        draft = dspy.InputField(desc="The whitepaper draft to edit.")
        whitepaper_markdown = dspy.OutputField(desc="Polished final Markdown whitepaper.")

    class WhitepaperWriterModule(dspy.Module):
        def __init__(self) -> None:
            super().__init__()
            self.plan = dspy.ChainOfThought(WhitepaperPlanSignature)
            self.draft = dspy.Predict(WhitepaperDraftSignature)
            self.editor = dspy.Predict(WhitepaperEditorSignature)

        def forward(self, audience: str, brief: str, journey_stage: str = "consideration", icp: str = "") -> Any:
            plan_result = self.plan(audience=audience, journey_stage=journey_stage, brief=brief, icp=icp)
            draft_result = self.draft(audience=audience, structure=plan_result.structure)
            edited_result = self.editor(draft=draft_result.whitepaper_markdown)
            return edited_result

    return WhitepaperWriterModule()


def build_blog_quality_check(dspy: Any) -> Any:
    """DSPy module that scores a blog post and decides ready vs draft."""

    class BlogQualityCheckSignature(dspy.Signature):
        """
        Evaluate a blog post draft for publishing quality.
        Score 0–10 across relevance, depth, clarity, and audience fit.
        Decide 'ready' when score >= 7, 'draft' when score < 7.
        """
        title = dspy.InputField(desc="Blog post title.")
        content = dspy.InputField(desc="First 3,000 characters of the blog post in Markdown.")
        target_audience = dspy.InputField(desc="Intended reader — e.g. 'Head of Support, B2B SaaS'.")
        quality_score = dspy.OutputField(desc="Quality score as a digit string 0–10 (e.g. '8'). Callers must cast with int().")
        publish_decision = dspy.OutputField(desc="'ready' if score >= 7, else 'draft'.")
        reason = dspy.OutputField(desc="One sentence explaining the decision.")

    class BlogQualityCheckModule(dspy.Module):
        def __init__(self) -> None:
            super().__init__()
            self.check = dspy.ChainOfThought(BlogQualityCheckSignature)

        def forward(self, title: str, content: str, target_audience: str) -> Any:
            return self.check(title=title, content=content, target_audience=target_audience)

    return BlogQualityCheckModule()


# ── YouTube Cadence Signatures ─────────────────────────────────────────────

YOUTUBE_ILLUSTRATION_BRAND_STYLE = (
    "Editorial illustration, hand-drawn ink lines with watercolour wash, "
    "warm muted palette (navy, terracotta, cream), textured paper feel, "
    "loose gestural linework, human figures with natural proportions, "
    "professional magazine quality, no text, no UI chrome, no 3D render, "
    "no gradients, no gloss — think New Yorker editorial, not stock photo. "
)


def build_youtube_signatures(dspy: Any) -> Dict[str, Any]:
    """Return all four YouTube cadence DSPy signatures."""

    class YouTubeLongFormScript(dspy.Signature):
        """Generate a pain-point-first YouTube long form script (8-12 min) for a specific ICP persona.
        The script must open with the named ICP pain point. {product_name} must not appear in the
        first 5 seconds (HOOK). Structure: HOOK (pain) -> PROBLEM -> RESOLUTION -> PROOF -> CTA.
        The RESOLUTION beat must explicitly name {product_name} as the solution (do not say
        'chatbots', 'AI tools', or any generic category — name the product). The PROOF beat must
        cite a concrete outcome from {product_value_proposition}. The CTA must say
        'Start free at kalevent.com'."""

        blog_post_content: str = dspy.InputField(desc="Source blog post content to base the video on.")
        icp_persona: str = dspy.InputField(desc="ICP persona, e.g. 'Head of Support, B2B SaaS, 10-50 employees'.")
        pain_point: str = dspy.InputField(desc="Specific ICP pain point from ICPPainPoint table. Do not invent.")
        consequence: str = dspy.InputField(desc="What happens if this pain point is not resolved.")
        video_style: str = dspy.InputField(desc="'avatar' (Caroline presenter) or 'illustration' (editorial art).")
        product_name: str = dspy.InputField(desc="Product brand name to name in the RESOLUTION beat (e.g. 'InboxIQ').")
        product_value_proposition: str = dspy.InputField(desc="One-paragraph product value prop. Drives the RESOLUTION + PROOF beats so the script doesn't drift to source-blog framing.")

        script: str = dspy.OutputField(desc="Full spoken script. HOOK 0-30s opens with pain, no greeting. RESOLUTION explicitly names {product_name}. CTA: 'Start free at kalevent.com'.")
        hook_line: str = dspy.OutputField(desc="First spoken sentence. Must name the pain. No product name.")
        chapter_markers: str = dspy.OutputField(desc="JSON list of {time, title} chapter markers for YouTube.")
        cta_line: str = dspy.OutputField(desc="Final spoken sentence. One ask only: 'Start free at kalevent.com'.")

    class YouTubeShortScript(dspy.Signature):
        """Extract a 60-second Short from a long form script. Pattern interrupt -> agitation -> resolution -> CTA.
        First 3 seconds must name the pain with no greeting. The RESOLUTION beat (20-50s) must
        explicitly name {product_name} — do not collapse it into 'AI', 'a tool', or the source
        blog's terminology. The CTA must be exactly: "Link in description. Free to start."
        Do NOT speak the domain in the short — the URL lives in the YouTube description.

        Each short for a given long form must hit a different angle from {short_focus}. Two shorts
        with the same focus will publish as duplicates, so {short_focus} is the variation knob."""

        long_form_script: str = dspy.InputField(desc="Full long form script to extract the Short from.")
        pain_point: str = dspy.InputField(desc="ICP pain point this Short addresses.")
        parent_youtube_url: str = dspy.InputField(desc="YouTube URL of the parent long form video.")
        product_name: str = dspy.InputField(desc="Product brand name to name in the RESOLUTION beat (e.g. 'InboxIQ').")
        short_focus: str = dspy.InputField(desc="Which beat from the long form this Short should extract (e.g. 'the emotional cost of the pain' vs 'the visible outcome after {product_name}'). Distinct value per short ensures variety.")

        short_script: str = dspy.OutputField(desc="60-second script. Seconds 0-3: pain. 3-20: agitation. 20-50: {product_name} resolves it. 50-60: CTA must be exactly 'Link in description. Free to start.' — do NOT speak the domain.")
        pattern_interrupt_line: str = dspy.OutputField(desc="First sentence (0-3s). Names the pain. No greeting.")
        cta_line: str = dspy.OutputField(desc="Final line. Must be: 'Link in description. Free to start.'")

    class YouTubeSEOMetadata(dspy.Signature):
        """Generate YouTube SEO metadata for a video. Title format: [Pain outcome] — [How {product_name} does it] | {product_name}.
        The 'How' segment must describe a {product_name} capability (e.g. 'AI Triage', 'Auto-Reply')
        — never source-blog terminology like 'Use Chatbots' or 'With AI'. Description must state
        pain and {product_name}'s resolution in first 2 lines."""

        script: str = dspy.InputField(desc="Video script.")
        pain_point: str = dspy.InputField(desc="ICP pain point this video addresses.")
        blog_post_primary_keyword: str = dspy.InputField(desc="Primary SEO keyword from the source BlogPost.")
        video_type: str = dspy.InputField(desc="'long_form' or 'short'.")
        product_name: str = dspy.InputField(desc="Product brand name (e.g. 'InboxIQ'). Anchors the title's 'How' segment + suffix.")
        product_value_proposition: str = dspy.InputField(desc="One-paragraph product value prop — drives the description's 'resolution' line.")

        title: str = dspy.OutputField(desc="YouTube title <=60 chars. Format: [Pain outcome] — [How {product_name} does it] | {product_name}. The 'How' must reflect a {product_name} capability, not source-blog terminology.")
        description: str = dspy.OutputField(desc="YouTube description. Line 1: pain. Line 2: how {product_name} resolves it. Line 3: UTM link placeholder {{UTM_LINK}}.")
        tags: str = dspy.OutputField(desc="JSON list of 10 tags: 3 broad (inbox management, customer support, B2B SaaS) + 7 specific.")
        thumbnail_prompt: str = dspy.OutputField(desc="DALL-E prompt for thumbnail. Must show before/after state or visible problem. No logo only.")

    # brand_style_prefix is a module constant, not an input — prevents off-brand illustrations
    class YouTubeIllustrationPrompts(dspy.Signature):
        """Generate 6-10 DALL-E illustration prompts for an illustration-style video.
        Each prompt must be prefixed with the brand style and show a real human situation with emotional body language.
        No photorealistic renders, no stock-art figures, no UI elements, no text inside images."""

        script: str = dspy.InputField(desc="Video script to generate scene illustrations for.")
        pain_point: str = dspy.InputField(desc="ICP pain point — scenes should visually express this pain and its resolution.")
        chapter_markers: str = dspy.InputField(desc="JSON chapter markers — one illustration per chapter beat.")

        scene_prompts: str = dspy.OutputField(
            desc=f"JSON list of 6-10 DALL-E prompts. Each prompt MUST start with: '{YOUTUBE_ILLUSTRATION_BRAND_STYLE}'. "
            "Each scene shows a real human situation (person at desk overwhelmed, team in meeting, phone left unattended). "
            "Emotional states via body language only — no text labels. No screenshots, no device mockups, no floating UI."
        )

    return {
        "YouTubeLongFormScript": YouTubeLongFormScript,
        "YouTubeShortScript": YouTubeShortScript,
        "YouTubeSEOMetadata": YouTubeSEOMetadata,
        "YouTubeIllustrationPrompts": YouTubeIllustrationPrompts,
    }


def build_outreach_reply_drafter(dspy: Any) -> Any:
    """
    Returns a ChainOfThought module that drafts a warm, context-aware reply
    to a lead who has responded to a cold outreach email.
    """

    class OutreachReplyDraftSig(dspy.Signature):
        """
        Draft a short, warm reply to a prospect who responded to a cold outreach email.
        The tone should be friendly and conversational — not a support ticket response.
        Acknowledge their reply, continue the conversation naturally, and suggest a next step
        (e.g. quick call, demo, answering their question). Keep it under 120 words.
        Do NOT use placeholder text like [Your Name] — end with 'Kofi'.
        """
        lead_name: str = dspy.InputField(desc="Name of the prospect who replied")
        campaign_name: str = dspy.InputField(desc="Name of the outreach campaign")
        original_subject: str = dspy.InputField(desc="Subject line of the original outreach email sent to this lead")
        reply_preview: str = dspy.InputField(desc="The prospect's reply content (may be truncated)")
        reply_text: str = dspy.OutputField(desc="Draft reply — warm, concise, under 120 words, ends with 'Kofi'")

    return dspy.ChainOfThought(OutreachReplyDraftSig)


# Module-level references for direct import
class YouTubeLongFormScript:
    """Placeholder — use build_youtube_signatures(dspy) for the real DSPy signature."""
    pass


class YouTubeShortScript:
    """Placeholder — use build_youtube_signatures(dspy) for the real DSPy signature."""
    pass


class YouTubeSEOMetadata:
    """Placeholder — use build_youtube_signatures(dspy) for the real DSPy signature."""
    pass


class YouTubeIllustrationPrompts:
    """Placeholder — use build_youtube_signatures(dspy) for the real DSPy signature."""
    pass


def build_onboarding_signatures(dspy: Any) -> Dict[str, Any]:
    """Return the OnboardingVideoScript DSPy signature."""

    class OnboardingVideoScript(dspy.Signature):
        """Generate a personalised onboarding video script for a new InboxIQ customer.
        Three beats: personalised welcome (10s), what InboxIQ is now doing with their
        connected inbox (40s), what to expect in day 1 (30s). Warm, direct, under 90 seconds."""

        recipient_name: str = dspy.InputField(desc="First name or full name of the new customer.")
        recipient_company: str = dspy.InputField(desc="Company name. Use 'your company' if blank.")
        referral_source: str = dspy.InputField(
            desc="How they heard about InboxIQ (e.g. 'LinkedIn', 'Google search'). Use 'us' if blank."
        )

        script: str = dspy.OutputField(
            desc="Full spoken script. Opens with '[Name], welcome to InboxIQ.' Three beats: welcome (10s), "
            "what is happening now (40s), what to expect (30s). Under 90 seconds. No filler phrases."
        )
        hook_line: str = dspy.OutputField(
            desc="First spoken sentence. Must address recipient by name and welcome them."
        )
        cta_line: str = dspy.OutputField(
            desc="Final spoken sentence. One ask: go to the dashboard and check your first triaged emails."
        )

    return {"OnboardingVideoScript": OnboardingVideoScript}


class OnboardingVideoScript:
    """Placeholder — use build_onboarding_signatures(dspy) for the real DSPy signature."""
    pass


def build_outreach_signatures(dspy: Any) -> Dict[str, Any]:
    """Return the OutreachVideoScript DSPy signature."""

    class OutreachVideoScript(dspy.Signature):
        """Generate a personalised outreach video script for a high-fit warm non-responder.
        Three beats: hook using fresh intent signal (10s), pain + solution connecting the
        signal to inbox overload (40s), single CTA ask (10s). Direct, specific, under 60 seconds."""

        recipient_name: str = dspy.InputField(desc="First name or full name of the lead.")
        recipient_company: str = dspy.InputField(desc="Lead's company name.")
        industry: str = dspy.InputField(desc="Lead's industry. Use 'B2B SaaS' if blank.")
        intent_signals: str = dspy.InputField(
            desc="Fresh buying intent signals for the company (e.g. 'hiring VP of Operations'). "
            "Use 'no recent signals found' if unavailable."
        )
        pain_point: str = dspy.InputField(
            desc="Specific pain point derived from the lead's industry and ICP fit."
        )

        script: str = dspy.OutputField(
            desc="Full spoken script. Beat 1 (10s): hook opening with the intent signal. "
            "Beat 2 (40s): connect signal to inbox overload problem InboxIQ solves. "
            "Beat 3 (10s): one ask — reply to this email or book a 15-min call. Under 60 seconds."
        )
        hook_line: str = dspy.OutputField(
            desc="First spoken sentence. Must reference the intent signal. No greeting."
        )
        cta_line: str = dspy.OutputField(
            desc="Final spoken sentence. One ask only: reply to email or book a call."
        )
        subject_line: str = dspy.OutputField(
            desc="Email subject line for the video delivery email. Personalised, <=60 chars."
        )

    return {"OutreachVideoScript": OutreachVideoScript}


class OutreachVideoScript:
    """Placeholder — use build_outreach_signatures(dspy) for the real DSPy signature."""
    pass


def build_linkedin_message_draft(dspy: Any) -> Any:
    """DSPy module that drafts three LinkedIn outreach messages for a single prospect.

    first_name is always resolved in Python before calling this — the LLM must never
    derive or change the name, only use it verbatim in the greeting.
    """

    class LinkedInMessageDraftSignature(dspy.Signature):
        """
        Draft three personalised LinkedIn outreach messages for a cold prospect.
        Rules:
        - msg_1 is the connection request note. Must start with 'Hi {first_name},'.
          Must be under 200 characters including the greeting. No pitch — one sentence of shared context.
        - msg_2 is sent after the connection is accepted. Adds genuine value: share the blog_post_url
          if provided, or a relevant insight. No direct pitch.
        - msg_3 is a soft ask for a 15-minute call. One sentence. No pressure.
        - Use first_name exactly as provided. Never substitute, abbreviate, or change it.
        """
        first_name: str = dspy.InputField(desc="Prospect's first name. Use this exact string in every greeting.")
        company_name: str = dspy.InputField(desc="Prospect's company name.")
        job_title: str = dspy.InputField(desc="Prospect's job title.")
        industry: str = dspy.InputField(desc="Prospect's industry.")
        product_name: str = dspy.InputField(desc="Our product name and one-line value proposition.")
        blog_post_url: str = dspy.InputField(desc="URL of a relevant blog post to share in msg_2. Empty string if none found.")
        msg_1: str = dspy.OutputField(desc="Connection request note. Start with 'Hi {first_name},'. Under 200 chars total.")
        msg_2: str = dspy.OutputField(desc="Value-add follow-up after connecting. Reference blog_post_url if provided.")
        msg_3: str = dspy.OutputField(desc="Soft ask for a 15-minute call. One sentence.")

    class LinkedInMessageDraftModule(dspy.Module):
        def __init__(self) -> None:
            super().__init__()
            self.draft = dspy.ChainOfThought(LinkedInMessageDraftSignature)

        def forward(self, **kwargs: Any) -> Any:
            return self.draft(**kwargs)

    return LinkedInMessageDraftModule()


def build_youtube_video_social_caption(dspy: Any) -> Dict[str, Any]:
    """Return the YouTubeVideoSocialCaption DSPy signature."""

    class YouTubeVideoSocialCaption(dspy.Signature):
        """Generate a social media caption promoting a YouTube video.

        Length limits per platform:
          linkedin: <= 3000 chars; professional tone; encourage click-through.
          twitter:  <= 280 chars; punchy; one hashtag max.
          facebook: <= 5000 chars; conversational; emoji ok.
        Always include the youtube_url at the end. Never use 'InboxIQ' in the first sentence.
        """

        title = dspy.InputField(desc="YouTube video title")
        video_type = dspy.InputField(desc="'long_form' or 'short'")
        pain_point_text = dspy.InputField(desc="The viewer pain the video addresses")
        youtube_url = dspy.InputField(desc="YouTube watch URL of the video")
        platform = dspy.InputField(desc="'linkedin' | 'twitter' | 'facebook'")
        caption_text = dspy.OutputField(desc="Caption body, length-appropriate for platform")
        hashtags = dspy.OutputField(desc="2-4 space-separated hashtags, no leading text")

    return {"YouTubeVideoSocialCaption": YouTubeVideoSocialCaption}


class YouTubeVideoSocialCaption:
    """Placeholder — use build_youtube_video_social_caption(dspy) for the real DSPy signature."""
    pass


class ReelStoryboard(dspy.Signature):
    """
    Write a 5-scene storyboard for a voice-free product Reel.

    Two scene types:
    - "asset": AI-generated scene image + punchy copy. For emotional/narrative moments.
    - "clip": trimmed segment from a real product demo video. For proof moments.

    Story arc (exactly 5 scenes):
    1. HOOK    (asset) — ≤5 words naming the exact pain. Viewer thinks "that's me."
    2. AGITATE (asset) — the real human cost. Specific and felt. No product mention.
    3. PROOF   (clip)  — the product doing the thing. Show don't tell.
    4. PROOF   (clip)  — another product moment. The outcome becoming clear.
    5. CTA     (asset) — exactly this text: "Try free at kalevent.com"

    Copy rules (text_overlay for asset scenes):
    - 3–6 words. Sentence case. Question marks ok. No other punctuation.
    - Human, not marketer. Write like a friend describing the pain.
    - Bad: "Streamline your scheduling workflow"
    - Good: "5 emails. Still no meeting."

    Image concept rules (image_concept for asset scenes):
    - Describe what the VIEWER SHOULD FEEL, not what should be on screen.
    - Scene 1 (HOOK): show the frustration — a person overwhelmed by email chains
    - Scene 2 (AGITATE): show the cost — a missed opportunity, a wasted afternoon
    - Scene 5 (CTA): show the relief — a clean inbox, a calm moment, a done feeling
    - Style: editorial photography aesthetic, natural light, real human, single focal point
    - No UI screenshots, no device mockups, no floating app windows

    Clip rules:
    - start_s / end_s: pick moments where the key action is clearly visible (5–10s each)
    - text_overlay: what the viewer is seeing, ≤6 words, no hype
    """
    pain_point: str = dspy.InputField(desc="ICP pain point being solved")
    platform: str = dspy.InputField(desc="instagram | tiktok | linkedin | facebook")
    target_duration_s: int = dspy.InputField(desc="Target total duration in seconds (15–90)")
    available_assets: str = dspy.InputField(
        desc="Comma-separated list of fallback brand image filenames (without extension)"
    )
    available_demo_videos: str = dspy.InputField(
        desc=(
            "JSON list of {filename, description, segments} where segments is a list of "
            "{start_s, end_s, label}. You MUST only pick start_s/end_s values from within "
            "these declared segments — do not invent timestamps outside them."
        )
    )
    scenes: list = dspy.OutputField(
        desc=(
            "JSON list of exactly 5 scene dicts. "
            "Asset scene: {type:'asset', image_concept:str, text_overlay:str, duration_s:int}. "
            "image_concept is a vivid 1-2 sentence description for an AI image generator — "
            "describe the emotional scene, NOT a brand asset filename. "
            "Clip scene: {type:'clip', video_file:str, start_s:int, end_s:int, text_overlay:str}."
        )
    )


class LinkedInUrlSelection(dspy.Signature):
    """
    Pick the LinkedIn profile URL that belongs to the named lead at the named company.

    Strict rules:
      - Return skip_reason and empty selected_url if there is NO clear match.
      - "Clear match" = the candidate name matches lead_name AND the candidate's
        current employer matches lead_company.
      - NEVER pick a profile just because the person was mentioned in an article
        or news headline. Funding announcements, listicles, and blog posts are
        never valid sources for company affiliation.
      - The selected_job_title must come from the candidate's LinkedIn profile,
        not from a search result snippet.
    """
    lead_name = dspy.InputField(desc="The lead's full name")
    lead_company = dspy.InputField(desc="The lead's company")
    lead_industry = dspy.InputField(desc="Expected industry for ICP fit")
    candidate_profiles = dspy.InputField(
        desc="JSON list of {name, job_title, company, linkedin_url, snippet} from MCP search"
    )
    selected_url = dspy.OutputField(desc="The chosen linkedin.com/in/... URL, or empty if no match")
    selected_name = dspy.OutputField(desc="The name on the selected profile")
    selected_job_title = dspy.OutputField(desc="The role from the selected profile")
    skip_reason = dspy.OutputField(
        desc="If no clear match, explain why in one short phrase. Empty if a URL was selected."
    )
