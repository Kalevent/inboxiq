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
    module = _load_compiled_module(dspy, model_id, account_id, labels=label_config) or build_triage_module(dspy, label_config)
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
