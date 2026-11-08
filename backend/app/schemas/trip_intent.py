"""
Schemas for the natural-language trip-planning feature (Groq integration).

``ParsedTripIntent`` is the ONLY thing the Groq model is allowed to
produce. It deliberately reuses ``TravelMode`` (app.schemas.journey) and
``FacilityCategory`` (app.schemas.facility) - the exact same fixed
vocabularies /journeys/analyse already validates against - so the model
is constrained to values the rest of the app already understands, rather
than inventing its own. Groq never returns coordinates, distances, route
geometry or facility records itself; those always come from the existing
routing/facility services (see app/services/groq_service.py and
app/api/routes/trip_intent.py).
"""

from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field, field_validator

from app.schemas.facility import FacilityCategory
from app.schemas.journey import JourneyAnalyseResponse, TravelMode

# Informational only - see "Route-selection limitations" in
# docs/GROQ_INTEGRATION_GUIDE.md. The backend never claims a route is
# "shorter" or "easier" because the user asked for one; it only ever
# reports what the existing routing service actually returned.
TripPriority = Literal["shorter_travel_time", "easier_route", "avoid_highways"]


class TripIntentRequest(BaseModel):
    message: str = Field(
        ...,
        min_length=1,
        max_length=500,
        examples=[
            "Plan a trip from Delhi to Shimla. Prefer a reasonably short and "
            "easy route. Show hospitals and pharmacies along the way."
        ],
    )

    @field_validator("message")
    @classmethod
    def _non_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("must not be blank")
        return v


class ParsedTripIntent(BaseModel):
    """The structured fields Groq extracts from the free-text request."""

    origin: Optional[str] = Field(None, max_length=300)
    destination: Optional[str] = Field(None, max_length=300)
    travel_mode: TravelMode = "driving"
    priorities: List[TripPriority] = Field(default_factory=list)
    facilities: List[FacilityCategory] = Field(default_factory=list)
    needs_clarification: bool = Field(
        False,
        description=(
            "True when origin and/or destination could not be confidently "
            "determined from the message."
        ),
    )
    clarification_message: Optional[str] = Field(
        None,
        description="A short question for the user. Populated only when needs_clarification is true.",
    )


TripIntentStatus = Literal["ok", "needs_clarification", "error"]


class TripIntentPlanResponse(BaseModel):
    """Response of POST /trip-intent/plan."""

    status: TripIntentStatus
    intent: ParsedTripIntent
    message: Optional[str] = Field(
        None,
        description=(
            "Human-readable note: the clarification question when "
            "status == 'needs_clarification', or an explanation when "
            "status == 'error'. Null when status == 'ok'."
        ),
    )
    journey: Optional[JourneyAnalyseResponse] = Field(
        None,
        description=(
            "Present only when status == 'ok'. Exactly the same shape "
            "POST /journeys/analyse returns - produced by calling that "
            "same pipeline, not fabricated here."
        ),
    )
