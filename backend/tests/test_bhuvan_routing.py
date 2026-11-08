from __future__ import annotations

import httpx
import pytest

from app.core.config import Settings
from app.schemas.common import Coordinates
from app.services.routing import RoutingService


ORIGIN = Coordinates(lat=28.6139, lon=77.2090)
DESTINATION = Coordinates(lat=28.5355, lon=77.3910)
OSRM_RESPONSE = {
    "code": "Ok",
    "routes": [
        {
            "distance": 12000,
            "duration": 1800,
            "geometry": {
                "type": "LineString",
                "coordinates": [[77.209, 28.6139], [77.391, 28.5355]],
            },
        }
    ],
}
BHUVAN_GEOJSON = {
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "geometry": {
                "type": "LineString",
                "coordinates": [[77.209, 28.6139], [77.3, 28.57], [77.391, 28.5355]],
            },
            "properties": {},
        }
    ],
}


@pytest.mark.asyncio
async def test_bhuvan_route_returns_geojson_without_fabricating_metrics(mock_router):
    mock_router.get(
        "https://bhuvan.test/route",
        params={
            "lat1": "28.6139",
            "lon1": "77.209",
            "lat2": "28.5355",
            "lon2": "77.391",
            "token": "test-token",
        },
    ).mock(return_value=httpx.Response(200, json=BHUVAN_GEOJSON))
    settings = Settings(
        ROUTING_PROVIDER_URL="https://router.test",
        ISRO_BHUVAN_TOKEN="test-token",
        ISRO_BHUVAN_SHORTEST_PATH_URL="https://bhuvan.test/route",
    )

    async with httpx.AsyncClient() as client:
        result = await RoutingService(settings, client).get_route(
            ORIGIN, DESTINATION, "driving"
        )

    assert result.provider == "isro-bhuvan-routing"
    assert result.fallback_reason is None
    assert result.distance_km is None
    assert result.duration_minutes is None
    assert result.geometry == {
        "type": "LineString",
        "coordinates": BHUVAN_GEOJSON["features"][0]["geometry"]["coordinates"],
    }


@pytest.mark.asyncio
async def test_expired_bhuvan_token_uses_osrm_backup_and_records_reason(mock_router):
    mock_router.get("https://bhuvan.test/route").mock(
        return_value=httpx.Response(401, json={"detail": "expired token"})
    )
    mock_router.get(
        url__regex=r"^https://router\.test/route/v1/driving/.*$"
    ).mock(return_value=httpx.Response(200, json=OSRM_RESPONSE))
    settings = Settings(
        ROUTING_PROVIDER_URL="https://router.test",
        ISRO_BHUVAN_TOKEN="expired-token",
        ISRO_BHUVAN_SHORTEST_PATH_URL="https://bhuvan.test/route",
    )

    async with httpx.AsyncClient() as client:
        result = await RoutingService(settings, client).get_route(
            ORIGIN, DESTINATION, "driving"
        )

    assert result.provider == "osrm-routing"
    assert result.fallback_status == "error"
    assert "invalid or expired" in result.fallback_reason
    assert result.distance_km == 12
    assert result.duration_minutes == 30


@pytest.mark.asyncio
async def test_missing_bhuvan_token_uses_osrm_backup(mock_router):
    mock_router.get(
        url__regex=r"^https://router\.test/route/v1/driving/.*$"
    ).mock(return_value=httpx.Response(200, json=OSRM_RESPONSE))
    settings = Settings(
        ROUTING_PROVIDER_URL="https://router.test",
        ISRO_BHUVAN_TOKEN=None,
    )

    async with httpx.AsyncClient() as client:
        result = await RoutingService(settings, client).get_route(
            ORIGIN, DESTINATION, "driving"
        )

    assert result.provider == "osrm-routing"
    assert result.fallback_status == "not_configured"
    assert "ISRO_BHUVAN_TOKEN is not configured" in result.fallback_reason
    assert result.geometry == OSRM_RESPONSE["routes"][0]["geometry"]


def test_bhuvan_geojson_multi_line_is_normalized_to_linestring():
    geometry = RoutingService._bhuvan_linestring(
        {
            "type": "MultiLineString",
            "coordinates": [
                [[77.0, 28.0], [77.1, 28.1]],
                [[77.1, 28.1], [77.2, 28.2]],
            ],
        }
    )

    assert geometry == {
        "type": "LineString",
        "coordinates": [[77.0, 28.0], [77.1, 28.1], [77.2, 28.2]],
    }


@pytest.mark.parametrize(
    ("mode", "profile"),
    [
        ("two-wheeler", "driving"),
        ("cycling", "cycling"),
        ("transit", "driving"),
    ],
)
@pytest.mark.asyncio
async def test_non_driving_modes_skip_bhuvan_and_use_osrm_profile(
    mock_router, mode, profile
):
    mock_router.get(
        url__regex=rf"^https://router\.test/route/v1/{profile}/.*$"
    ).mock(return_value=httpx.Response(200, json=OSRM_RESPONSE))
    settings = Settings(
        ROUTING_PROVIDER_URL="https://router.test",
        ISRO_BHUVAN_TOKEN="configured-token",
        ISRO_BHUVAN_SHORTEST_PATH_URL="https://bhuvan.test/route",
    )

    async with httpx.AsyncClient() as client:
        result = await RoutingService(settings, client).get_route(
            ORIGIN, DESTINATION, mode
        )

    assert result.provider == "osrm-routing"
    assert result.distance_km == 12
    assert not any("bhuvan.test" in str(call.request.url) for call in mock_router.calls)
