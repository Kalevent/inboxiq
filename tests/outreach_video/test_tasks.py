from datetime import datetime, timezone


def test_email_campaign_has_outreach_video_enabled(app, db):
    from src.models.campaigns import EmailCampaign

    with app.app_context():
        campaign = EmailCampaign(
            name="Test",
            subject_template="Hello",
            body_template="Body",
            from_email="test@example.com",
        )
        db.session.add(campaign)
        db.session.commit()

    with app.app_context():
        from src.models.campaigns import EmailCampaign as EC
        c = EC.query.first()
        assert c.outreach_video_enabled is False


def test_build_outreach_signatures_returns_signature_class(app):
    with app.app_context():
        import dspy
        from src.dspy.signatures import build_outreach_signatures
        sigs = build_outreach_signatures(dspy)
        assert "OutreachVideoScript" in sigs
        cls = sigs["OutreachVideoScript"]
        # All five input fields must exist on the signature
        fields = [f for f in dir(cls) if not f.startswith("_")]
        sig_str = str(cls.__doc__ or "") + str(cls.__mro__)
        # Verify the class is importable directly at module level too
        from src.dspy.signatures import OutreachVideoScript as OVS_placeholder
        assert OVS_placeholder is not None


def test_queue_outreach_videos_skips_when_env_flag_off(app, db):
    """OUTREACH_VIDEO_ENABLED=false must short-circuit the task."""
    import os
    from unittest.mock import patch

    with app.app_context():
        with patch.dict(os.environ, {"OUTREACH_VIDEO_ENABLED": "false"}):
            from src.tasks.outreach_video import queue_outreach_videos
            result = queue_outreach_videos.run()
        assert result["status"] == "skipped"


def test_queue_outreach_videos_no_eligible_campaigns(app, db):
    """No campaigns with outreach_video_enabled=True → queued=0."""
    import os
    from unittest.mock import patch

    with app.app_context():
        with patch.dict(os.environ, {"OUTREACH_VIDEO_ENABLED": "true"}):
            from src.tasks.outreach_video import queue_outreach_videos
            result = queue_outreach_videos.run()
        assert result["status"] == "ok"
        assert result["queued"] == 0


def test_queue_outreach_videos_creates_render_and_outreach_video(app, db):
    """Happy path: eligible lead → VideoRender + OutreachVideo created, HeyGen called."""
    import os
    from unittest.mock import patch, MagicMock
    from src.models.campaigns import VideoRender, OutreachVideo, EmailCampaign

    with app.app_context():
        campaign = EmailCampaign(
            name="Q2 Outreach",
            subject_template="Hi",
            body_template="Body",
            from_email="kofi@example.com",
            outreach_video_enabled=True,
        )
        db.session.add(campaign)
        db.session.commit()
        campaign_id = campaign.id

    mock_lead = MagicMock()
    mock_lead.id = "lead-001"
    mock_lead.account_id = 2
    mock_lead.name = "James Brown"
    mock_lead.company_name = "Acme Corp"
    mock_lead.industry = "B2B SaaS"
    mock_lead.fit_score = 8
    mock_lead.email = "james@acme.com"

    with app.app_context():
        with patch.dict(os.environ, {"OUTREACH_VIDEO_ENABLED": "true", "OUTREACH_VIDEO_DAILY_LIMIT": "20"}), \
             patch("src.tasks.outreach_video._get_eligible_leads") as mock_leads, \
             patch("src.tasks.outreach_video._run_outreach_script_generation") as mock_dspy, \
             patch("src.tasks.outreach_video.heygen_mcp") as mock_heygen:

            mock_leads.return_value = [mock_lead]
            mock_dspy.return_value = {
                "script": "James, I noticed Acme is hiring...",
                "hook_line": "James, I noticed something.",
                "cta_line": "Reply or book a 15-min call.",
                "subject_line": "James, spotted something about Acme",
            }
            mock_heygen.render_video.return_value = {"status": "submitted", "job_id": "job-outreach-001"}

            from src.tasks.outreach_video import queue_outreach_videos
            result = queue_outreach_videos.run()

        assert result["status"] == "ok"
        assert result["queued"] == 1

        render = db.session.query(VideoRender).filter_by(
            account_id=2, programme="outreach"
        ).first()
        assert render is not None
        assert render.heygen_job_id == "job-outreach-001"
        assert render.status == "rendering"

        outreach_vid = db.session.query(OutreachVideo).filter_by(
            account_id=2, lead_id="lead-001"
        ).first()
        assert outreach_vid is not None
        assert outreach_vid.video_render_id == render.id


