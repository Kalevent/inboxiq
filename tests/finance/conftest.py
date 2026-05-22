import os
os.environ.setdefault("APP_ENV", "test")

import pytest
from sqlalchemy.pool import StaticPool
from src.app import create_app
from src.extensions import db as _db
from src.models.core import Account
from src.models.addons import AccountAddOn


@pytest.fixture
def app():
    """Create application for the tests."""
    app = create_app()
    app.config["TESTING"] = True
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite://"
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
        "connect_args": {"check_same_thread": False},
        "poolclass": StaticPool,
    }
    app.config["SECRET_KEY"] = "test-secret"
    app.config["JWT_SECRET_KEY"] = "test-jwt-secret"

    with app.app_context():
        Account.__table__.create(_db.engine, checkfirst=True)
        AccountAddOn.__table__.create(_db.engine, checkfirst=True)
        yield app
        _db.session.remove()
        AccountAddOn.__table__.drop(_db.engine, checkfirst=True)
        Account.__table__.drop(_db.engine, checkfirst=True)


@pytest.fixture
def db(app):
    """Provide the SQLAlchemy database object."""
    return _db


@pytest.fixture
def client(app):
    """A test client for the app."""
    return app.test_client()


@pytest.fixture
def auth_headers(app):
    from flask_jwt_extended import create_access_token
    with app.app_context():
        token = create_access_token(identity="1")
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
