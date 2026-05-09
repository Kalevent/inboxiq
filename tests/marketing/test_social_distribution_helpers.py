from unittest.mock import patch, MagicMock


# ---------------------------------------------------------------------------
# _get_social_token
# ---------------------------------------------------------------------------

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
    from src.models.campaigns import SocialDistributionQueueItem
    from src.crypto import encrypt_value
    db.session.add(User(id=2, email="other@example.com", account_id=99))
    db.session.commit()
    db.session.add(InboxConnection(
        id="c-other", account_id=99, user_id=2, provider="facebook_social", status="connected",
        metadata_json={"access_token_enc": encrypt_value("fb-token"), "page_id": "999"},
    ))
    db.session.commit()

    item = SocialDistributionQueueItem(
        account_id=2, content_type="blog", content_id="post-1",
        platform="facebook", caption="x",
        target_url="https://example.com",
    )
    db.session.add(item)
    db.session.commit()

    from src.marketing.content_distribution import _post_to_facebook
    result = _post_to_facebook(item)
    assert result["status"] == "skipped"
    assert result["reason"] == "not_connected"


# ---------------------------------------------------------------------------
# _post_to_linkedin
# ---------------------------------------------------------------------------

def test_post_to_linkedin_uses_queue_item_and_org_id(app, db, kalevent_account, monkeypatch):
    from src.models.core import InboxConnection
    from src.models.campaigns import SocialDistributionQueueItem
    from src.crypto import encrypt_value

    db.session.add(InboxConnection(
        id="c1", account_id=2, user_id=1, provider="linkedin_social", status="connected",
        metadata_json={
            "access_token_enc": encrypt_value("li-token"),
            "org_id": "999",
        },
    ))
    item = SocialDistributionQueueItem(
        account_id=2, content_type="blog", content_id="post-1",
        platform="linkedin", caption="Hello LinkedIn",
        target_url="https://kalevent.com/blog/post-1",
    )
    db.session.add(item)
    db.session.commit()

    captured = {}
    def fake_post(url, json, headers, timeout):
        captured["url"] = url
        captured["json"] = json
        captured["headers"] = headers
        resp = MagicMock()
        resp.raise_for_status = lambda: None
        resp.json = lambda: {"id": "urn:li:share:abc"}
        return resp

    import requests as http
    monkeypatch.setattr(http, "post", fake_post)

    from src.marketing.content_distribution import _post_to_linkedin
    result = _post_to_linkedin(item)

    assert result["status"] == "ok"
    assert result["post_url"] == "https://www.linkedin.com/feed/update/urn:li:share:abc"
    assert captured["url"] == "https://api.linkedin.com/v2/ugcPosts"
    body = captured["json"]
    assert body["author"] == "urn:li:organization:999"
    assert body["specificContent"]["com.linkedin.ugc.ShareContent"]["shareCommentary"]["text"] == "Hello LinkedIn"
    assert body["specificContent"]["com.linkedin.ugc.ShareContent"]["media"][0]["originalUrl"] == "https://kalevent.com/blog/post-1"


def test_post_to_linkedin_skips_when_not_connected(app, db, kalevent_account):
    from src.models.campaigns import SocialDistributionQueueItem
    item = SocialDistributionQueueItem(
        account_id=2, content_type="blog", content_id="post-1",
        platform="linkedin", caption="x", target_url="u",
    )
    db.session.add(item)
    db.session.commit()

    from src.marketing.content_distribution import _post_to_linkedin
    result = _post_to_linkedin(item)
    assert result["status"] == "skipped"
    assert result["reason"] == "not_connected"


# ---------------------------------------------------------------------------
# _post_to_twitter
# ---------------------------------------------------------------------------

def test_post_to_twitter_uses_queue_item(app, db, kalevent_account, monkeypatch):
    from src.models.core import InboxConnection
    from src.models.campaigns import SocialDistributionQueueItem
    from src.crypto import encrypt_value

    db.session.add(InboxConnection(
        id="tw1", account_id=2, user_id=1, provider="twitter_social", status="connected",
        metadata_json={"access_token_enc": encrypt_value("tw-token")},
    ))
    item = SocialDistributionQueueItem(
        account_id=2, content_type="blog", content_id="post-tw",
        platform="twitter", caption="Hello Twitter",
        target_url="https://kalevent.com/blog/post-tw",
    )
    db.session.add(item)
    db.session.commit()

    captured = {}
    def fake_post(url, json, headers, timeout):
        captured["url"] = url
        captured["json"] = json
        resp = MagicMock()
        resp.raise_for_status = lambda: None
        resp.json = lambda: {"data": {"id": "tweet-123", "text": json.get("text", "")}}
        return resp

    import requests as http
    monkeypatch.setattr(http, "post", fake_post)

    from src.marketing.content_distribution import _post_to_twitter
    result = _post_to_twitter(item)

    assert result["status"] == "ok"
    assert result["post_url"] == "https://twitter.com/i/web/status/tweet-123"
    assert captured["url"] == "https://api.twitter.com/2/tweets"
    # caption should be in the tweet text
    assert "Hello Twitter" in captured["json"]["text"]
    # target_url should be appended
    assert "https://kalevent.com/blog/post-tw" in captured["json"]["text"]


