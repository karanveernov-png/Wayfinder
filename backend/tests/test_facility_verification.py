from __future__ import annotations

import httpx
import pytest

from app.services.demo import get_demo_facilities

OVERPASS_RESULTS = {
    "elements": [
        {
            "type": "node",
            "id": 1,
            "lat": 30.74,
            "lon": 76.78,
            "tags": {"amenity": "hospital", "name": "City Hospital"},
        },
    ]
}


@pytest.mark.asyncio
async def test_live_facility_results_are_marked_verified(client, mock_router):
    mock_router.post("https://overpass.test/api/interpreter").mock(
        return_value=httpx.Response(200, json=OVERPASS_RESULTS)
    )
    resp = await client.get(
        "/api/v1/facilities/nearby", params={"lat": 30.73, "lon": 76.77, "radius_km": 5}
    )
    data = resp.json()
    f = data["facilities"][0]
    assert f["verification_status"] == "verified"
    assert f["coordinate_source"] == "openstreetmap-overpass"
    assert f["last_verified_at"] is not None


def test_demo_facilities_are_marked_unverified_not_verified():
    """Core data-integrity fix: demo facility coordinates are manual
    address-derived estimates and must never claim to be 'verified'."""
    facilities = get_demo_facilities()
    assert len(facilities) == 18
    for f in facilities:
        assert f.verification_status == "unverified_coordinates"
        assert f.last_verified_at is None
        assert f.coordinate_source is not None
        assert "approximation" in f.coordinate_source.lower()
