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
from typing import Any, Dict, Tuple

from src.dspy.config import configure_dspy, get_provider_chain
from src.dspy.cache import _load_compiled_module
from src.dspy.email_detection import detect_email_type, NON_ACTIONABLE_EMAIL_TYPES
from src.dspy.formatting import format_payload, decision_outcome
from src.dspy.signatures import build_triage_module, build_decision_program
from src.dspy.draft_reply import (
    draft_reply_enabled,
    fetch_kb_context,
    fetch_calendar_slots,
    sanitize_reply,
    compute_reply_confidence,
)
from src.monitoring.observability import get_tracer
from src.monitoring.sanitizer import safe_span_attribute

logger = logging.getLogger(__name__)
tracer = get_tracer(__name__)

# Cost per 1M tokens (input_usd, output_usd) — update as pricing changes
_COST_PER_1M: Dict[str, Tuple[float, float]] = {
    # OpenAI
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
    "gpt-4-turbo": (10.00, 30.00),
    "gpt-4": (30.00, 60.00),
    "gpt-3.5-turbo": (0.50, 1.50),
    # Anthropic
    "claude-3-haiku-20240307": (0.25, 1.25),
    "claude-3-5-haiku-20241022": (0.80, 4.00),
    "claude-3-5-sonnet-20241022": (3.00, 15.00),
    "claude-3-opus-20240229": (15.00, 75.00),
    "claude-sonnet-4-6": (3.00, 15.00),
    # Google
    "gemini-1.5-flash": (0.075, 0.30),
    "gemini-1.5-pro": (1.25, 5.00),
    "gemini-2.0-flash": (0.10, 0.40),
}


def _is_quota_error(exc: Exception) -> bool:
    s = f"{type(exc).__name__} {exc}".lower()
    return any(k in s for k in ("ratelimit", "insufficient_quota", "quota_exceeded", "429"))


def _try_with_provider_failover(call_fn):
    """
    Call call_fn(). On quota/rate-limit error, reconfigure DSPy with the next
    provider in the chain and retry. Raises if all providers are exhausted.
    """
    chain = get_provider_chain()
    last_exc: Exception | None = None

    for idx, (provider, model) in enumerate(chain):
        if idx > 0:
            prev_provider = chain[idx - 1][0]
            logger.warning("DSPy provider %s unavailable, retrying with %s%s",
                           prev_provider, provider, f"/{model}" if model else "")
            configure_dspy(provider=provider, model=model)
        try:
            return call_fn()
        except Exception as exc:
            if _is_quota_error(exc) and idx < len(chain) - 1:
                last_exc = exc
                continue
            raise

    raise RuntimeError(f"All DSPy providers exhausted: {[p for p, _ in chain]}") from last_exc


def _compute_cost_usd(model_id: str, tokens_in: int, tokens_out: int) -> float:
    """Return estimated USD cost given model and token counts."""
    # model_id may be prefixed: "openai/gpt-4o-mini" → strip prefix
    bare = model_id.split("/")[-1] if "/" in model_id else model_id
    price = _COST_PER_1M.get(bare)
    if not price:
        # Unknown model — default to gpt-4o-mini pricing as a conservative estimate
        price = (0.15, 0.60)
    in_cost = tokens_in * price[0] / 1_000_000
    out_cost = tokens_out * price[1] / 1_000_000
    return round(in_cost + out_cost, 8)


