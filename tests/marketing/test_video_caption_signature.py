def test_youtube_video_social_caption_signature_fields():
    import dspy
    from src.dspy.signatures import build_youtube_video_social_caption

    sig = build_youtube_video_social_caption(dspy)["YouTubeVideoSocialCaption"]
    # Inputs
    assert "title" in sig.model_fields
    assert "video_type" in sig.model_fields
    assert "pain_point_text" in sig.model_fields
    assert "youtube_url" in sig.model_fields
    assert "platform" in sig.model_fields
    # Outputs
    assert "caption_text" in sig.model_fields
    assert "hashtags" in sig.model_fields
