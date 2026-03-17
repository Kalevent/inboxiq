"""
Tests for the DSPy pipeline changes:
- NL rule parser (validate_workflow_structure, parse_natural_language_rule)
- DSPy signature builders (nl_rule_parser, blog, newsletter, whitepaper writers)
- execute_workflow_with_tool_calling_agent wrapper

DSPy module tests use dspy.utils.DummyLM — no real LLM calls.
ChainOfThought responses must include a "reasoning" key; Predict responses do not.
"""
from __future__ import annotations

import json
from unittest.mock import patch, MagicMock

import dspy
import pytest


# ---------------------------------------------------------------------------
# Shared fixture data
# ---------------------------------------------------------------------------

_VALID_WORKFLOW = {
    "name": "Archive promotions",
    "trigger": {"event": "email.received"},
    "conditions": [
        {"field": "label", "operator": "equals", "value": "promotion"}
    ],
    "condition_logic": "AND",
    "actions": [
        {"type": "provider_action", "config": {"action": "archive"}}
    ],
}

_ACCOUNT_CONTEXT = {
    "teams": ["support", "billing"],
    "priorities": ["P1", "P2"],
    "custom_fields": [],
}


def _dummy_configure_dspy():
    """Patch target: returns (model, model_id, dspy) so real LLM config is skipped."""
    return "test-model", "openai/test-model", dspy


# ---------------------------------------------------------------------------
# validate_workflow_structure — pure validation, no LLM
# ---------------------------------------------------------------------------

class TestValidateWorkflowStructure:
    def setup_method(self):
        from src.automation.nl_parser import validate_workflow_structure
        self.validate = validate_workflow_structure

    def test_valid_workflow_passes(self):
        result = self.validate(dict(_VALID_WORKFLOW), _ACCOUNT_CONTEXT)
        assert result["name"] == "Archive promotions"
        assert result["condition_logic"] == "AND"
        assert result["enabled"] is True

    def test_defaults_are_applied(self):
        wf = dict(_VALID_WORKFLOW)
        wf.pop("condition_logic", None)
        result = self.validate(wf, _ACCOUNT_CONTEXT)
        assert result["condition_logic"] == "AND"
        assert result["enabled"] is True
        assert result["stop_on_error"] is False

    def test_missing_required_fields_raises(self):
        with pytest.raises(ValueError, match="Missing required field"):
            self.validate({"name": "x"}, _ACCOUNT_CONTEXT)

    def test_invalid_trigger_event_raises(self):
        wf = {**_VALID_WORKFLOW, "trigger": {"event": "totally.fake"}}
        with pytest.raises(ValueError, match="Invalid trigger event"):
            self.validate(wf, _ACCOUNT_CONTEXT)

    def test_invalid_operator_raises(self):
        wf = {**_VALID_WORKFLOW, "conditions": [
            {"field": "label", "operator": "BADOP", "value": "x"}
        ]}
        with pytest.raises(ValueError, match="invalid operator"):
            self.validate(wf, _ACCOUNT_CONTEXT)

    def test_empty_actions_raises(self):
        wf = {**_VALID_WORKFLOW, "actions": []}
        with pytest.raises(ValueError, match="At least one action"):
            self.validate(wf, _ACCOUNT_CONTEXT)

    def test_provider_action_missing_action_key_raises(self):
        wf = {**_VALID_WORKFLOW, "actions": [
            {"type": "provider_action", "config": {}}
        ]}
        with pytest.raises(ValueError, match="config.action"):
            self.validate(wf, _ACCOUNT_CONTEXT)

    def test_provider_action_invalid_action_raises(self):
        wf = {**_VALID_WORKFLOW, "actions": [
            {"type": "provider_action", "config": {"action": "delete_everything"}}
        ]}
        with pytest.raises(ValueError, match="invalid action"):
            self.validate(wf, _ACCOUNT_CONTEXT)

    def test_webhook_must_use_https(self):
        wf = {**_VALID_WORKFLOW, "actions": [
            {"type": "send_webhook", "config": {"url": "http://example.com/hook"}}
        ]}
        with pytest.raises(ValueError, match="must use HTTPS"):
            self.validate(wf, _ACCOUNT_CONTEXT)

    def test_webhook_must_not_target_localhost(self):
        wf = {**_VALID_WORKFLOW, "actions": [
            {"type": "send_webhook", "config": {"url": "https://localhost/hook"}}
        ]}
        with pytest.raises(ValueError, match="internal/private"):
            self.validate(wf, _ACCOUNT_CONTEXT)

    def test_webhook_must_not_target_private_ip(self):
        wf = {**_VALID_WORKFLOW, "actions": [
            {"type": "send_webhook", "config": {"url": "https://10.0.0.1/hook"}}
        ]}
        with pytest.raises(ValueError, match="internal/private"):
            self.validate(wf, _ACCOUNT_CONTEXT)

    def test_send_email_invalid_recipient_raises(self):
        wf = {**_VALID_WORKFLOW, "actions": [
            {"type": "send_email", "config": {"to": "not-an-email", "subject": "Hi"}}
        ]}
        with pytest.raises(ValueError, match="valid email address"):
            self.validate(wf, _ACCOUNT_CONTEXT)

    def test_email_subject_with_newline_raises(self):
        wf = {**_VALID_WORKFLOW, "actions": [
            {"type": "send_email", "config": {"to": "a@b.com", "subject": "Hi\nBCC: evil"}}
        ]}
        with pytest.raises(ValueError, match="newlines"):
            self.validate(wf, _ACCOUNT_CONTEXT)

    def test_move_to_folder_path_traversal_raises(self):
        wf = {**_VALID_WORKFLOW, "actions": [
            {"type": "move_to_folder", "config": {"folder": "../../etc"}}
        ]}
        with pytest.raises(ValueError, match="path traversal"):
            self.validate(wf, _ACCOUNT_CONTEXT)

    def test_provider_forward_requires_valid_email(self):
        wf = {**_VALID_WORKFLOW, "actions": [
            {"type": "provider_action", "config": {"action": "forward", "to": "notvalid"}}
        ]}
        with pytest.raises(ValueError, match="valid email address"):
            self.validate(wf, _ACCOUNT_CONTEXT)

    def test_multiple_valid_actions(self):
        wf = {**_VALID_WORKFLOW, "actions": [
            {"type": "tag_email", "config": {"tag": "promo"}},
            {"type": "provider_action", "config": {"action": "mark_read"}},
        ]}
        result = self.validate(wf, _ACCOUNT_CONTEXT)
        assert len(result["actions"]) == 2

    def test_all_valid_trigger_events_accepted(self):
        for event in ("email.received", "ticket.created", "ticket.updated",
                      "lead.created", "webhook.received"):
            wf = {**_VALID_WORKFLOW, "trigger": {"event": event}}
            result = self.validate(wf, _ACCOUNT_CONTEXT)
            assert result["trigger"]["event"] == event


