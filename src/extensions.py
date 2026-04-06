from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_jwt_extended import JWTManager
from flask_caching import Cache
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# Shared extensions for the InboxIQ app.
db = SQLAlchemy()
migrate = Migrate()
jwt = JWTManager()
cache = Cache()
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[],
    storage_uri=None,  # populated from app config
    swallow_errors=True,  # if Redis is unreachable, fail open — never return 500 to the user
)
