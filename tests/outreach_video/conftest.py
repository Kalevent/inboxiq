import os
import pytest

os.environ.setdefault("APP_ENV", "test")

from src.app import create_app
from src.extensions import db as _db
from src.models.campaigns import VideoRender, OutreachVideo, EmailCampaign


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
        OutreachVideo.__table__.create(_db.engine, checkfirst=True)
        EmailCampaign.__table__.create(_db.engine, checkfirst=True)
        yield app
        _db.session.remove()
        OutreachVideo.__table__.drop(_db.engine, checkfirst=True)
        VideoRender.__table__.drop(_db.engine, checkfirst=True)
        EmailCampaign.__table__.drop(_db.engine, checkfirst=True)


@pytest.fixture
def db(app):
    return _db
