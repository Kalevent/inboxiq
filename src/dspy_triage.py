"""
DSPy integration scaffolding for InboxIQ triage.
"""
from __future__ import annotations

import os
import pickle
import re
import json
from datetime import datetime, timezone
import logging
from typing import Any, Dict


def _env_bool(name: str, default: bool = False) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.lower() in ("1", "true", "yes", "on")


def _configure_dspy() -> tuple[str, str, Any]:
    try:
        import dspy  # type: ignore
    except Exception as exc:  # pragma: no cover - depends on optional dep
        raise RuntimeError(
            "DSPy is not installed. Install with `pip install dspy-ai` and set DSPY_ENABLED=1."
        ) from exc

    model = os.getenv("DSPY_MODEL", "gpt-4o-mini")
    provider = os.getenv("DSPY_PROVIDER")
    if not provider:
        if _env_bool("DSPY_USE_OPENAI", False) and os.getenv("OPENAI_API_KEY"):
            provider = "openai"
        elif _env_bool("DSPY_USE_ANTHROPIC", False) and os.getenv("ANTHROPIC_API_KEY"):
            provider = "anthropic"
        elif _env_bool("DSPY_USE_GEMINI", False) and os.getenv("GEMINI_API_KEY"):
            provider = "gemini"
        else:
            raise RuntimeError("DSPy provider is required. Set DSPY_PROVIDER=openai|anthropic|gemini.")
    provider = provider.strip().lower()

    if provider == "openai":
        if not os.getenv("OPENAI_API_KEY"):
            raise RuntimeError("OPENAI_API_KEY is required for DSPy OpenAI provider.")
        try:
            model_id = model if "/" in model else f"openai/{model}"
            lm = dspy.LM(model=model_id, max_tokens=300, temperature=0.2)
        except Exception as exc:
            raise RuntimeError("Failed to configure DSPy OpenAI backend.") from exc
    elif provider == "anthropic":
        if not os.getenv("ANTHROPIC_API_KEY"):
            raise RuntimeError("ANTHROPIC_API_KEY is required for DSPy Anthropic provider.")
        try:
            model_id = model if "/" in model else f"anthropic/{model}"
            lm = dspy.LM(model=model_id, max_tokens=300, temperature=0.2)
        except Exception as exc:
            raise RuntimeError("Failed to configure DSPy Anthropic backend.") from exc
    elif provider in {"gemini", "google"}:
        if not os.getenv("GEMINI_API_KEY"):
            raise RuntimeError("GEMINI_API_KEY is required for DSPy Gemini provider.")
        try:
            prefix = "google" if provider in {"gemini", "google"} else provider
            model_id = model if "/" in model else f"{prefix}/{model}"
            lm = dspy.LM(model=model_id, max_tokens=300, temperature=0.2)
        except Exception as exc:
            raise RuntimeError("Failed to configure DSPy Gemini backend.") from exc
    else:
        raise RuntimeError("DSPy backend not configured. Set DSPY_PROVIDER or DSPY_USE_OPENAI=1/DSPY_USE_ANTHROPIC=1/DSPY_USE_GEMINI=1.")

    if getattr(dspy.settings, "lm", None) is None:
        dspy.settings.configure(lm=lm)
    return model, model_id, dspy


def _compiled_dir() -> str:
    return os.path.abspath(os.getenv("DSPY_COMPILED_DIR", os.path.join(os.path.dirname(__file__), "..", ".dspy")))


def _compiled_artifact_path(model_id: str, account_id: int | None = None) -> str:
    safe_key = re.sub(r"[^a-zA-Z0-9_.-]+", "_", model_id)
    if account_id is None:
        return os.path.join(_compiled_dir(), f"triage-{safe_key}.pkl")
    return os.path.join(_compiled_dir(), f"triage-{safe_key}-acct{account_id}.pkl")


