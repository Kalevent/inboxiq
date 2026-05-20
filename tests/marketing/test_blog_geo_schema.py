# tests/marketing/test_blog_geo_schema.py
import os, pytest
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("INBOXIQ_ENCRYPTION_KEY", "test-encryption-key-for-unit-tests")

from src.blog.services import extract_faq_pairs


def test_extract_faq_pairs_returns_empty_list_when_no_faq_section():
    md = "# Title\n\nSome content without FAQ."
    assert extract_faq_pairs(md) == []


def test_extract_faq_pairs_parses_bold_q_and_a():
    md = """# Title

Some content.

## Frequently Asked Questions

**What is InboxIQ?**

InboxIQ is an AI email triage tool.

**Does it work in Gmail?**

Yes, it works inside Gmail and Outlook with no new dashboard.
"""
    pairs = extract_faq_pairs(md)
    assert len(pairs) == 2
    assert pairs[0]["q"] == "What is InboxIQ?"
    assert "AI email triage" in pairs[0]["a"]
    assert pairs[1]["q"] == "Does it work in Gmail?"


def test_extract_faq_pairs_returns_at_most_six():
    questions = "\n\n".join(
        f"**Question {i}?**\n\nAnswer {i}." for i in range(10)
    )
    md = f"# Title\n\n## Frequently Asked Questions\n\n{questions}"
    pairs = extract_faq_pairs(md)
    assert len(pairs) <= 6


def test_extract_faq_pairs_handles_missing_faq_section_gracefully():
    assert extract_faq_pairs("") == []
    assert extract_faq_pairs(None) == []
