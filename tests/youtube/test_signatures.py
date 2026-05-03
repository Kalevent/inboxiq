def test_youtube_signature_imports():
    from src.dspy.signatures import (
        YouTubeLongFormScript,
        YouTubeShortScript,
        YouTubeSEOMetadata,
        YouTubeIllustrationPrompts,
    )
    assert YouTubeLongFormScript is not None
    assert YouTubeShortScript is not None
    assert YouTubeSEOMetadata is not None
    assert YouTubeIllustrationPrompts is not None


def test_build_youtube_signatures_returns_all_four():
    import dspy
    from src.dspy.signatures import build_youtube_signatures
    sigs = build_youtube_signatures(dspy)
    assert "YouTubeLongFormScript" in sigs
    assert "YouTubeShortScript" in sigs
    assert "YouTubeSEOMetadata" in sigs
    assert "YouTubeIllustrationPrompts" in sigs