def _compiled_meta_path(model_id: str, account_id: int | None = None) -> str:
    safe_key = re.sub(r"[^a-zA-Z0-9_.-]+", "_", model_id)
    if account_id is None:
        return os.path.join(_compiled_dir(), f"triage-{safe_key}.meta.json")
    return os.path.join(_compiled_dir(), f"triage-{safe_key}-acct{account_id}.meta.json")


def _labels_hash(labels: Dict[str, Any] | None) -> str:
    payload = labels or {}
    try:
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    except Exception:
        encoded = json.dumps(str(payload), sort_keys=True, separators=(",", ":"))
    return str(hash(encoded))


def _load_compiled_meta(model_id: str, account_id: int | None) -> Dict[str, Any] | None:
    path = _compiled_meta_path(model_id, account_id)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except Exception as exc:
        logging.getLogger(__name__).warning("failed to load DSPy compiled metadata: %s", exc)
        return None


def _load_compiled_module(
    dspy: Any,
    model_id: str,
    account_id: int | None = None,
    labels: Dict[str, Any] | None = None,
) -> Any | None:
    if not _env_bool("DSPY_COMPILED_ENABLED", True):
        return None
    path = _compiled_artifact_path(model_id, account_id)
    if not os.path.exists(path):
        return None
    meta = _load_compiled_meta(model_id, account_id)
    if meta:
        expected = _labels_hash(labels)
        if meta.get("labels_hash") and meta.get("labels_hash") != expected:
            logging.getLogger(__name__).warning(
                "DSPy compiled module stale: labels hash mismatch (model_id=%s account_id=%s expected=%s actual=%s).",
                model_id,
                account_id,
                expected,
                meta.get("labels_hash"),
            )
            return None
    try:
        if hasattr(dspy, "load"):
            return dspy.load(path)
        with open(path, "rb") as handle:
            return pickle.load(handle)
    except Exception as exc:
        logging.getLogger(__name__).warning("failed to load DSPy compiled module: %s", exc)
        return None


def _save_compiled_module(
    dspy: Any,
    module: Any,
    model_id: str,
    account_id: int | None = None,
    labels: Dict[str, Any] | None = None,
    extra_meta: Dict[str, Any] | None = None,
) -> str:
    path = _compiled_artifact_path(model_id, account_id)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if hasattr(dspy, "save"):
        dspy.save(module, path)
    else:
        with open(path, "wb") as handle:
            pickle.dump(module, handle)
    meta_path = _compiled_meta_path(model_id, account_id)
    meta = {
        "model_id": model_id,
        "account_id": account_id,
        "labels_hash": _labels_hash(labels),
        "version": "v1",
        "compiled_at": datetime.now(timezone.utc).isoformat(),
    }
    if extra_meta:
        meta.update(extra_meta)
    try:
        with open(meta_path, "w", encoding="utf-8") as handle:
            json.dump(meta, handle)
    except Exception as exc:
        logging.getLogger(__name__).warning("failed to write DSPy compiled metadata: %s", exc)
    return path


def _format_payload(payload: Dict[str, Any], context: Dict[str, Any] | None) -> str:
    subject = (payload.get("subject") or "").strip()
    body = (payload.get("body") or "").strip()
    from_email = (payload.get("from_email") or payload.get("from") or "").strip()
    provider = (payload.get("provider") or payload.get("source") or "").strip()
    source = (payload.get("source") or "").strip()
    received_at = payload.get("received_at") or ""

    lines = [
        f"subject: {subject}",
        f"from: {from_email}",
        f"provider: {provider}",
        f"source: {source}",
        f"received_at: {received_at}",
        "body:",
        body,
    ]
    if context:
        lines.append(f"context: {context}")
    return "\n".join(line for line in lines if line is not None)


def _label_desc(labels: Dict[str, Any], key: str, fallback: str) -> str:
    values = labels.get(key) if labels else None
    if isinstance(values, list) and values:
        return f"One of: {', '.join(str(v) for v in values)}"
    return fallback


# Email types that should be auto-handled without human review
NON_ACTIONABLE_EMAIL_TYPES = {
    "spam", "marketing", "newsletter", "transactional",
    "auto_reply", "out_of_office", "promotional", "notification"
}

