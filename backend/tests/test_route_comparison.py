from __future__ import annotations

import httpx
import pytest

GEOCODE_JALANDHAR = [
    {"lat": "31.3260", "lon": "75.5762", "display_name": "Jalandhar, Punjab, India"}
]
GEOCODE_CHANDIGARH = [
    {"lat": "30.7333", "lon": "76.7794", "display_name": "Chandigarh, India"}
]

OSRM_TWO_ROUTES = {
    "code": "Ok",
    "routes": [
        {
            "distance": 144000.0,
            "duration": 9000.0,  # 150 min — the faster of the two
            "geometry": {
                "type": "LineString",
                "coordinates": [[75.5762, 31.3260], [76.7794, 30.7333]],
            },
        },
        {
            "distance": 139000.0,  # shorter distance, but slower below
            "duration": 10200.0,  # 170 min
            "geometry": {
                "type": "LineString",
                "coordinates": [[75.5762, 31.3260], [75.9, 31.0], [76.7794, 30.7333]],
            },
        },
    ],
}

OSRM_ONE_ROUTE = {
    "code": "Ok",
    "routes": [OSRM_TWO_ROUTES["routes"][0]],
}

WEATHER_CLEAR = {
    "current_weather": {
        "temperature": 22.0,
        "windspeed": 10.0,
        "winddirection": 180,
        "weathercode": 0,
        "is_day": 1,
        "time": "2026-10-19T10:00",
    }
}


def _mock_geocoding(mock_router):
    mock_router.get(url__regex=r"^https://nominatim\.test/search.*Jalandhar.*$").mock(
        return_value=httpx.Response(200, json=GEOCODE_JALANDHAR)
    )
    mock_router.get(url__regex=r"^https://nominatim\.test/search.*Chandigarh.*$").mock(
        return_value=httpx.Response(200, json=GEOCODE_CHANDIGARH)
    )


@pytest.mark.asyncio
async def test_compare_routes_returns_labeled_options_with_fastest_and_shortest_flags(
    client, mock_router
):
    _mock_geocoding(mock_router)
    mock_router.get(url__regex=r"^https://router\.test/route/v1/driving/.*$").mock(
        return_value=httpx.Response(200, json=OSRM_TWO_ROUTES)
    )
    mock_router.get("https://weather.test/v1/forecast").mock(
        return_value=httpx.Response(200, json=WEATHER_CLEAR)
    )

    resp = await client.post(
        "/api/v1/journeys/compare-routes",
        json={"origin": "Jalandhar, Punjab, India", "destination": "Chandigarh, India"},
    )

    assert resp.status_code == 200
    data = resp.json()
    assert len(data["routes"]) == 2

    fastest, alternate = data["routes"]
    assert fastest["label"] == "Fastest route"
    assert fastest["duration_minutes"] == 150.0
    assert fastest["is_fastest"] is True
    assert fastest["is_shortest_distance"] is False  # route 2 is the shorter one

    assert alternate["label"] == "Alternate route 1"
    assert alternate["distance_km"] == 139.0
    assert alternate["is_shortest_distance"] is True
    assert alternate["is_fastest"] is False

    # Both routes got their own risk assessment and weather sample.
    for option in data["routes"]:
        assert option["risk_assessment"]["level"] in ("unknown", "low", "moderate", "high")
        assert option["weather"]["temperature_c"] == pytest.approx(22.0)

    assert data["data_status"]["mode"] == "live"


@pytest.mark.asyncio
async def test_compare_routes_handles_a_single_route_without_error(client, mock_router):
    """Not every OSRM deployment/profile returns real alternatives (see
    get_route_alternatives' docstring) - one route back should still be a
    normal, non-error response, not a failure."""
    _mock_geocoding(mock_router)
    mock_router.get(url__regex=r"^https://router\.test/route/v1/driving/.*$").mock(
        return_value=httpx.Response(200, json=OSRM_ONE_ROUTE)
    )
    mock_router.get("https://weather.test/v1/forecast").mock(
        return_value=httpx.Response(200, json=WEATHER_CLEAR)
    )

    resp = await client.post(
        "/api/v1/journeys/compare-routes",
        json={"origin": "Jalandhar, Punjab, India", "destination": "Chandigarh, India"},
    )

    assert resp.status_code == 200
    data = resp.json()
    assert len(data["routes"]) == 1
    assert data["routes"][0]["label"] == "Fastest route"
    assert data["routes"][0]["is_fastest"] is True
    assert data["routes"][0]["is_shortest_distance"] is True
    assert data["data_status"]["mode"] == "partial"


@pytest.mark.asyncio
async def test_compare_routes_ungeocodable_origin_is_degraded_not_an_error(client, mock_router):
    mock_router.get(url__regex=r"^https://nominatim\.test/search.*$").mock(
        return_value=httpx.Response(200, json=[])
    )

    resp = await client.post(
        "/api/v1/journeys/compare-routes",
        json={"origin": "Nowhere At All Xyzzy", "destination": "Also Nowhere Xyzzy"},
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["routes"] == []
    assert data["data_status"]["mode"] == "degraded"
