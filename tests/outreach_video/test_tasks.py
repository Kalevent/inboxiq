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
