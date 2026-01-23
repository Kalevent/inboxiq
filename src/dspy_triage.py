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
            lm = dspy.OpenAI(model=model, max_tokens=300)
        except Exception as exc:
            raise RuntimeError("Failed to configure DSPy OpenAI backend.") from exc
    else:
        raise RuntimeError("DSPy backend not configured. Set DSPY_USE_OPENAI=1 or add another backend.")

    if getattr(dspy.settings, "lm", None) is None:
        dspy.settings.configure(lm=lm)
    return model, dspy


def run_dspy_llm(user_input: str, context: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """
    Return a structured triage hint using DSPy when enabled.
    """
    model, dspy = _configure_dspy()

    class TriageSignature(dspy.Signature):
        """Classify the email for support triage."""

        email = dspy.InputField(desc="Email subject and body content.")
        category = dspy.OutputField(desc="billing|bug|refund|general|other")
        priority = dspy.OutputField(desc="P0|P1|P2|P3")
        sentiment = dspy.OutputField(desc="positive|neutral|negative")
        intent = dspy.OutputField(desc="billing|incident|bug|feature|how_to|general")
        action_required = dspy.OutputField(desc="true|false|optional")
        ai_reason = dspy.OutputField(desc="Short reason for the decision.")

    class TriageModule(dspy.Module):
        def __init__(self) -> None:
            super().__init__()
            self.predict = dspy.Predict(TriageSignature)

        def forward(self, email: str) -> Any:
            return self.predict(email=email)

    payload = user_input
    if context:
        payload = f"{user_input}\n\nContext:\n{context}"

    module = TriageModule()
    result = module(email=payload)

    content = {
        "category": getattr(result, "category", None),
        "priority": getattr(result, "priority", None),
        "sentiment": getattr(result, "sentiment", None),
        "intent": getattr(result, "intent", None),
        "action_required": getattr(result, "action_required", None),
        "ai_reason": getattr(result, "ai_reason", None),
    }
    return {
        "provider": "dspy",
        "model": model,
        "content": content,
        **content,
    }