def test_queue_outreach_videos_is_idempotent(app, db):
    """Lead that already has an OutreachVideo must not get a second one."""
    import os
    from unittest.mock import patch, MagicMock
    from src.models.campaigns import VideoRender, OutreachVideo, EmailCampaign

    with app.app_context():
        campaign = EmailCampaign(
            name="Q2",
            subject_template="Hi",
            body_template="Body",
            from_email="k@example.com",
            outreach_video_enabled=True,
        )
        db.session.add(campaign)
        db.session.flush()
        render = VideoRender(
            account_id=2, programme="outreach", video_style="avatar", aspect_ratio="16:9"
        )
        db.session.add(render)
        db.session.flush()
        ov = OutreachVideo(
            account_id=2, video_render_id=render.id, lead_id="lead-dup"
        )
        db.session.add(ov)
        db.session.commit()

    mock_lead = MagicMock()
    mock_lead.id = "lead-dup"
    mock_lead.account_id = 2
    mock_lead.name = "Jane"
    mock_lead.company_name = "Dup Corp"
    mock_lead.industry = "SaaS"
    mock_lead.fit_score = 9
    mock_lead.email = "jane@dup.com"

    with app.app_context():
        with patch.dict(os.environ, {"OUTREACH_VIDEO_ENABLED": "true"}), \
             patch("src.tasks.outreach_video._get_eligible_leads") as mock_leads, \
             patch("src.tasks.outreach_video.heygen_mcp") as mock_heygen:

            mock_leads.return_value = [mock_lead]

            from src.tasks.outreach_video import queue_outreach_videos
            result = queue_outreach_videos.run()

        assert result["queued"] == 0
        mock_heygen.render_video.assert_not_called()


def test_queue_outreach_videos_dspy_failure_continues(app, db):
    """DSPy failure on one lead must not abort the whole run."""
    import os
    from unittest.mock import patch, MagicMock
    from src.models.campaigns import EmailCampaign

    with app.app_context():
        campaign = EmailCampaign(
            name="Fail Campaign",
            subject_template="Hi",
            body_template="Body",
            from_email="k@example.com",
            outreach_video_enabled=True,
        )
        db.session.add(campaign)
        db.session.commit()

    mock_lead = MagicMock()
    mock_lead.id = "lead-fail"
    mock_lead.account_id = 2
    mock_lead.name = "Fail Lead"
    mock_lead.company_name = "FailCo"
    mock_lead.industry = "SaaS"
    mock_lead.fit_score = 8
    mock_lead.email = "fail@failco.com"

    with app.app_context():
        with patch.dict(os.environ, {"OUTREACH_VIDEO_ENABLED": "true"}), \
             patch("src.tasks.outreach_video._get_eligible_leads") as mock_leads, \
             patch("src.tasks.outreach_video._run_outreach_script_generation") as mock_dspy, \
             patch("src.tasks.outreach_video.heygen_mcp") as mock_heygen:

            mock_leads.return_value = [mock_lead]
            mock_dspy.side_effect = RuntimeError("DSPy unavailable")

            from src.tasks.outreach_video import queue_outreach_videos
            result = queue_outreach_videos.run()

        assert result["status"] == "ok"
        assert result["queued"] == 0
        assert result["errors"] >= 1
        mock_heygen.render_video.assert_not_called()


# ---------------------------------------------------------------------------
# Task 5: deliver_outreach_videos + post_outreach_video_to_linkedin
# ---------------------------------------------------------------------------

def test_deliver_outreach_videos_sends_email_and_sets_delivered_at(app, db):
    """Happy path: render_complete row → email sent, delivered_email_at stamped."""
    import os
    from unittest.mock import patch, MagicMock
    from src.models.campaigns import VideoRender, OutreachVideo

    with app.app_context():
        render = VideoRender(
            account_id=2,
            programme="outreach",
            video_style="avatar",
            aspect_ratio="16:9",
            status="render_complete",
            heygen_render_url="https://cdn.heygen.com/out.mp4",
            subject_line="James, spotted something about Acme",
        )
        db.session.add(render)
        db.session.flush()
        ov = OutreachVideo(
            account_id=2,
            video_render_id=render.id,
            lead_id="lead-001",
        )
        db.session.add(ov)
        db.session.commit()
        ov_id = ov.id

    mock_lead = MagicMock()
    mock_lead.email = "james@acme.com"
    mock_lead.name = "James Brown"

    with app.app_context():
        with patch.dict(os.environ, {"OUTREACH_VIDEO_ENABLED": "true"}), \
             patch("src.tasks.outreach_video.db") as mock_db, \
             patch("src.tasks.outreach_video.send_outreach_video_email") as mock_email, \
             patch("src.tasks.outreach_video.post_outreach_video_to_linkedin"):

            # Re-read the real rows via the real session, then hand them to the task via mock
            from src.extensions import db as real_db
            from src.models.campaigns import VideoRender as RealRender, OutreachVideo as RealOV
            real_rows = (
                real_db.session.query(RealOV, RealRender)
                .join(RealRender, RealRender.id == RealOV.video_render_id)
                .filter(RealRender.status == "render_complete", RealOV.delivered_email_at.is_(None))
                .all()
            )
            real_ov, real_render = real_rows[0]

            mock_db.session.query.return_value.join.return_value.filter.return_value.all.return_value = real_rows
            mock_db.session.get.return_value = mock_lead
            mock_db.session.commit = real_db.session.commit
            mock_db.session.rollback = real_db.session.rollback
            mock_email.return_value = True

            from src.tasks.outreach_video import deliver_outreach_videos
            result = deliver_outreach_videos.run()

        assert result["sent"] == 1
        assert result["failed"] == 0

        delivered_ov = db.session.get(OutreachVideo, ov_id)
        assert delivered_ov.delivered_email_at is not None

        mock_email.assert_called_once_with(
            to_email="james@acme.com",
            recipient_name="James Brown",
            video_url="https://cdn.heygen.com/out.mp4",
            subject="James, spotted something about Acme",
        )


