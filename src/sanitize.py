import bleach

# Minimal allowlist for rich-text inputs we might accept in the future.
ALLOWED_TAGS = [
    "p",
    "br",
    "strong",
    "em",
    "ul",
    "ol",
    "li",
    "a",
    "code",
    "pre",
    "span",
]
ALLOWED_ATTRIBUTES = {
    "a": ["href", "title", "rel", "target"],
    "span": ["class"],
    "code": ["class"],
    "pre": ["class"],
}
ALLOWED_PROTOCOLS = ["http", "https", "mailto"]


def sanitize_html(value: str) -> str:
    """Return sanitized HTML using a tight allowlist."""
    return bleach.clean(
        value or "",
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        protocols=ALLOWED_PROTOCOLS,
        strip=True,
    )
