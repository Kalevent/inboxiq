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


def test_short_script_has_short_focus_input():
    """Each short needs a per-short focus so the two shorts come out distinct.
    Without a varying input the predictor receives identical prompts twice
    and (with caching/low temperature) returns identical text — production
    has been publishing duplicate shorts because of this."""
    import dspy
    from src.dspy.signatures import build_youtube_signatures
    sig = build_youtube_signatures(dspy)["YouTubeShortScript"]
    fields = sig.model_fields
    assert "short_focus" in fields, "YouTubeShortScript must accept short_focus to vary outputs"


def test_short_script_instruction_uses_link_in_description_cta():
    """Per the cadence skill, shorts CTA = 'Link in description. Free to start.'
    The spoken short script must NOT say kalevent.com — that's a long-form
    pattern. Today DSPy produces 'Start free at kalevent.com' for shorts
    because the signature's short_script field description says so."""
    import dspy
    from src.dspy.signatures import build_youtube_signatures
    sig = build_youtube_signatures(dspy)["YouTubeShortScript"]
    # dspy stores field desc under json_schema_extra['desc'], not pydantic .description
    field = sig.model_fields["short_script"]
    short_field_desc = ((field.json_schema_extra or {}).get("desc") or "").lower()
    assert "link in description" in short_field_desc, \
        "YouTubeShortScript.short_script field must instruct CTA = 'Link in description'"
    assert "kalevent.com" not in short_field_desc, \
        "YouTubeShortScript.short_script must not instruct domain CTA — that's long-form only"


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


def test_signatures_use_kalevent_com_not_inboxiq_com():
    """Production domain is kalevent.com (the /signup page). inboxiq.com is
    not registered — viewers clicking that link 404. Every signature
    instruction that names the CTA URL must reference kalevent.com."""
    import dspy
    from src.dspy.signatures import build_youtube_signatures
    sigs = build_youtube_signatures(dspy)
    for name in ("YouTubeLongFormScript", "YouTubeShortScript", "YouTubeSEOMetadata"):
        sig = sigs[name]
        instruction = (sig.__doc__ or "").lower()
        for fname, field in sig.model_fields.items():
            instruction += " " + (str(field.description or "")).lower()
        assert "inboxiq.com" not in instruction, f"{name} still references inboxiq.com"
        # At least one of the three should mention kalevent.com (the long form
        # signature is where the CTA URL belongs).
    long_doc = (sigs["YouTubeLongFormScript"].__doc__ or "").lower()
    long_fields = " ".join((str(f.description or "")).lower() for f in sigs["YouTubeLongFormScript"].model_fields.values())
    assert "kalevent.com" in long_doc + long_fields, "Long form signature must instruct CTA to kalevent.com"


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
