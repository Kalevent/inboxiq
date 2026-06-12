"""
Lightweight LLM client with primary OpenAI GPT-4o-mini and fallback to local Ollama (Llama 3.1).

Per-account BYOL (Bring Your Own LLM):
  Call resolve_llm_config(account_id) to get an account's custom LLM settings.
  Pass the result to invoke_llm() or call_byol() to route to the customer's endpoint.
"""
from __future__ import annotations

import logging
import os
import requests
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _env_bool(name: str, default: bool = False) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.lower() in ("1", "true", "yes", "on")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1")
OLLAMA_ENABLED = _env_bool("OLLAMA_ENABLED", False)
DSPY_ENABLED = _env_bool("DSPY_ENABLED", False)
HTTP_TIMEOUT = float(os.getenv("LLM_HTTP_TIMEOUT", "15"))


def _chat_payload(model: str, messages: List[Dict[str, str]], max_tokens: int = 300, temperature: float = 0.2) -> Dict[str, Any]:
    return {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }


def resolve_llm_config(account_id: int) -> Optional[Dict[str, Any]]:
    """
    Look up a per-account LLM config from AccountLLMConfig.

    Returns a dict with keys: provider, base_url, model, api_key (decrypted), enabled
    Returns None if no custom config exists or it is disabled.
    """
    try:
        from src.models.core import AccountLLMConfig
        from src.crypto import decrypt_value

        config = AccountLLMConfig.query.filter_by(account_id=account_id, enabled=True).first()
        if config is None:
            return None

        api_key: Optional[str] = None
        if config.api_key_enc:
            api_key = decrypt_value(config.api_key_enc)

        return {
            "provider": config.provider,
            "base_url": config.base_url,
            "model": config.model,
            "api_key": api_key,
        }
    except Exception as exc:
        logger.warning("resolve_llm_config failed for account %s: %s", account_id, exc)
        return None


def call_byol(
    messages: List[Dict[str, str]],
    config: Dict[str, Any],
    max_tokens: int = 300,
) -> Dict[str, Any]:
    """
    Call a customer-supplied LLM endpoint.

    Supports openai, openai_compatible, and ollama via the OpenAI-compatible
    /chat/completions wire format.  Anthropic uses its own Messages API.
    """
    provider = config["provider"]
    model = config["model"]
    api_key = config.get("api_key")
    base_url = config.get("base_url", "").rstrip("/") if config.get("base_url") else ""

    if provider == "anthropic":
        return _call_anthropic_byol(messages, model, api_key, max_tokens)

    # openai / ollama / openai_compatible — all use OpenAI-compatible chat completions
    if provider == "openai":
        base_url = "https://api.openai.com/v1"
    elif provider == "ollama" and not base_url:
        raise ValueError("Ollama requires a base_url (e.g. https://your-server:11434/v1)")

    # Ensure base_url ends with /v1 for openai_compatible if not already
    if provider == "openai_compatible" and not base_url:
        raise ValueError("openai_compatible provider requires a base_url")

    url = f"{base_url}/chat/completions"
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    elif provider == "ollama":
        headers["Authorization"] = "Bearer ollama"

    payload = _chat_payload(model, messages, max_tokens=max_tokens)
    resp = requests.post(url, json=payload, headers=headers, timeout=HTTP_TIMEOUT)
    resp.raise_for_status()
    data = resp.json()
    choice = (data.get("choices") or [{}])[0]
    content = (choice.get("message") or {}).get("content", "")
    return {"provider": provider, "model": model, "content": content, "raw": data, "byol": True}


