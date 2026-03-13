from flask import Blueprint
import os

bp = Blueprint(
    'kb',
    __name__,
    url_prefix='/kb',
    template_folder=os.path.join('..', 'templates', 'kb'),
    static_folder=os.path.join('..', 'static', 'kb'),
)

from src.kb import routes  # noqa: E402,F401
