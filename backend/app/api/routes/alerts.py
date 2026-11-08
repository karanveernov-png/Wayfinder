from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_alert_service
from app.schemas.alert import AlertSearchResponse
from app.schemas.common import Coordinates, DataStatus, SourceMeta
from app.services.alerts import AlertService
from app.services.exceptions import ServiceResponseError, ServiceUnavailableError

router = APIRouter(tags=["alerts"])


@router.get("/alerts", response_model=AlertSearchResponse)
async def alerts(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    radius_km: float = Query(25.0, gt=0, le=200),
    service: AlertService = Depends(get_alert_service),
) -> AlertSearchResponse:
    point = Coordinates(lat=lat, lon=lon)

    try:
        results = await service.get_alerts(point, radius_km)
        return AlertSearchResponse(
            query=point,
            alerts=results,
            data_status=DataStatus(
                mode="live", sources=[SourceMeta(name="alerts", status="ok")]
            ),
        )
    except ServiceUnavailableError as exc:
        # Explicit "not_configured"/"unavailable" status, read directly from
        # the exception's structured `reason` - never represented as an
        # empty-but-successful result, which would read as "no disruptions".
        status = "not_configured" if exc.reason == "not_configured" else "unavailable"
        return AlertSearchResponse(
            query=point,
            alerts=[],
            data_status=DataStatus(
                mode="degraded",
                sources=[SourceMeta(name="alerts", status=status, detail=exc.message)],
            ),
        )
    except ServiceResponseError as exc:
        return AlertSearchResponse(
            query=point,
            alerts=[],
            data_status=DataStatus(
                mode="degraded",
                sources=[SourceMeta(name="alerts", status="error", detail=exc.message)],
            ),
        )


