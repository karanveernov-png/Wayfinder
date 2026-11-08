from __future__ import annotations

from urllib.parse import parse_qs

import httpx
import pytest

OVERPASS_RESULTS = {
    "elements": [
        {
            "type": "node",
            "id": 1,
            "lat": 30.74,
            "lon": 76.78,
            "tags": {"amenity": "hospital", "name": "City Hospital"},
        },
        {
            "type": "way",
            "id": 2,
            "center": {"lat": 30.735, "lon": 76.77},
            "tags": {"amenity": "fuel"},
        },
        {
            "type": "node",
            "id": 3,
            "lat": 30.70,
            "lon": 76.80,
            "tags": {"shop": "bakery"},
        },  # unmapped category - excluded
    ]
}


@pytest.mark.asyncio
async def test_facilities_nearby_success(client, mock_router):
    mock_router.post("https://overpass.test/api/interpreter").mock(
        return_value=httpx.Response(200, json=OVERPASS_RESULTS)
    )
    resp = await client.get(
        "/api/v1/facilities/nearby", params={"lat": 30.73, "lon": 76.77, "radius_km": 5}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["data_status"]["mode"] == "live"
    # Unmapped "bakery" element must be excluded, not guessed into a category
    assert len(data["facilities"]) == 2
    categories = {f["category"] for f in data["facilities"]}
    assert categories == {"hospital", "fuel"}
    # Facility with no name tag must surface name: null, never a fabricated name
    fuel = next(f for f in data["facilities"] if f["category"] == "fuel")
    assert fuel["name"] is None
    # Results must be sorted by distance ascending
    assert data["facilities"][0]["distance_km"] <= data["facilities"][1]["distance_km"]


@pytest.mark.asyncio
async def test_facilities_detects_pharmacy_lodging_and_broadened_restaurant_tags(
    client, mock_router
):
    """pharmacy/lodging are new categories; cafe and fast_food must now
    classify as "restaurant" (previously only amenity=restaurant did),
    matching what the frontend already labels this category as."""
    elements = {
        "elements": [
            {"type": "node", "id": 10, "lat": 30.731, "lon": 76.771, "tags": {"amenity": "pharmacy", "name": "Apollo Pharmacy"}},
            {"type": "node", "id": 11, "lat": 30.732, "lon": 76.772, "tags": {"tourism": "hotel", "name": "Grand Hotel"}},
            {"type": "node", "id": 12, "lat": 30.733, "lon": 76.773, "tags": {"amenity": "cafe", "name": "Corner Cafe"}},
            {"type": "node", "id": 13, "lat": 30.734, "lon": 76.774, "tags": {"amenity": "fast_food", "name": "Quick Bite"}},
            {"type": "node", "id": 14, "lat": 30.735, "lon": 76.775, "tags": {"tourism": "camp_site", "name": "Excluded Campsite"}},
        ]
    }
    mock_router.post("https://overpass.test/api/interpreter").mock(
        return_value=httpx.Response(200, json=elements)
    )
    resp = await client.get(
        "/api/v1/facilities/nearby", params={"lat": 30.73, "lon": 76.77, "radius_km": 5}
    )
    assert resp.status_code == 200
    data = resp.json()
    by_name = {f["name"]: f["category"] for f in data["facilities"]}
    assert by_name["Apollo Pharmacy"] == "pharmacy"
    assert by_name["Grand Hotel"] == "lodging"
    assert by_name["Corner Cafe"] == "restaurant"
    assert by_name["Quick Bite"] == "restaurant"
    # camp_site is deliberately not mapped to "lodging" - excluded entirely
    assert "Excluded Campsite" not in by_name


@pytest.mark.asyncio
async def test_facilities_invalid_coordinates(client, mock_router):
    resp = await client.get(
        "/api/v1/facilities/nearby", params={"lat": 999, "lon": 76.77}
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_facilities_radius_too_large(client, mock_router):
    resp = await client.get(
        "/api/v1/facilities/nearby",
        params={"lat": 30.73, "lon": 76.77, "radius_km": 500},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "radius_km,expected_radius_m",
    [
        (0.2, 200),
        (0.3, 300),
        (0.5, 500),
        (1.0, 1000),
    ],
)
async def test_facilities_fractional_radius_km_conversion(
    client, mock_router, radius_km, expected_radius_m
):
    """
    The Nearby Places frontend now works in metres (200 m, 300 m, 500 m, 1 km
    presets) and only converts to the API's `radius_km` parameter at the
    request boundary. This guards both directions of that conversion:
    fractional radius_km must be accepted and echoed back unchanged, and the
    Overpass query the backend builds from it must use the matching
    whole-metre `around:` radius - not a truncated or rounded-down value.
    """
    route = mock_router.post("https://overpass.test/api/interpreter").mock(
        return_value=httpx.Response(200, json={"elements": []})
    )
    resp = await client.get(
        "/api/v1/facilities/nearby",
        params={"lat": 30.73, "lon": 76.77, "radius_km": radius_km},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["radius_km"] == radius_km
    assert data["data_status"]["mode"] == "live"

    # The service posts the Overpass QL as a urlencoded `data` form field, not raw text.
    sent_body = route.calls.last.request.content.decode("utf-8")
    sent_query = parse_qs(sent_body)["data"][0]
    assert f"around:{expected_radius_m}," in sent_query


@pytest.mark.asyncio
async def test_facilities_radius_below_minimum(client, mock_router):
    """200m (0.2km) is the smallest supported preset and must be accepted;
    anything below it must be rejected with the same 422 contract as an
    over-large radius."""
    resp = await client.get(
        "/api/v1/facilities/nearby",
        params={"lat": 30.73, "lon": 76.77, "radius_km": 0.1},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize("radius_km", [0.2, 1.0, 20.0, 50.0, 70.0])
async def test_facilities_radius_boundary_values_accepted(client, mock_router, radius_km):
    """The full supported range (200m through the new 70km max) must be
    accepted — this is the exact boundary set the hybrid map-to-globe spec
    calls out for testing."""
    mock_router.post("https://overpass.test/api/interpreter").mock(
        return_value=httpx.Response(200, json={"elements": []})
    )
    resp = await client.get(
        "/api/v1/facilities/nearby",
        params={"lat": 30.73, "lon": 76.77, "radius_km": radius_km},
    )
    assert resp.status_code == 200
    assert resp.json()["radius_km"] == radius_km


@pytest.mark.asyncio
async def test_facilities_radius_above_new_max_rejected(client, mock_router):
    """71km (just over the new 70km max) must still be rejected — the max
    moved from 50 to 70, not removed."""
    resp = await client.get(
        "/api/v1/facilities/nearby",
        params={"lat": 30.73, "lon": 76.77, "radius_km": 71},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_facilities_large_radius_uses_larger_overpass_timeout_and_limit(
    client, mock_router
):
    """A >20km search (FACILITY_LARGE_RADIUS_THRESHOLD_KM) must use the
    larger, explicit FACILITY_LARGE_RADIUS_TIMEOUT_SECONDS /
    FACILITY_LARGE_RADIUS_RESULT_LIMIT, not the small-radius defaults -
    never a blind/unevaluated 30s or 500-item constant."""
    route = mock_router.post("https://overpass.test/api/interpreter").mock(
        return_value=httpx.Response(200, json={"elements": []})
    )
    resp = await client.get(
        "/api/v1/facilities/nearby",
        params={"lat": 30.73, "lon": 76.77, "radius_km": 50, "category": "hospital"},
    )
    assert resp.status_code == 200
    sent_body = route.calls.last.request.content.decode("utf-8")
    sent_query = parse_qs(sent_body)["data"][0]
    assert "[timeout:25]" in sent_query  # FACILITY_LARGE_RADIUS_TIMEOUT_SECONDS default
    assert "out center 400;" in sent_query  # FACILITY_LARGE_RADIUS_RESULT_LIMIT default (> 1*50+50)


@pytest.mark.asyncio
async def test_facilities_small_radius_keeps_existing_timeout_and_limit(
    client, mock_router
):
    """A search at/under the large-radius threshold must keep the original,
    unevaluated-by-this-feature behaviour exactly as before."""
    route = mock_router.post("https://overpass.test/api/interpreter").mock(
        return_value=httpx.Response(200, json={"elements": []})
    )
    resp = await client.get(
        "/api/v1/facilities/nearby",
        params={"lat": 30.73, "lon": 76.77, "radius_km": 5, "category": "hospital"},
    )
    assert resp.status_code == 200
    sent_body = route.calls.last.request.content.decode("utf-8")
    sent_query = parse_qs(sent_body)["data"][0]
    assert "[timeout:10]" in sent_query  # REQUEST_TIMEOUT_SECONDS default, unchanged
    assert "out center 100;" in sent_query  # original n*50+50 formula (1 category)


@pytest.mark.asyncio
async def test_facilities_result_truncated_when_overpass_hits_the_cap(client, mock_router):
    """When Overpass returns as many elements as the requested out-limit,
    the response must honestly flag result_truncated rather than implying
    the list is exhaustive (spec section 7)."""
    # radius_km=50 (large-radius path) with a single category -> out_limit
    # is FACILITY_LARGE_RADIUS_RESULT_LIMIT (400), since max(1*50+50, 400) = 400.
    elements = [
        {
            "type": "node",
            "id": i,
            "lat": 30.73 + i * 0.0001,
            "lon": 76.77,
            "tags": {"amenity": "hospital", "name": f"Hospital {i}"},
        }
        for i in range(400)
    ]
    mock_router.post("https://overpass.test/api/interpreter").mock(
        return_value=httpx.Response(200, json={"elements": elements})
    )
    resp = await client.get(
        "/api/v1/facilities/nearby",
        params={"lat": 30.73, "lon": 76.77, "radius_km": 50, "category": "hospital"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["result_truncated"] is True
    assert data["result_limit"] == 400
    assert len(data["facilities"]) == 400


@pytest.mark.asyncio
async def test_facilities_result_not_truncated_under_the_cap(client, mock_router):
    """A normal response well under the out-limit must not be flagged as
    truncated, and result_limit must stay null."""
    mock_router.post("https://overpass.test/api/interpreter").mock(
        return_value=httpx.Response(200, json=OVERPASS_RESULTS)
    )
    resp = await client.get(
        "/api/v1/facilities/nearby",
        params={"lat": 30.73, "lon": 76.77, "radius_km": 5},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["result_truncated"] is False
    assert data["result_limit"] is None


@pytest.mark.asyncio
async def test_facilities_provider_unavailable(client, mock_router):
    mock_router.post("https://overpass.test/api/interpreter").mock(
        side_effect=httpx.TimeoutException("timeout")
    )
    resp = await client.get(
        "/api/v1/facilities/nearby", params={"lat": 30.73, "lon": 76.77}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["facilities"] == []
    assert data["data_status"]["mode"] == "degraded"
    assert data["data_status"]["sources"][0]["status"] == "unavailable"
