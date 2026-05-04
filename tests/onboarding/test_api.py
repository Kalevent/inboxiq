import pytest


@pytest.fixture
def client(app):
    return app.test_client()


def test_dismiss_video_banner_no_record_returns_ok(client, app, auth_headers):
    """Returns 200 {"ok": true} even when no OnboardingVideo record exists."""
    resp = client.post(
        "/api/v1/onboarding/dismiss-video-banner",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.get_json()["ok"] is True


def test_dismiss_video_banner_sets_dismissed_at(client, app, db, auth_headers):
    from src.models.campaigns import VideoRender, OnboardingVideo

    with app.app_context():
        render = VideoRender(
            account_id=2, programme="onboarding", video_style="avatar", aspect_ratio="16:9"
        )
        db.session.add(render)
        db.session.flush()
        onboarding = OnboardingVideo(
            account_id=2, video_render_id=render.id,
            recipient_user_id=1, recipient_name="Sarah"
        )
        db.session.add(onboarding)
        db.session.commit()
        onboarding_id = onboarding.id

    resp = client.post(
        "/api/v1/onboarding/dismiss-video-banner",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.get_json()["ok"] is True

    with app.app_context():
        from src.models.campaigns import OnboardingVideo as OV
        ov = db.session.get(OV, onboarding_id)
        assert ov.banner_dismissed_at is not None


def test_dismiss_video_banner_requires_auth(client):
    """Returns 401 when no JWT token is provided."""
    resp = client.post("/api/v1/onboarding/dismiss-video-banner")
    assert resp.status_code == 401
