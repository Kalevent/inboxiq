"""
DEPRECATED: This module has been refactored into src/dspy/.

All functionality has been moved to the src/dspy package with improved:
- Security (HMAC signing of compiled artifacts)
- Organization (modular structure)
- Maintainability (smaller, focused files)

Imports are re-exported here for backward compatibility.
Update your imports to use `from src.dspy import ...` instead.

This shim will be removed in a future version.
"""
from __future__ import annotations

import warnings

# Issue deprecation warning
warnings.warn(
    "src.dspy_triage is deprecated and will be removed in a future version. "
    "Use 'from src.dspy import ...' instead.",
    DeprecationWarning,
    stacklevel=2,
)

# Re-export public API for backward compatibility
from src.dspy import (
    # Main entry points
    configure_dspy,
    run_dspy_triage,
    run_dspy_llm,
    # Module builders
    build_triage_module,
    build_decision_program,
    # Artifact management
    load_compiled_module,
    save_compiled_module,
    compiled_artifact_path,
    # Formatting
    format_payload,
    label_desc,
    decision_outcome,
    # Email detection
    detect_email_type,
    NON_ACTIONABLE_EMAIL_TYPES,
    # Draft reply
    draft_reply_enabled,
    fetch_kb_context,
    sanitize_reply,
    compute_reply_confidence,
)

# Re-export private functions (underscore prefix) for backward compatibility
from src.dspy import (
    _configure_dspy,
    _load_compiled_module,
    _save_compiled_module,
    _compiled_artifact_path,
    _compiled_dir,
    _labels_hash,
    _load_compiled_meta,
    _format_payload,
    _label_desc,
    _decision_outcome,
    _detect_email_type,
    _draft_reply_enabled,
    _fetch_kb_context,
    _sanitize_reply,
    _compute_reply_confidence,
)

# Re-export constants
from src.dspy.email_detection import (
    AUTOMATED_SENDER_PATTERNS,
    SPAM_SUBJECT_PATTERNS,
    MARKETING_SUBJECT_PATTERNS,
    AUTO_REPLY_SUBJECT_PATTERNS,
)

# For type annotations
from src.dspy.cache import _load_compiled_meta, _env_bool

__all__ = [
    # Main functions
    "configure_dspy",
    "run_dspy_triage",
    "run_dspy_llm",
    "build_triage_module",
    "build_decision_program",
    # Public wrappers
    "load_compiled_module",
    "save_compiled_module",
    "compiled_artifact_path",
    "format_payload",
    "label_desc",
    "decision_outcome",
    "detect_email_type",
    "draft_reply_enabled",
    "fetch_kb_context",
    "sanitize_reply",
    "compute_reply_confidence",
    # Private functions
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
    "_env_bool",
    # Constants
    "NON_ACTIONABLE_EMAIL_TYPES",
    "AUTOMATED_SENDER_PATTERNS",
    "SPAM_SUBJECT_PATTERNS",
    "MARKETING_SUBJECT_PATTERNS",
    "AUTO_REPLY_SUBJECT_PATTERNS",
]
