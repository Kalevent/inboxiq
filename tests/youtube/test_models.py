import pytest
from datetime import datetime, timezone
from src.models.leads import ICPPainPoint
from src.models.campaigns import YouTubeVideo


def test_icp_pain_point_creation(db):
    pp = ICPPainPoint(
        account_id=1,
        icp_config_id="test-config-id",
        pain_point="Support emails pile up unread over the weekend",
        consequence="Customers churn before Monday",
        persona="Head of Support",
        priority=10,
    )
    db.session.add(pp)
    db.session.commit()
    fetched = db.session.get(ICPPainPoint, pp.id)
    assert fetched.pain_point == "Support emails pile up unread over the weekend"
    assert fetched.active is True
    assert fetched.priority == 10


def test_icp_pain_point_requires_pain_point_and_consequence(db):
    with pytest.raises(Exception):
        pp = ICPPainPoint(account_id=1, icp_config_id="x")
        db.session.add(pp)
        db.session.commit()
    db.session.rollback()


def test_youtube_video_creation(db):
    video = YouTubeVideo(
        account_id=1,
        icp_pain_point_id="test-pain-id",
        video_type="long_form",
        video_style="avatar",
        title="Never miss a support email again | InboxIQ",
        utm_slug="yt-long-inbox-chaos-may-2026",
        utm_medium="long_form",
        utm_campaign="inbox-chaos-may-2026",
    )
    db.session.add(video)
    db.session.commit()
    fetched = db.session.get(YouTubeVideo, video.id)
    assert fetched.status == "script_pending"
    assert fetched.video_style == "avatar"
    assert fetched.utm_source == "youtube"


def test_youtube_video_utm_slug_unique(db):
    v1 = YouTubeVideo(
        account_id=1, icp_pain_point_id="pid", video_type="long_form",
        utm_slug="unique-slug-abc", utm_medium="long_form"
    )
    v2 = YouTubeVideo(
        account_id=1, icp_pain_point_id="pid", video_type="short",
        utm_slug="unique-slug-abc", utm_medium="short"
    )
    db.session.add(v1)
    db.session.commit()
    db.session.add(v2)
    with pytest.raises(Exception):
        db.session.commit()
    db.session.rollback()


def test_short_links_to_parent(db):
    parent = YouTubeVideo(
        account_id=1, icp_pain_point_id="pid", video_type="long_form",
        utm_slug="parent-slug-xyz", utm_medium="long_form"
    )
    db.session.add(parent)
    db.session.commit()
    short = YouTubeVideo(
        account_id=1, icp_pain_point_id="pid", video_type="short",
        parent_video_id=parent.id, utm_slug="short-slug-xyz", utm_medium="short"
    )
    db.session.add(short)
    db.session.commit()
    assert short.parent_video_id == parent.id
