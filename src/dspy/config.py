"""
DSPy provider configuration.

Handles initialization of DSPy with multiple LLM backends.

Supported providers:
- OpenAI (DSPY_PROVIDER=openai, requires OPENAI_API_KEY)
- Anthropic (DSPY_PROVIDER=anthropic, requires ANTHROPIC_API_KEY)
- Gemini (DSPY_PROVIDER=gemini, requires GEMINI_API_KEY)
- Ollama (DSPY_PROVIDER=ollama, requires OLLAMA_BASE_URL)

Training data (manual overrides) is model-agnostic. Compiled artifacts are
model-specific but can be recompiled for any model using the same training data.
"""
from __future__ import annotations

import os
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Supported providers and their required env vars
SUPPORTED_PROVIDERS = {
    "openai": {"api_key": "OPENAI_API_KEY", "prefix": "openai"},
    "anthropic": {"api_key": "ANTHROPIC_API_KEY", "prefix": "anthropic"},
    "gemini": {"api_key": "GEMINI_API_KEY", "prefix": "google"},
    "google": {"api_key": "GEMINI_API_KEY", "prefix": "google"},
    "ollama": {"api_key": None, "prefix": "ollama", "base_url": "OLLAMA_BASE_URL"},
}

# Default models per provider (used when DSPY_MODEL not set)
DEFAULT_MODELS = {
    "openai": "gpt-4o-mini",
    "anthropic": "claude-3-haiku-20240307",
    "gemini": "gemini-1.5-flash",
    "google": "gemini-1.5-flash",
    "ollama": "llama3.2",
}


def _env_bool(name: str, default: bool = False) -> bool:
    """Parse boolean from environment variable."""
    val = os.getenv(name)
    if val is None:
        return default
    return val.lower() in ("1", "true", "yes", "on")


def get_current_model_id() -> Optional[str]:
    """
    Get the current model ID without fully configuring DSPy.

    Useful for checking if training exists for the current model.

    Returns:
        Model ID string (e.g., "openai/gpt-4o-mini") or None if not configured
    """
    provider = os.getenv("DSPY_PROVIDER", "").strip().lower()
    if not provider:
        # Try auto-detect
        if os.getenv("OPENAI_API_KEY"):
            provider = "openai"
        elif os.getenv("ANTHROPIC_API_KEY"):
            provider = "anthropic"
        elif os.getenv("GEMINI_API_KEY"):
            provider = "gemini"
        elif os.getenv("OLLAMA_BASE_URL"):
            provider = "ollama"
        else:
            return None

    model = os.getenv("DSPY_MODEL") or DEFAULT_MODELS.get(provider, "gpt-4o-mini")
    prefix = SUPPORTED_PROVIDERS.get(provider, {}).get("prefix", provider)

    if "/" in model:
        return model
    return f"{prefix}/{model}"


def get_provider_chain() -> list[tuple[str, Optional[str]]]:
    """
    Returns [(provider, model_or_None), ...] to try in order.

    Primary comes from DSPY_PROVIDER + DSPY_MODEL.
    Fallbacks from DSPY_FALLBACK_PROVIDERS — supports explicit model pinning:
      DSPY_FALLBACK_PROVIDERS=anthropic:claude-haiku-4-5-20251001,gemini
    Only includes providers whose API key is present.
    """
    primary = os.getenv("DSPY_PROVIDER", "").strip().lower()
    if not primary:
        for p in ("openai", "anthropic", "gemini", "ollama"):
            cfg = SUPPORTED_PROVIDERS[p]
            key = cfg.get("api_key")
            if (key and os.getenv(key)) or (p == "ollama" and os.getenv("OLLAMA_BASE_URL")):
                primary = p
                break
    primary_model = os.getenv("DSPY_MODEL", "").strip() or None

    fallback_str = os.getenv("DSPY_FALLBACK_PROVIDERS", "").strip()
    fallbacks: list[tuple[str, Optional[str]]] = []
    for entry in (fallback_str.split(",") if fallback_str else []):
        entry = entry.strip()
        if ":" in entry:
            p, m = entry.split(":", 1)
            fallbacks.append((p.strip().lower(), m.strip() or None))
        else:
            fallbacks.append((entry.lower(), None))

    def _has_credentials(p: str) -> bool:
        cfg = SUPPORTED_PROVIDERS.get(p, {})
        key = cfg.get("api_key")
        if p == "ollama":
            return bool(os.getenv("OLLAMA_BASE_URL"))
        return bool(key and os.getenv(key))

    chain = [(primary, primary_model)] + [(p, m) for p, m in fallbacks if p != primary]
    return [(p, m) for p, m in chain if p and p in SUPPORTED_PROVIDERS and _has_credentials(p)]


