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


def _draft_reply_enabled(context: Dict[str, Any] | None) -> bool:
    if not _env_bool("DSPY_DRAFT_REPLY_ENABLED", False):
        return False
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
        """Classify inbound support content for triage."""

        content = dspy.InputField(desc="Inbound payload with subject, body, sender, source, and context.")
        category = dspy.OutputField(desc=_label_desc(label_config, "categories", "Provide a concise category label."))
        priority = dspy.OutputField(desc=_label_desc(label_config, "priorities", "Provide a priority label."))
        sentiment = dspy.OutputField(desc=_label_desc(label_config, "sentiments", "Provide a sentiment label."))
        intent = dspy.OutputField(desc=_label_desc(label_config, "intents", "Provide an intent label."))
        action_required = dspy.OutputField(desc=_label_desc(label_config, "action_required", "true|false|optional"))
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
        case_json = dspy.InputField(desc="JSON of normalized case payload.")
        entities_json = dspy.OutputField(desc="JSON with intent, sentiment, urgency, identifiers, and missing_info.")

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
        case_json = dspy.InputField()
        entities_json = dspy.InputField()
        route_json = dspy.InputField()
        workflow_json = dspy.InputField()
        escalation_json = dspy.OutputField(desc="JSON with decision, reason, required_role.")

    class DraftReplySig(dspy.Signature):
        case_json = dspy.InputField()
        entities_json = dspy.InputField()
        workflow_json = dspy.InputField()
        escalation_json = dspy.InputField()
        reply_text = dspy.OutputField(desc="Optional draft reply for a human to review. Keep concise.")

    class DecisionProgram(dspy.Module):
        def __init__(self) -> None:
            super().__init__()
            self.extract = dspy.ChainOfThought(ExtractEntitiesSig)
            self.route = dspy.Predict(RouteCaseSig)
            self.select = dspy.Predict(SelectWorkflowSig)
            self.escalate = dspy.Predict(EscalationDecisionSig)
            self.draft = dspy.ChainOfThought(DraftReplySig)

        def forward(self, case_json: str, draft_enabled: bool = False) -> Any:
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
    draft_enabled = _draft_reply_enabled(context)
    try:
        result = module(case_json=case_json, draft_enabled=draft_enabled)
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
    decision = escalation.get("decision")
    action_required: bool | str = True
    if decision in {"auto_resolve"}:
        action_required = False
    elif decision in {"ask_clarifying", "escalate_on_reply"}:
        action_required = "optional"
    else:
        # Fallback when escalation decision is missing: infer from route/priority.
        priority = (route.get("priority") or "").strip().upper()
        if priority in {"P0", "P1"}:
            action_required = True
        elif priority in {"P2"}:
            action_required = "optional"
        elif priority in {"P3", "P4"}:
            action_required = False
        else:
            action_required = "optional"

    content = {
        "category": route.get("queue") or entities.get("intent"),
        "priority": route.get("priority"),
        "sentiment": entities.get("sentiment"),
        "intent": entities.get("intent"),
        "action_required": action_required,
        "ai_reason": escalation.get("reason") or route.get("rationale"),
        "team": route.get("queue"),
        "assigned_to": escalation.get("required_role"),
        "owner": escalation.get("required_role"),
        "decision_type": "triage",
        "decision_outcome": _decision_outcome(action_required),
        "decision_trace": ["dspy:extract", "dspy:route", "dspy:workflow", "dspy:escalate"],
        "reply_text": reply_text,
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
