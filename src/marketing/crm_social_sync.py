"""
CRM sync for LinkedIn and Twitter/X social connections.

Reads the stored OAuth tokens from InboxConnection and calls the platform APIs
to verify the connection is live and upsert a Lead record for the connected profile.

This is intentionally lightweight — LinkedIn's standard OAuth only exposes the
authenticated user's own profile (/v2/userinfo), not their connections list. Twitter's
v2 API similarly gives access to the authenticated user's profile. Deeper data
(follower imports, contacts) requires elevated API access negotiated with each platform.

What this task does:
  LinkedIn: verify token → upsert Lead(source="linkedin") for the authenticated profile
  Twitter:  verify token → upsert Lead(source="twitter") for the authenticated profile

The admin can then build on these leads manually or via LinkedIn/Twitter outreach.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import requests

from src.celery_inboxiq import celery
from src.extensions import db
from src.funnel.stages import DISCOVERY
from src.models.core import InboxConnection
from src.models.leads import Lead

logger = logging.getLogger(__name__)

_LINKEDIN_USERINFO_URL = "https://api.linkedin.com/v2/userinfo"
_TWITTER_USERINFO_URL = "https://api.twitter.com/2/users/me"
_TWITTER_USER_FIELDS = "id,name,username,description,public_metrics,entities"


@celery.task(name="marketing.sync_social_crm_leads")
def sync_social_crm_leads() -> Dict[str, Any]:
    """
    Daily task: sync connected LinkedIn and Twitter profiles as CRM lead records.

    Iterates over all InboxConnections with provider linkedin_social or twitter_social,
    calls the platform userinfo endpoint, and upserts a Lead per connected profile.

    Returns:
        {"synced": N, "failed": N, "skipped": N}
    """
    from src.crypto import decrypt_value

    synced = 0
    failed = 0
    skipped = 0

    connections = db.session.query(InboxConnection).filter(
        InboxConnection.provider.in_(["linkedin_social", "twitter_social"]),
        InboxConnection.status == "connected",
    ).all()

    for conn in connections:
        try:
            meta = conn.metadata_json or {}
            token_enc = meta.get("access_token_enc") or conn.access_token
            if not token_enc:
                skipped += 1
                continue

            access_token = decrypt_value(token_enc) if token_enc else None
            if not access_token:
                skipped += 1
                continue

            if conn.provider == "linkedin_social":
                profile = _fetch_linkedin_profile(access_token)
                if profile:
                    _upsert_lead(conn.account_id, "linkedin", profile)
                    synced += 1
                else:
                    failed += 1

            elif conn.provider == "twitter_social":
                profile = _fetch_twitter_profile(access_token)
                if profile:
                    _upsert_lead(conn.account_id, "twitter", profile)
                    synced += 1
                else:
                    failed += 1

            try:
                db.session.commit()
            except Exception as commit_exc:
                db.session.rollback()
                logger.warning("Commit failed for connection %s: %s", conn.id, commit_exc)
                failed += 1

        except Exception as exc:
            db.session.rollback()
            logger.error("Failed to sync social CRM for connection %s: %s", conn.id, exc)
            failed += 1
    logger.info("[CRM SOCIAL SYNC] synced=%d failed=%d skipped=%d", synced, failed, skipped)
    return {"synced": synced, "failed": failed, "skipped": skipped}


# ── Platform API helpers ───────────────────────────────────────────────────────

def _fetch_linkedin_profile(access_token: str) -> Optional[Dict[str, Any]]:
    """Fetch authenticated user's LinkedIn profile via /v2/userinfo (OIDC)."""
    try:
        resp = requests.get(
            _LINKEDIN_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json()
            return {
                "name": data.get("name") or f"{data.get('given_name', '')} {data.get('family_name', '')}".strip(),
                "email": data.get("email"),
                "profile_url": data.get("sub"),  # LinkedIn member ID
                "source": "linkedin",
            }
        logger.warning("LinkedIn userinfo returned %s", resp.status_code)
        return None
    except Exception as exc:
        logger.warning("LinkedIn userinfo fetch failed: %s", exc)
        return None


def _fetch_twitter_profile(access_token: str) -> Optional[Dict[str, Any]]:
    """Fetch authenticated user's Twitter profile via /2/users/me."""
    try:
        resp = requests.get(
            _TWITTER_USERINFO_URL,
            params={"user.fields": _TWITTER_USER_FIELDS},
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json().get("data", {})
            return {
                "name": data.get("name"),
                "email": None,  # Twitter API doesn't expose email by default
                "twitter_username": data.get("username"),
                "twitter_id": data.get("id"),
                "source": "twitter",
            }
        logger.warning("Twitter userinfo returned %s", resp.status_code)
        return None
    except Exception as exc:
        logger.warning("Twitter userinfo fetch failed: %s", exc)
        return None


def _upsert_lead(account_id: int, source: str, profile: Dict[str, Any]) -> Lead:
    """
    Upsert a Lead record for the given social profile.

    Matches on (account_id, source, email) if email is available, else
    on (account_id, source, name) to avoid duplicates.
    """
    email = profile.get("email")
    name = profile.get("name") or profile.get("twitter_username") or "Unknown"

    existing = None
    if email:
        existing = db.session.query(Lead).filter_by(
            account_id=account_id,
            source=source,
            email=email,
        ).first()

    if not existing:
        existing = db.session.query(Lead).filter_by(
            account_id=account_id,
            source=source,
            name=name,
        ).first()

    if existing:
        # Refresh last_engagement_at to indicate we re-verified this profile
        existing.last_engagement_at = datetime.now(timezone.utc)
        return existing

    lead = Lead(
        account_id=account_id,
        name=name,
        email=email,
        source=source,
        status="New Lead",
        current_funnel_stage=DISCOVERY,
        stage_entered_at=datetime.now(timezone.utc),
    )

    # Store Twitter-specific metadata in notes
    if profile.get("twitter_username"):
        lead.notes = f"Twitter: @{profile['twitter_username']} (id: {profile.get('twitter_id')})"
    elif profile.get("profile_url"):
        lead.notes = f"LinkedIn member ID: {profile['profile_url']}"

    db.session.add(lead)
    logger.info("Upserted Lead from %s: %s (account %s)", source, name, account_id)
    return lead
