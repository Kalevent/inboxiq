"""
DSPy integration for InboxIQ triage and reasoning.

This package provides AI-powered triage and decision-making using DSPy
with support for multiple LLM providers (OpenAI, Anthropic, Gemini).

Main entry points:
- run_dspy_triage: Full triage pipeline with decision logic
- run_dspy_llm: Lightweight LLM interaction wrapper
- configure_dspy: Initialize DSPy provider

Compiled artifact management:
- load_compiled_module: Load cached compiled modules
- save_compiled_module: Save compiled modules with HMAC signing
- compiled_artifact_path: Get path to artifact file

Utilities:
- build_triage_module: Build simple triage module
- build_decision_program: Build complex decision program
- format_payload: Format email payload for prompts
- detect_email_type: Heuristic email classification
- NON_ACTIONABLE_EMAIL_TYPES: Set of auto-handled email types
"""
from __future__ import annotations

# Public API - maintain backward compatibility
from src.dspy.config import configure_dspy, _configure_dspy
from src.dspy.triage import run_dspy_triage, run_dspy_llm
from src.dspy.signatures import build_triage_module, build_decision_program
from src.dspy.cache import (
    load_compiled_module,
    save_compiled_module,
    compiled_artifact_path,
    _load_compiled_module,
    _save_compiled_module,
    _compiled_artifact_path,
    _compiled_dir,
    _labels_hash,
    _load_compiled_meta,
)
from src.dspy.formatting import (
    format_payload,
    label_desc,
    decision_outcome,
    _format_payload,
    _label_desc,
    _decision_outcome,
)
from src.dspy.email_detection import (
    detect_email_type,
    NON_ACTIONABLE_EMAIL_TYPES,
    _detect_email_type,
)
from src.dspy.draft_reply import (
    draft_reply_enabled,
    fetch_kb_context,
    sanitize_reply,
    compute_reply_confidence,
    _draft_reply_enabled,
    _fetch_kb_context,
    _sanitize_reply,
    _compute_reply_confidence,
)

__all__ = [
    # Main entry points
    "configure_dspy",
    "run_dspy_triage",
    "run_dspy_llm",
    # Module builders
    "build_triage_module",
    "build_decision_program",
    # Artifact management
    "load_compiled_module",
    "save_compiled_module",
    "compiled_artifact_path",
    # Formatting
    "format_payload",
    "label_desc",
    "decision_outcome",
    # Email detection
    "detect_email_type",
    "NON_ACTIONABLE_EMAIL_TYPES",
    # Draft reply
    "draft_reply_enabled",
    "fetch_kb_context",
    "sanitize_reply",
    "compute_reply_confidence",
    # Private functions (for backward compat)
    "_configure_dspy",
    "_load_compiled_module",
    "_save_compiled_module",
    "_compiled_artifact_path",
    "_compiled_dir",
    "_labels_hash",
    "_load_compiled_meta",
    "_format_payload",
    "_label_desc",
    "_decision_outcome",
    "_detect_email_type",
    "_draft_reply_enabled",
    "_fetch_kb_context",
    "_sanitize_reply",
    "_compute_reply_confidence",
]

__version__ = "2.0.0"