def _collect_lm_usage(lm: Any, history_start: int) -> Tuple[int, int]:
    """
    Sum prompt/completion tokens from dspy lm.history entries added since history_start.

    DSPy appends one entry per LM call. Each entry may expose usage via:
    - entry["usage"] dict  (newer DSPy versions)
    - entry["response"].usage  (OpenAI ChatCompletion object)
    - entry["response"]["usage"]  (dict response)
    """
    try:
        history = list(getattr(lm, "history", []))
    except Exception:
        return 0, 0

    tokens_in, tokens_out = 0, 0
    for entry in history[history_start:]:
        try:
            usage = entry.get("usage") if isinstance(entry, dict) else None
            if not usage:
                response = entry.get("response") if isinstance(entry, dict) else None
                if response is not None:
                    if hasattr(response, "usage"):
                        usage = response.usage
                    elif isinstance(response, dict):
                        usage = response.get("usage") or {}
            if not usage:
                continue
            # Usage may be a pydantic object or plain dict
            get = usage.get if isinstance(usage, dict) else lambda k, d=0: getattr(usage, k, d)
            tokens_in += int(get("prompt_tokens", 0) or get("input_tokens", 0))
            tokens_out += int(get("completion_tokens", 0) or get("output_tokens", 0))
        except Exception:
            continue
    return tokens_in, tokens_out


