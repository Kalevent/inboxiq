from flask import Blueprint
import os

# Dedicated documentation blueprint (moved from legacy MCP docs)
bp = Blueprint(
    'docs',
    __name__, 
    url_prefix='/docs',
    template_folder=os.path.join('..', 'templates', 'docs'),
    static_folder=os.path.join('..', 'static', 'docs'),
)

from src.docs import routes  # noqa: E402,F401
