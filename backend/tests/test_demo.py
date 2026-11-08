"""
Tests for demo mode (POST /api/v1/journeys/analyse with demo=true).

Demo mode makes zero live provider calls, so no respx mocking is
required.  Every test here verifies deterministic behaviour of the
pre-stored data pipeline.
"""

from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# Demo data unit tests (no HTTP client needed)
# ---------------------------------------------------------------------------


def test_demo_journey_loads():
    from app.services.demo import get_demo_journey

    j = get_demo_journey()
    assert j.origin_query == "Chandigarh, India"
    assert j.destination_query == "Ludhiana, Punjab, India"
    assert abs(j.origin_coords.lat - 30.7333) < 0.01
    assert abs(j.destination_coords.lat - 30.9010) < 0.01
    assert j.distance_km > 0
    assert j.duration_minutes > 0
    assert j.geometry["type"] == "LineString"
    # GeoJSON coordinates are [lon, lat] pairs
    assert all(len(pt) == 2 for pt in j.geometry["coordinates"])


def test_demo_facilities_loads_all_18():
    from app.services.demo import get_demo_facilities

    facilities = get_demo_facilities()
    assert len(facilities) == 18


def test_demo_facilities_categories_covered():
    from app.services.demo import get_demo_facilities

    facilities = get_demo_facilities()
    cats = {f.category for f in facilities}
    assert cats == {"fuel", "hospital", "restaurant", "rest_stop"}


def test_demo_facilities_coordinates_valid():
    from app.services.demo import get_demo_facilities

    for f in get_demo_facilities():
        assert -90 <= f.coordinates.lat <= 90
        assert -180 <= f.coordinates.lon <= 180
        # All facilities should be somewhere in Punjab/India corridor
        assert 30.0 <= f.coordinates.lat <= 31.5
        assert 75.0 <= f.coordinates.lon <= 77.5


def test_demo_facilities_all_have_source():
    from app.services.demo import get_demo_facilities

    for f in get_demo_facilities():
        assert f.source == "demo-deepak-directory"


def test_demo_alerts_loads():
    from app.services.demo import get_demo_alerts

    alerts = get_demo_alerts()
    assert len(alerts) == 2


def test_demo_alerts_are_unverified():
    """Demo alerts must never claim to be verified live reports."""
    from app.services.demo import get_demo_alerts

    for a in get_demo_alerts():
        assert a.verified is False
        assert a.source == "demo-data"


def test_demo_alerts_have_location():
    from app.services.demo import get_demo_alerts

    for a in get_demo_alerts():
        assert a.location is not None
        # Both demo alerts are near Ludhiana (<15 km), within the risk engine
        # proximity threshold used for route-endpoint relevance checks.
        assert a.location.lon < 76.1  # west of Samrala → near Ludhiana


