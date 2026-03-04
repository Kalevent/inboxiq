from flask import Blueprint, abort, g, render_template

from src.settings import login_required_settings

marketing_bp = Blueprint("marketing_ops", __name__)

_VALID_SECTIONS = {"funnel", "content", "marketing", "campaigns"}
_MARKETING_ROLES = {"owner", "admin"}


def _resolve_marketing_access(user) -> bool:
    """Return True if the user may access marketing pages."""
    return getattr(user, "role", None) in _MARKETING_ROLES


@marketing_bp.route("/marketing")
@marketing_bp.route("/marketing/<section>")
@login_required_settings
def marketing_dashboard(section="funnel"):
    user = g.current_user
    if not _resolve_marketing_access(user):
        abort(403)
    if section not in _VALID_SECTIONS:
        section = "funnel"
    return render_template("marketing_ops.html", active_section=section)
