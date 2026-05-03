import pytest


def test_video_render_create(app, db):
    from src.models.campaigns import VideoRender
    with app.app_context():
        r = VideoRender(account_id=2, programme="youtube", video_style="avatar", aspect_ratio="16:9")
        db.session.add(r)
        db.session.commit()
        assert r.id is not None
        assert r.status == "pending"
        assert r.heygen_job_id is None


def test_onboarding_video_create(app, db):
    from src.models.campaigns import VideoRender, OnboardingVideo
    with app.app_context():
        r = VideoRender(account_id=2, programme="onboarding", video_style="avatar", aspect_ratio="16:9")
        db.session.add(r)
        db.session.flush()
        ov = OnboardingVideo(
            account_id=2,
            video_render_id=r.id,
            recipient_user_id=1,
            recipient_name="Sarah Jones",
            recipient_company="Acme Corp",
        )
        db.session.add(ov)
        db.session.commit()
        assert ov.id is not None
        assert ov.email_sent_at is None


def test_outreach_video_create(app, db):
    import uuid
    from src.models.campaigns import VideoRender, OutreachVideo
    with app.app_context():
        r = VideoRender(account_id=2, programme="outreach", video_style="avatar", aspect_ratio="16:9")
        db.session.add(r)
        db.session.flush()
        # SQLite test DB does not enforce FK constraints — fake lead_id is safe here
        ov = OutreachVideo(
            account_id=2,
            video_render_id=r.id,
            lead_id=str(uuid.uuid4()),
        )
        db.session.add(ov)
        db.session.commit()
        assert ov.id is not None
        assert ov.delivered_email_at is None
        assert ov.delivered_linkedin_at is None
