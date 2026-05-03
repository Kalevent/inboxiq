import pytest


@pytest.fixture
def client(app):
    return app.test_client()


def test_webhook_returns_200_for_unknown_job_id(client):
    resp = client.post("/api/v1/heygen/webhook", json={
        "event_type": "avatar_video.success",
        "event_data": {"video_id": "no-such-job", "video_url": "https://cdn.heygen.com/v.mp4"},
    })
    assert resp.status_code == 200
    assert resp.get_json()["ok"] is True


def test_webhook_sets_render_complete_on_success(client, app, db):
    from src.models.campaigns import VideoRender
    with app.app_context():
        r = VideoRender(
            account_id=2, programme="youtube", video_style="avatar", aspect_ratio="16:9",
            heygen_job_id="job-ok-001", status="rendering",
        )
        db.session.add(r)
        db.session.commit()

    resp = client.post("/api/v1/heygen/webhook", json={
        "event_type": "avatar_video.success",
        "event_data": {"video_id": "job-ok-001", "video_url": "https://cdn.heygen.com/out.mp4"},
    })
    assert resp.status_code == 200

    with app.app_context():
        r = VideoRender.query.filter_by(heygen_job_id="job-ok-001").first()
        assert r.status == "render_complete"
        assert r.heygen_render_url == "https://cdn.heygen.com/out.mp4"
        assert r.render_completed_at is not None


def test_webhook_sets_failed_on_failure(client, app, db):
    from src.models.campaigns import VideoRender
    with app.app_context():
        r = VideoRender(
            account_id=2, programme="youtube", video_style="avatar", aspect_ratio="16:9",
            heygen_job_id="job-fail-002", status="rendering",
        )
        db.session.add(r)
        db.session.commit()

    resp = client.post("/api/v1/heygen/webhook", json={
        "event_type": "avatar_video.fail",
        "event_data": {"video_id": "job-fail-002"},
    })
    assert resp.status_code == 200

    with app.app_context():
        r = VideoRender.query.filter_by(heygen_job_id="job-fail-002").first()
        assert r.status == "failed"


def test_webhook_missing_video_id_returns_400(client):
    resp = client.post("/api/v1/heygen/webhook", json={
        "event_type": "avatar_video.success",
        "event_data": {},
    })
    assert resp.status_code == 400
    assert "missing video_id" in resp.get_json()["error"]


def test_webhook_non_dict_event_data_returns_400(client):
    resp = client.post("/api/v1/heygen/webhook", json={
        "event_type": "avatar_video.success",
        "event_data": "not-a-dict",
    })
    assert resp.status_code == 400
    assert "invalid event_data" in resp.get_json()["error"]


def test_webhook_unrecognised_event_type_is_silent_noop(client, app, db):
    from src.models.campaigns import VideoRender
    with app.app_context():
        r = VideoRender(
            account_id=2, programme="youtube", video_style="avatar", aspect_ratio="16:9",
            heygen_job_id="job-noop-003", status="rendering",
        )
        db.session.add(r)
        db.session.commit()

    resp = client.post("/api/v1/heygen/webhook", json={
        "event_type": "avatar_video.processing",
        "event_data": {"video_id": "job-noop-003"},
    })
    assert resp.status_code == 200

    with app.app_context():
        r = VideoRender.query.filter_by(heygen_job_id="job-noop-003").first()
        assert r.status == "rendering"  # unchanged — no-op
