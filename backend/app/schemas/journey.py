from __future__ import annotations

from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator

from app.schemas.alert import Alert
from app.schemas.common import Coordinates, DataStatus
from app.schemas.facility import Facility, FacilityCategory
from app.schemas.weather import WeatherObservation

TravelMode = Literal[
    "driving", "two-wheeler", "cycling", "transit"
]  # driving: ISRO Bhuvan + OSRM fallback; others: OSRM fallback only

DEFAULT_FACILITY_CATEGORIES: List[FacilityCategory] = ["hospital", "fuel", "rest_stop"]


class JourneyAnalyseRequest(BaseModel):
    origin: str = Field(
        ..., min_length=1, max_length=300, examples=["Jalandhar, Punjab, India"]
    )
    destination: str = Field(
        ..., min_length=1, max_length=300, examples=["Chandigarh, India"]
    )
    origin_coordinates: Optional[Coordinates] = Field(
        None, description="Optional WGS84 origin coordinates; bypasses text geocoding."
    )
    destination_coordinates: Optional[Coordinates] = Field(
        None,
        description="Optional WGS84 destination coordinates; bypasses text geocoding.",
    )
    travel_mode: TravelMode = "driving"
    include_facilities: bool = True
    include_alerts: bool = True
    # No hardcoded upper bound here (previously `le=50`, stale against the
    # 50 -> 70km raise for the hybrid map-to-globe feature — see
    # config.py MAX_FACILITY_RADIUS_KM). Pydantic Field constraints are
    # fixed at class-definition time and can't read Settings, so this
    # endpoint validates facility_radius_km against the live
    # MIN/MAX_FACILITY_RADIUS_KM settings in the route handler instead,
    # the same single-source-of-truth pattern /facilities/nearby already
    # uses, rather than keeping a second hardcoded number here that can
    # silently drift out of sync again.
    facility_radius_km: float = Field(5.0, gt=0)
    facility_categories: List[FacilityCategory] = Field(
        default_factory=lambda: list(DEFAULT_FACILITY_CATEGORIES)
    )

    demo: bool = Field(
        False,
        description=(
            "When true the backend returns pre-stored demonstration data for "
            "the Chandigarh → Ludhiana (NH-95) corridor. No live provider "
            "calls are made; origin and destination inputs are ignored; "
            "data_status.mode will be 'demo'. Use this for a repeatable, "
            "network-independent presentation of the full journey dashboard."
        ),
    )

    @field_validator("origin", "destination")
    @classmethod
    def _non_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("must not be blank")
        return v


class Location(BaseModel):
    query: str = Field(..., description="The text originally supplied by the client")
    resolved: Optional[Coordinates] = Field(
        None, description="Null if geocoding failed"
    )
    display_name: Optional[str] = Field(
        None, description="Normalized place name from the geocoder"
    )


class RouteInfo(BaseModel):
    distance_km: Optional[float] = None
    duration_minutes: Optional[float] = None
    geometry: Optional[Dict] = Field(
        None,
        description="GeoJSON LineString geometry of the route, when the provider returns one",
    )


class JourneyPayload(BaseModel):
    origin: Location
    destination: Location
    distance_km: Optional[float] = None
    duration_minutes: Optional[float] = None
    geometry: Optional[Dict] = None


RiskLevel = Literal["unknown", "low", "moderate", "high"]


class RiskAssessment(BaseModel):
    level: RiskLevel = "unknown"
    score: Optional[float] = Field(
        None, ge=0, le=100, description="Null when there is insufficient data to score"
    )
    reasons: List[str] = Field(default_factory=list)


class JourneyAnalyseResponse(BaseModel):
    journey: JourneyPayload
    facilities: List[Facility] = Field(default_factory=list)
    alerts: List[Alert] = Field(default_factory=list)
    weather_samples: List[WeatherObservation] = Field(
        default_factory=list,
        description=(
            "Weather observations at a small, fixed number of points along the "
            "route (e.g. origin/midpoint/destination). This is a limited sample, "
            "NOT a comprehensive forecast of every route segment - see "
            "docs/API_CONTRACT.md. Empty if weather was unavailable or not requested."
        ),
    )
    risk_assessment: RiskAssessment
    recommendations: List[str] = Field(default_factory=list)
    data_status: DataStatus


class RouteComparisonRequest(BaseModel):
    """
    Deliberately narrower than JourneyAnalyseRequest: route comparison is
    about choosing between paths before committing to one, not the full
    facility/alert dashboard - so there's no facility_radius_km or
    facility_categories here. Run /journeys/analyse afterwards with the
    chosen route's parameters for the full picture.
    """

    origin: str = Field(..., min_length=1, max_length=300)
    destination: str = Field(..., min_length=1, max_length=300)
    origin_coordinates: Optional[Coordinates] = None
    destination_coordinates: Optional[Coordinates] = None
    travel_mode: TravelMode = "driving"
    max_alternatives: int = Field(3, ge=1, le=5)

    @field_validator("origin", "destination")
    @classmethod
    def _non_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("must not be blank")
        return v


class RouteOption(BaseModel):
    label: str = Field(
        ..., description="e.g. 'Fastest route', 'Alternate 2' - display label, not an id"
    )
    distance_km: Optional[float] = None
    duration_minutes: Optional[float] = None
    geometry: Optional[Dict] = Field(None, description="GeoJSON LineString")
    risk_assessment: RiskAssessment
    weather: Optional[WeatherObservation] = Field(
        None, description="Single destination-area sample for this specific route, not a multi-point series"
    )
    alerts_count: int = 0
    is_fastest: bool = False
    is_shortest_distance: bool = False


class RouteComparisonResponse(BaseModel):
    origin: Location
    destination: Location
    routes: List[RouteOption] = Field(default_factory=list)
    data_status: DataStatus
