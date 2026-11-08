from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import Settings, get_facility_service, get_settings
from app.schemas.common import Coordinates, DataStatus, SourceMeta
from app.schemas.facility import FacilityCategory, FacilitySearchResponse
from app.services.exceptions import ServiceResponseError, ServiceUnavailableError
from app.services.facilities import FacilityService

router = APIRouter(tags=["facilities"])


@router.get("/facilities/nearby", response_model=FacilitySearchResponse)
async def facilities_nearby(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    radius_km: float = Query(5.0, gt=0, description="Search radius in kilometers"),
    category: Optional[FacilityCategory] = Query(
        None, description="Omit to search all supported categories"
    ),
    settings: Settings = Depends(get_settings),
    service: FacilityService = Depends(get_facility_service),
) -> FacilitySearchResponse:
    if radius_km > settings.MAX_FACILITY_RADIUS_KM:
        raise HTTPException(
            status_code=422,
            detail=f"radius_km must not exceed {settings.MAX_FACILITY_RADIUS_KM} km",
        )
    if radius_km < settings.MIN_FACILITY_RADIUS_KM:
        raise HTTPException(
            status_code=422,
            detail=f"radius_km must be at least {settings.MIN_FACILITY_RADIUS_KM} km",
        )

    point = Coordinates(lat=lat, lon=lon)
    categories = (
        [category]
        if category
        else ["hospital", "fuel", "restaurant", "rest_stop", "pharmacy", "lodging"]
    )

    try:
        result = await service.search_nearby(point, radius_km, categories)
        facilities = result.facilities
        status = DataStatus(
            mode="live",
            sources=[
                SourceMeta(
                    name="overpass-osm",
                    status="ok",
                    retrieved_at=datetime.now(timezone.utc),
                )
            ],
        )
    except ServiceUnavailableError as exc:
        return FacilitySearchResponse(
            query=point,
            radius_km=radius_km,
            category=category,
            facilities=[],
            data_status=DataStatus(
                mode="degraded",
                sources=[
                    SourceMeta(
                        name="overpass-osm", status="unavailable", detail=exc.message
                    )
                ],
            ),
        )
    except ServiceResponseError as exc:
        return FacilitySearchResponse(
            query=point,
            radius_km=radius_km,
            category=category,
            facilities=[],
            data_status=DataStatus(
                mode="degraded",
                sources=[
                    SourceMeta(name="overpass-osm", status="error", detail=exc.message)
                ],
            ),
        )

    return FacilitySearchResponse(
        query=point,
        radius_km=radius_km,
        category=category,
        facilities=facilities,
        data_status=status,
        # Honest result-limiting signal (spec section 7: "never silently
        # imply that a limited result list contains every nearby facility").
        # Only meaningful when the Overpass response itself looked capped -
        # see FacilityService._overpass_out_limit / search_nearby.
        result_truncated=result.truncated,
        result_limit=result.limit if result.truncated else None,
    )
