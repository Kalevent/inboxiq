"""
Main DSPy triage orchestration.

Coordinates the full triage pipeline:
1. Configure DSPy provider
2. Format payload
3. Load compiled module or build fresh
4. Run decision program with draft reply (optional)
5. Parse results and apply multi-layered action_required logic
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict

from src.dspy.config import configure_dspy
from src.dspy.cache import _load_compiled_module
from src.dspy.email_detection import detect_email_type, NON_ACTIONABLE_EMAIL_TYPES
from src.dspy.formatting import format_payload, decision_outcome
from src.dspy.signatures import build_triage_module, build_decision_program
from src.dspy.draft_reply import (
    draft_reply_enabled,
    fetch_kb_context,
    sanitize_reply,
    compute_reply_confidence,
)
from src.observability import get_tracer
from src.observability_sanitizer import safe_span_attribute

logger = logging.getLogger(__name__)
tracer = get_tracer(__name__)


def run_dspy_triage(
    payload: Dict[str, Any],
    context: Dict[str, Any] | None = None,
    labels: Dict[str, Any] | None = None,
    account_id: int | None = None,
) -> Dict[str, Any]:
    """
    Run DSPy triage with multi-layered decision logic.

    Decision priority (highest to lowest):
    1. Heuristic detection (spam/marketing/auto-reply patterns)
    2. LLM email_type classification
    3. LLM automated + no human response needed
    4. LLM explicit escalation decision
    5. Priority-based fallback

    Args:
        payload: Email/case payload with subject, body, from_email, etc.
        context: Optional context dict with features, plan, etc.
        labels: Label configuration (categories, priorities, etc.)
        account_id: Account ID for feature access and artifact caching

    Returns:
        Structured triage decision dict with:
        - provider: "dspy"
        - model: Model name used
        - content: Nested dict with all decision fields
        - All content fields flattened to top level
    """
    with tracer.start_as_current_span("dspy.triage") as span:
        # Add input context attributes (sanitized)
        safe_span_attribute(span, "account_id", account_id)
        safe_span_attribute(span, "payload.provider", payload.get("provider"))
        safe_span_attribute(span, "payload.source", payload.get("source"))
        safe_span_attribute(span, "payload.subject_length", len(payload.get("subject", "")))
        safe_span_attribute(span, "payload.body_length", len(payload.get("body", "")))

        return _run_dspy_triage_impl(span, payload, context, labels, account_id)


def _run_dspy_triage_impl(
    span,
    payload: Dict[str, Any],
    context: Dict[str, Any] | None,
    labels: Dict[str, Any] | None,
    account_id: int | None,
) -> Dict[str, Any]:
    """Internal implementation of run_dspy_triage with span context."""
    model, model_id, dspy = configure_dspy()
    label_config = labels or {}

    # Record model information
    safe_span_attribute(span, "dspy.model", model)
    safe_span_attribute(span, "dspy.model_id", model_id)

    # Format payload for DSPy prompt
    prompt_payload = format_payload(payload, context)
    case = {
        "channel": payload.get("channel") or payload.get("source") or payload.get("provider") or "email",
        "text": payload.get("body") or payload.get("text") or prompt_payload,
        "metadata": {
            "subject": payload.get("subject"),
            "from_email": payload.get("from_email") or payload.get("from"),
            "provider": payload.get("provider"),
            "source": payload.get("source"),
            "received_at": payload.get("received_at"),
        },
        "crm_snapshot": payload.get("crm_snapshot") or {},
        "history": payload.get("history") or [],
    }
    case_json = json.dumps(case)

    # Load compiled module or build fresh
    module = _load_compiled_module(dspy, model_id, account_id, labels=label_config) or \
             build_decision_program(dspy, label_config)

    # Check if draft reply is enabled
    draft_enabled = draft_reply_enabled(context, account_id)

    # Fetch KB context if draft reply is enabled
    kb_context_list = []
    kb_context_json = "[]"
    if draft_enabled:
        subject = payload.get("subject", "")
        body = payload.get("body") or payload.get("text") or ""
        kb_context_list = fetch_kb_context(subject, body, account_id, limit=3)
        kb_context_json = json.dumps(kb_context_list)

    # Run DSPy decision program
    try:
        result = module(case_json=case_json, draft_enabled=draft_enabled, kb_context=kb_context_json)
    except Exception as exc:
        logger.warning("DSPy decision program failed, falling back to simple triage: %s", exc)
        module = build_triage_module(dspy, label_config)
        result = module(content=prompt_payload)

    # Extract results
    entities_json = getattr(result, "entities_json", None)
    route_json = getattr(result, "route_json", None)
    workflow_json = getattr(result, "workflow_json", None)
    escalation_json = getattr(result, "escalation_json", None)
    reply_text = getattr(result, "reply_text", None)

    def _safe_parse(val: Any) -> Dict[str, Any]:
        if not val or not isinstance(val, str):
            return {}
        try:
            return json.loads(val)
        except Exception:
            return {}

    entities = _safe_parse(entities_json)
    route = _safe_parse(route_json)
    workflow = _safe_parse(workflow_json)
    escalation = _safe_parse(escalation_json)

    # Sanitize and enrich reply if present
    reply_confidence = None
    reply_metadata = {}
    if reply_text and draft_enabled:
        reply_text = sanitize_reply(reply_text, account_id)
        reply_confidence = compute_reply_confidence(result)
        reply_metadata = {
            "kb_articles_used": [article.get("id") for article in kb_context_list if article.get("id")],
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "requires_review": reply_confidence < 0.7,
            "confidence": reply_confidence,
        }

    # Extract email type classification from entities
    email_type = str(entities.get("email_type", "")).lower().strip()
    is_automated_str = str(entities.get("is_automated", "")).lower().strip()
    is_automated = is_automated_str in ("true", "yes", "1")
    requires_human = str(entities.get("requires_human_response", "")).lower().strip()
    requires_human_response = requires_human in ("true", "yes", "1")

    # Pre-filter using heuristics (before LLM decision)
    heuristic_type, heuristic_automated, heuristic_reason = detect_email_type(payload)
    decision_trace = ["dspy:extract", "dspy:route", "dspy:workflow", "dspy:escalate"]

    # Determine action_required based on multiple signals
    decision = escalation.get("decision")
    action_required: bool | str = True  # Default, will be overridden

    # PRIORITY 1: Heuristic detection of spam/marketing/auto-replies (highest confidence)
    if heuristic_type in NON_ACTIONABLE_EMAIL_TYPES:
        action_required = False
        decision_trace.append(f"heuristic:{heuristic_type}")
        if not email_type or email_type == "unknown":
            email_type = heuristic_type
        is_automated = True

    # PRIORITY 2: LLM classified as non-actionable email type
    elif email_type in NON_ACTIONABLE_EMAIL_TYPES:
        action_required = False
        decision_trace.append(f"llm_email_type:{email_type}")

    # PRIORITY 3: LLM says it's automated and doesn't require human response
    elif is_automated and not requires_human_response:
        action_required = False
        decision_trace.append("llm:automated_no_human_needed")

    # PRIORITY 4: Explicit escalation decision from LLM
    elif decision in {"auto_resolve", "auto-resolve", "resolved", "ignore"}:
        action_required = False
        decision_trace.append("llm:auto_resolve")
    elif decision in {"ask_clarifying", "escalate_on_reply", "optional"}:
        action_required = "optional"
        decision_trace.append("llm:optional")
    elif decision in {"escalate", "human_required", "urgent"}:
        action_required = True
        decision_trace.append("llm:escalate")

    # PRIORITY 5: Fallback based on priority level
    else:
        priority = (route.get("priority") or "").strip().upper()
        if priority == "P1":  # Urgent
            action_required = True
            decision_trace.append("fallback:high_priority")
        elif priority in {"P2"}:
            # P2 with neutral sentiment and no urgency markers -> optional
            sentiment = str(entities.get("sentiment", "")).lower()
            if sentiment in {"neutral", "positive"}:
                action_required = "optional"
                decision_trace.append("fallback:p2_neutral")
            else:
                action_required = True
                decision_trace.append("fallback:p2_negative")
        elif priority in {"P3", "P4", ""}:
            # Low priority -> auto-handle by default
            action_required = False
            decision_trace.append("fallback:low_priority")
        else:
            # Unknown priority -> be cautious, mark as optional
            action_required = "optional"
            decision_trace.append("fallback:unknown_priority")

    # Build AI reason using configurable fallbacks
    from src.triage_config import get_triage_config
    triage_cfg = get_triage_config(account_id)

    ai_reason = escalation.get("reason") or route.get("rationale")
    if not ai_reason:
        if action_required is False:
            if email_type in NON_ACTIONABLE_EMAIL_TYPES:
                ai_reason = f"Auto-handled: {email_type.replace('_', ' ')} email"
            elif heuristic_reason:
                ai_reason = f"Auto-handled: {heuristic_reason}"
            else:
                ai_reason = triage_cfg.get_fallback_message("auto_handled")
        elif action_required == "optional":
            ai_reason = triage_cfg.get_fallback_message("optional")
        else:
            ai_reason = triage_cfg.get_fallback_message("action_required")

    content = {
        "category": route.get("queue") or entities.get("intent") or email_type or triage_cfg.default_category,
        "priority": route.get("priority") or ("P4" if action_required is False else triage_cfg.default_priority),
        "sentiment": entities.get("sentiment") or "neutral",
        "intent": entities.get("intent"),
        "email_type": email_type or heuristic_type or "unknown",
        "is_automated": is_automated or heuristic_automated,
        "action_required": action_required,
        "ai_reason": ai_reason,
        "team": route.get("queue"),
        "assigned_to": escalation.get("required_role"),
        "owner": escalation.get("required_role"),
        "decision_type": "triage",
        "decision_outcome": decision_outcome(action_required),
        "decision_trace": decision_trace,
        "reply_text": reply_text,
        "reply_confidence": reply_confidence,
        "reply_metadata": reply_metadata if reply_metadata else None,
        "entities_json": entities_json,
        "route_json": route_json,
        "workflow_json": workflow_json,
        "escalation_json": escalation_json,
    }

    # Record triage decision results (sanitized)
    safe_span_attribute(span, "triage.category", content["category"])
    safe_span_attribute(span, "triage.priority", content["priority"])
    safe_span_attribute(span, "triage.sentiment", content["sentiment"])
    safe_span_attribute(span, "triage.email_type", content["email_type"])
    safe_span_attribute(span, "triage.is_automated", content["is_automated"])
    safe_span_attribute(span, "triage.action_required", str(content["action_required"]))
    safe_span_attribute(span, "triage.decision_outcome", content["decision_outcome"])

    # Record decision trace (first 5 steps to avoid bloat)
    if decision_trace:
        span.set_attribute("triage.decision_trace", ",".join(decision_trace[:5]))

    # Record draft reply status if enabled
    if reply_text:
        span.set_attribute("triage.draft_reply_generated", True)
        safe_span_attribute(span, "triage.reply_confidence", reply_confidence)
        span.set_attribute("triage.reply_requires_review", reply_confidence < 0.7 if reply_confidence else True)

    # Add span event for audit trail
    span.add_event("triage_completed", {
        "category": content["category"],
        "priority": content["priority"],
        "action_required": str(content["action_required"]),
        "decision_outcome": content["decision_outcome"],
    })

    return {
        "provider": "dspy",
        "model": model,
        "content": content,
        **content,
    }


def run_dspy_llm(user_input: str, context: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """
    Lightweight wrapper for ad-hoc LLM interactions.

    Formats user_input as a minimal email payload and runs triage.

    Args:
        user_input: Text input from user
        context: Optional context dict

    Returns:
        Triage decision dict
    """
    payload = {"subject": "", "body": user_input, "from_email": "", "provider": "llm"}
    return run_dspy_triage(payload, context)
