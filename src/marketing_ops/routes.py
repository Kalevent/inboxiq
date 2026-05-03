from flask import Blueprint, abort, current_app, g, render_template, jsonify

from src.settings import login_required_settings

marketing_bp = Blueprint("marketing_ops", __name__)

_VALID_SECTIONS = {"funnel", "content", "marketing", "campaigns", "linkedin", "youtube"}
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


@marketing_bp.route("/<key>.txt", methods=["GET"])
def indexnow_key_file(key: str):
    """Serve IndexNow domain verification file at /<INDEXNOW_API_KEY>.txt."""
    configured = current_app.config.get("INDEXNOW_API_KEY", "")
    if not configured or key != configured:
        abort(404)
    return configured, 200, {"Content-Type": "text/plain"}


@marketing_bp.route("/unsubscribe/<token>", methods=["GET"])
def newsletter_unsubscribe(token: str):
    """One-click unsubscribe from blog newsletters. Token is HMAC-signed user ID."""
    from itsdangerous import URLSafeSerializer, BadSignature
    from src.extensions import db
    from src.models.core import User

    try:
        s = URLSafeSerializer(current_app.config["SECRET_KEY"], salt="newsletter-unsubscribe")
        user_id = s.loads(token)
    except BadSignature:
        return jsonify({"error": "Invalid or expired unsubscribe link."}), 400

    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"error": "User not found."}), 404

    if user.newsletter_opt_in:
        user.newsletter_opt_in = False
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise

    return jsonify({"status": "unsubscribed", "email": user.email}), 200
