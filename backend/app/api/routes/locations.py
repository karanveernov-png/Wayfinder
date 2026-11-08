"""
GET /api/v1/locations/suggest

Location autocomplete / misspelling / disambiguation suggestions for the
origin and destination fields (see docs/LOCATION_AUTOCOMPLETE_GUIDE.md).

Deliberately separate from POST /journeys/analyse: this endpoint only
ever looks up candidates for the user to choose from - it never resolves
a journey, and a selected candidate's coordinates are sent back to
/journeys/analyse as origin_coordinates/destination_coordinates exactly
the same way a map-click selection already is (see
app/api/routes/journeys.py _resolve_location).

Same "always return a structurally valid response" convention as the
rest of this API (see journeys.py's module docstring and
facilities.py): a provider failure is reported via `data_status`, not a
5xx, so the frontend can show "couldn't reach the location service"
without special-casing HTTP status codes for what is, from the user's
point of view, just an autocomplete dropdown.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_routing_service
from app.schemas.common import DataStatus, SourceMeta
from app.schemas.location import LocationSuggestion, LocationSuggestResponse
from app.services.exceptions import ServiceResponseError, ServiceUnavailableError
from app.services.routing import RoutingService

router = APIRouter(tags=["locations"])

_SOURCE_NAME = "nominatim-geocoding-suggest"

# Mirrors RoutingService.suggest_locations' own bound; validated again here
# so an out-of-range client value is rejected with a clear 422 rather than
# silently clamped deep inside the service.
_MAX_LIMIT = 10


@router.get("/locations/suggest", response_model=LocationSuggestResponse)
async def suggest_locations(
    q: str = Query(
        ...,
        min_length=1,
        max_length=300,
        description="Free-text place name to search for.",
    ),
    limit: int = Query(6, ge=1, le=_MAX_LIMIT),
    routing: RoutingService = Depends(get_routing_service),
) -> LocationSuggestResponse:
    try:
        result = await routing.suggest_locations(q, limit=limit)
    except ServiceUnavailableError as exc:
        status = "not_configured" if exc.reason == "not_configured" else "unavailable"
        return LocationSuggestResponse(
            query=q,
            suggestions=[],
            used_fallback=False,
            data_status=DataStatus(
                mode="degraded",
                sources=[SourceMeta(name=_SOURCE_NAME, status=status, detail=exc.message)],
            ),
        )
    except ServiceResponseError as exc:
        return LocationSuggestResponse(
            query=q,
            suggestions=[],
            used_fallback=False,
            data_status=DataStatus(
                mode="degraded",
                sources=[SourceMeta(name=_SOURCE_NAME, status="error", detail=exc.message)],
            ),
        )

    suggestions = [
        LocationSuggestion(
            place_id=item.place_id,
            display_name=item.display_name,
            name=item.name,
            region=item.region,
            country=item.country,
            place_type=item.place_type,
            coordinates=item.coordinates,
            match_confidence=item.match_confidence,
            is_fallback_match=item.is_fallback_match,
        )
        for item in result.suggestions
    ]

    return LocationSuggestResponse(
        query=q,
        suggestions=suggestions,
        used_fallback=result.used_fallback,
        data_status=DataStatus(
            mode="live",
            sources=[
                SourceMeta(
                    name=_SOURCE_NAME, status="ok", retrieved_at=datetime.now(timezone.utc)
                )
            ],
        ),
    )
