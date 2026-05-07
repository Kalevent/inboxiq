"""Unit tests for the name/URL token-overlap heuristic that guards LinkedIn enrichment.

The agent picks LinkedIn URLs via LLM judgement. This heuristic catches obvious
mis-associations like name='Mieke Fonteyn' bound to url='/in/namnnguyen'.
"""
from src.agents.linkedin_cadence import name_url_tokens_match


def test_match_hyphenated_slug():
    assert name_url_tokens_match("Anne Kreutzer", "https://www.linkedin.com/in/anne-kreutzer-a1395a9/")
    assert name_url_tokens_match("Lisa R Green", "https://www.linkedin.com/in/lisa-r-green-35135425")


def test_match_run_together_slug():
    """slugs without separators still match via substring check."""
    assert name_url_tokens_match("Nam Nguyen", "https://www.linkedin.com/in/namnnguyen")


def test_real_world_mismatch_is_rejected():
    """The bug we are guarding against: name='Mieke Fonteyn' wired to a slug for someone else."""
    assert not name_url_tokens_match("Mieke Fonteyn", "https://www.linkedin.com/in/namnnguyen")


def test_completely_different_names_are_rejected():
    assert not name_url_tokens_match("Sarah Chen", "https://www.linkedin.com/in/john-smith-12345")


def test_short_name_falls_back_to_permissive():
    """Names with no >= 3-char tokens (e.g. 'Bo Li') skip the check rather than block legitimate edge cases."""
    assert name_url_tokens_match("Bo Li", "https://www.linkedin.com/in/random-slug-xyz")


def test_empty_inputs_are_permissive():
    assert name_url_tokens_match("", "https://www.linkedin.com/in/anyone")
    assert name_url_tokens_match("Anyone", "")


def test_url_without_in_path_is_permissive():
    """We only inspect /in/<slug>; other LinkedIn URL shapes are not our problem."""
    assert name_url_tokens_match("Anne Kreutzer", "https://www.linkedin.com/company/some-corp")


def test_trailing_slash_handled():
    assert name_url_tokens_match("Anne Kreutzer", "https://www.linkedin.com/in/anne-kreutzer/")


def test_case_insensitive():
    assert name_url_tokens_match("ANNE KREUTZER", "https://www.linkedin.com/in/Anne-Kreutzer")


def test_punctuation_in_name_is_stripped():
    """Names like 'Mary-Anne O'Brien' tokenize cleanly."""
    assert name_url_tokens_match("Mary-Anne O'Brien", "https://www.linkedin.com/in/mary-anne-obrien")
