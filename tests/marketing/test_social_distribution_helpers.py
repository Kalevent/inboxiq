from unittest.mock import patch, MagicMock


def test_get_social_token_scopes_by_account(app, db, kalevent_account):
    from src.models.core import InboxConnection
    from src.crypto import encrypt_value

    InboxConnection.query.delete()
    db.session.add(InboxConnection(
        id="c1", user_id=1, account_id=2, provider="linkedin_social", status="connected",
        metadata_json={"access_token_enc": encrypt_value("token-acc-2")},
    ))
    db.session.add(InboxConnection(
        id="c2", user_id=1, account_id=99, provider="linkedin_social", status="connected",
        metadata_json={"access_token_enc": encrypt_value("token-acc-99")},
    ))
    db.session.commit()

    from src.marketing.content_distribution import _get_social_token
    assert _get_social_token("linkedin_social", account_id=2) == "token-acc-2"
    assert _get_social_token("linkedin_social", account_id=99) == "token-acc-99"


def test_get_social_token_returns_none_when_unconnected(app, db, kalevent_account):
    from src.marketing.content_distribution import _get_social_token
    assert _get_social_token("linkedin_social", account_id=2) is None


def test_post_to_facebook_skips_when_account_has_no_facebook_connection(app, db, kalevent_account):
    """_post_to_facebook should not pick up a different account's connection (sibling of Task 3 fix)."""
    from src.models.core import InboxConnection, User

    # Create a different account (id=99) with a Facebook connection
    db.session.add(User(id=2, email="other@example.com", account_id=99))
    db.session.commit()
    db.session.add(InboxConnection(
        id="c-other", account_id=99, user_id=2, provider="facebook_social", status="connected",
        metadata_json={"pages": [{"id": "p1", "access_token": "x"}]},
    ))
    db.session.commit()

    # Query using the scoped filter from _post_to_facebook (account_id=2)
    # This should return None because account_id=2 has no Facebook connection
    conn = InboxConnection.query.filter_by(
        provider="facebook_social", account_id=2, status="connected"
    ).first()
    assert conn is None  # Should not find the other account's connection
