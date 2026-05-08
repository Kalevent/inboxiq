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


def test_long_form_script_has_product_context_inputs():
    """Long form must take product_name + product_value_proposition so the
    RESOLUTION section can name InboxIQ explicitly. Without these inputs the
    DSPy model defaults to the source blog post's framing (e.g. 'chatbots')
    and never mentions the product."""
    import dspy
    from src.dspy.signatures import build_youtube_signatures
    sig = build_youtube_signatures(dspy)["YouTubeLongFormScript"]
    fields = sig.model_fields
    assert "product_name" in fields, "YouTubeLongFormScript must accept product_name"
    assert "product_value_proposition" in fields, "YouTubeLongFormScript must accept product_value_proposition"


def test_short_script_has_product_name_input():
    """Shorts must also take product_name so the resolution beat names the
    product. Shorts are derived from the long form but DSPy can still drop
    the product mention without explicit instruction."""
    import dspy
    from src.dspy.signatures import build_youtube_signatures
    sig = build_youtube_signatures(dspy)["YouTubeShortScript"]
    fields = sig.model_fields
    assert "product_name" in fields, "YouTubeShortScript must accept product_name"


def test_seo_metadata_has_product_name_input():
    """SEO must take product_name so the title's 'How' segment describes the
    product's capability, not source-blog terminology (e.g. avoid 'Use
    Chatbots' when the product is InboxIQ)."""
    import dspy
    from src.dspy.signatures import build_youtube_signatures
    sig = build_youtube_signatures(dspy)["YouTubeSEOMetadata"]
    fields = sig.model_fields
    assert "product_name" in fields, "YouTubeSEOMetadata must accept product_name"
    assert "product_value_proposition" in fields, "YouTubeSEOMetadata must accept product_value_proposition"


def test_long_form_signature_instructs_product_in_resolution():
    """Signature instruction must explicitly require the product be named in the
    RESOLUTION beat — otherwise the model defaults to source-blog framing."""
    import dspy
    from src.dspy.signatures import build_youtube_signatures
    sig = build_youtube_signatures(dspy)["YouTubeLongFormScript"]
    instruction = (sig.__doc__ or "").lower()
    assert "resolution" in instruction
    # Must reference the product input, not just the literal "inboxiq" string —
    # otherwise the existing "InboxIQ must NOT appear in first 5 seconds" line
    # passes vacuously without any new resolution-level enforcement.
    assert (
        "name {product_name}" in instruction
        or "must name the product" in instruction
        or "must mention {product_name}" in instruction
        or "explicitly name {product_name}" in instruction
    ), "Long form signature must instruct the model to name the product in RESOLUTION"