# ---------------------------------------------------------------------------
# parse_natural_language_rule — JSON decoding edge cases
# ---------------------------------------------------------------------------

class TestParseNLRuleJSONHandling:
    """
    Tests for the JSON parsing and double-decode resilience.

    _configure_dspy is mocked so no API key is required.
    The DSPy module's parse() call is also mocked to return controlled raw JSON.
    """

    def _run_with_raw_output(self, raw_rule_json: str) -> dict:
        """
        Run parse_natural_language_rule with a mocked DSPy module that
        returns raw_rule_json as the rule_json output field.
        """
        from src.automation.nl_parser import parse_natural_language_rule

        mock_result = MagicMock()
        mock_result.rule_json = raw_rule_json

        mock_parser = MagicMock()
        mock_parser.return_value = mock_result

        with patch("src.automation.nl_parser._configure_dspy", return_value=_dummy_configure_dspy()), \
             patch("src.automation.nl_parser.build_nl_rule_parser", return_value=mock_parser):
            return parse_natural_language_rule(
                "When the label is promotion, move to archive",
                account_id=1,
                account_context=_ACCOUNT_CONTEXT,
            )

    def test_clean_json_object_parses(self):
        result = self._run_with_raw_output(json.dumps(_VALID_WORKFLOW))
        assert result["name"] == "Archive promotions"

    def test_markdown_fenced_json_parses(self):
        fenced = "```json\n" + json.dumps(_VALID_WORKFLOW) + "\n```"
        result = self._run_with_raw_output(fenced)
        assert result["trigger"]["event"] == "email.received"

    def test_double_encoded_json_is_unwrapped(self):
        """
        Core fix: DSPy sometimes returns a JSON string instead of a JSON object.
        The parser must detect this and decode one more level.
        """
        double_encoded = json.dumps(json.dumps(_VALID_WORKFLOW))
        result = self._run_with_raw_output(double_encoded)
        assert result["name"] == "Archive promotions"

    def test_non_dict_raises_clear_error(self):
        """A JSON array at the top level is rejected with a clear message."""
        from src.automation.nl_parser import parse_natural_language_rule

        mock_result = MagicMock()
        mock_result.rule_json = json.dumps([1, 2, 3])
        mock_parser = MagicMock(return_value=mock_result)

        with patch("src.automation.nl_parser._configure_dspy", return_value=_dummy_configure_dspy()), \
             patch("src.automation.nl_parser.build_nl_rule_parser", return_value=mock_parser), \
             pytest.raises(ValueError, match="unexpected type"):
            parse_natural_language_rule(
                "do something", account_id=1, account_context=_ACCOUNT_CONTEXT
            )

    def test_invalid_json_raises(self):
        """Garbage output from the model raises a ValueError."""
        from src.automation.nl_parser import parse_natural_language_rule

        mock_result = MagicMock()
        mock_result.rule_json = "this is not json at all"
        mock_parser = MagicMock(return_value=mock_result)

        with patch("src.automation.nl_parser._configure_dspy", return_value=_dummy_configure_dspy()), \
             patch("src.automation.nl_parser.build_nl_rule_parser", return_value=mock_parser), \
             pytest.raises(ValueError):
            parse_natural_language_rule(
                "do something", account_id=1, account_context=_ACCOUNT_CONTEXT
            )

    def test_description_is_added_as_default(self):
        """
        The API endpoint calls workflow_json.setdefault("description", nl_description)
        after parsing. Confirm the returned dict supports that.
        """
        result = self._run_with_raw_output(json.dumps(_VALID_WORKFLOW))
        result.setdefault("description", "When the label is promotion, move to archive")
        assert "description" in result


