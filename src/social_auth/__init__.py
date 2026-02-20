from flask import Blueprint

bp = Blueprint("social_auth", __name__, url_prefix="/social_auth")

from src.social_auth import routes  # noqa: E402,F401
