from flask import Blueprint

bp = Blueprint("blog", __name__, url_prefix="/blog")

from . import routes  # noqa: E402,F401 keep at end to register routes
