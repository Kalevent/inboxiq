from flask import Blueprint, render_template

from src.settings import login_required_settings

marketing_bp = Blueprint("marketing_ops", __name__)

_VALID_SECTIONS = {"funnel", "content", "marketing", "campaigns"}


@marketing_bp.route("/marketing")
@marketing_bp.route("/marketing/<section>")
@login_required_settings
def marketing_dashboard(section="funnel"):
    if section not in _VALID_SECTIONS:
        section = "funnel"
    return render_template("marketing_ops.html", active_section=section)
