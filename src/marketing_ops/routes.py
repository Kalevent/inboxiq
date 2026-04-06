from flask import Blueprint, abort, current_app, g, render_template

from src.settings import login_required_settings

marketing_bp = Blueprint("marketing_ops", __name__)

_VALID_SECTIONS = {"funnel", "content", "marketing", "campaigns"}
_MARKETING_ROLES = {"owner", "admin"}

# Sections that are restricted to Kalevent internal staff only
_INTERNAL_ONLY_SECTIONS = {"content"}


def _resolve_marketing_access(user) -> bool:
    """Return True if the user may access marketing pages."""
    return getattr(user, "role", None) in _MARKETING_ROLES


def _is_kalevent_staff(user) -> bool:
    """Return True only for Kalevent internal email addresses."""
    if not user or not user.email:
        return False
    allowed = set(
        e.strip().lower()
        for e in (current_app.config.get("ADMIN_EMAILS", "") or "kofi@kalevent.com").split(",")
        if e.strip()
    )
    return user.email.lower() in allowed


@marketing_bp.route("/marketing")
@marketing_bp.route("/marketing/<section>")
@login_required_settings
def marketing_dashboard(section="funnel"):
    user = g.current_user
    if not _resolve_marketing_access(user):
        abort(403)
    if section not in _VALID_SECTIONS:
        section = "funnel"
    # Content generation is internal-only — block tenants even with owner/admin role
    if section in _INTERNAL_ONLY_SECTIONS and not _is_kalevent_staff(user):
        abort(403)
    return render_template(
        "marketing_ops.html",
        active_section=section,
        show_content_section=_is_kalevent_staff(user),
    )
