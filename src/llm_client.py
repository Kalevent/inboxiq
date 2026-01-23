"""
Lightweight LLM client with primary OpenAI GPT-4o-mini and fallback to local Ollama (Llama 3.1).
"""
from __future__ import annotations

import os
import requests
from typing import Any, Dict, List

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


def invoke_llm(user_input: str, context: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """
    Try OpenAI first; fall back to Ollama local model on failure.
    """
    if DSPY_ENABLED:
        from src.dspy_triage import run_dspy_llm

        return run_dspy_llm(user_input, context)

    messages: List[Dict[str, str]] = [
        {
            "role": "system",
            "content": (
                "You are InboxIQ. Summarize and classify support emails (intent, priority, sentiment) and extract IDs. "
                "Respond concisely. If the user requests cancellation, mark sentiment as negative/concerned. "
                "If the message is praise or thanks, mark sentiment as positive."
            ),
        },
        {"role": "user", "content": user_input},
    ]
    if context:
        messages.append({"role": "system", "content": f"Context: {context}"})

    try:
        return call_openai(messages)
    except Exception as exc_openai:
        if not OLLAMA_ENABLED:
            raise RuntimeError(f"LLM invocation failed (OpenAI). OpenAI error: {exc_openai}")
        try:
            fallback = call_ollama(messages)
            fallback["warning"] = f"OpenAI failed: {exc_openai}"
            return fallback
        except Exception as exc_ollama:
            raise RuntimeError(f"LLM invocation failed (OpenAI and Ollama). OpenAI error: {exc_openai}; Ollama error: {exc_ollama}")
