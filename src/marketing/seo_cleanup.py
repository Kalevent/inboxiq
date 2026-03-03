"""
SEO cleanup middleware for handling old/deprecated URLs.

Returns 410 Gone for permanently removed content to tell search engines
to stop crawling these URLs.
"""
from flask import request, abort, redirect
import re


# Patterns for old URLs that should return 410 Gone
OLD_URL_PATTERNS = [
    r'^/home/?$',
    r'^/en-gb/',
    r'^/es-es/',
    r'^/en-us/',
    r'^/fr-fr/',
    r'^/de-de/',
    r'^/set_locale/',
    r'^/careers/',
    r'^/crm/',
    # Add more patterns as needed
]

# Optional: Redirects for URLs that have new equivalents
URL_REDIRECTS = {
    '/home/': '/',
    '/en-gb/contacts/contact': '/contact',
    '/en-gb/auth/reset_password_request': '/auth/reset-password',
    # Add more redirects as needed
}


def is_old_url(path: str) -> bool:
    """
    Check if a URL matches old app patterns.

    Args:
        path: Request path (e.g., '/en-gb/contacts/contact')

    Returns:
        True if URL matches old app pattern
    """
    for pattern in OLD_URL_PATTERNS:
        if re.match(pattern, path):
            return True
    return False


def handle_old_urls():
    """
    Middleware to handle old URLs before they hit 404.

    - Returns 410 Gone for old app URLs (tells Google to stop crawling)
    - Optionally redirects to new equivalents

    Usage: Call this in a @app.before_request handler
    """
    path = request.path

    # Check if URL has a redirect mapping
    if path in URL_REDIRECTS:
        return redirect(URL_REDIRECTS[path], code=301)

    # Check if URL matches old app patterns
    if is_old_url(path):
        # Return 410 Gone (tells Google: "This is permanently deleted, stop crawling")
        abort(410)

    # Let other URLs proceed normally
    return None


def register_seo_cleanup(app):
    """
    Register SEO cleanup handlers with Flask app.

    Args:
        app: Flask application instance
    """

    # Before request handler
    @app.before_request
    def cleanup_old_urls():
        return handle_old_urls()

    # 410 error handler
    @app.errorhandler(410)
    def gone(error):
        """
        Custom 410 Gone handler.

        This tells search engines the content is permanently gone
        and they should remove it from their index.
        """
        return {
            "error": "Gone",
            "message": "This resource has been permanently removed.",
            "status": 410
        }, 410

    print("✅ SEO cleanup handlers registered")
