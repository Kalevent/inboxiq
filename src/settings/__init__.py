# Import flask dependencies
from functools import wraps
from flask import Blueprint, current_app, g, redirect, request, url_for
from flask_jwt_extended import get_jwt, get_jwt_identity, verify_jwt_in_request

from src.extensions import db
from src.models import User
from src.api.v1.access_control import account_allows_api

bp = Blueprint("settings", __name__, url_prefix="")


def login_required_settings(view_func):
  """Require a valid JWT and redirect to login when missing/invalid."""

  @wraps(view_func)
  def wrapper(*args, **kwargs):
    try:
      verify_jwt_in_request()
    except Exception as exc:
      try:
        current_app.logger.warning(
          {
            "event": "auth.page_redirect",
            "reason": str(exc),
            "path": request.path,
            "cookies": list((request.cookies or {}).keys()),
          }
        )
      except Exception:
        pass
      login_url = url_for("login_page")
      next_param = request.path if request.path and request.path != "/login" else None
      if next_param:
        return redirect(f"{login_url}?next={next_param}")
      return redirect(login_url)

    claims = get_jwt() or {}
    raw_user_id = get_jwt_identity()
    raw_account_id = claims.get("account_id")
    user = db.session.get(User, int(raw_user_id)) if raw_user_id else None
    account_id = int(raw_account_id) if raw_account_id else None
    if not user:
      login_url = url_for("login_page")
      return redirect(login_url)
    g.current_user = user
    g.current_account_id = account_id

    # Enforce upgrade redirect when trial expired and not allowed for API/Business.
    if account_id and request.path != url_for("upgrade"):
      if not account_allows_api(account_id):
        return redirect(url_for("upgrade", trial="ended"))

    return view_func(*args, **kwargs)

  return wrapper


# Import routes so the blueprint registers its views.
from src.settings import routes  # noqa: E402,F401