def run_dspy_triage(
    payload: Dict[str, Any],
    context: Dict[str, Any] | None = None,
    labels: Dict[str, Any] | None = None,
    account_id: int | None = None,
    sender_hint: str = "",
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

        return _run_dspy_triage_impl(span, payload, context, labels, account_id, sender_hint)


def _run_dspy_triage_impl(
    span,
    payload: Dict[str, Any],
    context: Dict[str, Any] | None,
    labels: Dict[str, Any] | None,
    account_id: int | None,
    sender_hint: str = "",
) -> Dict[str, Any]:
    """Internal implementation of run_dspy_triage with span context."""
    model, model_id, dspy = configure_dspy()
    label_config = labels or {}

    # Record model information
    safe_span_attribute(span, "dspy.model", model)
    safe_span_attribute(span, "dspy.model_id", model_id)

    # Snapshot history length so we can diff after the run
    _lm = getattr(dspy.settings, "lm", None)
    _history_start = len(list(getattr(_lm, "history", []))) if _lm else 0

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

    # Load compiled TriageModule (what training produces).
    # Used as fallback when DecisionProgram fails; stored separately so we
    # don't throw it away and rebuild an uncompiled module on error.
    compiled_module = _load_compiled_module(dspy, model_id, account_id, labels=label_config)
    module = compiled_module or build_decision_program(dspy, label_config)

    # Check if draft reply is enabled
    draft_enabled = draft_reply_enabled(context, account_id)

    # Thread history is already in case["history"]; surface it explicitly for DraftReplySig
    thread_history_json = json.dumps(case.get("history") or [])

    # Fetch KB context if draft reply and KB drafts are enabled on the plan
    kb_context_list = []
    kb_context_json = "[]"
    if draft_enabled:
        from src.features import get_draft_reply_config
        draft_cfg = get_draft_reply_config(account_id) if account_id else {}
        kb_allowed = draft_cfg.get("kb_enabled", False)

        subject = payload.get("subject", "")
        body = payload.get("body") or payload.get("text") or ""
        if kb_allowed:
            kb_context_list = fetch_kb_context(subject, body, account_id, limit=3)
        # If the email is a meeting request and the account has Google Calendar
        # connected, surface available slots so the draft reply can include them.
        from_email = payload.get("from_email") or payload.get("from") or ""
        calendar_slots = fetch_calendar_slots(subject, body, account_id, requester_email=from_email or None)
        if calendar_slots:
            kb_context_list.append({
                "type": "calendar_availability",
                "content": calendar_slots,
            })
        kb_context_json = json.dumps(kb_context_list)

    inbox_owner_email = payload.get("inbox_owner_email") or ""

    # Run DSPy decision program
    try:
        result = _try_with_provider_failover(
            lambda: module(case_json=case_json, draft_enabled=draft_enabled, kb_context=kb_context_json, sender_hint=sender_hint, thread_history=thread_history_json, inbox_owner_email=inbox_owner_email)
        )
    except Exception as exc:
        logger.warning("DSPy decision program failed, falling back to compiled triage: %s", exc)
        fallback_module = compiled_module or build_triage_module(dspy, label_config)
        triage_pred = _try_with_provider_failover(
            lambda: fallback_module(content=prompt_payload)
        )
        # Synthesize DecisionProgram-format JSON blobs from the flat TriageModule
        # fields so the rest of the pipeline parses them correctly.
        ar = str(getattr(triage_pred, "action_required", "optional")).lower().strip()
        escalation_decision = (
            "escalate" if ar == "true" else
            "auto_resolve" if ar == "false" else
            "ask_clarifying"
        )
        _fallback_entities = json.dumps({
            "intent": getattr(triage_pred, "intent", ""),
            "sentiment": getattr(triage_pred, "sentiment", "neutral"),
            "email_type": getattr(triage_pred, "email_type", "unknown"),
            "is_automated": getattr(triage_pred, "is_automated", "false"),
            "requires_human_response": str(ar == "true").lower(),
        })
        _fallback_escalation = json.dumps({
            "decision": escalation_decision,
            "reason": getattr(triage_pred, "ai_reason", ""),
            "required_role": getattr(triage_pred, "assigned_to", ""),
        })
        # Attempt standalone draft even though the main pipeline fell back.
        # The 5-stage DecisionProgram may have failed, but a single-step draft
        # call is far more likely to succeed and must not be silently skipped.
        _fallback_reply = None
        if draft_enabled:
            try:
                from src.dspy.signatures import build_decision_program as _bdp
                _draft_prog = _bdp(dspy, label_config)
                _dr = _draft_prog.draft(
                    inbox_owner_email=inbox_owner_email,
                    case_json=case_json,
                    thread_history=thread_history_json,
                    entities_json=_fallback_entities,
                    workflow_json="{}",
                    escalation_json=_fallback_escalation,
                    kb_context=kb_context_json,
                )
                _fallback_reply = _dr.reply_text
            except Exception as _fde:
                logger.warning("fallback draft generation failed (non-fatal): %s", _fde)

        result = dspy.Prediction(
            entities_json=_fallback_entities,
            route_json=json.dumps({
                "queue": getattr(triage_pred, "category", ""),
                "priority": getattr(triage_pred, "priority", "P3"),
                "rationale": getattr(triage_pred, "ai_reason", ""),
            }),
            workflow_json="{}",
            escalation_json=_fallback_escalation,
            reply_text=_fallback_reply,
        )

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
    from src.dspy.triage_config import get_triage_config
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

    # Snap the raw queue value to a canonical InboxIQ category.
    # DSPy may return free-form strings ("general", "bug", "technical") — map these
    # to the nearest canonical label so Gmail writeback uses a proper InboxIQ/* label.
    _CANONICAL_CATEGORIES = {
        "support", "billing", "transactions", "updates", "promotions", "social", "forums",
    }
    _CATEGORY_MAP = {
        # DSPy default label set → canonical
        "sales": "support", "technical": "support", "feedback": "support",
        "bug_report": "support", "bug": "support", "general": "support",
        "other": "support",
        "marketing": "promotions", "newsletter": "updates",
        "spam": "updates", "auto_reply": "updates", "notification": "updates",
        "informational": "updates",
    }
    _raw_cat = (route.get("queue") or entities.get("intent") or email_type or triage_cfg.default_category or "").lower().strip()
    if _raw_cat in _CANONICAL_CATEGORIES:
        _resolved_category = _raw_cat
    else:
        _resolved_category = _CATEGORY_MAP.get(_raw_cat, triage_cfg.default_category or "support")

    content = {
        "category": _resolved_category,
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

    # Collect LLM token usage from history entries added during this run
    llm_tokens_in, llm_tokens_out = _collect_lm_usage(_lm, _history_start)
    llm_cost_usd = _compute_cost_usd(model_id, llm_tokens_in, llm_tokens_out)

    safe_span_attribute(span, "llm.tokens_in", llm_tokens_in)
    safe_span_attribute(span, "llm.tokens_out", llm_tokens_out)
    safe_span_attribute(span, "llm.cost_usd", llm_cost_usd)

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
        "model_id": model_id,
        "llm_tokens_in": llm_tokens_in,
        "llm_tokens_out": llm_tokens_out,
        "llm_cost_usd": llm_cost_usd,
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
