from src.dspy.signatures import LinkedInUrlSelection


def test_signature_has_structured_input_fields():
    sig = LinkedInUrlSelection
    for name in ("lead_name", "lead_company", "lead_industry", "candidate_profiles"):
        assert name in sig.input_fields, f"missing input field: {name}"


def test_signature_has_structured_output_fields():
    sig = LinkedInUrlSelection
    for name in ("selected_url", "selected_name", "selected_job_title", "skip_reason"):
        assert name in sig.output_fields, f"missing output field: {name}"


def test_signature_docstring_mentions_skip_path():
    doc = (LinkedInUrlSelection.__doc__ or "").lower()
    assert "skip" in doc
    assert "no clear match" in doc or "no match" in doc
