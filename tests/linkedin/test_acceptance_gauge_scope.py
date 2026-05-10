"""Verify the acceptance-ratio gauge only iterates LinkedIn-connected accounts.

Memory rule (no hardcoded account IDs / derive scoping from data): per-account
labelled metrics must only emit for accounts that actually have a
linkedin_social InboxConnection. The previous implementation iterated every
Account row and bloated Prometheus label cardinality.
"""
import os
import pytest
from sqlalchemy.pool import StaticPool

os.environ.setdefault("APP_ENV", "test")

from src.app import create_app
from src.extensions import db as _db
from src.models.core import Account, User, InboxConnection
from src.models.campaigns import LinkedInProspect


@pytest.fixture
def gauge_app():
    """App fixture with the tables we need for the helper test.

    Distinct from tests/linkedin/conftest.py's `app` fixture because that one
    only creates Lead/LinkedInProspect/ICPConfig — we additionally need
    Account, User, and InboxConnection.
    """
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
        LinkedInProspect.__table__.create(_db.engine, checkfirst=True)
        yield app
        _db.session.remove()
        LinkedInProspect.__table__.drop(_db.engine, checkfirst=True)
        InboxConnection.__table__.drop(_db.engine, checkfirst=True)
        User.__table__.drop(_db.engine, checkfirst=True)
        Account.__table__.drop(_db.engine, checkfirst=True)


def test_helper_returns_only_linkedin_connected_accounts(gauge_app):
    from src.tasks.linkedin import _linkedin_connected_account_ids

    with gauge_app.app_context():
        # Three accounts: 1 has linkedin_social, 2 has gmail only, 3 has no connection.
        for aid, name in [(1, "Acct-LI"), (2, "Acct-Gmail"), (3, "Acct-None")]:
            _db.session.add(Account(id=aid, name=name))
        _db.session.flush()
        for uid, aid in [(10, 1), (20, 2)]:
            _db.session.add(User(id=uid, email=f"u{uid}@x.com", account_id=aid))
        _db.session.flush()
        _db.session.add(InboxConnection(
            id="ic-1", user_id=10, account_id=1, provider="linkedin_social",
            email_address="li1@x.com", status="connected",
        ))
        _db.session.add(InboxConnection(
            id="ic-2", user_id=20, account_id=2, provider="gmail",
            email_address="g1@x.com", status="connected",
        ))
        _db.session.commit()

        ids = _linkedin_connected_account_ids()
        assert ids == [1], f"expected only account 1 (linkedin_social), got {ids}"


def test_helper_dedupes_multiple_linkedin_connections_per_account(gauge_app):
    from src.tasks.linkedin import _linkedin_connected_account_ids

    with gauge_app.app_context():
        _db.session.add(Account(id=5, name="Acct-multi"))
        _db.session.flush()
        _db.session.add(User(id=50, email="u50@x.com", account_id=5))
        _db.session.flush()
        # Two linkedin_social connections for the same account → must appear once.
        _db.session.add(InboxConnection(
            id="ic-a", user_id=50, account_id=5, provider="linkedin_social",
            email_address="li-a@x.com", status="connected",
        ))
        _db.session.add(InboxConnection(
            id="ic-b", user_id=50, account_id=5, provider="linkedin_social",
            email_address="li-b@x.com", status="connected",
        ))
        _db.session.commit()

        ids = _linkedin_connected_account_ids()
        assert ids == [5]


def test_helper_returns_empty_when_no_linkedin_connections(gauge_app):
    from src.tasks.linkedin import _linkedin_connected_account_ids

    with gauge_app.app_context():
        _db.session.add(Account(id=9, name="Acct-none"))
        _db.session.commit()
        assert _linkedin_connected_account_ids() == []
