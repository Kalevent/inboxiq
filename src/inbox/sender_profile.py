"""
SenderProfile — domain-level classification cache.

After each DSPy triage the pipeline calls upsert_sender_profile() to record the
result.  On the next email from the same domain, lookup_sender_profile() returns
the prior so the triage flow can:

  confidence >= 0.85  → bypass DSPy entirely (fast path)
  0.5–0.85            → run DSPy with sender_hint as an input field
  < 0.5 / None        → full DSPy, no prior

Lookup order: account-specific profile first, then global (account_id=NULL).
This means new accounts get instant warmup from the global pool; their own
corrections override it once they have enough samples.
"""
from __future__ import annotations

import re
import logging
from datetime import datetime, timezone
from typing import Optional

from src.extensions import db

_log = logging.getLogger(__name__)

# Confidence thresholds from the pipeline document
BYPASS_THRESHOLD = 0.85   # skip DSPy entirely
HINT_THRESHOLD   = 0.50   # pass sender_hint to DSPy

# How many samples before confidence starts climbing toward bypass
MIN_SAMPLES_FOR_BYPASS = 5


def _extract_domain(from_email: str) -> str | None:
    """
    Return the lowercase domain from an email address or display-name header.

    Handles:  'Jane <jane@example.com>' → 'example.com'
              'jane@example.com'         → 'example.com'
    Returns None if no valid domain found.
    """
    if not from_email:
        return None
    # Strip display name wrapper
    match = re.search(r"[\w.+-]+@([\w.-]+\.[a-z]{2,})", from_email, re.IGNORECASE)
    if match:
        return match.group(1).lower()
    return None


def lookup_sender_profile(domain: str, account_id: int | None):
    """
    Return the most specific SenderProfile for this domain, or None.

    Prefers account-specific over global (account_id=NULL).
    """
    from src.models.tickets import SenderProfile

    return (
        SenderProfile.query
        .filter(
            db.or_(
                SenderProfile.account_id == account_id,
                SenderProfile.account_id.is_(None),
            ),
            SenderProfile.domain == domain,
        )
        .order_by(SenderProfile.account_id.nullslast())
        .first()
    )


def get_sender_hint(from_email: str, account_id: int | None) -> tuple[str | None, float, bool]:
    """
    Inspect the SenderProfile for the sender's domain and return
    (hint_text, confidence, bypass).

      bypass=True  → skip DSPy, use category directly
      hint_text    → string to pass as sender_hint input field
      confidence   → raw confidence value for decision trace

    Returns (None, 0.0, False) when no useful prior exists.
    """
    domain = _extract_domain(from_email)
    if not domain:
        return None, 0.0, False

    profile = lookup_sender_profile(domain, account_id)
    if not profile:
        return None, 0.0, False

    confidence = profile.confidence

    if confidence >= BYPASS_THRESHOLD:
        return profile.category, confidence, True

    if confidence >= HINT_THRESHOLD:
        hint = f"{profile.category} (confidence: {confidence:.2f}, sample_size: {profile.sample_size})"
        return hint, confidence, False

    return None, confidence, False


def upsert_sender_profile(
    from_email: str,
    category: str,
    account_id: int | None,
    user_verified: bool = False,
) -> None:
    """
    Update the account-specific SenderProfile for this sender's domain.

    Confidence update rules:
    - Same category → confidence increases toward 1.0 (Bayesian-style increment)
    - Different category → confidence decays; if it falls below 0.3 the category flips
    - user_verified=True → confidence jumps to 0.95 immediately (explicit correction)

    Always writes to the account-specific profile, never to the global one.
    Global profiles are promoted separately by a future batch job (Phase 7).
    """
    from src.models.tickets import SenderProfile

    domain = _extract_domain(from_email)
    if not domain:
        return

    now = datetime.now(timezone.utc)

    try:
        # Only look for an account-specific profile — we never mutate the global one here
        profile = SenderProfile.query.filter_by(
            account_id=account_id, domain=domain
        ).first()

        if profile is None:
            # First time we've seen this domain for this account
            initial_confidence = 0.95 if user_verified else 0.5
            profile = SenderProfile(
                account_id=account_id,
                domain=domain,
                category=category,
                confidence=initial_confidence,
                sample_size=1,
                user_verified=user_verified,
                last_seen_at=now,
            )
            db.session.add(profile)
        else:
            profile.last_seen_at = now
            profile.sample_size += 1

            if user_verified:
                # Explicit correction — override everything
                profile.category = category
                profile.confidence = 0.95
                profile.user_verified = True
            elif profile.category == category:
                # Agreement — nudge confidence up toward 1.0
                # Each new agreement halves the gap to 1.0
                gap = 1.0 - profile.confidence
                profile.confidence = min(0.99, profile.confidence + gap / max(profile.sample_size, 2))
            else:
                # Disagreement — decay confidence
                profile.confidence = max(0.0, profile.confidence * 0.7)
                if profile.confidence < 0.3:
                    # Category has shifted — update to the new one
                    profile.category = category
                    profile.confidence = 0.4

        db.session.commit()

    except Exception as exc:
        db.session.rollback()
        _log.warning(
            "upsert_sender_profile failed: domain=%s account=%s error=%s",
            domain, account_id, exc,
        )