# Sender patterns that indicate automated emails
AUTOMATED_SENDER_PATTERNS = [
    "noreply@", "no-reply@", "donotreply@", "do-not-reply@",
    "mailer-daemon", "postmaster@", "notifications@", "alerts@",
    "newsletter@", "marketing@", "promo@", "bounce@", "auto@"
]

# Subject patterns indicating non-actionable emails
SPAM_SUBJECT_PATTERNS = [
    "you've won", "congratulations", "act now", "limited time",
    "click here", "free gift", "winner", "claim your"
]

MARKETING_SUBJECT_PATTERNS = [
    "newsletter", "unsubscribe", "weekly digest", "monthly update",
    "special offer", "% off", "sale ends", "don't miss"
]

AUTO_REPLY_SUBJECT_PATTERNS = [
    "out of office", "automatic reply", "auto:", "re: automatic",
    "away from", "on vacation", "currently unavailable"
]


def _detect_email_type(payload: Dict[str, Any]) -> tuple[str, bool, str | None]:
    """
    Detect email type using heuristics before LLM classification.
    Returns: (email_type, is_automated, skip_reason)
    """
    subject = (payload.get("subject") or "").lower()
    from_email = (payload.get("from_email") or payload.get("from") or "").lower()
    body = (payload.get("body") or "").lower()

    # Check for automated sender patterns
    is_automated = any(pattern in from_email for pattern in AUTOMATED_SENDER_PATTERNS)

    # Check for spam patterns
    if any(pattern in subject for pattern in SPAM_SUBJECT_PATTERNS):
        return "spam", True, "Spam subject pattern detected"

    # Check for marketing patterns
    if any(pattern in subject for pattern in MARKETING_SUBJECT_PATTERNS):
        return "marketing", True, "Marketing email pattern detected"
    if "unsubscribe" in body and ("view in browser" in body or "email preferences" in body):
        return "newsletter", True, "Newsletter pattern detected"

    # Check for auto-reply patterns
    if any(pattern in subject for pattern in AUTO_REPLY_SUBJECT_PATTERNS):
        return "auto_reply", True, "Auto-reply detected"
    if "i am currently out" in body or "automatic response" in body:
        return "auto_reply", True, "Auto-reply body pattern detected"

    # Check for transactional/notification emails
    if is_automated:
        if any(word in subject for word in ["shipped", "delivered", "confirmation", "receipt", "invoice"]):
            return "transactional", True, "Transactional email from no-reply sender"
        return "notification", True, "Automated notification from no-reply sender"

    return "unknown", False, None


def _draft_reply_enabled(context: Dict[str, Any] | None, account_id: int | None = None) -> bool:
    """
    Check if draft reply generation is enabled for this request.
    Uses the centralized features.check_draft_reply_access for consistency.
    """
    if not _env_bool("DSPY_DRAFT_REPLY_ENABLED", False):
        return False
    if not account_id:
        # Fallback to legacy context-based check if no account_id
        if not context:
            return False
        features = context.get("features") if isinstance(context, dict) else None
        if isinstance(features, dict):
            if features.get("draft_reply") is True:
                return True
            if features.get("draft_reply") is False:
                return False
        plan = str(context.get("plan") or "").lower() if isinstance(context, dict) else ""
        return plan in {"business", "enterprise"}

    # Use centralized feature access control
    try:
        from src.features import check_draft_reply_access
        return check_draft_reply_access(account_id, context)
    except Exception as exc:
        logging.warning(f"Failed to check draft_reply access: {exc}")
        return False


def _fetch_kb_context(
    subject: str,
    body: str,
    account_id: int | None = None,
    limit: int = 3
) -> list[dict]:
    """
    Retrieve relevant knowledge base articles using semantic search.

    Returns a list of dicts with: {"id": str, "title": str, "snippet": str}

    Note: This is a placeholder implementation. When a proper KB system exists,
    this should query the KB using vector similarity search with embeddings.
    """
    # TODO: Implement actual KB retrieval when KB system is available
    # For now, return empty list - draft replies will work without KB context

    # Future implementation should:
    # 1. Combine subject + body into query text
    # 2. Generate embedding using src.embeddings.embed_text
    # 3. Query KB articles table with pgvector similarity search
    # 4. Return top N relevant articles with title and content snippet

    return []


