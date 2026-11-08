from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_weather_service
from app.schemas.common import Coordinates, DataStatus, SourceMeta
from app.schemas.weather import WeatherResponse
from app.services.exceptions import ServiceResponseError, ServiceUnavailableError
from app.services.weather import WeatherService

router = APIRouter(tags=["weather"])


@router.get("/weather", response_model=WeatherResponse)
async def weather(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    service: WeatherService = Depends(get_weather_service),
) -> WeatherResponse:
    point = Coordinates(lat=lat, lon=lon)

    try:
        observation = await service.get_current_weather(point)
        return WeatherResponse(
            observation=observation,
            data_status=DataStatus(
                mode="live",
                sources=[
                    SourceMeta(
                        name="open-meteo",
                        status="ok",
                        retrieved_at=datetime.now(timezone.utc),
                    )
                ],
            ),
        )
    except ServiceUnavailableError as exc:
        return WeatherResponse(
            observation=None,
            data_status=DataStatus(
                mode="degraded",
                sources=[
                    SourceMeta(
                        name="open-meteo", status="unavailable", detail=exc.message
                    )
                ],
            ),
        )
    except ServiceResponseError as exc:
        return WeatherResponse(
            observation=None,
            data_status=DataStatus(
                mode="degraded",
                sources=[
                    SourceMeta(name="open-meteo", status="error", detail=exc.message)
                ],
            ),
        )
