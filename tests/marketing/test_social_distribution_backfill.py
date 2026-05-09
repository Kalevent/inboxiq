from unittest.mock import patch
from src.models.campaigns import SocialDistributionQueueItem, YouTubeVideo, VideoRender
from src.models.content import BlogPost


def test_backfill_seeds_blogs_and_videos(app, db, kalevent_account):
    db.session.add(BlogPost(
        id="b1", account_id=2, title="t", slug="t",
        canonical_url="https://kalevent.com/blog/t", status="published",
    ))
    render = VideoRender(id="r1", account_id=2, programme="youtube",
                         video_style="avatar", aspect_ratio="9:16", status="delivered")
    db.session.add(render)
    db.session.commit()
    # Need ICPConfig + ICPPainPoint for YouTubeVideo.icp_pain_point_id NOT NULL FK.
    # Mirror the existing youtube enqueue test fixtures.
    from src.models.marketing import ICPConfig
    from src.models.leads import ICPPainPoint
    db.session.add(ICPConfig(id="icp-bf", account_id=2))
    db.session.commit()
    db.session.add(ICPPainPoint(id="pain-bf", account_id=2, icp_config_id="icp-bf",
                                pain_point="x", consequence="y"))
    db.session.commit()
    db.session.add(YouTubeVideo(
        id="v1", account_id=2, video_render_id="r1",
        icp_pain_point_id="pain-bf",
        video_type="short", title="title", status="published",
        youtube_url="https://www.youtube.com/watch?v=abc",
        utm_medium="short", utm_campaign="x",
    ))
    db.session.commit()

    fake_blog_content = {p: {"text": "x", "hashtags": ""} for p in ("linkedin","twitter","facebook")}
    with patch("src.marketing.social_distribution.generate_social_content", return_value=fake_blog_content), \
         patch("src.marketing.social_distribution._generate_video_caption",
               side_effect=lambda **kw: type("R", (), {"caption_text":"c","hashtags":""})()):
        from src.marketing.social_distribution import backfill_social_distribution
        result = backfill_social_distribution.run()

    assert result["blogs_enqueued"] == 1
    assert result["videos_enqueued"] == 1
    assert db.session.query(SocialDistributionQueueItem).count() == 6  # 3 blog + 3 video


def test_backfill_is_idempotent(app, db, kalevent_account):
    db.session.add(BlogPost(
        id="b1", account_id=2, title="t", slug="t",
        canonical_url="https://kalevent.com/blog/t", status="published",
    ))
    db.session.commit()

    fake_content = {p: {"text": "x", "hashtags": ""} for p in ("linkedin","twitter","facebook")}
    with patch("src.marketing.social_distribution.generate_social_content", return_value=fake_content):
        from src.marketing.social_distribution import backfill_social_distribution
        backfill_social_distribution.run()
        backfill_social_distribution.run()  # second run inserts no new rows

    assert db.session.query(SocialDistributionQueueItem).count() == 3
