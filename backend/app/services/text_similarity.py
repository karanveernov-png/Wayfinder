"""
Small, dependency-free string-similarity utilities used to help the
location-suggestions feature cope with misspelled input (see
app/services/routing.py RoutingService.suggest_locations and
docs/LOCATION_AUTOCOMPLETE_GUIDE.md).

Deliberately NOT a geocoder and NOT a spellchecker: everything here only
ever compares two already-known strings (the user's raw input against a
candidate's name/display_name). It never invents a place, a coordinate, or
a "corrected" spelling - see RoutingService.suggest_locations for how
these helpers are combined with real geocoding-provider results.

Uses only the Python standard library (difflib) - no new dependency, per
the project's "do not add an enormous static city database / complex
matching library" scope constraint.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import List

# Below this length a prefix/suffix-trim fallback query is unlikely to be a
# meaningful place name and more likely to return noisy, irrelevant
# results (and costs an extra provider request) - so the trimming fallback
# in generate_fallback_queries() never produces a variant shorter than this.
MIN_FALLBACK_QUERY_LENGTH = 3

# Hard cap on how many extra "did you mean" queries a single misspelled
# search can trigger. Bounded deliberately: this feature must never turn
# into an uncontrolled burst of geocoding requests (see
# RoutingService._nominatim_throttle, which still serializes every one of
# these with the normal 1 req/sec policy on top of this cap).
MAX_FALLBACK_QUERIES = 3

_WHITESPACE_RE = re.compile(r"\s+")


def normalize_for_comparison(text: str) -> str:
    """Lowercase, trim, and collapse internal whitespace. Used on both
    sides of every similarity comparison so differences in case or
    spacing never affect the score."""
    if not text:
        return ""
    return _WHITESPACE_RE.sub(" ", text.strip().lower())


def similarity_ratio(a: str, b: str) -> float:
    """
    A 0.0-1.0 similarity score between two strings, using the standard
    library's difflib (Ratcliff/Obershelp matching - no extra dependency).
    Both inputs are normalized first (see normalize_for_comparison), so
    "  Chandigarh" and "chandigarh" score 1.0 against each other.

    This is a SUGGESTION signal only - see the module docstring and
    RoutingService.suggest_locations for how callers must treat it (never
    as proof that a match is correct).
    """
    norm_a = normalize_for_comparison(a)
    norm_b = normalize_for_comparison(b)
    if not norm_a or not norm_b:
        return 0.0
    if norm_a == norm_b:
        return 1.0
    return SequenceMatcher(None, norm_a, norm_b).ratio()


def generate_fallback_queries(raw_query: str) -> List[str]:
    """
    A small, bounded set of alternate search strings to retry against the
    geocoding provider when the user's raw input returned no results at
    all (see RoutingService.suggest_locations). These are deterministic
    trims of the original text - NOT guessed spellings - so every
    resulting "suggestion" the caller shows is still a real place the
    provider returned for a real query, just one slightly different from
    what was typed.

    Technique: progressively drop one trailing character, then one
    leading character, stopping once the remaining text is shorter than
    MIN_FALLBACK_QUERY_LENGTH or MAX_FALLBACK_QUERIES variants have been
    produced. This mainly helps with a stray/missing character at a word
    boundary (e.g. a trailing typo); a typo in the middle of the word
    (like a few missing letters) may not be recoverable this way at all -
    see the module docstring. That is an accepted, documented limitation,
    not a bug: this module never fabricates a match it cannot find for
    real (docs/LOCATION_AUTOCOMPLETE_GUIDE.md "Known limitations").

    Always excludes the raw query itself (the caller already tried that)
    and any duplicate/blank variant.
    """
    cleaned = raw_query.strip()
    if len(cleaned) <= MIN_FALLBACK_QUERY_LENGTH:
        return []

    variants: List[str] = []
    seen = {normalize_for_comparison(cleaned)}

    def _maybe_add(candidate: str) -> bool:
        candidate = candidate.strip()
        key = normalize_for_comparison(candidate)
        if len(candidate) < MIN_FALLBACK_QUERY_LENGTH or key in seen:
            return False
        seen.add(key)
        variants.append(candidate)
        return len(variants) >= MAX_FALLBACK_QUERIES

    # Trim from the end first - a trailing stray/missing character is the
    # most common edge typo for a place name typed quickly.
    trimmed = cleaned
    while len(trimmed) - 1 >= MIN_FALLBACK_QUERY_LENGTH:
        trimmed = trimmed[:-1]
        if _maybe_add(trimmed):
            return variants

    # Then try trimming from the start, in case the stray character was
    # at the beginning instead.
    trimmed = cleaned
    while len(trimmed) - 1 >= MIN_FALLBACK_QUERY_LENGTH:
        trimmed = trimmed[1:]
        if _maybe_add(trimmed):
            return variants

    return variants
