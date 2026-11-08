from __future__ import annotations

from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field

from app.schemas.common import Coordinates, DataStatus

FacilityCategory = Literal[
    "hospital", "fuel", "restaurant", "rest_stop", "pharmacy", "lodging"
]

# How confidently this record's *coordinates* can be trusted - this is about
# location confidence only, never about operating status, capacity, or
# capabilities (open/closed, has EV charging, has CNG, etc.), which this
# backend never asserts unless a source explicitly provides it.
#
#   "verified"              - coordinates came directly from the designated
#                              authoritative geographic source for this data
#                              (e.g. returned by the OSM/Overpass node itself).
#   "address_matched"       - coordinates came from geocoding a text address
#                              (e.g. Nominatim) but were not independently
#                              cross-checked against a second source.
#   "unverified_coordinates" - coordinates are a manual/approximate estimate
#                              (e.g. derived by a human reading an address),
#                              not produced by a geocoder or authoritative map.
#   "unavailable"            - no usable coordinates could be established at all.
FacilityVerificationStatus = Literal[
    "verified", "address_matched", "unverified_coordinates", "unavailable"
]


class Facility(BaseModel):
    id: Optional[str] = Field(
        None, description="Provider-native identifier, when available"
    )
    name: Optional[str] = Field(
        None, description="None when the source record has no name tag"
    )
    category: FacilityCategory
    coordinates: Coordinates
    distance_km: Optional[float] = Field(
        None,
        description="Great-circle distance from the query point; null if not calculable",
    )
    address: Optional[str] = None
    source: str = Field(
        ..., description="Provider that returned this record, e.g. 'overpass-osm'"
    )

    verification_status: FacilityVerificationStatus = Field(
        ...,
        description=(
            "Confidence level of the COORDINATES only. Never implies the "
            "facility is open, operational, or has any particular capability "
            "(emergency services, EV charging, CNG, etc.) - required, not "
            "defaulted, so every code path must state this explicitly rather "
            "than silently implying a favorable status."
        ),
    )
    coordinate_source: Optional[str] = Field(
        None,
        description="What produced these coordinates, e.g. 'openstreetmap-overpass' "
        "or 'address-derived-approximation'. Null when unavailable.",
    )
    last_verified_at: Optional[datetime] = Field(
        None,
        description="UTC timestamp coordinates were last retrieved/checked. "
        "Null for manually-estimated or unavailable coordinates.",
    )


class FacilitySearchResponse(BaseModel):
    query: Coordinates
    radius_km: float
    category: Optional[FacilityCategory] = None
    facilities: List[Facility] = Field(default_factory=list)
    data_status: DataStatus
    result_truncated: bool = Field(
        False,
        description=(
            "True when the provider's raw response looked capped by its own "
            "result-count limit (see FacilityService._overpass_out_limit), "
            "most relevant for wide-radius (globe-view) searches. When true, "
            "`facilities` is the closest `result_limit` matches the provider "
            "returned, NOT a guarantee that every real facility in the "
            "radius is included - callers must not present it as exhaustive."
        ),
    )
    result_limit: Optional[int] = Field(
        None,
        description="The cap that was hit, only populated when result_truncated is true.",
    )
