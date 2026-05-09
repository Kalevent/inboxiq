import pytest
from sqlalchemy.exc import IntegrityError

from src.models.campaigns import SocialDistributionQueueItem


def test_queue_item_persists_with_defaults(app, db, kalevent_account):
    item = SocialDistributionQueueItem(
        account_id=2,
        content_type="blog",
        content_id="post-abc",
        platform="linkedin",
        caption="Read our new post on inbox triage.",
        target_url="https://kalevent.com/blog/post-abc",
    )
    db.session.add(item)
    db.session.commit()

    fetched = db.session.query(SocialDistributionQueueItem).first()
    assert fetched.status == "pending"
    assert fetched.attempts == 0
    assert fetched.posted_at is None
    assert fetched.created_at is not None


def test_queue_item_unique_per_content_platform(app, db, kalevent_account):
    item1 = SocialDistributionQueueItem(
        account_id=2, content_type="blog", content_id="post-abc",
        platform="linkedin", caption="x", target_url="u",
    )
    db.session.add(item1)
    db.session.commit()

    item2 = SocialDistributionQueueItem(
        account_id=2, content_type="blog", content_id="post-abc",
        platform="linkedin", caption="y", target_url="u",
    )
    db.session.add(item2)
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


def test_queue_item_allows_same_content_on_different_platforms(app, db, kalevent_account):
    for p in ("linkedin", "twitter", "facebook"):
        db.session.add(SocialDistributionQueueItem(
            account_id=2, content_type="blog", content_id="post-abc",
            platform=p, caption="x", target_url="u",
        ))
    db.session.commit()
    assert db.session.query(SocialDistributionQueueItem).count() == 3
