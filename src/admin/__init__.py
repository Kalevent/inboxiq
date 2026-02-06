from flask import Blueprint

bp = Blueprint("admin", __name__, url_prefix='/admin')

# Import routes to register them with the blueprint
from src.admin import routes  # noqa: F401, E402
