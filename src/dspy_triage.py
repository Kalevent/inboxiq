"""
DSPy integration scaffolding for InboxIQ triage.
"""
from __future__ import annotations

import os
from typing import Any, Dict


def _env_bool(name: str, default: bool = False) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.lower() in ("1", "true", "yes", "on")


def _configure_dspy() -> tuple[str, Any]:
    try:
        import dspy  # type: ignore
    except Exception as exc:  # pragma: no cover - depends on optional dep
        raise RuntimeError(
            "DSPy is not installed. Install with `pip install dspy-ai` and set DSPY_ENABLED=1."
        ) from exc

    model = os.getenv("DSPY_MODEL", "gpt-4o-mini")
    if _env_bool("DSPY_USE_OPENAI", True):
        try:
            model_id = model if "/" in model else f"openai/{model}"
            lm = dspy.LM(model=model_id, max_tokens=300, temperature=0.2)
        except Exception as exc:
            raise RuntimeError("Failed to configure DSPy OpenAI backend.") from exc
    else:
        raise RuntimeError("DSPy backend not configured. Set DSPY_USE_OPENAI=1 or add another backend.")

    if getattr(dspy.settings, "lm", None) is None:
        dspy.settings.configure(lm=lm)
    return model, dspy


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


def run_dspy_triage(payload: Dict[str, Any], context: Dict[str, Any] | None = None, labels: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """
    Return a structured triage hint using DSPy when enabled.
    """
    model, dspy = _configure_dspy()
    label_config = labels or {}

    prompt_payload = _format_payload(payload, context)
    module = build_triage_module(dspy, label_config)
    result = module(content=prompt_payload)

    content = {
        "category": getattr(result, "category", None),
        "priority": getattr(result, "priority", None),
        "sentiment": getattr(result, "sentiment", None),
        "intent": getattr(result, "intent", None),
        "action_required": getattr(result, "action_required", None),
        "ai_reason": getattr(result, "ai_reason", None),
        "team": getattr(result, "team", None),
        "assigned_to": getattr(result, "assigned_to", None),
        "owner": getattr(result, "owner", None),
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