def configure_dspy(
    byol_config: Optional[Dict[str, Any]] = None,
    max_tokens: int = 300,
    temperature: float = 0.2,
    provider: Optional[str] = None,
    model: Optional[str] = None,
) -> tuple[str, str, Any]:
    """
    Configure DSPy with the appropriate LLM provider.

    Args:
        byol_config: Optional per-account BYOL config dict with keys
                     provider, base_url, model, api_key.  When provided,
                     overrides all env-var-based provider selection.
        max_tokens: Token limit for LM responses. Default 300 suits triage/classification.
                    Pass higher values for content generation (e.g. max_tokens=2000).
        temperature: Sampling temperature. Default 0.2 suits deterministic tasks.

    The system is model-agnostic for training data:
    - Manual overrides (training examples) are stored in the database
    - Compiled artifacts are model-specific but recompilable
    - Switching models just requires running training again

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

    # --- BYOL override: use account's own LLM endpoint ---
    if byol_config:
        return _configure_dspy_byol(dspy, byol_config)

    if provider is None:
        provider = os.getenv("DSPY_PROVIDER", "").strip().lower()

    # Auto-detect provider from legacy env vars or API keys if not explicitly set
    if not provider:
        if _env_bool("DSPY_USE_OPENAI", False) and os.getenv("OPENAI_API_KEY"):
            provider = "openai"
        elif _env_bool("DSPY_USE_ANTHROPIC", False) and os.getenv("ANTHROPIC_API_KEY"):
            provider = "anthropic"
        elif _env_bool("DSPY_USE_GEMINI", False) and os.getenv("GEMINI_API_KEY"):
            provider = "gemini"
        elif os.getenv("OLLAMA_BASE_URL"):
            provider = "ollama"
        elif os.getenv("OPENAI_API_KEY"):
            provider = "openai"
        else:
            raise RuntimeError(
                "DSPy provider is required. Set DSPY_PROVIDER=openai|anthropic|gemini|ollama."
            )

    if provider not in SUPPORTED_PROVIDERS:
        raise RuntimeError(
            f"Unknown DSPy provider: {provider}. "
            f"Supported: {', '.join(SUPPORTED_PROVIDERS.keys())}"
        )

    # Get model (use provider default if not specified)
    if model is None:
        model = os.getenv("DSPY_MODEL") or DEFAULT_MODELS.get(provider, "gpt-4o-mini")
    provider_config = SUPPORTED_PROVIDERS[provider]
    prefix = provider_config["prefix"]

    # Configure provider-specific backend
    if provider == "openai":
        if not os.getenv("OPENAI_API_KEY"):
            raise RuntimeError("OPENAI_API_KEY is required for DSPy OpenAI provider.")
        try:
            model_id = model if "/" in model else f"{prefix}/{model}"
            lm = dspy.LM(model=model_id, max_tokens=max_tokens, temperature=temperature)
        except Exception as exc:
            raise RuntimeError(f"Failed to configure DSPy OpenAI backend: {exc}") from exc

    elif provider == "anthropic":
        if not os.getenv("ANTHROPIC_API_KEY"):
            raise RuntimeError("ANTHROPIC_API_KEY is required for DSPy Anthropic provider.")
        try:
            model_id = model if "/" in model else f"{prefix}/{model}"
            lm = dspy.LM(model=model_id, max_tokens=max_tokens, temperature=temperature)
        except Exception as exc:
            raise RuntimeError(f"Failed to configure DSPy Anthropic backend: {exc}") from exc

    elif provider in {"gemini", "google"}:
        if not os.getenv("GEMINI_API_KEY"):
            raise RuntimeError("GEMINI_API_KEY is required for DSPy Gemini provider.")
        try:
            model_id = model if "/" in model else f"{prefix}/{model}"
            lm = dspy.LM(model=model_id, max_tokens=max_tokens, temperature=temperature)
        except Exception as exc:
            raise RuntimeError(f"Failed to configure DSPy Gemini backend: {exc}") from exc

    elif provider == "ollama":
        base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        try:
            model_id = model if "/" in model else f"{prefix}/{model}"
            lm = dspy.LM(
                model=model_id,
                api_base=f"{base_url}/v1",
                api_key="ollama",
                max_tokens=max_tokens,
                temperature=temperature,
            )
        except Exception as exc:
            raise RuntimeError(f"Failed to configure DSPy Ollama backend: {exc}") from exc

    else:
        raise RuntimeError(
            f"DSPy backend not configured for provider: {provider}. "
            "Set DSPY_PROVIDER or appropriate API keys."
        )

    dspy.settings.configure(lm=lm)

    logger.info("DSPy configured with provider=%s model=%s", provider, model_id)

    return model, model_id, dspy


def _configure_dspy_byol(dspy: Any, byol_config: Dict[str, Any]) -> tuple[str, str, Any]:
    """Configure DSPy using a customer's own LLM endpoint."""

    provider = byol_config["provider"]
    model = byol_config["model"]
    base_url = (byol_config.get("base_url") or "").rstrip("/")
    api_key = byol_config.get("api_key")

    try:
        if provider == "anthropic":
            model_id = model if "/" in model else f"anthropic/{model}"
            lm = dspy.LM(model=model_id, api_key=api_key, max_tokens=300, temperature=0.2)

        elif provider == "openai":
            model_id = model if "/" in model else f"openai/{model}"
            lm = dspy.LM(model=model_id, api_key=api_key, max_tokens=300, temperature=0.2)

        else:
            # ollama or openai_compatible — OpenAI-compatible wire format
            if not base_url:
                raise ValueError(f"provider={provider} requires a base_url")
            model_id = model if "/" in model else f"openai/{model}"
            lm = dspy.LM(
                model=model_id,
                api_base=f"{base_url}/v1" if not base_url.endswith("/v1") else base_url,
                api_key=api_key or "byol",
                max_tokens=300,
                temperature=0.2,
            )
    except Exception as exc:
        raise RuntimeError(f"Failed to configure DSPy BYOL backend ({provider}): {exc}") from exc

    dspy.settings.configure(lm=lm)
    logger.info("DSPy configured with BYOL provider=%s model=%s", provider, model_id)
    return model, model_id, dspy


