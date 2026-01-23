
from flask import Blueprint
from src.api.v1 import v1 as v1_bp

# Prefix must start with a slash to avoid malformed routes (e.g., "api/v1/agents")
bp = Blueprint("api", __name__, url_prefix="/api")
bp.register_blueprint(v1_bp, url_prefix="/v1")