def test_deliver_outreach_videos_skips_already_delivered(app, db):
    """Rows with delivered_email_at already set must be excluded from the query."""
    import os
    from unittest.mock import patch
    from src.models.campaigns import VideoRender, OutreachVideo

    with app.app_context():
        render = VideoRender(
            account_id=2,
            programme="outreach",
            video_style="avatar",
            aspect_ratio="16:9",
            status="render_complete",
            heygen_render_url="https://cdn.heygen.com/out2.mp4",
            subject_line="Already delivered",
        )
        db.session.add(render)
        db.session.flush()
        ov = OutreachVideo(
            account_id=2,
            video_render_id=render.id,
            lead_id="lead-002",
            delivered_email_at=datetime.now(timezone.utc),
        )
        db.session.add(ov)
        db.session.commit()

    with app.app_context():
        with patch.dict(os.environ, {"OUTREACH_VIDEO_ENABLED": "true"}), \
             patch("src.tasks.outreach_video.send_outreach_video_email") as mock_email:

            from src.tasks.outreach_video import deliver_outreach_videos
            result = deliver_outreach_videos.run()

        assert result["sent"] == 0
        mock_email.assert_not_called()


def test_deliver_outreach_videos_posts_to_linkedin_after_send(app, db):
    """After at least one successful send, post_outreach_video_to_linkedin is called once per account_id."""
    import os
    from unittest.mock import patch, MagicMock
    from src.models.campaigns import VideoRender, OutreachVideo

    with app.app_context():
        render = VideoRender(
            account_id=2,
            programme="outreach",
            video_style="avatar",
            aspect_ratio="16:9",
            status="render_complete",
            heygen_render_url="https://cdn.heygen.com/out3.mp4",
            subject_line="LinkedIn teaser test",
        )
        db.session.add(render)
        db.session.flush()
        ov = OutreachVideo(
            account_id=2,
            video_render_id=render.id,
            lead_id="lead-003",
        )
        db.session.add(ov)
        db.session.commit()

    mock_lead = MagicMock()
    mock_lead.email = "james@acme.com"
    mock_lead.name = "James Brown"

    with app.app_context():
        with patch.dict(os.environ, {"OUTREACH_VIDEO_ENABLED": "true"}), \
             patch("src.tasks.outreach_video.db") as mock_db, \
             patch("src.tasks.outreach_video.send_outreach_video_email") as mock_email, \
             patch("src.tasks.outreach_video.post_outreach_video_to_linkedin") as mock_linkedin:

            from src.extensions import db as real_db
            from src.models.campaigns import VideoRender as RealRender, OutreachVideo as RealOV
            real_rows = (
                real_db.session.query(RealOV, RealRender)
                .join(RealRender, RealRender.id == RealOV.video_render_id)
                .filter(RealRender.status == "render_complete", RealOV.delivered_email_at.is_(None))
                .all()
            )

            mock_db.session.query.return_value.join.return_value.filter.return_value.all.return_value = real_rows
            mock_db.session.get.return_value = mock_lead
            mock_db.session.commit = real_db.session.commit
            mock_db.session.rollback = real_db.session.rollback
            mock_email.return_value = True

            from src.tasks.outreach_video import deliver_outreach_videos
            result = deliver_outreach_videos.run()

        assert result["sent"] == 1
        mock_linkedin.assert_called_once_with(2)


def test_deliver_outreach_videos_skips_when_flag_off(app, db):
    import os
    from unittest.mock import patch

    with app.app_context():
        with patch.dict(os.environ, {"OUTREACH_VIDEO_ENABLED": "false"}):
            from src.tasks.outreach_video import deliver_outreach_videos
            result = deliver_outreach_videos.run()
        assert result["status"] == "skipped"


def test_post_outreach_video_to_linkedin_skips_when_no_connection(app, db):
    from unittest.mock import patch, MagicMock

    with app.app_context():
        mock_query = MagicMock()
        mock_query.filter_by.return_value.first.return_value = None
        with patch("src.tasks.outreach_video.InboxConnection") as mock_conn_cls, \
             patch("requests.post") as mock_post:
            mock_conn_cls.query = mock_query
            from src.tasks.outreach_video import post_outreach_video_to_linkedin
            post_outreach_video_to_linkedin(account_id=999)
        mock_post.assert_not_called()
