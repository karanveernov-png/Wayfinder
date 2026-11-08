"""
Tests for GET /api/v1/locations/suggest (app/api/routes/locations.py,
app/services/routing.py RoutingService.suggest_locations).

Mirrors the mocking conventions already used in tests/test_journeys.py:
respx intercepts the outbound Nominatim call, so these never touch the
real network.
"""

from __future__ import annotations

import re
import urllib.parse

import httpx
import pytest

CHANDIGARH_RESULT = {
    "place_id": 12345,
    "osm_id": 167644,
    "lat": "30.7333148",
    "lon": "76.7794179",
    "display_name": "Chandigarh, India",
    "address": {"state": "Chandigarh", "country": "India", "country_code": "in"},
    "addresstype": "state",
    "type": "administrative",
}

EXAMPLE_CITY_PUNJAB = {
    "place_id": 1001,
    "osm_id": 2001,
    "lat": "30.9000",
    "lon": "75.8500",
    "display_name": "Example City, Punjab, India",
    "address": {"city": "Example City", "state": "Punjab", "country": "India"},
    "addresstype": "city",
    "type": "city",
}

EXAMPLE_CITY_HARYANA = {
    "place_id": 1002,
    "osm_id": 2002,
    "lat": "29.1500",
    "lon": "76.6200",
    "display_name": "Example City, Haryana, India",
    "address": {"city": "Example City", "state": "Haryana", "country": "India"},
    "addresstype": "city",
    "type": "city",
}


def _query_url_regex(query_value: str) -> str:
    """A regex matching the Nominatim /search URL for an exact `q=`
    value, anchored so e.g. q=Chag never also matches q=Chagarh.

    httpx URL-encodes query params before sending the request, and a
    value containing a space can come out as either `+` or `%20`
    depending on the encoder used - this matches either, rather than
    hard-coding one encoding and risking a false "provider wasn't
    called" test failure.
    """
    plus_form = urllib.parse.quote_plus(query_value)
    percent_form = urllib.parse.quote(query_value, safe="")
    alternatives = sorted({plus_form, percent_form}, key=len, reverse=True)
    value_pattern = "|".join(re.escape(alt) for alt in alternatives)
    return rf"^https://nominatim\.test/search\?q=(?:{value_pattern})&.*$"


def _mock_search(mock_router, query_value: str, payload):
    """Mock the raw Nominatim /search call for an exact `q=<query_value>`
    value."""
    mock_router.get(url__regex=_query_url_regex(query_value)).mock(
        return_value=httpx.Response(200, json=payload)
    )


@pytest.mark.asyncio
async def test_exact_match_returns_one_high_confidence_suggestion(client, mock_router):
    _mock_search(mock_router, "Chandigarh", [CHANDIGARH_RESULT])

    resp = await client.get("/api/v1/locations/suggest", params={"q": "Chandigarh"})

    assert resp.status_code == 200
    data = resp.json()
    assert data["data_status"]["mode"] == "live"
    assert data["used_fallback"] is False
    assert len(data["suggestions"]) == 1
    suggestion = data["suggestions"][0]
    assert suggestion["display_name"] == "Chandigarh, India"
    assert suggestion["country"] == "India"
    assert suggestion["coordinates"]["lat"] == pytest.approx(30.7333148)
    assert suggestion["match_confidence"] == pytest.approx(1.0)
    assert suggestion["is_fallback_match"] is False


@pytest.mark.asyncio
async def test_partial_name_returns_multiple_suggestions(client, mock_router):
    _mock_search(mock_router, "Example", [EXAMPLE_CITY_PUNJAB, EXAMPLE_CITY_HARYANA])

    resp = await client.get("/api/v1/locations/suggest", params={"q": "Example"})

    assert resp.status_code == 200
    data = resp.json()
    assert len(data["suggestions"]) == 2


@pytest.mark.asyncio
async def test_multiple_places_same_name_are_distinguished_by_region(
    client, mock_router
):
    _mock_search(
        mock_router, "Example City", [EXAMPLE_CITY_PUNJAB, EXAMPLE_CITY_HARYANA]
    )

    resp = await client.get("/api/v1/locations/suggest", params={"q": "Example City"})

    assert resp.status_code == 200
    data = resp.json()
    assert len(data["suggestions"]) == 2
    regions = {s["region"] for s in data["suggestions"]}
    assert regions == {"Punjab", "Haryana"}
    # Not collapsed into one entry despite sharing a display name prefix.
    coords = {(s["coordinates"]["lat"], s["coordinates"]["lon"]) for s in data["suggestions"]}
    assert len(coords) == 2


@pytest.mark.asyncio
async def test_misspelled_name_uses_fallback_and_flags_it(client, mock_router):
    # Raw query and the two longer trimmed variants find nothing; the
    # shortest trimmed variant ("Chag") is the one that turns up a match.
    _mock_search(mock_router, "Chagarh", [])
    _mock_search(mock_router, "Chagar", [])
    _mock_search(mock_router, "Chaga", [])
    _mock_search(mock_router, "Chag", [CHANDIGARH_RESULT])

    resp = await client.get("/api/v1/locations/suggest", params={"q": "Chagarh"})

    assert resp.status_code == 200
    data = resp.json()
    assert data["data_status"]["mode"] == "live"
    assert data["used_fallback"] is True
    assert len(data["suggestions"]) == 1
    suggestion = data["suggestions"][0]
    assert suggestion["display_name"] == "Chandigarh, India"
    assert suggestion["is_fallback_match"] is True
    # A fuzzy match is only ever a suggestion, never asserted as certain.
    assert 0.0 < suggestion["match_confidence"] < 1.0


