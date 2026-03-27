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
    """Reply to a website visitor message on the chat widget. Concise, friendly, 2-3 sentences."""

    class ChatWidgetReplySignature(dspy.Signature):
        """
        You are a friendly assistant for a B2B SaaS product.
        Help website visitors understand the product, answer feature questions, and encourage them to start a free trial.
        Keep replies to 2-3 sentences. If asked about pricing, mention the free trial.
        If you cannot answer, suggest they start a free trial or contact the team.
        """
        account_name = dspy.InputField(desc="Name of the company whose chat widget this is.")
        visitor_name = dspy.InputField(desc="Name of the website visitor (may be empty).")
        conversation_history = dspy.InputField(desc="Prior messages in this chat as a JSON array, oldest first.")
        message = dspy.InputField(desc="The visitor's latest message.")
        reply = dspy.OutputField(desc="A helpful, concise reply of 2-3 sentences.")

    class ChatWidgetReplyModule(dspy.Module):
        def __init__(self) -> None:
            super().__init__()
            self.predict = dspy.Predict(ChatWidgetReplySignature)

        def forward(self, account_name: str, visitor_name: str, conversation_history: str, message: str) -> Any:
            return self.predict(
                account_name=account_name,
                visitor_name=visitor_name,
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
