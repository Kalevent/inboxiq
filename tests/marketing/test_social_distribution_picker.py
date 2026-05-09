from unittest.mock import patch
from datetime import datetime, timezone, timedelta

from src.models.campaigns import SocialDistributionQueueItem
from src.models.core import InboxConnection

# Call .run() on Celery tasks to bypass the ContextTask wrapper (which would
# push a separate app context with a different in-memory SQLite database).


def _seed_connection(db, account_id, provider="linkedin_social"):
    db.session.add(InboxConnection(
        id=f"c-{account_id}-{provider}", account_id=account_id, user_id=1,
        provider=provider, status="connected", metadata_json={},
    ))
    db.session.commit()


def _seed_pending(db, account_id, platform, content_id, created_at=None):
    item = SocialDistributionQueueItem(
        account_id=account_id, content_type="blog", content_id=content_id,
        platform=platform, caption=f"caption-{content_id}-{platform}",
        target_url=f"https://example.com/{content_id}",
    )
    if created_at:
        item.created_at = created_at
    db.session.add(item)
    db.session.commit()
    return item


def test_picker_picks_oldest_pending_per_account_platform(app, db, kalevent_account):
    _seed_connection(db, 2, "linkedin_social")
    now = datetime.now(timezone.utc)
    older = _seed_pending(db, 2, "linkedin", "post-A", created_at=now - timedelta(days=2))
    newer = _seed_pending(db, 2, "linkedin", "post-B", created_at=now - timedelta(days=1))

    with patch("src.marketing.social_distribution._post_to_linkedin",
               return_value={"status": "ok", "post_url": "https://li.com/x"}):
        from src.marketing.social_distribution import run_social_distribution_queue
        result = run_social_distribution_queue.run()

    db.session.refresh(older)
    db.session.refresh(newer)
    assert older.status == "posted"
    assert newer.status == "pending"
    assert older.posted_url == "https://li.com/x"
    assert older.posted_at is not None
    assert result["posted"] == 1


def test_picker_marks_failed_after_three_attempts(app, db, kalevent_account):
    _seed_connection(db, 2, "linkedin_social")
    item = _seed_pending(db, 2, "linkedin", "post-X")
    item.attempts = 2
    db.session.commit()

    with patch("src.marketing.social_distribution._post_to_linkedin",
               return_value={"status": "error", "error": "boom"}):
        from src.marketing.social_distribution import run_social_distribution_queue
        run_social_distribution_queue.run()

    db.session.refresh(item)
    assert item.status == "failed"
    assert item.attempts == 3
    assert "boom" in (item.error or "")


def test_picker_skips_accounts_without_connections(app, db, kalevent_account):
    _seed_pending(db, 2, "linkedin", "post-A")  # NO InboxConnection seeded

    with patch("src.marketing.social_distribution._post_to_linkedin") as li:
        from src.marketing.social_distribution import run_social_distribution_queue
        run_social_distribution_queue.run()
        li.assert_not_called()


def test_picker_one_per_platform_per_run(app, db, kalevent_account):
    _seed_connection(db, 2, "linkedin_social")
    _seed_connection(db, 2, "twitter_social")
    a = _seed_pending(db, 2, "linkedin", "blog-1")
    b = _seed_pending(db, 2, "linkedin", "blog-2")
    c = _seed_pending(db, 2, "twitter", "blog-1")

    posted = []
    def ok(item):
        posted.append((item.platform, item.content_id))
        return {"status": "ok", "post_url": "https://x"}

    with patch("src.marketing.social_distribution._post_to_linkedin", side_effect=ok), \
         patch("src.marketing.social_distribution._post_to_twitter", side_effect=ok), \
         patch("src.marketing.social_distribution._post_to_facebook", side_effect=ok):
        from src.marketing.social_distribution import run_social_distribution_queue
        run_social_distribution_queue.run()

    assert len(posted) == 2  # one linkedin, one twitter
    assert ("linkedin", "blog-1") in posted  # oldest first
    assert ("twitter", "blog-1") in posted