def _sanitize_reply(reply_text: str, account_id: int | None = None) -> str:
    """
    Sanitize and improve draft reply text.

    - Removes internal markers like [INTERNAL: ...]
    - Ensures professional tone
    - Adds signature placeholder if missing
    - Applies account-specific tone preferences (future enhancement)

    Args:
        reply_text: The raw reply text from DSPy
        account_id: Optional account ID for account-specific preferences

    Returns:
        Sanitized reply text ready for human review
    """
    if not reply_text:
        return ""

    # Remove internal markers and notes
    reply_text = re.sub(r'\[INTERNAL:.*?\]', '', reply_text, flags=re.IGNORECASE | re.DOTALL)
    reply_text = re.sub(r'\[NOTE:.*?\]', '', reply_text, flags=re.IGNORECASE | re.DOTALL)

    # Clean up excessive whitespace
    reply_text = re.sub(r'\n{3,}', '\n\n', reply_text)
    reply_text = reply_text.strip()

    # Ensure signature placeholder if not present
    signature_markers = ["best regards", "sincerely", "thanks", "thank you", "regards"]
    has_signature = any(marker in reply_text.lower() for marker in signature_markers)

    if not has_signature and len(reply_text) > 20:
        reply_text += "\n\nBest regards"

    return reply_text


def _compute_reply_confidence(result: Any) -> float:
    """
    Compute confidence score for generated draft reply.

    Currently returns a default confidence of 0.8.
    Future enhancement: analyze reply quality, length, specificity, etc.

    Args:
        result: The DSPy prediction result

    Returns:
        Confidence score between 0.0 and 1.0
    """
    # TODO: Implement actual confidence calculation based on:
    # - Reply length (too short or too long = lower confidence)
    # - Presence of specific answers vs vague responses
    # - KB article relevance scores
    # - Entity extraction confidence

    return 0.8


def _decision_outcome(action_required: Any) -> str:
    if isinstance(action_required, str):
        lowered = action_required.lower()
        if lowered in {"optional", "needs_review"}:
            return "needs_review"
        if lowered in {"false", "no", "none"}:
            return "auto_handled"
    if action_required is True:
        return "action_required"
    if action_required in ("optional", "needs_review"):
        return "needs_review"
    if action_required is False:
        return "auto_handled"
    return "action_required"


