from flask import Blueprint

# Unique name "social_auth", same /auth prefix as the main auth blueprint.
# Flask allows multiple blueprints sharing a url_prefix.
bp = Blueprint("social_auth", __name__, url_prefix="/auth")

from src.social_auth import routes  # noqa: E402,F401
