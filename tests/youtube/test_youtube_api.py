import pytest
from unittest.mock import patch, MagicMock


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture(autouse=True)
def auth_bypass():
    """Patch JWT auth so all requests pass login_required_settings."""
    mock_user = MagicMock()
    mock_user.id = 1
    with (
        patch("src.settings.verify_jwt_in_request"),
        patch("src.settings.get_jwt", return_value={"account_id": 2}),
        patch("src.settings.get_jwt_identity", return_value="1"),
        patch("src.settings.account_allows_api", return_value=True),
        patch("src.extensions.db.session.get", return_value=mock_user),
    ):
        yield


def test_list_videos_empty(client, app):
    resp = client.get("/api/v1/youtube/videos", headers={"Content-Type": "application/json"})
    assert resp.status_code == 200
    assert resp.get_json() == []


def test_list_videos_returns_records(client, app, db):
    from src.models.leads import ICPPainPoint
    from src.models.marketing import ICPConfig
    from src.models.campaigns import YouTubeVideo

    with app.app_context():
        cfg = ICPConfig(account_id=2)
        db.session.add(cfg)
        db.session.flush()
        pp = ICPPainPoint(
            account_id=2, icp_config_id=cfg.id,
            pain_point="Weekend backlog", consequence="Churn", priority=10,
        )
        db.session.add(pp)
        db.session.flush()
        v = YouTubeVideo(
            account_id=2, icp_pain_point_id=pp.id,
            video_type="long_form", video_style="avatar",
            title="Never miss a support email", status="published",
        )
        db.session.add(v)
        db.session.commit()

    resp = client.get("/api/v1/youtube/videos")
    data = resp.get_json()
    assert resp.status_code == 200
    assert len(data) == 1
    assert data[0]["title"] == "Never miss a support email"
    assert data[0]["pain_point"] == "Weekend backlog"
    assert data[0]["video_type"] == "long_form"


def test_list_videos_status_filter(client, app, db):
    from src.models.leads import ICPPainPoint
    from src.models.marketing import ICPConfig
    from src.models.campaigns import YouTubeVideo

    with app.app_context():
        cfg = ICPConfig(account_id=2)
        db.session.add(cfg)
        db.session.flush()
        pp = ICPPainPoint(
            account_id=2, icp_config_id=cfg.id,
            pain_point="p", consequence="c", priority=1,
        )
        db.session.add(pp)
        db.session.flush()
        for status in ("published", "rendering", "script_ready"):
            db.session.add(YouTubeVideo(
                account_id=2, icp_pain_point_id=pp.id,
                video_type="long_form", video_style="avatar", status=status,
            ))
        db.session.commit()

    resp = client.get("/api/v1/youtube/videos?status=published")
    data = resp.get_json()
    assert resp.status_code == 200
    assert len(data) == 1
    assert data[0]["status"] == "published"


def test_list_pain_points(client, app, db):
    from src.models.leads import ICPPainPoint
    from src.models.marketing import ICPConfig

    with app.app_context():
        cfg = ICPConfig(account_id=2)
        db.session.add(cfg)
        db.session.flush()
        db.session.add(ICPPainPoint(
            account_id=2, icp_config_id=cfg.id,
            pain_point="Weekend backlog", consequence="Churn", priority=10,
        ))
        db.session.commit()

    resp = client.get("/api/v1/youtube/pain_points")
    data = resp.get_json()
    assert resp.status_code == 200
    assert len(data) == 1
    assert data[0]["pain_point"] == "Weekend backlog"
    assert data[0]["priority"] == 10


def test_create_pain_point(client, app, db):
    from src.models.marketing import ICPConfig

    with app.app_context():
        db.session.add(ICPConfig(account_id=2))
        db.session.commit()

    resp = client.post(
        "/api/v1/youtube/pain_points",
        json={"pain_point": "Manual outreach", "consequence": "Hours wasted", "priority": 8},
    )
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "ok"

    from src.models.leads import ICPPainPoint
    with app.app_context():
        pp = ICPPainPoint.query.filter_by(account_id=2).first()
        assert pp.pain_point == "Manual outreach"


def test_trigger_unknown_task_returns_400(client):
    resp = client.post("/api/v1/youtube/trigger/unknown_task")
    assert resp.status_code == 400


def test_trigger_valid_task_queues(client):
    with patch("src.api.v1.youtube.generate_scripts") as mock_task:
        mock_task.delay = MagicMock()
        resp = client.post("/api/v1/youtube/trigger/generate_scripts")
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "queued"
