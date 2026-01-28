"""
InboxIQ encryption helpers.
No dependency on legacy/other app code.
"""
from __future__ import annotations

import base64
import hashlib
import os
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

_PREFIX = "enc:v1:"


def _build_fernet_key(raw: str) -> bytes:
    """
    Accept either a valid Fernet key (urlsafe base64, 32 bytes) or any string.
    For non-Fernet input, derive a key via SHA-256 and base64-url encoding.
    """
    raw = (raw or "").strip()
    if not raw:
        raise RuntimeError("INBOXIQ_ENCRYPTION_KEY is required for encryption.")
    try:
        decoded = base64.urlsafe_b64decode(raw.encode("utf-8"))
        if len(decoded) == 32:
            return raw.encode("utf-8")
    except Exception:
        pass
    digest = hashlib.sha256(raw.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


def _get_fernet() -> Fernet:
    key = _build_fernet_key(os.getenv("INBOXIQ_ENCRYPTION_KEY", ""))
    return Fernet(key)


def encrypt_value(value: str) -> str:
    """
    Encrypt a sensitive value and return a tagged ciphertext string.
    """
    if value is None:
        raise ValueError("value is required")
    value = str(value)
    if value.startswith(_PREFIX):
        return value
    token = _get_fernet().encrypt(value.encode("utf-8")).decode("utf-8")
    return f"{_PREFIX}{token}"


def decrypt_value(value: str) -> Optional[str]:
    """
    Decrypt a tagged ciphertext string. Returns None for invalid/empty values.
    """
    if not value:
        return None
    if not value.startswith(_PREFIX):
        return value
    token = value[len(_PREFIX):]
    try:
        return _get_fernet().decrypt(token.encode("utf-8")).decode("utf-8")
    except InvalidToken:
        return None
