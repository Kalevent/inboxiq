import os
import pytest

os.environ.setdefault("APP_ENV", "test")

from src.app import create_app
from src.extensions import db as _db
from src.models.campaigns import VideoRender, OnboardingVideo


@pytest.fixture
def app():
    from sqlalchemy.pool import StaticPool

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
        VideoRender.__table__.create(_db.engine, checkfirst=True)
        OnboardingVideo.__table__.create(_db.engine, checkfirst=True)
        yield app
        _db.session.remove()
        OnboardingVideo.__table__.drop(_db.engine, checkfirst=True)
        VideoRender.__table__.drop(_db.engine, checkfirst=True)


@pytest.fixture
def db(app):
    return _db


@pytest.fixture
def auth_headers(app):
    from flask_jwt_extended import create_access_token
    with app.app_context():
        token = create_access_token(identity=2)
    return {"Authorization": f"Bearer {token}"}
