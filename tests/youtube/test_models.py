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
    from src.models.campaigns import VideoRender
    render = VideoRender(
        account_id=1, programme="youtube", video_style="avatar", aspect_ratio="16:9",
    )
    db.session.add(render)
    db.session.flush()

    video = YouTubeVideo(
        account_id=1,
        icp_pain_point_id="test-pain-id",
        video_type="long_form",
        video_style="avatar",
        video_render_id=render.id,
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
    assert fetched.video_render_id == render.id


def test_youtube_video_utm_slug_unique(db):
    from src.models.campaigns import VideoRender
    r1 = VideoRender(account_id=1, programme="youtube", video_style="avatar", aspect_ratio="16:9")
    r2 = VideoRender(account_id=1, programme="youtube", video_style="avatar", aspect_ratio="9:16")
    db.session.add_all([r1, r2])
    db.session.flush()

    v1 = YouTubeVideo(
        account_id=1, icp_pain_point_id="pid", video_type="long_form",
        video_render_id=r1.id, utm_slug="unique-slug-abc", utm_medium="long_form"
    )
    v2 = YouTubeVideo(
        account_id=1, icp_pain_point_id="pid", video_type="short",
        video_render_id=r2.id, utm_slug="unique-slug-abc", utm_medium="short"
    )
    db.session.add(v1)
    db.session.commit()
    db.session.add(v2)
    with pytest.raises(Exception):
        db.session.commit()
    db.session.rollback()


def test_short_links_to_parent(db):
    from src.models.campaigns import VideoRender
    r1 = VideoRender(account_id=1, programme="youtube", video_style="avatar", aspect_ratio="16:9")
    r2 = VideoRender(account_id=1, programme="youtube", video_style="avatar", aspect_ratio="9:16")
    db.session.add_all([r1, r2])
    db.session.flush()

    parent = YouTubeVideo(
        account_id=1, icp_pain_point_id="pid", video_type="long_form",
        video_render_id=r1.id, utm_slug="parent-slug-xyz", utm_medium="long_form"
    )
    db.session.add(parent)
    db.session.commit()
    short = YouTubeVideo(
        account_id=1, icp_pain_point_id="pid", video_type="short",
        video_render_id=r2.id, parent_video_id=parent.id,
        utm_slug="short-slug-xyz", utm_medium="short"
    )
    db.session.add(short)
    db.session.commit()
    assert short.parent_video_id == parent.id
