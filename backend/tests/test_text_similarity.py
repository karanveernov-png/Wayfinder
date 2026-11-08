"""
Pure-function tests for app/services/text_similarity.py. No network, no
mocking needed - these only exercise deterministic string logic.
"""

from __future__ import annotations

from app.services.text_similarity import (
    MAX_FALLBACK_QUERIES,
    MIN_FALLBACK_QUERY_LENGTH,
    generate_fallback_queries,
    normalize_for_comparison,
    similarity_ratio,
)


def test_normalize_for_comparison_lowercases_trims_and_collapses_whitespace():
    assert normalize_for_comparison("  Chandigarh  ") == "chandigarh"
    assert normalize_for_comparison("New   Delhi") == "new delhi"
    assert normalize_for_comparison("") == ""
    assert normalize_for_comparison(None) == ""


def test_similarity_ratio_identical_strings_is_one():
    assert similarity_ratio("Chandigarh", "chandigarh") == 1.0
    assert similarity_ratio("  Delhi ", "Delhi") == 1.0


def test_similarity_ratio_empty_strings_is_zero():
    assert similarity_ratio("", "Chandigarh") == 0.0
    assert similarity_ratio("Chandigarh", "") == 0.0
    assert similarity_ratio("", "") == 0.0


def test_similarity_ratio_misspelling_scores_higher_than_unrelated():
    misspelled_score = similarity_ratio("Chagarh", "Chandigarh")
    unrelated_score = similarity_ratio("Chagarh", "Mumbai")
    assert 0.0 < misspelled_score < 1.0
    assert misspelled_score > unrelated_score


def test_similarity_ratio_is_symmetric():
    a, b = "Jalandhar", "Jalandhar"
    assert similarity_ratio(a, b) == similarity_ratio(b, a)


def test_generate_fallback_queries_returns_trimmed_variants():
    variants = generate_fallback_queries("Chandigarhh")
    assert variants  # at least one variant produced
    assert "Chandigarhh" not in variants  # never repeats the raw query itself
    for v in variants:
        assert len(v) >= MIN_FALLBACK_QUERY_LENGTH
        assert v != "Chandigarhh"


def test_generate_fallback_queries_bounded_count():
    variants = generate_fallback_queries("Chandigarh")
    assert len(variants) <= MAX_FALLBACK_QUERIES


def test_generate_fallback_queries_short_input_returns_nothing():
    # At or below the minimum fallback length there's nothing meaningful
    # left to trim down to.
    assert generate_fallback_queries("ab") == []
    assert generate_fallback_queries("abc") == []


def test_generate_fallback_queries_no_duplicates():
    variants = generate_fallback_queries("aabbaabb")
    assert len(variants) == len(set(v.lower() for v in variants))


def test_generate_fallback_queries_never_returns_blank_or_whitespace():
    for variant in generate_fallback_queries("   Delhi   "):
        assert variant.strip() == variant
        assert variant != ""
