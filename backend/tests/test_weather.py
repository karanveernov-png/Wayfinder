from __future__ import annotations

import httpx
import pytest

from tests.conftest import make_settings


@pytest.mark.asyncio
async def test_weather_success(client, mock_router):
    mock_router.get("https://weather.test/v1/forecast").mock(
        return_value=httpx.Response(
            200,
            json={
                "current_weather": {
                    "temperature": 24.5,
                    "windspeed": 12.0,
                    "winddirection": 90,
                    "weathercode": 0,
                    "is_day": 1,
                    "time": "2026-10-19T12:00",
                }
            },
        )
    )
    resp = await client.get("/api/v1/weather", params={"lat": 30.73, "lon": 76.77})
    assert resp.status_code == 200
    data = resp.json()
    assert data["data_status"]["mode"] == "live"
    assert data["observation"]["temperature_c"] == 24.5
    assert data["observation"]["source"] == "open-meteo"


@pytest.mark.asyncio
async def test_weather_invalid_coordinates(client, mock_router):
    resp = await client.get("/api/v1/weather", params={"lat": -999, "lon": 76.77})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_weather_provider_timeout(client, mock_router):
    mock_router.get("https://weather.test/v1/forecast").mock(
        side_effect=httpx.TimeoutException("timeout")
    )
    resp = await client.get("/api/v1/weather", params={"lat": 30.73, "lon": 76.77})
    assert resp.status_code == 200
    data = resp.json()
    assert data["observation"] is None
    assert data["data_status"]["mode"] == "degraded"
    assert data["data_status"]["sources"][0]["status"] == "unavailable"


@pytest.mark.asyncio
async def test_weather_not_configured(client, mock_router):
    from app.core.config import get_settings
    from app.main import app

    app.dependency_overrides[get_settings] = lambda: make_settings(
        WEATHER_PROVIDER_URL=None
    )
    try:
        resp = await client.get("/api/v1/weather", params={"lat": 30.73, "lon": 76.77})
    finally:
        app.dependency_overrides.clear()
    assert resp.status_code == 200
    data = resp.json()
    assert data["observation"] is None
    assert data["data_status"]["sources"][0]["status"] == "unavailable"


@pytest.mark.asyncio
async def test_weather_invalid_upstream_response(client, mock_router):
    mock_router.get("https://weather.test/v1/forecast").mock(
        return_value=httpx.Response(200, json={"unexpected": True})
    )
    resp = await client.get("/api/v1/weather", params={"lat": 30.73, "lon": 76.77})
    data = resp.json()
    assert resp.status_code == 200
    assert data["observation"] is None
    assert data["data_status"]["sources"][0]["status"] == "error"
