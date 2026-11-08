"""
Schemas for GET /locations/suggest - location autocomplete/disambiguation.

See app/services/routing.py RoutingService.suggest_locations() for how
these are produced, and docs/LOCATION_AUTOCOMPLETE_GUIDE.md for the
feature end-to-end.
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field

from app.schemas.common import Coordinates, DataStatus

# Deliberately NOT a closed enum (Literal) like FacilityCategory - Nominatim's
# `addresstype`/`type`/`class` fields span a very wide, provider-defined
# vocabulary (city, town, village, suburb, state, county, administrative,
# road, house, ...). Constraining this to a fixed list would mean silently
# dropping or mis-labelling legitimate place types; see
# RoutingService._place_type_from_nominatim for how this value is derived.
PlaceType = str


class LocationSuggestion(BaseModel):
    """One normalized, real geocoding-provider result. Never fabricated -
    every field here traces back to a single Nominatim response entry."""

    place_id: str = Field(
        ...,
        description=(
            "Provider-specific identifier (Nominatim's place_id/osm_id). "
            "Stable for a given provider response but NOT guaranteed stable "
            "across requests - do not use as a long-term database key. "
            "Use coordinates + display_name to recognize the same place."
        ),
    )
    display_name: str = Field(
        ..., description="Full, human-readable name as returned by the provider."
    )
    name: str = Field(
        ..., description="Short name of the place (e.g. the city/town name)."
    )
    region: Optional[str] = Field(
        None, description="State/province, when the provider supplied one."
    )
    country: Optional[str] = Field(
        None, description="Country, when the provider supplied one."
    )
    place_type: Optional[PlaceType] = Field(
        None,
        description="Provider-reported place type (e.g. 'city', 'town', "
        "'village', 'suburb'). Null when the provider did not classify it.",
    )
    coordinates: Coordinates
    match_confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description=(
            "How closely this result's name textually matches the user's "
            "raw query (1.0 = exact, normalized match). This is a STRING- "
            "similarity signal only, not a geocoding-quality or "
            "distance-based score, and it is informational for the client "
            "to use for sorting/highlighting - it is never used by the "
            "backend to auto-select a location on the user's behalf."
        ),
    )
    is_fallback_match: bool = Field(
        False,
        description=(
            "True when this result was found via the misspelling fallback "
            "(a trimmed variant of the raw query - see "
            "app/services/text_similarity.py) rather than the user's exact "
            "input. Lets the client label these as 'did you mean?' rather "
            "than presenting them as equally confident with everything "
            "else."
        ),
    )


class LocationSuggestResponse(BaseModel):
    query: str = Field(..., description="The raw text the client searched for.")
    suggestions: List[LocationSuggestion] = Field(default_factory=list)
    used_fallback: bool = Field(
        False,
        description=(
            "True when the raw query returned no provider results and a "
            "misspelling fallback (see app/services/text_similarity.py) "
            "was attempted. True even if the fallback itself found "
            "nothing - check `suggestions` for whether it succeeded."
        ),
    )
    data_status: DataStatus = Field(
        ...,
        description=(
            "mode is 'live' whenever the geocoding provider was reachable "
            "and responded - including when it legitimately found zero "
            "matches. 'degraded' means the provider itself could not be "
            "reached/responded with an error, which the client should "
            "treat differently from a confirmed no-match (Scenario D vs "
            "a transient failure the user may want to retry)."
        ),
    )
