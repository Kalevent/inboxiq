from flask import Blueprint, abort, g, render_template

from src.settings import login_required_settings

marketing_bp = Blueprint("marketing_ops", __name__)

_VALID_SECTIONS = {"funnel", "content", "marketing", "campaigns"}
_MARKETING_ROLES = {"owner", "admin"}


def _resolve_marketing_access(user) -> bool:
    """
    Return True if the user may access marketing pages.

    Checks DB role first. Falls back to treating the oldest user in the account
    as "owner" when no explicit owner has been assigned yet (bootstrap state
    after the role column migration).
    """
    if getattr(user, "role", None) in _MARKETING_ROLES:
        return True

    # Bootstrap fallback: if no one in this account has an explicit owner role,
    # treat the first (lowest ID) user as owner and persist it.
    from src.extensions import db
    from src.models.core import User as _User

    account_id = getattr(user, "account_id", None)
    if not account_id:
        return False

    account_users = (
        db.session.query(_User)
        .filter_by(account_id=account_id)
        .order_by(_User.id)
        .all()
    )
    has_owner = any(getattr(u, "role", None) == "owner" for u in account_users)
    if not has_owner and account_users and account_users[0].id == user.id:
        # Persist the resolved role so future checks hit the fast path
        user.role = "owner"
        db.session.commit()
        return True

    return False


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