def check_training_status(account_id: Optional[int] = None) -> dict:
    """
    Check if the current model has trained artifacts.

    Useful for showing warnings in UI when model changed but not retrained.

    Args:
        account_id: Account ID to check training for

    Returns:
        Dict with:
        - current_model: Current configured model ID
        - has_training: Whether compiled artifact exists
        - training_data_count: Number of manual overrides available
        - last_trained_model: Model ID of most recent training (if any)
    """
    from src.dspy.cache import _compiled_artifact_path
    from src.models import Ticket, DspyTrainingMetric

    current_model = get_current_model_id()
    result = {
        "current_model": current_model,
        "has_training": False,
        "training_data_count": 0,
        "last_trained_model": None,
        "last_trained_at": None,
        "needs_retraining": False,
    }

    if not current_model:
        return result

    # Check if artifact exists for current model
    artifact_path = _compiled_artifact_path(current_model, account_id)
    result["has_training"] = os.path.exists(artifact_path)

    # Count available training data (model-agnostic)
    query = Ticket.query.filter(Ticket.manual_override.is_(True))
    if account_id is not None:
        query = query.filter(Ticket.account_id == account_id)
    result["training_data_count"] = query.count()

    # Get most recent training metrics
    metrics_query = DspyTrainingMetric.query
    if account_id is not None:
        metrics_query = metrics_query.filter(DspyTrainingMetric.account_id == account_id)
    latest_metric = metrics_query.order_by(DspyTrainingMetric.created_at.desc()).first()

    if latest_metric:
        result["last_trained_model"] = latest_metric.model_id
        result["last_trained_at"] = latest_metric.created_at.isoformat() if latest_metric.created_at else None
        # Check if current model differs from last trained
        if latest_metric.model_id != current_model:
            result["needs_retraining"] = True

    # If we have training data but no artifact, suggest training
    if result["training_data_count"] > 0 and not result["has_training"]:
        result["needs_retraining"] = True

    return result


# Alias for backward compatibility
_configure_dspy = configure_dspy
