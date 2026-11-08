from __future__ import annotations

import httpx
import pytest

from tests.conftest import make_settings

EONET_SAMPLE = {
    "title": "EONET Events",
    "events": [
        {
            "id": "EONET_1",
            "title": "Wildfire - Test County",
            "categories": [{"id": "wildfires", "title": "Wildfires"}],
            "sources": [{"id": "InciWeb", "url": "https://inciweb.test/1"}],
            "geometry": [
                {
                    "date": "2026-10-20T00:00:00Z",
                    "type": "Point",
                    "coordinates": [76.78, 30.74],  # [lon, lat] - near the query point
                }
            ],
        },
        {
            "id": "EONET_2",
            "title": "Severe Storm - Far Away",
            "categories": [{"id": "severeStorms", "title": "Severe Storms"}],
            "sources": [{"id": "JTWC", "url": "https://jtwc.test/2"}],
            "geometry": [
                {
                    "date": "2026-10-20T00:00:00Z",
                    "type": "Point",
                    "coordinates": [10.0, 10.0],  # far from the query point
                }
            ],
        },
        {
            "id": "EONET_3",
            "title": "Unmapped Category Event",
            "categories": [{"id": "manmade", "title": "Man-made"}],
            "sources": [],
            "geometry": [
                {
                    "date": "2026-10-19T00:00:00Z",
                    "type": "Point",
                    "coordinates": [76.77, 30.73],
                }
            ],
        },
    ],
}

@pytest.mark.asyncio
async def test_alerts_not_configured_when_explicitly_unset(client, mock_router):
    """conftest's base settings set ALERT_PROVIDER_URL=None for test
    isolation (the real app default is NASA EONET - see config.py); this
    confirms the explicit "not_configured" contract still holds when a
    deployment genuinely has no alerts provider set."""
    resp = await client.get("/api/v1/alerts", params={"lat": 30.73, "lon": 76.77})
    assert resp.status_code == 200
    data = resp.json()
    assert data["alerts"] == []
    assert data["data_status"]["mode"] == "degraded"
    assert data["data_status"]["sources"][0]["status"] == "not_configured"


@pytest.mark.asyncio
async def test_alerts_invalid_coordinates(client, mock_router):
    resp = await client.get("/api/v1/alerts", params={"lat": 200, "lon": 76.77})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_alerts_eonet_live_success(client, mock_router):
    """Real normalization against EONET's actual documented shape: the
    near event is kept with the right category/severity/source, the far
    event is filtered out by real haversine distance (not just the bbox
    rectangle), and the unmapped category gets severity 'unknown' rather
    than a guessed value."""
    mock_router.get("https://alerts.test/events").mock(
        return_value=httpx.Response(200, json=EONET_SAMPLE)
    )
    from app.core.config import get_settings
    from app.main import app

    app.dependency_overrides[get_settings] = lambda: make_settings(
        ALERT_PROVIDER_URL="https://alerts.test"
    )
    try:
        resp = await client.get(
            "/api/v1/alerts", params={"lat": 30.73, "lon": 76.77, "radius_km": 25}
        )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    data = resp.json()
    assert data["data_status"]["sources"][0]["status"] == "ok"

    ids = {a["id"] for a in data["alerts"]}
    assert ids == {"EONET_1", "EONET_3"}  # EONET_2 is too far away

    wildfire = next(a for a in data["alerts"] if a["id"] == "EONET_1")
    assert wildfire["category"] == "Wildfires"
    assert wildfire["severity"] == "moderate"
    assert wildfire["source"] == "nasa-eonet (InciWeb)"
    assert wildfire["verified"] is None

    unmapped = next(a for a in data["alerts"] if a["id"] == "EONET_3")
    assert unmapped["severity"] == "unknown"


@pytest.mark.asyncio
async def test_alerts_eonet_unreachable(client, mock_router):
    mock_router.get("https://alerts.test/events").mock(
        side_effect=httpx.TimeoutException("timeout")
    )
    from app.core.config import get_settings
    from app.main import app

    app.dependency_overrides[get_settings] = lambda: make_settings(
        ALERT_PROVIDER_URL="https://alerts.test"
    )
    try:
        resp = await client.get("/api/v1/alerts", params={"lat": 30.73, "lon": 76.77})
    finally:
        app.dependency_overrides.clear()
    assert resp.status_code == 200
    data = resp.json()
    assert data["alerts"] == []
    assert data["data_status"]["sources"][0]["status"] == "unavailable"


@pytest.mark.asyncio
async def test_alerts_eonet_invalid_response(client, mock_router):
    mock_router.get("https://alerts.test/events").mock(
        return_value=httpx.Response(200, json={"unexpected": True})
    )
    from app.core.config import get_settings
    from app.main import app

    app.dependency_overrides[get_settings] = lambda: make_settings(
        ALERT_PROVIDER_URL="https://alerts.test"
    )
    try:
        resp = await client.get("/api/v1/alerts", params={"lat": 30.73, "lon": 76.77})
    finally:
        app.dependency_overrides.clear()
    data = resp.json()
    assert resp.status_code == 200
    assert data["data_status"]["sources"][0]["status"] == "error"




