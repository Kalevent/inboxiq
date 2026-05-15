from __future__ import annotations
from typing import Optional

PRODUCT_CATALOG: list[dict] = [
    {
        "slug": "chat",
        "name": "Chat / Aria Widget",
        "icon": "💬",
        "description": "Embed an AI-powered chat widget on your site or app.",
        "approval": "reviewed",
    },
    {
        "slug": "forms",
        "name": "External Forms",
        "icon": "📋",
        "description": "Route external form submissions into InboxIQ triage.",
        "approval": "reviewed",
    },
    {
        "slug": "intake_api",
        "name": "Intake API",
        "icon": "📥",
        "description": "Submit tickets and messages directly into InboxIQ.",
        "approval": "auto",
    },
]

_CATALOG_BY_SLUG = {p["slug"]: p for p in PRODUCT_CATALOG}


def get_product_by_slug(slug: str) -> Optional[dict]:
    return _CATALOG_BY_SLUG.get(slug)
