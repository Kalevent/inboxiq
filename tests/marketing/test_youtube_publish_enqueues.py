from unittest.mock import patch, MagicMock
from src.models.campaigns import SocialDistributionQueueItem


def test_publish_videos_enqueues_after_youtube_upload(app, db, kalevent_account):
    from src.models.campaigns import VideoRender, YouTubeVideo
    from src.models.marketing import ICPConfig
    from src.models.leads import ICPPainPoint

    db.session.add(ICPConfig(id="icp-pub", account_id=2))
    db.session.commit()
    db.session.add(ICPPainPoint(id="pain-pub", account_id=2, icp_config_id="icp-pub",
                                pain_point="x", consequence="y"))
    db.session.commit()

    render = VideoRender(
        id="r-pub", account_id=2, programme="youtube",
        video_style="avatar", aspect_ratio="9:16", status="render_complete",
        heygen_job_id="job-1",
    )
    db.session.add(render)
    db.session.add(YouTubeVideo(
        id="v-pub", account_id=2, video_render_id="r-pub",
        icp_pain_point_id="pain-pub",
        video_type="short", title="t",
        utm_medium="short", utm_campaign="c",
        status="render_complete", description="desc {{UTM_LINK}}",
        tags=[],
    ))
    db.session.commit()

    fake_caption = lambda **kw: type("R", (), {"caption_text":"c","hashtags":""})()

    with patch("src.tasks.youtube.heygen_mcp") as heygen, \
         patch("src.tasks.youtube.youtube_mcp") as ytmcp, \
         patch("src.marketing.social_distribution._generate_video_caption", side_effect=fake_caption):
        heygen.get_render_status.return_value = {"status": "completed", "render_url": "https://x.mp4"}
        ytmcp.upload_video.return_value = {"status": "published",
                                           "youtube_video_id": "yt-id",
                                           "youtube_url": "https://www.youtube.com/watch?v=yt-id"}
        ytmcp.add_end_screen.return_value = None
        ytmcp.add_card.return_value = None
        ytmcp.post_pinned_comment.return_value = None

        from src.tasks.youtube import publish_videos
        publish_videos.run(account_id=2)

    items = db.session.query(SocialDistributionQueueItem).all()
    assert len(items) == 3
    assert {i.platform for i in items} == {"linkedin","twitter","facebook"}
    assert all(i.target_url == "https://www.youtube.com/watch?v=yt-id" for i in items)
