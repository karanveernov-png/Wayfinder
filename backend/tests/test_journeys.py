from __future__ import annotations

import httpx
import pytest

GEOCODE_JALANDHAR = [
    {"lat": "31.3260", "lon": "75.5762", "display_name": "Jalandhar, Punjab, India"}
]
GEOCODE_CHANDIGARH = [
    {"lat": "30.7333", "lon": "76.7794", "display_name": "Chandigarh, India"}
]

OSRM_OK = {
    "code": "Ok",
    "routes": [
        {
            "distance": 144000.0,
            "duration": 9000.0,
            "geometry": {
                "type": "LineString",
                "coordinates": [[75.5762, 31.3260], [76.7794, 30.7333]],
            },
        }
    ],
}

OVERPASS_OK = {
    "elements": [
        {
            "type": "node",
            "id": 1,
            "lat": 30.73,
            "lon": 76.77,
            "tags": {"amenity": "hospital", "name": "Test Hospital"},
        },
    ]
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
WEATHER_STORM = {
    "current_weather": {
        "temperature": 18.0,
        "windspeed": 15.0,
        "winddirection": 180,
        "weathercode": 95,
        "is_day": 1,
        "time": "2026-10-19T10:00",
    }
}


def _mock_happy_path(mock_router):
    mock_router.get(url__regex=r"^https://nominatim\.test/search.*Jalandhar.*$").mock(
        return_value=httpx.Response(200, json=GEOCODE_JALANDHAR)
    )
    mock_router.get(url__regex=r"^https://nominatim\.test/search.*Chandigarh.*$").mock(
        return_value=httpx.Response(200, json=GEOCODE_CHANDIGARH)
    )
    mock_router.get(url__regex=r"^https://router\.test/route/v1/driving/.*$").mock(
        return_value=httpx.Response(200, json=OSRM_OK)
    )
    mock_router.post("https://overpass.test/api/interpreter").mock(
        return_value=httpx.Response(200, json=OVERPASS_OK)
    )
    mock_router.get("https://weather.test/v1/forecast").mock(
        return_value=httpx.Response(200, json=WEATHER_CLEAR)
    )


@pytest.mark.asyncio
async def test_journey_analyse_happy_path_is_live(client, mock_router):
    _mock_happy_path(mock_router)
    resp = await client.post(
        "/api/v1/journeys/analyse",
        json={
            "origin": "Jalandhar, Punjab, India",
            "destination": "Chandigarh, India",
            # Alerts are opt-out here so this test focuses on the route and
            # core journey pipeline; Bhuvan is unconfigured, so the result
            # should correctly report its successful OSRM backup as partial.
            "include_alerts": False,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["journey"]["distance_km"] == 144.0
    assert data["journey"]["duration_minutes"] == 150.0
    assert data["journey"]["geometry"]["type"] == "LineString"
    assert data["journey"]["origin"]["resolved"]["lat"] == pytest.approx(31.326)
    assert len(data["facilities"]) == 1
    assert data["facilities"][0]["category"] == "hospital"
    assert data["risk_assessment"]["level"] in ("low", "moderate", "high")
    assert data["risk_assessment"]["score"] is not None
    assert data["data_status"]["mode"] == "partial"


@pytest.mark.asyncio
async def test_journey_reports_osrm_backup_when_bhuvan_token_is_missing(
    client, mock_router
):
    _mock_happy_path(mock_router)
    response = await client.post(
        "/api/v1/journeys/analyse",
        json={
            "origin": "Jalandhar, Punjab, India",
            "destination": "Chandigarh, India",
            "include_alerts": False,
        },
    )

    assert response.status_code == 200
    data = response.json()
    bhuvan_status = next(
        source
        for source in data["data_status"]["sources"]
        if source["name"] == "isro-bhuvan-routing"
    )
    backup_status = next(
        source
        for source in data["data_status"]["sources"]
        if source["name"] == "osrm-routing"
    )
    assert bhuvan_status["status"] == "not_configured"
    assert backup_status["status"] == "ok"
    assert "Backup routing used" in backup_status["detail"]


@pytest.mark.asyncio
async def test_journey_analyse_alerts_not_configured_by_default(client, mock_router):
    """With alerts requested (the default) and no ALERT_PROVIDER_URL set, the
    response must say so explicitly rather than silently omitting alerts."""
    _mock_happy_path(mock_router)
    resp = await client.post(
        "/api/v1/journeys/analyse",
        json={"origin": "Jalandhar, Punjab, India", "destination": "Chandigarh, India"},
    )
    data = resp.json()
    assert data["data_status"]["mode"] == "partial"
    alert_sources = [s for s in data["data_status"]["sources"] if s["name"] == "alerts"]
    assert alert_sources[0]["status"] == "not_configured"


@pytest.mark.asyncio
async def test_journey_analyse_full_pipeline_integration(client, mock_router):
    """End-to-end pipeline check with controlled test data (routing -> facilities ->
    weather -> risk engine -> recommendations), per spec section 9."""
    _mock_happy_path(mock_router)
    mock_router.get("https://weather.test/v1/forecast").mock(
        return_value=httpx.Response(200, json=WEATHER_STORM)
    )

    resp = await client.post(
        "/api/v1/journeys/analyse",
        json={"origin": "Jalandhar, Punjab, India", "destination": "Chandigarh, India"},
    )
    data = resp.json()
    assert resp.status_code == 200
    # Thunderstorm weather code should push score above 0 and be explained in reasons
    assert data["risk_assessment"]["score"] > 0
    assert any(
        "weather" in r.lower() or "hazard" in r.lower()
        for r in data["risk_assessment"]["reasons"]
    )
    assert any(
        "No significant issues" in r
        or "caution" in r.lower()
        or "delaying" in r.lower()
        for r in data["recommendations"]
    )


@pytest.mark.asyncio
async def test_journey_analyse_invalid_travel_mode(client, mock_router):
    resp = await client.post(
        "/api/v1/journeys/analyse",
        json={"origin": "A", "destination": "B", "travel_mode": "flying"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_journey_uses_supplied_coordinates_and_selected_cycling_mode(
    client, mock_router
):
    mock_router.get(
        url__regex=r"^https://router\.test/route/v1/cycling/.*$"
    ).mock(return_value=httpx.Response(200, json=OSRM_OK))
    mock_router.get("https://weather.test/v1/forecast").mock(
        return_value=httpx.Response(200, json=WEATHER_CLEAR)
    )

    response = await client.post(
        "/api/v1/journeys/analyse",
        json={
            "origin": "Map point A",
            "destination": "Map point B",
            "origin_coordinates": {"lat": 31.0, "lon": 75.0},
            "destination_coordinates": {"lat": 30.5, "lon": 76.0},
            "travel_mode": "cycling",
            "include_facilities": False,
            "include_alerts": False,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["journey"]["origin"]["resolved"] == {"lat": 31.0, "lon": 75.0}
    assert data["journey"]["destination"]["resolved"] == {"lat": 30.5, "lon": 76.0}
    # The supplied origin/destination text is now echoed back as the
    # display_name whenever trusted coordinates are supplied, instead of
    # a synthesized "Map point (lat, lon)" string that discarded it (see
    # app/api/routes/journeys.py _resolve_location and
    # docs/LOCATION_AUTOCOMPLETE_GUIDE.md "Pre-existing issues fixed").
    # For this request that text already happens to be "Map point A" -
    # this assertion is about it being echoed through unchanged, not
    # about the backend synthesizing that particular string itself.
    assert data["journey"]["origin"]["display_name"] == "Map point A"
    assert data["journey"]["geometry"]["type"] == "LineString"
    assert any(
        "cycling profile" in source["detail"]
        for source in data["data_status"]["sources"]
        if source["name"] == "osrm-routing"
    )
    assert not any(
        "nominatim.test" in str(call.request.url) for call in mock_router.calls
    )


@pytest.mark.asyncio
async def test_journey_analyse_missing_fields(client, mock_router):
    resp = await client.post("/api/v1/journeys/analyse", json={"origin": "A"})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_journey_analyse_blank_origin_rejected(client, mock_router):
    resp = await client.post(
        "/api/v1/journeys/analyse", json={"origin": "   ", "destination": "Chandigarh"}
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_journey_analyse_routing_timeout_is_degraded_not_fabricated(
    client, mock_router
):
    mock_router.get(url__regex=r"^https://nominatim\.test/search.*Jalandhar.*$").mock(
        return_value=httpx.Response(200, json=GEOCODE_JALANDHAR)
    )
    mock_router.get(url__regex=r"^https://nominatim\.test/search.*Chandigarh.*$").mock(
        return_value=httpx.Response(200, json=GEOCODE_CHANDIGARH)
    )
    mock_router.get(url__regex=r"^https://router\.test/route/v1/driving/.*$").mock(
        side_effect=httpx.TimeoutException("timed out")
    )
    mock_router.post("https://overpass.test/api/interpreter").mock(
        return_value=httpx.Response(200, json={"elements": []})
    )
    mock_router.get("https://weather.test/v1/forecast").mock(
        return_value=httpx.Response(200, json=WEATHER_CLEAR)
    )

    resp = await client.post(
        "/api/v1/journeys/analyse",
        json={"origin": "Jalandhar, Punjab, India", "destination": "Chandigarh, India"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["journey"]["distance_km"] is None
    assert data["journey"]["duration_minutes"] is None
    assert data["journey"]["geometry"] is None
    assert data["data_status"]["mode"] == "degraded"
    assert data["risk_assessment"]["level"] == "unknown"
    assert data["risk_assessment"]["score"] is None
    routing_sources = [
        s for s in data["data_status"]["sources"] if s["name"] == "osrm-routing"
    ]
    assert routing_sources[0]["status"] == "unavailable"


@pytest.mark.asyncio
async def test_journey_analyse_invalid_upstream_route_response(client, mock_router):
    mock_router.get(url__regex=r"^https://nominatim\.test/search.*Jalandhar.*$").mock(
        return_value=httpx.Response(200, json=GEOCODE_JALANDHAR)
    )
    mock_router.get(url__regex=r"^https://nominatim\.test/search.*Chandigarh.*$").mock(
        return_value=httpx.Response(200, json=GEOCODE_CHANDIGARH)
    )
    # Missing "routes" / malformed payload
    mock_router.get(url__regex=r"^https://router\.test/route/v1/driving/.*$").mock(
        return_value=httpx.Response(200, json={"code": "Ok"})
    )
    mock_router.post("https://overpass.test/api/interpreter").mock(
        return_value=httpx.Response(200, json={"elements": []})
    )
    mock_router.get("https://weather.test/v1/forecast").mock(
        return_value=httpx.Response(200, json=WEATHER_CLEAR)
    )

    resp = await client.post(
        "/api/v1/journeys/analyse",
        json={"origin": "Jalandhar, Punjab, India", "destination": "Chandigarh, India"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["journey"]["distance_km"] is None
    assert data["data_status"]["mode"] == "degraded"


@pytest.mark.asyncio
async def test_journey_analyse_partial_when_weather_fails(client, mock_router):
    mock_router.get(url__regex=r"^https://nominatim\.test/search.*Jalandhar.*$").mock(
        return_value=httpx.Response(200, json=GEOCODE_JALANDHAR)
    )
    mock_router.get(url__regex=r"^https://nominatim\.test/search.*Chandigarh.*$").mock(
        return_value=httpx.Response(200, json=GEOCODE_CHANDIGARH)
    )
    mock_router.get(url__regex=r"^https://router\.test/route/v1/driving/.*$").mock(
        return_value=httpx.Response(200, json=OSRM_OK)
    )
    mock_router.post("https://overpass.test/api/interpreter").mock(
        return_value=httpx.Response(200, json={"elements": []})
    )
    mock_router.get("https://weather.test/v1/forecast").mock(
        side_effect=httpx.TimeoutException("timed out")
    )

    resp = await client.post(
        "/api/v1/journeys/analyse",
        json={"origin": "Jalandhar, Punjab, India", "destination": "Chandigarh, India"},
    )
    assert resp.status_code == 200
    data = resp.json()
    # Critical path (route) succeeded -> usable result, but not fully "live"
    assert data["journey"]["distance_km"] == 144.0
    assert data["data_status"]["mode"] == "partial"
    weather_sources = [
        s for s in data["data_status"]["sources"] if s["name"] == "open-meteo"
    ]
    assert weather_sources[0]["status"] == "unavailable"


@pytest.mark.asyncio
async def test_journey_analyse_insufficient_data_for_risk_score(client, mock_router):
    """When both weather and alerts are unavailable, risk must be 'unknown', not a fabricated score."""
    mock_router.get(url__regex=r"^https://nominatim\.test/search.*Jalandhar.*$").mock(
        return_value=httpx.Response(200, json=GEOCODE_JALANDHAR)
    )
    mock_router.get(url__regex=r"^https://nominatim\.test/search.*Chandigarh.*$").mock(
        return_value=httpx.Response(200, json=GEOCODE_CHANDIGARH)
    )
    mock_router.get(url__regex=r"^https://router\.test/route/v1/driving/.*$").mock(
        return_value=httpx.Response(200, json=OSRM_OK)
    )
    mock_router.post("https://overpass.test/api/interpreter").mock(
        return_value=httpx.Response(200, json={"elements": []})
    )
    mock_router.get("https://weather.test/v1/forecast").mock(
        side_effect=httpx.TimeoutException("timed out")
    )

    resp = await client.post(
        "/api/v1/journeys/analyse",
        json={
            "origin": "Jalandhar, Punjab, India",
            "destination": "Chandigarh, India",
            "include_alerts": True,
        },
    )
    data = resp.json()
    # alerts source is not_configured (default), weather fails -> both unusable -> unknown
    assert data["risk_assessment"]["level"] == "unknown"
    assert data["risk_assessment"]["score"] is None


# --------------------------------------------------------------------------
# facility_radius_km bounds on /journeys/analyse.
#
# Regression tests for a schema/settings drift bug: JourneyAnalyseRequest
# used to hardcode `le=50` on facility_radius_km, while /facilities/nearby
# (and the frontend's 200m-70km contract, and config.py's
# MAX_FACILITY_RADIUS_KM=70.0 default) all agree on a 70km max. A request
# with facility_radius_km between 50 and 70 was therefore rejected by
# /journeys/analyse despite being entirely valid everywhere else in the
# app. Fixed by removing the hardcoded bound from the schema and validating
# against the live settings in the route handler instead, the same pattern
# /facilities/nearby already used - see analyse_journey() in journeys.py.
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_journey_analyse_accepts_facility_radius_above_old_50km_cap(
    client, mock_router
):
    """70km must be accepted now that the hardcoded `le=50` is gone -
    this specific value was rejected by the pre-fix schema."""
    _mock_happy_path(mock_router)
    resp = await client.post(
        "/api/v1/journeys/analyse",
        json={
            "origin": "Jalandhar, Punjab, India",
            "destination": "Chandigarh, India",
            "include_alerts": False,
            "facility_radius_km": 70.0,
        },
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_journey_analyse_rejects_facility_radius_above_max(client, mock_router):
    """Still must reject anything past the real (settings-driven) max -
    the fix must not have turned into 'accept anything'."""
    resp = await client.post(
        "/api/v1/journeys/analyse",
        json={
            "origin": "Jalandhar, Punjab, India",
            "destination": "Chandigarh, India",
            "include_alerts": False,
            "facility_radius_km": 70.1,
        },
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_journey_analyse_rejects_facility_radius_below_min(client, mock_router):
    """0.01km is > 0 (passes the schema's gt=0) but below
    MIN_FACILITY_RADIUS_KM (0.2 by default) - must still be rejected now
    that the only schema-level check is gt=0."""
    resp = await client.post(
        "/api/v1/journeys/analyse",
        json={
            "origin": "Jalandhar, Punjab, India",
            "destination": "Chandigarh, India",
            "include_alerts": False,
            "facility_radius_km": 0.01,
        },
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_journey_analyse_facility_radius_bound_not_enforced_when_facilities_excluded(
    client, mock_router
):
    """facility_radius_km is irrelevant when include_facilities=False;
    an out-of-range value must not block an otherwise-valid request that
    never uses it, mirroring /facilities/nearby only validating radius on
    the path that actually performs a facility search."""
    _mock_happy_path(mock_router)
    resp = await client.post(
        "/api/v1/journeys/analyse",
        json={
            "origin": "Jalandhar, Punjab, India",
            "destination": "Chandigarh, India",
            "include_alerts": False,
            "include_facilities": False,
            "facility_radius_km": 999.0,
        },
    )
    assert resp.status_code == 200
