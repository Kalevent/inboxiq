from argon2 import PasswordHasher
from argon2.exceptions import InvalidHash, VerificationError, VerifyMismatchError
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
