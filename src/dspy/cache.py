"""
DSPy compilation artifact caching with HMAC security.

This module handles loading and saving compiled DSPy modules with:
- HMAC-SHA256 signature verification to prevent tampering
- Strict file permissions (0o600 for files, 0o700 for directories)
- Audit logging of all artifact operations
- Path traversal protection
- Stale artifact detection via labels hash
"""
from __future__ import annotations

import os
import re
import json
import hmac
import hashlib
import logging
from datetime import datetime, timezone
from typing import Any, Dict

import dspy as _dspy_module

# Use cloudpickle for serializing dynamically-created DSPy classes
# (standard pickle can't serialize classes defined inside functions)
try:
    import cloudpickle as pickle
except ImportError:
    import pickle
    logger = logging.getLogger(__name__)
    logger.warning(
        "cloudpickle not installed - DSPy module serialization may fail for "
        "dynamically created classes. Install with: pip install cloudpickle"
    )

logger = logging.getLogger(__name__)


def _env_bool(name: str, default: bool = False) -> bool:
    """Parse boolean from environment variable."""
    val = os.getenv(name)
    if val is None:
        return default
    return val.lower() in ("1", "true", "yes", "on")


def _get_signing_key() -> bytes:
    """
    Get the secret key for HMAC signing.

    Tries DSPY_ARTIFACT_SECRET first, falls back to app SECRET_KEY.
    For maximum security, set a dedicated DSPY_ARTIFACT_SECRET.
    """
    secret = os.getenv("DSPY_ARTIFACT_SECRET")
    if not secret:
        # Fallback to Flask app SECRET_KEY
        secret = os.getenv("SECRET_KEY")

    if not secret:
        logger.warning(
            "No DSPY_ARTIFACT_SECRET or SECRET_KEY found. "
            "Artifact signing disabled. Set DSPY_ARTIFACT_SECRET for security."
        )
        return b""

    return secret.encode() if isinstance(secret, str) else secret


def _compute_signature(file_path: str) -> str:
    """
    Compute HMAC-SHA256 signature for a file.

    Args:
        file_path: Path to the file to sign

    Returns:
        Hex-encoded HMAC signature
    """
    key = _get_signing_key()
    if not key:
        return ""

    with open(file_path, "rb") as f:
        content = f.read()

    return hmac.new(key, content, hashlib.sha256).hexdigest()


def _verify_signature(file_path: str, expected_sig: str) -> bool:
    """
    Verify HMAC signature of a file.

    Args:
        file_path: Path to the file to verify
        expected_sig: Expected HMAC signature (hex-encoded)

    Returns:
        True if signature matches, False otherwise
    """
    if not expected_sig:
        return False

    actual_sig = _compute_signature(file_path)
    if not actual_sig:
        return False

    return hmac.compare_digest(actual_sig, expected_sig)


def _audit_log(operation: str, path: str, success: bool, details: dict):
    """
    Log artifact operations for security audit trail.

    Args:
        operation: Type of operation (load, save, verify_fail, etc.)
        path: File path involved
        success: Whether operation succeeded
        details: Additional context (model_id, account_id, etc.)
    """
    logger.info(
        "[AUDIT] DSPy artifact %s: %s | success=%s | %s",
        operation,
        path,
        success,
        details
    )


def _compiled_dir() -> str:
    """
    Get the compiled artifacts directory with path traversal protection.

    Returns:
        Absolute path to artifacts directory
    """
    base_dir = os.getenv("DSPY_COMPILED_DIR", ".dspy")

    # Resolve to absolute path
    abs_path = os.path.abspath(base_dir)

    # Ensure it's within project directory or explicitly allowed
    project_root = os.path.abspath(os.getcwd())
    if not abs_path.startswith(project_root):
        allowed_paths = os.getenv("DSPY_ALLOWED_DIRS", "").split(":")
        allowed_paths = [p.strip() for p in allowed_paths if p.strip()]

        if abs_path not in allowed_paths:
            logger.warning(
                "DSPY_COMPILED_DIR outside project: %s, using default .dspy",
                abs_path
            )
            abs_path = os.path.join(project_root, ".dspy")

    return abs_path


def _compiled_artifact_path(model_id: str, account_id: int | None = None) -> str:
    """
    Get path to compiled artifact file.

    Args:
        model_id: Model identifier (e.g., "gpt-4o-mini")
        account_id: Optional account ID for tenant-specific artifacts

    Returns:
        Absolute path to .pkl file
    """
    safe_key = re.sub(r"[^a-zA-Z0-9_.-]+", "_", model_id)
    if account_id is None:
        return os.path.join(_compiled_dir(), f"triage-{safe_key}.pkl")
    return os.path.join(_compiled_dir(), f"triage-{safe_key}-acct{account_id}.pkl")