# ---------------------------------------------------------------------------
# DSPy signature builder — instantiation checks (no LLM call)
# ---------------------------------------------------------------------------

class TestSignatureBuilderInstantiation:
    """
    These tests verify the builder functions return modules with the expected
    stage attributes. No LLM call is needed.
    """

    def test_nl_rule_parser_has_parse_stage(self):
        from src.dspy.signatures import build_nl_rule_parser
        module = build_nl_rule_parser(dspy)
        assert hasattr(module, "parse")

    def test_blog_writer_has_five_stages(self):
        from src.dspy.signatures import build_blog_writer
        module = build_blog_writer(dspy)
        for stage in ("persona", "outline", "draft", "editor", "seo"):
            assert hasattr(module, stage), f"missing stage: {stage}"

    def test_newsletter_writer_has_three_stages(self):
        from src.dspy.signatures import build_newsletter_writer
        module = build_newsletter_writer(dspy)
        for stage in ("strategy", "draft", "editor"):
            assert hasattr(module, stage), f"missing stage: {stage}"

    def test_whitepaper_writer_has_three_stages(self):
        from src.dspy.signatures import build_whitepaper_writer
        module = build_whitepaper_writer(dspy)
        for stage in ("plan", "draft", "editor"):
            assert hasattr(module, stage), f"missing stage: {stage}"

    def test_email_summarizer_has_predict_stage(self):
        from src.dspy.signatures import build_email_summarizer
        module = build_email_summarizer(dspy)
        assert hasattr(module, "predict")

    def test_document_extractor_has_predict_stage(self):
        from src.dspy.signatures import build_document_extractor
        module = build_document_extractor(dspy)
        assert hasattr(module, "predict")

    def test_chat_widget_reply_has_predict_stage(self):
        from src.dspy.signatures import build_chat_widget_reply
        module = build_chat_widget_reply(dspy)
        assert hasattr(module, "predict")


# ---------------------------------------------------------------------------
# DSPy signature builder — forward() with DummyLM
# ---------------------------------------------------------------------------

class TestNLRuleParserForward:
    def test_forward_returns_rule_json_string(self):
        from src.dspy.signatures import build_nl_rule_parser

        lm = dspy.utils.DummyLM([
            {"reasoning": "Trigger on email, action is archive", "rule_json": json.dumps(_VALID_WORKFLOW)}
        ])
        dspy.configure(lm=lm)
        module = build_nl_rule_parser(dspy)
        result = module(
            description="When the label is promotion, archive",
            account_context="{}",
        )
        assert hasattr(result, "rule_json")
        parsed = json.loads(result.rule_json)
        assert parsed["name"] == "Archive promotions"


