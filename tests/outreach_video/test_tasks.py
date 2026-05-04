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