def _compiled_meta_path(model_id: str, account_id: int | None = None) -> str:
    """
    Get path to artifact metadata file.

    Args:
        model_id: Model identifier
        account_id: Optional account ID for tenant-specific artifacts

    Returns:
        Absolute path to .meta.json file
    """
    safe_key = re.sub(r"[^a-zA-Z0-9_.-]+", "_", model_id)
    if account_id is None:
        return os.path.join(_compiled_dir(), f"triage-{safe_key}.meta.json")
    return os.path.join(_compiled_dir(), f"triage-{safe_key}-acct{account_id}.meta.json")


def _labels_hash(labels: Dict[str, Any] | None) -> str:
    """
    Compute hash of label configuration for stale detection.

    Args:
        labels: Label configuration dict

    Returns:
        Hash string
    """
    payload = labels or {}
    try:
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    except Exception:
        encoded = json.dumps(str(payload), sort_keys=True, separators=(",", ":"))
    return str(hash(encoded))


def _load_compiled_meta(model_id: str, account_id: int | None) -> Dict[str, Any] | None:
    """
    Load artifact metadata from JSON file.

    Args:
        model_id: Model identifier
        account_id: Optional account ID

    Returns:
        Metadata dict or None if not found/invalid
    """
    path = _compiled_meta_path(model_id, account_id)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except Exception as exc:
        logger.warning("Failed to load DSPy compiled metadata: %s", exc)
        return None


def _load_compiled_module(
    dspy: Any,
    model_id: str,
    account_id: int | None = None,
    labels: Dict[str, Any] | None = None,
) -> Any | None:
    """
    Load compiled DSPy module with security validation.

    Performs:
    1. File existence check
    2. Permission verification (warns if too permissive)
    3. Metadata loading
    4. HMAC signature verification
    5. Labels hash validation (stale detection)
    6. Safe unpickling

    Args:
        dspy: DSPy module reference
        model_id: Model identifier
        account_id: Optional account ID for tenant-specific artifacts
        labels: Current label configuration for stale detection

    Returns:
        Compiled DSPy module or None if not found/invalid
    """
    if not _env_bool("DSPY_COMPILED_ENABLED", True):
        return None

    path = _compiled_artifact_path(model_id, account_id)
    if not os.path.exists(path):
        return None

    # Security check: Verify file permissions
    try:
        stat_info = os.stat(path)
        if stat_info.st_mode & 0o077:  # World or group readable
            logger.warning(
                "Insecure permissions on %s: %s (should be 0o600)",
                path,
                oct(stat_info.st_mode)
            )
    except Exception as exc:
        logger.warning("Failed to check permissions on %s: %s", path, exc)

    # Load metadata
    meta = _load_compiled_meta(model_id, account_id)
    if not meta:
        logger.warning("Missing metadata for %s", path)
        # Allow load for backward compatibility (grace period)
        if not _env_bool("DSPY_REQUIRE_SIGNATURES", False):
            logger.info("Loading artifact without metadata (grace period)")
        else:
            _audit_log("load", path, False, {"reason": "missing_metadata"})
            return None

    # Security check: Verify HMAC signature
    if meta:
        expected_sig = meta.get("signature")
        if expected_sig:
            if not _verify_signature(path, expected_sig):
                logger.error(
                    "Signature verification FAILED for %s - possible tampering!",
                    path
                )
                _audit_log("verify_fail", path, False, {
                    "model_id": model_id,
                    "account_id": account_id,
                    "reason": "signature_mismatch"
                })
                return None
        elif _env_bool("DSPY_REQUIRE_SIGNATURES", False):
            logger.error("No signature in metadata for %s - rejecting", path)
            _audit_log("load", path, False, {
                "model_id": model_id,
                "account_id": account_id,
                "reason": "missing_signature"
            })
            return None
        else:
            # Grace period: allow artifacts without signatures
            logger.warning(
                "Loading artifact %s without signature (grace period). "
                "Set DSPY_REQUIRE_SIGNATURES=1 to enforce.",
                path
            )

    # Check labels hash for stale detection
    if labels and meta:
        expected = _labels_hash(labels)
        if meta.get("labels_hash") and meta.get("labels_hash") != expected:
            logger.warning(
                "DSPy compiled module stale: labels hash mismatch "
                "(model_id=%s account_id=%s expected=%s actual=%s)",
                model_id,
                account_id,
                expected,
                meta.get("labels_hash"),
            )
            _audit_log("load", path, False, {
                "model_id": model_id,
                "account_id": account_id,
                "reason": "stale_labels"
            })
            return None

    # DSPy library version check (warn-only, do not block)
    if meta:
        current_dspy_version = getattr(_dspy_module, "__version__", None)
        artifact_dspy_version = meta.get("dspy_version")
        if artifact_dspy_version is None:
            logger.info(
                "DSPy artifact %s predates dspy_version tracking; "
                "current dspy=%s",
                path,
                current_dspy_version,
            )
        elif artifact_dspy_version != current_dspy_version:
            logger.warning(
                "DSPy version mismatch for artifact %s: "
                "compiled with dspy=%s, loading under dspy=%s "
                "(possible prompt/signature drift)",
                path,
                artifact_dspy_version,
                current_dspy_version,
            )

    # Load module
    try:
        if hasattr(dspy, "load"):
            module = dspy.load(path)
        else:
            with open(path, "rb") as handle:
                module = pickle.load(handle)

        _audit_log("load", path, True, {
            "model_id": model_id,
            "account_id": account_id
        })
        return module
    except Exception as exc:
        logger.warning("Failed to load DSPy compiled module: %s", exc)
        _audit_log("load", path, False, {
            "model_id": model_id,
            "account_id": account_id,
            "error": str(exc)
        })
        return None