@pytest.mark.asyncio
async def test_empty_query_is_rejected_with_422(client, mock_router):
    resp = await client.get("/api/v1/locations/suggest", params={"q": ""})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_single_character_query_returns_empty_without_calling_provider(
    client, mock_router
):
    # No mock registered for this query at all - if the service called the
    # provider for a 1-character query, respx (assert_all_called=False in
    # the fixture, but an unmocked route still raises) would error out.
    resp = await client.get("/api/v1/locations/suggest", params={"q": "a"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["suggestions"] == []
    assert data["used_fallback"] is False


@pytest.mark.asyncio
async def test_no_matching_results_anywhere_is_a_successful_empty_response(
    client, mock_router
):
    _mock_search(mock_router, "Zzzzzqx", [])
    _mock_search(mock_router, "Zzzzzq", [])
    _mock_search(mock_router, "Zzzzz", [])
    _mock_search(mock_router, "Zzzz", [])

    resp = await client.get("/api/v1/locations/suggest", params={"q": "Zzzzzqx"})

    assert resp.status_code == 200
    data = resp.json()
    assert data["suggestions"] == []
    assert data["used_fallback"] is True
    # A confirmed zero-match result is still a successful provider round
    # trip, not a degraded/failed one.
    assert data["data_status"]["mode"] == "live"


@pytest.mark.asyncio
async def test_geocoding_provider_server_error_reports_degraded(client, mock_router):
    mock_router.get(url__regex=_query_url_regex("Chandigarh")).mock(
        return_value=httpx.Response(503)
    )

    resp = await client.get("/api/v1/locations/suggest", params={"q": "Chandigarh"})

    assert resp.status_code == 200
    data = resp.json()
    assert data["suggestions"] == []
    assert data["data_status"]["mode"] == "degraded"
    # A 5xx from the provider is a ServiceUnavailableError (-> "unavailable"),
    # same as every other endpoint (see test_weather/test_alerts): "error" is
    # reserved for a 200 response with an unusable/malformed body
    # (ServiceResponseError).
    assert data["data_status"]["sources"][0]["status"] == "unavailable"


@pytest.mark.asyncio
async def test_geocoding_provider_rate_limited_reports_unavailable(client, mock_router):
    mock_router.get(url__regex=_query_url_regex("Chandigarh")).mock(
        return_value=httpx.Response(429)
    )

    resp = await client.get("/api/v1/locations/suggest", params={"q": "Chandigarh"})

    assert resp.status_code == 200
    data = resp.json()
    assert data["suggestions"] == []
    assert data["data_status"]["mode"] == "degraded"
    assert data["data_status"]["sources"][0]["status"] == "unavailable"


@pytest.mark.asyncio
async def test_invalid_coordinates_are_dropped_not_fatal(client, mock_router):
    bad_result = dict(CHANDIGARH_RESULT)
    bad_result["place_id"] = 99999
    bad_result["lat"] = "999.0"  # out of valid latitude range
    good_result = dict(EXAMPLE_CITY_PUNJAB)

    _mock_search(mock_router, "City", [bad_result, good_result])

    resp = await client.get("/api/v1/locations/suggest", params={"q": "City"})

    assert resp.status_code == 200
    data = resp.json()
    # The malformed entry is silently skipped; the valid one still comes
    # through and the request does not fail.
    assert len(data["suggestions"]) == 1
    assert data["suggestions"][0]["display_name"] == "Example City, Punjab, India"


@pytest.mark.asyncio
async def test_duplicate_suggestions_are_deduplicated(client, mock_router):
    duplicate = dict(CHANDIGARH_RESULT)
    duplicate["place_id"] = 54321  # different provider id, same place

    _mock_search(mock_router, "Chandigarh", [CHANDIGARH_RESULT, duplicate])

    resp = await client.get("/api/v1/locations/suggest", params={"q": "Chandigarh"})

    assert resp.status_code == 200
    data = resp.json()
    assert len(data["suggestions"]) == 1


@pytest.mark.asyncio
async def test_limit_is_respected(client, mock_router):
    results = []
    for i in range(5):
        item = dict(EXAMPLE_CITY_PUNJAB)
        item["place_id"] = 3000 + i
        item["lat"] = str(30.0 + i * 0.01)
        results.append(item)
    _mock_search(mock_router, "Example", results)

    resp = await client.get(
        "/api/v1/locations/suggest", params={"q": "Example", "limit": 2}
    )

    assert resp.status_code == 200
    data = resp.json()
    assert len(data["suggestions"]) == 2


@pytest.mark.asyncio
async def test_geocoding_not_configured_reports_not_configured(client, mock_router, settings):
    from app.core.config import get_settings
    from app.main import app

    unconfigured = settings.model_copy(update={"GEOCODING_PROVIDER_URL": None})
    app.dependency_overrides[get_settings] = lambda: unconfigured
    get_settings.cache_clear()
    try:
        resp = await client.get("/api/v1/locations/suggest", params={"q": "Chandigarh"})
    finally:
        app.dependency_overrides[get_settings] = lambda: settings
        get_settings.cache_clear()

    assert resp.status_code == 200
    data = resp.json()
    assert data["suggestions"] == []
    assert data["data_status"]["sources"][0]["status"] == "not_configured"
