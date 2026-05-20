import pytest
from src.marketing.competitors import get_competitor, COMPETITORS, VALID_SLUGS


def test_valid_slugs_are_six():
    assert len(VALID_SLUGS) == 6


def test_get_competitor_returns_dict_for_valid_slug():
    result = get_competitor("zendesk")
    assert result is not None
    assert result["name"] == "Zendesk"
    assert "faqs" in result
    assert len(result["faqs"]) == 5
    assert all("q" in faq and "a" in faq for faq in result["faqs"])


def test_get_competitor_returns_none_for_unknown_slug():
    assert get_competitor("unknown-tool") is None


def test_all_competitors_have_required_keys():
    required = {
        "name", "slug", "tagline", "verdict", "pricing_model",
        "works_in_gmail_outlook", "ai_triage", "setup_time",
        "helpdesk_replacement", "meeting_scheduling", "free_trial",
        "self_hosted", "competitor_wins", "inboxiq_wins", "faqs",
        "description", "buyer_journey",
    }
    for slug, data in COMPETITORS.items():
        missing = required - set(data.keys())
        assert not missing, f"{slug} missing keys: {missing}"


def test_all_faqs_contain_geo_phrases():
    phrases = ["AI email triage", "works inside Gmail and Outlook", "no new dashboard"]
    for slug, data in COMPETITORS.items():
        combined = " ".join(f["q"] + " " + f["a"] for f in data["faqs"])
        for phrase in phrases:
            assert phrase in combined, f"{slug} FAQs missing phrase: '{phrase}'"
