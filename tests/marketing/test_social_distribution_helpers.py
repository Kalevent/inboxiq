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
