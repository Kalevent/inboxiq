from unittest.mock import patch
from src.models.campaigns import SocialDistributionQueueItem
from src.models.content import BlogPost


def test_enqueue_blog_creates_three_rows(app, db, kalevent_account):
    post = BlogPost(
        id="post-x", account_id=2, title="A title",
        slug="a-title", canonical_url="https://kalevent.com/blog/a-title",
        status="published", excerpt="An excerpt",
    )
    db.session.add(post)
    db.session.commit()

    fake_content = {
        "linkedin": {"text": "LI body", "hashtags": "#a #b"},
        "twitter": {"text": "TW body", "hashtags": "#a"},
        "facebook": {"text": "FB body", "hashtags": ""},
    }
    with patch("src.marketing.social_distribution._generate_social_content", return_value=fake_content):
        from src.marketing.social_distribution import enqueue_blog_post
        n = enqueue_blog_post(post)
    assert n == 3

    rows = db.session.query(SocialDistributionQueueItem).order_by(SocialDistributionQueueItem.platform).all()
    assert [r.platform for r in rows] == ["facebook", "linkedin", "twitter"]
    li = [r for r in rows if r.platform == "linkedin"][0]
    assert li.account_id == 2
    assert li.content_type == "blog"
    assert li.content_id == "post-x"
    assert li.target_url == "https://kalevent.com/blog/a-title"
    assert li.caption == "LI body\n\n#a #b"
    assert li.status == "pending"


def test_enqueue_blog_idempotent(app, db, kalevent_account):
    post = BlogPost(
        id="post-x", account_id=2, title="t", slug="t",
        canonical_url="https://kalevent.com/blog/t", status="published",
    )
    db.session.add(post)
    db.session.commit()

    fake_content = {p: {"text": "x", "hashtags": ""} for p in ("linkedin","twitter","facebook")}
    with patch("src.marketing.social_distribution._generate_social_content", return_value=fake_content):
        from src.marketing.social_distribution import enqueue_blog_post
        enqueue_blog_post(post)
        enqueue_blog_post(post)  # second call should not duplicate
    assert db.session.query(SocialDistributionQueueItem).count() == 3


def test_enqueue_video_creates_three_rows(app, db, kalevent_account):
    from src.models.campaigns import VideoRender, YouTubeVideo
    from src.models.marketing import ICPConfig
    from src.models.leads import ICPPainPoint

    icp_config = ICPConfig(id="icp-cfg-1", account_id=2)
    db.session.add(icp_config)
    db.session.commit()

    pain_point = ICPPainPoint(
        id="pain-1", account_id=2, icp_config_id="icp-cfg-1",
        pain_point="Endless email chains waste hours", consequence="Lost productivity",
    )
    db.session.add(pain_point)
    db.session.commit()

    render = VideoRender(
        id="render-1", account_id=2, programme="youtube",
        video_style="avatar", aspect_ratio="9:16", status="delivered",
    )
    db.session.add(render)
    db.session.commit()
    video = YouTubeVideo(
        id="vid-1", account_id=2, video_render_id="render-1",
        icp_pain_point_id="pain-1",
        video_type="short", title="Endless Email Chains No More | InboxIQ",
        status="published", youtube_url="https://www.youtube.com/watch?v=YN1JHIARDvs",
        utm_medium="short", utm_campaign="endless-email-chains",
    )
    db.session.add(video)
    db.session.commit()

    def fake_caption(**kwargs):
        return type("R", (), {
            "caption_text": f"caption for {kwargs['platform']}",
            "hashtags": f"#{kwargs['platform']}",
        })()

    with patch("src.marketing.social_distribution._generate_video_caption", side_effect=fake_caption):
        from src.marketing.social_distribution import enqueue_youtube_video
        n = enqueue_youtube_video(video, render, pain_point_text="x")
    assert n == 3

    rows = db.session.query(SocialDistributionQueueItem).all()
    assert {r.platform for r in rows} == {"linkedin", "twitter", "facebook"}
    for r in rows:
        assert r.content_type == "video"
        assert r.content_id == "vid-1"
        assert r.target_url == "https://www.youtube.com/watch?v=YN1JHIARDvs"
