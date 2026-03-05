from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHash, VerificationError, VerifyMismatchError
from flask import g, request
from werkzeug.security import check_password_hash

# Centralized password hashing helpers (Argon2 with PBKDF2 fallback verification).
_ph = PasswordHasher()


def hash_password(password: str) -> str:
    """Hash password with Argon2 (memory-hard)."""
    return _ph.hash(password or "")


def verify_password(stored_hash: str | None, provided_password: str | None) -> tuple[bool, str | None]:
    """Verify password, returning (ok, algorithm_used). Falls back to PBKDF2 for legacy hashes."""
    if not stored_hash:
        return False, None

    try:
        _ph.verify(stored_hash, provided_password or "")
        return True, "argon2"
    except VerifyMismatchError:
        return False, "argon2"
    except (InvalidHash, VerificationError):
        pass

    # PBKDF2 fallback (Werkzeug legacy hashes)
    try:
        ok = check_password_hash(stored_hash, provided_password or "")
        return ok, "pbkdf2" if ok else None
    except ValueError:
        return False, None


def log_audit(
    action: str,
    resource_type: str | None = None,
    resource_id: str | None = None,
    metadata: dict | None = None,
    account_id: int | None = None,
    user_id: int | None = None,
) -> None:
    """
    Write an immutable audit log entry.

    Pulls account_id and user_id from Flask g if not provided explicitly.
    Silently swallows errors so a logging failure never breaks a request.

    Usage:
        log_audit("user.role_changed", resource_type="user", resource_id=str(target.id),
                  metadata={"old_role": old, "new_role": new})
    """
    try:
        from src.extensions import db
        from src.models.auth import AuditLog

        _account_id = account_id if account_id is not None else getattr(g, "current_account_id", None)
        _user_id    = user_id    if user_id    is not None else getattr(getattr(g, "current_user", None), "id", None)

        entry = AuditLog(
            account_id    = _account_id,
            user_id       = _user_id,
            action        = action,
            resource_type = resource_type,
            resource_id   = str(resource_id) if resource_id is not None else None,
            ip_address    = request.remote_addr if request else None,
            user_agent    = (request.headers.get("User-Agent") or "")[:300] if request else None,
            metadata_json = metadata or {},
        )
        db.session.add(entry)
        db.session.commit()
    except Exception:  # noqa: BLE001
        pass
