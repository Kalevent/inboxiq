from datetime import datetime, timedelta
from typing import Optional
from werkzeug.exceptions import BadRequest
from src.extensions import cache


def ensure_idempotency(idempotency_key: Optional[str], scope: str) -> str:
    """
    Lightweight in-memory idempotency guard. Production can swap to DB-backed persistence.
    """
    if not idempotency_key:
        return ""
    cache_key = f"idempotency:{scope}:{idempotency_key}"
    existing = cache.get(cache_key)
    if existing:
        raise BadRequest(f"Duplicate request: {idempotency_key}")
    cache.set(cache_key, {"seen_at": datetime.utcnow().isoformat()}, timeout=int(timedelta(minutes=30).total_seconds()))
    return idempotency_key