class TestBlogWriterForward:
    def test_returns_seo_markdown(self):
        from src.dspy.signatures import build_blog_writer

        # 5 responses: persona(CoT), outline(CoT), draft(Predict), editor(Predict), seo(Predict)
        lm = dspy.utils.DummyLM([
            {"reasoning": "Awareness stage, lead with pain", "content_angle": "Focus on the problem, no pitch"},
            {"reasoning": "Structure the article", "outline": "## Hook\n## Problem\n## CTA"},
            {"article_markdown": "# How to save time\n\nContent here."},
            {"article_markdown": "# How to save time\n\nPolished content."},
            {"seo_markdown": "# How to save time\n\nSEO-optimised. Keywords: inbox, email."},
        ])
        dspy.configure(lm=lm)
        module = build_blog_writer(dspy)
        result = module(
            title="How to save time on support emails",
            audience="Founders at B2B SaaS",
            brief="Explain how AI reduces repetitive email load.",
            journey_stage="awareness",
        )
        assert hasattr(result, "seo_markdown")
        assert "seo" in result.seo_markdown.lower() or len(result.seo_markdown) > 0

    def test_all_journey_stages_accepted(self):
        from src.dspy.signatures import build_blog_writer

        for stage in ("awareness", "consideration", "decision"):
            lm = dspy.utils.DummyLM([
                {"reasoning": "angle reasoning", "content_angle": "angle"},
                {"reasoning": "outline reasoning", "outline": "outline"},
                {"article_markdown": "draft"},
                {"article_markdown": "edited"},
                {"seo_markdown": "final"},
            ])
            dspy.configure(lm=lm)
            module = build_blog_writer(dspy)
            result = module(title="T", audience="A", brief="B", journey_stage=stage)
            assert hasattr(result, "seo_markdown")


class TestNewsletterWriterForward:
    def test_returns_newsletter_json(self):
        from src.dspy.signatures import build_newsletter_writer

        newsletter = {"subject": "Save 5 hrs/wk", "preview_text": "Here's how",
                      "headline": "Stop answering the same questions",
                      "body_sections": [{"heading": "The problem", "content": "..."}],
                      "cta_text": "Start free trial", "cta_url": ""}
        lm = dspy.utils.DummyLM([
            {"reasoning": "Awareness, soft CTA", "strategy": "Lead with pain, offer value"},
            {"newsletter_json": json.dumps(newsletter)},
            {"newsletter_json": json.dumps(newsletter)},
        ])
        dspy.configure(lm=lm)
        module = build_newsletter_writer(dspy)
        result = module(
            audience="Founders at B2B SaaS",
            brief="Highlight time savings from AI",
            journey_stage="awareness",
        )
        assert hasattr(result, "newsletter_json")
        parsed = json.loads(result.newsletter_json)
        assert "subject" in parsed


class TestWhitepaperWriterForward:
    def test_returns_whitepaper_markdown(self):
        from src.dspy.signatures import build_whitepaper_writer

        lm = dspy.utils.DummyLM([
            {"reasoning": "Consideration stage plan", "structure": "## Executive Summary\n## Problem"},
            {"whitepaper_markdown": "# Whitepaper\n\nContent."},
            {"whitepaper_markdown": "# Whitepaper\n\nPolished."},
        ])
        dspy.configure(lm=lm)
        module = build_whitepaper_writer(dspy)
        result = module(
            audience="Operations leads at B2B SaaS",
            brief="The cost of manual email triage at scale",
            journey_stage="consideration",
        )
        assert hasattr(result, "whitepaper_markdown")
        assert len(result.whitepaper_markdown) > 0


# ---------------------------------------------------------------------------
# execute_workflow_with_tool_calling_agent wrapper
# ---------------------------------------------------------------------------

class _FakeWorkflow:
    """Minimal stand-in for AutomationRule to avoid Flask/SQLAlchemy context."""
    def __init__(self, enabled=True):
        self.id = "test-id"
        self.enabled = enabled
        self.name = "Test rule"
        self.account_id = 1
        self.description = None
        self.trigger = "email.received"
        self.conditions = []
        self.condition_logic = "AND"
        self.actions = []
        self.execution_count = 0
        self.success_count = 0
        self.error_count = 0
        self.last_executed_at = None


class TestExecuteWorkflowWrapper:
    def test_missing_workflow_returns_error(self):
        from src.automation.tool_calling_agent import execute_workflow_with_tool_calling_agent

        mock_query = MagicMock()
        mock_query.filter_by.return_value.first.return_value = None

        with patch("src.automation.tool_calling_agent.AutomationRule") as mock_model:
            mock_model.query = mock_query
            result = execute_workflow_with_tool_calling_agent(
                workflow_id="nonexistent-id",
                trigger_context={},
            )

        assert result["executed"] is False
        assert "not found" in result["error"].lower()

    def test_disabled_workflow_returns_disabled(self):
        from src.automation.tool_calling_agent import execute_workflow_with_tool_calling_agent

        disabled_wf = _FakeWorkflow(enabled=False)
        mock_query = MagicMock()
        mock_query.filter_by.return_value.first.return_value = disabled_wf

        with patch("src.automation.tool_calling_agent.AutomationRule") as mock_model:
            mock_model.query = mock_query
            result = execute_workflow_with_tool_calling_agent(
                workflow_id="disabled-id",
                trigger_context={},
            )

        assert result["executed"] is False
        assert result["reason"] == "workflow_disabled"
