"""
DSPy provider configuration.

Handles initialization of DSPy with OpenAI, Anthropic, or Gemini backends.
"""
from __future__ import annotations

import os
import logging
from typing import Any

logger = logging.getLogger(__name__)


def _env_bool(name: str, default: bool = False) -> bool:
    """Parse boolean from environment variable."""
    val = os.getenv(name)
    if val is None:
        return default
    return val.lower() in ("1", "true", "yes", "on")


def configure_dspy() -> tuple[str, str, Any]:
    """
    Configure DSPy with the appropriate LLM provider.

    Supports:
    - OpenAI (DSPY_PROVIDER=openai, requires OPENAI_API_KEY)
    - Anthropic (DSPY_PROVIDER=anthropic, requires ANTHROPIC_API_KEY)
    - Gemini (DSPY_PROVIDER=gemini, requires GEMINI_API_KEY)

    Returns:
        Tuple of (model_name, model_id, dspy_module)

    Raises:
        RuntimeError: If DSPy not installed or provider not configured
    """
    try:
        import dspy  # type: ignore
    except Exception as exc:  # pragma: no cover - depends on optional dep
        raise RuntimeError(
            "DSPy is not installed. Install with `pip install dspy-ai` and set DSPY_ENABLED=1."
        ) from exc

    model = os.getenv("DSPY_MODEL", "gpt-4o-mini")
    provider = os.getenv("DSPY_PROVIDER")

    # Auto-detect provider from legacy env vars if not explicitly set
    if not provider:
        if _env_bool("DSPY_USE_OPENAI", False) and os.getenv("OPENAI_API_KEY"):
            provider = "openai"
        elif _env_bool("DSPY_USE_ANTHROPIC", False) and os.getenv("ANTHROPIC_API_KEY"):
            provider = "anthropic"
        elif _env_bool("DSPY_USE_GEMINI", False) and os.getenv("GEMINI_API_KEY"):
            provider = "gemini"
        else:
            raise RuntimeError(
                "DSPy provider is required. Set DSPY_PROVIDER=openai|anthropic|gemini."
            )

    provider = provider.strip().lower()

    # Configure provider-specific backend
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
        raise RuntimeError(
            "DSPy backend not configured. Set DSPY_PROVIDER or "
            "DSPY_USE_OPENAI=1/DSPY_USE_ANTHROPIC=1/DSPY_USE_GEMINI=1."
        )

    # Configure DSPy settings if not already set
    if getattr(dspy.settings, "lm", None) is None:
        dspy.settings.configure(lm=lm)

    logger.info("DSPy configured with provider=%s model=%s", provider, model_id)

    return model, model_id, dspy


# Alias for backward compatibility
_configure_dspy = configure_dspy
