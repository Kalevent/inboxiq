# tests/marketing/conftest.py
import os
import pytest

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("INBOXIQ_ENCRYPTION_KEY", "test-encryption-key-for-unit-tests")

from src.app import create_app
from src.extensions import db as _db
from src.models.core import Account, User, InboxConnection
from src.models.content import BlogPost
from src.models.campaigns import YouTubeVideo, VideoRender, SocialDistributionQueueItem
from src.models.marketing import ICPConfig
from src.models.leads import ICPPainPoint


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
    with app.app_context():
        Account.__table__.create(_db.engine, checkfirst=True)
        User.__table__.create(_db.engine, checkfirst=True)
        InboxConnection.__table__.create(_db.engine, checkfirst=True)
        BlogPost.__table__.create(_db.engine, checkfirst=True)
        ICPConfig.__table__.create(_db.engine, checkfirst=True)
        ICPPainPoint.__table__.create(_db.engine, checkfirst=True)
        VideoRender.__table__.create(_db.engine, checkfirst=True)
        YouTubeVideo.__table__.create(_db.engine, checkfirst=True)
        SocialDistributionQueueItem.__table__.create(_db.engine, checkfirst=True)
        yield app
        _db.session.remove()
        SocialDistributionQueueItem.__table__.drop(_db.engine, checkfirst=True)
        YouTubeVideo.__table__.drop(_db.engine, checkfirst=True)
        VideoRender.__table__.drop(_db.engine, checkfirst=True)
        ICPPainPoint.__table__.drop(_db.engine, checkfirst=True)
        ICPConfig.__table__.drop(_db.engine, checkfirst=True)
        BlogPost.__table__.drop(_db.engine, checkfirst=True)
        InboxConnection.__table__.drop(_db.engine, checkfirst=True)
        User.__table__.drop(_db.engine, checkfirst=True)
        Account.__table__.drop(_db.engine, checkfirst=True)


@pytest.fixture
def db(app):
    return _db


@pytest.fixture
def kalevent_account(db):
    a = Account(id=2, name="Kalevent")
    db.session.add(a)
    # Seed a stub user so InboxConnection rows can satisfy user_id NOT NULL
    u = User(id=1, email="test@kalevent.com", account_id=2)
    db.session.add(u)
    db.session.commit()
    return a