# ---------------------------------------------------------------------------
# HTTP endpoint tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_demo_endpoint_returns_200(client):
    resp = await client.post(
        "/api/v1/journeys/analyse",
        json={"origin": "ignored", "destination": "ignored", "demo": True},
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_demo_data_status_mode_is_demo(client):
    resp = await client.post(
        "/api/v1/journeys/analyse",
        json={"origin": "x", "destination": "y", "demo": True},
    )
    body = resp.json()
    assert body["data_status"]["mode"] == "demo"


@pytest.mark.asyncio
async def test_demo_returns_chandigarh_ludhiana_route(client):
    resp = await client.post(
        "/api/v1/journeys/analyse",
        json={"origin": "anything", "destination": "anything", "demo": True},
    )
    body = resp.json()
    journey = body["journey"]
    assert "Chandigarh" in journey["origin"]["query"]
    assert "Ludhiana" in journey["destination"]["query"]
    assert journey["distance_km"] == pytest.approx(98.3)
    assert journey["duration_minutes"] == pytest.approx(97.0)


@pytest.mark.asyncio
async def test_demo_geometry_is_geojson_linestring(client):
    resp = await client.post(
        "/api/v1/journeys/analyse",
        json={"origin": "x", "destination": "y", "demo": True},
    )
    geom = resp.json()["journey"]["geometry"]
    assert geom["type"] == "LineString"
    assert len(geom["coordinates"]) >= 2


@pytest.mark.asyncio
async def test_demo_returns_18_facilities(client):
    resp = await client.post(
        "/api/v1/journeys/analyse",
        json={"origin": "x", "destination": "y", "demo": True},
    )
    assert len(resp.json()["facilities"]) == 18


@pytest.mark.asyncio
async def test_demo_returns_2_alerts(client):
    resp = await client.post(
        "/api/v1/journeys/analyse",
        json={"origin": "x", "destination": "y", "demo": True},
    )
    assert len(resp.json()["alerts"]) == 2


@pytest.mark.asyncio
async def test_demo_risk_assessment_is_not_unknown(client):
    """
    The risk engine should produce a scored result in demo mode because
    demo alerts are provided (alerts_status='ok').  It must not return
    'unknown' due to missing data.
    """
    resp = await client.post(
        "/api/v1/journeys/analyse",
        json={"origin": "x", "destination": "y", "demo": True},
    )
    ra = resp.json()["risk_assessment"]
    assert ra["level"] != "unknown"
    assert ra["score"] is not None


@pytest.mark.asyncio
async def test_demo_risk_level_is_low_given_unverified_alerts(client):
    """
    Two unverified alerts (moderate + low severity) should produce a
    'low' risk level (score ~10, threshold < 25).
    """
    resp = await client.post(
        "/api/v1/journeys/analyse",
        json={"origin": "x", "destination": "y", "demo": True},
    )
    ra = resp.json()["risk_assessment"]
    assert ra["level"] == "low"
    assert ra["score"] == pytest.approx(10.0)


@pytest.mark.asyncio
async def test_demo_sources_include_demo_labels(client):
    resp = await client.post(
        "/api/v1/journeys/analyse",
        json={"origin": "x", "destination": "y", "demo": True},
    )
    source_names = {s["name"] for s in resp.json()["data_status"]["sources"]}
    assert "demo-journey" in source_names
    assert "demo-facilities" in source_names
    assert "demo-alerts" in source_names


@pytest.mark.asyncio
async def test_demo_weather_is_reported_unavailable(client):
    """Weather is not fetched in demo mode; it must be labelled unavailable."""
    resp = await client.post(
        "/api/v1/journeys/analyse",
        json={"origin": "x", "destination": "y", "demo": True},
    )
    sources = resp.json()["data_status"]["sources"]
    meteo = next((s for s in sources if s["name"] == "open-meteo"), None)
    assert meteo is not None
    assert meteo["status"] == "unavailable"


@pytest.mark.asyncio
async def test_live_mode_unaffected_by_demo_field(client, mock_router):
    """
    Requests with demo=False (the default) must still go through the live
    pipeline and respect provider mocks.
    """
    import httpx
    from tests.test_journeys import GEOCODE_CHANDIGARH, OSRM_OK, WEATHER_CLEAR

    GEOCODE_LUDHIANA = [
        {"lat": "30.9010", "lon": "75.8573", "display_name": "Ludhiana, India"}
    ]

    mock_router.get("https://nominatim.test/search").mock(
        side_effect=[
            httpx.Response(200, json=GEOCODE_CHANDIGARH),
            httpx.Response(200, json=GEOCODE_LUDHIANA),
        ]
    )
    mock_router.get(
        "https://router.test/route/v1/driving/76.7794,30.7333;75.8573,30.901"
    ).mock(return_value=httpx.Response(200, json=OSRM_OK))
    mock_router.post("https://overpass.test/api/interpreter").mock(
        return_value=httpx.Response(200, json={"elements": []})
    )
    mock_router.get("https://weather.test/v1/forecast").mock(
        return_value=httpx.Response(200, json=WEATHER_CLEAR)
    )

    resp = await client.post(
        "/api/v1/journeys/analyse",
        json={
            "origin": "Chandigarh, India",
            "destination": "Ludhiana, Punjab, India",
            "demo": False,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    # Live mode: data_status.mode should NOT be "demo"
    assert body["data_status"]["mode"] != "demo"