def test_post_to_twitter_skips_when_not_connected(app, db, kalevent_account):
    from src.models.campaigns import SocialDistributionQueueItem
    item = SocialDistributionQueueItem(
        account_id=2, content_type="blog", content_id="post-tw2",
        platform="twitter", caption="x", target_url="u",
    )
    db.session.add(item)
    db.session.commit()

    from src.marketing.content_distribution import _post_to_twitter
    result = _post_to_twitter(item)
    assert result["status"] == "skipped"
    assert result["reason"] == "not_connected"


# ---------------------------------------------------------------------------
# _post_to_facebook
# ---------------------------------------------------------------------------

def test_post_to_facebook_uses_queue_item(app, db, kalevent_account, monkeypatch):
    from src.models.core import InboxConnection
    from src.models.campaigns import SocialDistributionQueueItem
    from src.crypto import encrypt_value

    db.session.add(InboxConnection(
        id="fb1", account_id=2, user_id=1, provider="facebook_social", status="connected",
        metadata_json={
            "pages": [
                {"id": "fb-page-1", "access_token_enc": encrypt_value("fb-page-token")},
            ],
        },
    ))
    item = SocialDistributionQueueItem(
        account_id=2, content_type="blog", content_id="post-fb",
        platform="facebook", caption="Hello Facebook",
        target_url="https://kalevent.com/blog/post-fb",
    )
    db.session.add(item)
    db.session.commit()

    captured = {}
    def fake_post(url, data, timeout):
        captured["url"] = url
        captured["data"] = data
        resp = MagicMock()
        resp.raise_for_status = lambda: None
        resp.json = lambda: {"id": "fb-page-1_987654"}
        return resp

    import requests as http
    monkeypatch.setattr(http, "post", fake_post)

    from src.marketing.content_distribution import _post_to_facebook
    result = _post_to_facebook(item)

    assert result["status"] == "ok"
    assert "fb-page-1_987654" in result["post_url"]
    assert captured["url"] == "https://graph.facebook.com/v19.0/fb-page-1/feed"
    assert captured["data"]["message"] == "Hello Facebook"
    assert captured["data"]["link"] == "https://kalevent.com/blog/post-fb"


def test_post_to_facebook_skips_when_not_connected(app, db, kalevent_account):
    from src.models.campaigns import SocialDistributionQueueItem
    item = SocialDistributionQueueItem(
        account_id=2, content_type="blog", content_id="post-fb2",
        platform="facebook", caption="x", target_url="u",
    )
    db.session.add(item)
    db.session.commit()

    from src.marketing.content_distribution import _post_to_facebook
    result = _post_to_facebook(item)
    assert result["status"] == "skipped"
    assert result["reason"] == "not_connected"


def test_post_to_linkedin_skips_when_org_id_missing(app, db, kalevent_account):
    from src.models.core import InboxConnection
    from src.models.campaigns import SocialDistributionQueueItem
    from src.crypto import encrypt_value

    db.session.add(InboxConnection(
        id="c1-li-norg", account_id=2, user_id=1, provider="linkedin_social", status="connected",
        metadata_json={"access_token_enc": encrypt_value("li-token")},  # no org_id
    ))
    item = SocialDistributionQueueItem(
        account_id=2, content_type="blog", content_id="post-1",
        platform="linkedin", caption="x",
        target_url="https://kalevent.com/blog/post-1",
    )
    db.session.add(item)
    db.session.commit()

    from src.marketing.content_distribution import _post_to_linkedin
    result = _post_to_linkedin(item)
    assert result["status"] == "skipped"
    assert result["reason"] == "not_configured"


def test_post_to_facebook_skips_when_page_token_missing(app, db, kalevent_account):
    """_post_to_facebook returns no_page_token when pages list has an entry without access_token_enc."""
    from src.models.core import InboxConnection
    from src.models.campaigns import SocialDistributionQueueItem

    db.session.add(InboxConnection(
        id="cfb-nopt", account_id=2, user_id=1, provider="facebook_social", status="connected",
        # pages list present but no access_token_enc on the page entry
        metadata_json={"pages": [{"id": "fb-page-99"}]},
    ))
    item = SocialDistributionQueueItem(
        account_id=2, content_type="blog", content_id="post-1",
        platform="facebook", caption="x",
        target_url="https://kalevent.com/blog/post-1",
    )
    db.session.add(item)
    db.session.commit()

    from src.marketing.content_distribution import _post_to_facebook
    result = _post_to_facebook(item)
    assert result["status"] == "skipped"
    assert result["reason"] == "no_page_token"