def build_triage_module(dspy: Any, label_config: Dict[str, Any]) -> Any:
    class TriageSignature(dspy.Signature):
        """Classify inbound support content for triage. Identify spam, marketing, and auto-replies for auto-handling."""

        content = dspy.InputField(desc="Inbound payload with subject, body, sender, source, and context.")
        category = dspy.OutputField(desc=_label_desc(label_config, "categories", "Provide a concise category label."))
        priority = dspy.OutputField(desc=_label_desc(label_config, "priorities", "Provide a priority label."))
        sentiment = dspy.OutputField(desc=_label_desc(label_config, "sentiments", "Provide a sentiment label."))
        intent = dspy.OutputField(desc=_label_desc(label_config, "intents", "Provide an intent label."))
        # NEW: Email type classification for auto-handling
        email_type = dspy.OutputField(
            desc="One of: support_request | sales_inquiry | billing | bug_report | feature_request | "
                 "marketing | newsletter | spam | transactional | auto_reply | notification | internal | other. "
                 "Use marketing/newsletter/spam/auto_reply/transactional for non-actionable emails."
        )
        is_automated = dspy.OutputField(
            desc="true if this is an automated email (auto-reply, system notification, no-reply sender, newsletter), false if from a human requiring response"
        )
        action_required = dspy.OutputField(
            desc="false for spam/marketing/newsletter/auto_reply/transactional emails. true for support requests needing human response. optional for low-priority items."
        )
        ai_reason = dspy.OutputField(desc="Short reason for the decision.")
        team = dspy.OutputField(desc=_label_desc(label_config, "teams", "Suggested team name for assignment."))
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
    class ExtractEntitiesSig(dspy.Signature):
        """Extract entities and classify email type. Identify spam, marketing, newsletters, and auto-replies for auto-handling."""
        case_json = dspy.InputField(desc="JSON of normalized case payload.")
        entities_json = dspy.OutputField(
            desc="JSON with: intent, sentiment, urgency, identifiers, missing_info, "
                 "email_type (support_request|sales_inquiry|billing|bug_report|feature_request|marketing|newsletter|spam|transactional|auto_reply|notification|other), "
                 "is_automated (true/false), requires_human_response (true/false). "
                 "Set email_type to spam/marketing/newsletter/auto_reply/transactional and is_automated=true for non-actionable emails."
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


def run_dspy_triage(
    payload: Dict[str, Any],
    context: Dict[str, Any] | None = None,
    labels: Dict[str, Any] | None = None,
    account_id: int | None = None,
) -> Dict[str, Any]:
    """
    Return a structured triage hint using DSPy when enabled.
    """
    model, model_id, dspy = _configure_dspy()
    label_config = labels or {}

    prompt_payload = _format_payload(payload, context)
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

    module = _load_compiled_module(dspy, model_id, account_id, labels=label_config) or build_decision_program(dspy, label_config)
    draft_enabled = _draft_reply_enabled(context, account_id)

    # Fetch KB context if draft reply is enabled
    kb_context_list = []
    kb_context_json = "[]"
    if draft_enabled:
        subject = payload.get("subject", "")
        body = payload.get("body") or payload.get("text") or ""
        kb_context_list = _fetch_kb_context(subject, body, account_id, limit=3)
        kb_context_json = json.dumps(kb_context_list)

    try:
        result = module(case_json=case_json, draft_enabled=draft_enabled, kb_context=kb_context_json)
    except Exception as exc:
        logging.getLogger(__name__).warning("DSPy decision program failed, falling back to simple triage: %s", exc)
        module = build_triage_module(dspy, label_config)
        result = module(content=prompt_payload)

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
        reply_text = _sanitize_reply(reply_text, account_id)
        reply_confidence = _compute_reply_confidence(result)
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
    heuristic_type, heuristic_automated, heuristic_reason = _detect_email_type(payload)
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
        if priority in {"P0", "P1"}:
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

    # Build AI reason
    ai_reason = escalation.get("reason") or route.get("rationale")
    if not ai_reason:
        if action_required is False:
            if email_type in NON_ACTIONABLE_EMAIL_TYPES:
                ai_reason = f"Auto-handled: {email_type.replace('_', ' ')} email"
            elif heuristic_reason:
                ai_reason = f"Auto-handled: {heuristic_reason}"
            else:
                ai_reason = "Auto-handled: low priority or informational"
        elif action_required == "optional":
            ai_reason = "Optional follow-up when capacity allows"
        else:
            ai_reason = "Action required: customer needs response"

    content = {
        "category": route.get("queue") or entities.get("intent") or email_type or "general",
        "priority": route.get("priority") or ("P4" if action_required is False else "P2"),
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
        "decision_outcome": _decision_outcome(action_required),
        "decision_trace": decision_trace,
        "reply_text": reply_text,
        "reply_confidence": reply_confidence,
        "reply_metadata": reply_metadata if reply_metadata else None,
        "entities_json": entities_json,
        "route_json": route_json,
        "workflow_json": workflow_json,
        "escalation_json": escalation_json,
    }
    return {
        "provider": "dspy",
        "model": model,
        "content": content,
        **content,
    }


def run_dspy_llm(user_input: str, context: Dict[str, Any] | None = None) -> Dict[str, Any]:
    payload = {"subject": "", "body": user_input, "from_email": "", "provider": "llm"}
    return run_dspy_triage(payload, context)
