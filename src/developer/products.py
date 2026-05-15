from __future__ import annotations
from typing import Optional

PRODUCT_CATALOG: list[dict] = [
    {
        "slug": "chat",
        "name": "Chat / Aria Widget",
        "icon": "💬",
        "description": "Embed an AI-powered chat widget on your site or app.",
        "approval": "reviewed",
        "docs_url": None,
    },
    {
        "slug": "forms",
        "name": "External Forms",
        "icon": "📋",
        "description": "Route external form submissions into InboxIQ triage.",
        "approval": "reviewed",
        "docs_url": "/docs/external_forms",
    },
    {
        "slug": "intake_api",
        "name": "Intake API",
        "icon": "📥",
        "description": "Submit tickets and messages directly into InboxIQ.",
        "approval": "auto",
        "docs_url": "/docs/intake_api",
    },
]

_CATALOG_BY_SLUG = {p["slug"]: p for p in PRODUCT_CATALOG}


def get_product_by_slug(slug: str) -> Optional[dict]:
    return _CATALOG_BY_SLUG.get(slug)
