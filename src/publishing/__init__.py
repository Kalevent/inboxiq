from flask import Blueprint

bp = Blueprint("publishing", __name__, url_prefix="/publishing")

from . import routes  # noqa: E402,F401 keep at end to register routes