def _save_compiled_module(
    dspy: Any,
    module: Any,
    model_id: str,
    account_id: int | None = None,
    labels: Dict[str, Any] | None = None,
    extra_meta: Dict[str, Any] | None = None,
) -> str:
    """
    Save compiled DSPy module with security hardening.

    Performs:
    1. Create directory with strict permissions (0o700)
    2. Save pickle file
    3. Set file permissions to 0o600 (owner read/write only)
    4. Compute HMAC signature
    5. Save metadata with signature
    6. Set metadata permissions to 0o600

    Args:
        dspy: DSPy module reference
        module: Compiled DSPy module to save
        model_id: Model identifier
        account_id: Optional account ID for tenant-specific artifacts
        labels: Label configuration for hash computation
        extra_meta: Additional metadata (accuracy, sample counts, etc.)

    Returns:
        Path to saved artifact
    """
    path = _compiled_artifact_path(model_id, account_id)

    # Create parent directory with strict permissions
    parent_dir = os.path.dirname(path)
    os.makedirs(parent_dir, mode=0o700, exist_ok=True)

    # Force directory permissions even if it already exists
    try:
        os.chmod(parent_dir, 0o700)
    except Exception as exc:
        logger.warning("Failed to set directory permissions: %s", exc)

    # Save pickle file
    if hasattr(dspy, "save"):
        dspy.save(module, path)
    else:
        with open(path, "wb") as handle:
            pickle.dump(module, handle)

    # Set strict file permissions
    try:
        os.chmod(path, 0o600)
    except Exception as exc:
        logger.warning("Failed to set artifact permissions: %s", exc)

    # Compute signature
    signature = _compute_signature(path)

    # Save metadata
    meta_path = _compiled_meta_path(model_id, account_id)
    meta = {
        "model_id": model_id,
        "account_id": account_id,
        "labels_hash": _labels_hash(labels),
        "version": "v1",
        "dspy_version": getattr(_dspy_module, "__version__", None),
        "compiled_at": datetime.now(timezone.utc).isoformat(),
        "signature": signature,
        "signature_algorithm": "hmac-sha256",
    }
    if extra_meta:
        meta.update(extra_meta)

    try:
        with open(meta_path, "w", encoding="utf-8") as handle:
            json.dump(meta, handle, indent=2)

        # Set strict permissions on metadata
        os.chmod(meta_path, 0o600)
    except Exception as exc:
        logger.warning("Failed to write DSPy compiled metadata: %s", exc)

    # Audit log
    _audit_log("save", path, True, {
        "model_id": model_id,
        "account_id": account_id,
        "has_signature": bool(signature)
    })

    return path


# Public API for external use
def load_compiled_module(
    dspy: Any,
    model_id: str,
    account_id: int | None = None,
    labels: Dict[str, Any] | None = None,
) -> Any | None:
    """Public wrapper for _load_compiled_module."""
    return _load_compiled_module(dspy, model_id, account_id, labels)


def save_compiled_module(
    dspy: Any,
    module: Any,
    model_id: str,
    account_id: int | None = None,
    labels: Dict[str, Any] | None = None,
    extra_meta: Dict[str, Any] | None = None,
) -> str:
    """Public wrapper for _save_compiled_module."""
    return _save_compiled_module(dspy, module, model_id, account_id, labels, extra_meta)


def compiled_artifact_path(model_id: str, account_id: int | None = None) -> str:
    """Public wrapper for _compiled_artifact_path."""
    return _compiled_artifact_path(model_id, account_id)