def _call_anthropic_byol(
    messages: List[Dict[str, str]],
    model: str,
    api_key: Optional[str],
    max_tokens: int,
) -> Dict[str, Any]:
    """Call Anthropic Messages API with customer's API key."""
    if not api_key:
        raise ValueError("Anthropic provider requires an API key")

    # Separate system messages from conversation messages
    system_parts = [m["content"] for m in messages if m["role"] == "system"]
    conversation = [m for m in messages if m["role"] != "system"]

    payload: Dict[str, Any] = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": conversation,
    }
    if system_parts:
        payload["system"] = "\n".join(system_parts)

    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
    }
    resp = requests.post(
        "https://api.anthropic.com/v1/messages",
        json=payload,
        headers=headers,
        timeout=HTTP_TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json()
    content = (data.get("content") or [{}])[0].get("text", "")
    return {"provider": "anthropic", "model": model, "content": content, "raw": data, "byol": True}


def call_openai(messages: List[Dict[str, str]], max_tokens: int = 300) -> Dict[str, Any]:
    if not OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY not configured")
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = _chat_payload(OPENAI_MODEL, messages, max_tokens=max_tokens)
    resp = requests.post(
        "https://api.openai.com/v1/chat/completions",
        json=payload,
        headers=headers,
        timeout=HTTP_TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json()
    choice = (data.get("choices") or [{}])[0]
    content = (choice.get("message") or {}).get("content", "")
    return {"provider": "openai", "model": OPENAI_MODEL, "content": content, "raw": data}


def call_ollama(messages: List[Dict[str, str]], max_tokens: int = 300) -> Dict[str, Any]:
    if not OLLAMA_ENABLED:
        raise RuntimeError("Ollama disabled")
    url = f"{OLLAMA_BASE_URL.rstrip('/')}/chat/completions"
    payload = _chat_payload(OLLAMA_MODEL, messages, max_tokens=max_tokens)
    resp = requests.post(url, json=payload, timeout=HTTP_TIMEOUT)
    resp.raise_for_status()
    data = resp.json()
    choice = (data.get("choices") or [{}])[0]
    content = (choice.get("message") or {}).get("content", "")
    return {"provider": "ollama", "model": OLLAMA_MODEL, "content": content, "raw": data}


def invoke_llm(
    user_input: str,
    context: Dict[str, Any] | None = None,
    account_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Invoke the LLM for the given account.

    Priority:
    1. If account has a BYOL config (AccountLLMConfig), route to their endpoint.
    2. Use DSPy EmailSummarizer (respects DSPY_PROVIDER / DSPY_MODEL).
    3. Fall back to Ollama if enabled.
    """
    import json as _json
    from src.dspy.config import _configure_dspy
    from src.dspy.signatures import build_email_summarizer

    # 1. BYOL — route to customer's own LLM endpoint
    if account_id is not None:
        byol_config = resolve_llm_config(account_id)
        if byol_config:
            # BYOL still needs raw messages; keep the call_byol path
            messages: List[Dict[str, str]] = [
                {"role": "user", "content": user_input},
            ]
            if context:
                messages.append({"role": "system", "content": f"Context: {context}"})
            return call_byol(messages, byol_config)

    # 2. DSPy path (default)
    try:
        _, _, dspy = _configure_dspy()
        summarizer = build_email_summarizer(dspy)
        result = summarizer(
            email_content=user_input,
            context=_json.dumps(context) if context else "{}",
        )
        return {
            "provider": "dspy",
            "content": result.summary_json,
        }
    except Exception as exc_dspy:
        logger.warning("DSPy invoke_llm failed: %s", exc_dspy)
        if not OLLAMA_ENABLED:
            raise RuntimeError(f"LLM invocation failed: {exc_dspy}") from exc_dspy

    # 3. Ollama fallback
    messages = [{"role": "user", "content": user_input}]
    if context:
        messages.append({"role": "system", "content": f"Context: {context}"})
    try:
        fallback = call_ollama(messages)
        fallback["warning"] = "DSPy failed, used Ollama"
        return fallback
    except Exception as exc_ollama:
        raise RuntimeError(f"LLM invocation failed (DSPy and Ollama): {exc_ollama}") from exc_ollama
